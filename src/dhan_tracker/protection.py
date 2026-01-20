"""Portfolio protection strategies using super orders."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .client import DhanClient
from .nse_client import NSEClient, NSEError
from .models import Holding, SuperOrder, ProtectiveOrder

logger = logging.getLogger(__name__)


@dataclass
class ProtectionConfig:
    """Configuration for portfolio protection."""

    # Stop loss percentage below current LTP
    stop_loss_percent: float = 5.0

    # Target percentage above current LTP (for profit booking)
    target_percent: float = 20.0

    # Trailing stop loss jump (0 to disable)
    trailing_jump: float = 0.0

    # Minimum quantity to protect
    min_quantity: int = 1

    # Only protect holdings above this value
    min_value: float = 0.0

    # Exchange segment (NSE_EQ or BSE_EQ)
    exchange_segment: str = "NSE_EQ"


@dataclass
class ProtectionResult:
    """Result of a protection order attempt."""

    holding: Holding
    success: bool
    ltp: float = 0.0
    order_id: Optional[str] = None
    message: str = ""
    stop_loss_price: float = 0.0
    target_price: float = 0.0


class PortfolioProtector:
    """
    Manages portfolio protection by placing DDPI super orders with stop losses.

    Strategy:
    - At market open, fetch current LTP for all holdings
    - Place SELL super orders with stop loss trigger X% below LTP
    - If price falls and hits trigger → sells at market, protecting from further fall
    - If price rises → order stays pending, you keep the profits
    - Next day: cancel old orders and place new ones with updated LTP
    """

    def __init__(self, client: DhanClient, config: ProtectionConfig | None = None):
        """
        Initialize portfolio protector.

        Args:
            client: Dhan API client
            config: Protection configuration
        """
        self.client = client
        self.config = config or ProtectionConfig(
            stop_loss_percent=client.config.default_stop_loss_percent
        )
        self._ltp_cache: dict[str, float] = {}
        self._nse_client = NSEClient()

    def calculate_stop_loss_price(self, ltp: float) -> float:
        """
        Calculate stop loss price based on current LTP.

        Args:
            ltp: Last Traded Price (current market price)

        Returns:
            Stop loss trigger price
        """
        return round(ltp * (1 - self.config.stop_loss_percent / 100), 2)

    def calculate_target_price(self, ltp: float) -> float:
        """
        Calculate target price based on current LTP.

        Args:
            ltp: Last Traded Price (current market price)

        Returns:
            Target price for profit booking
        """
        return round(ltp * (1 + self.config.target_percent / 100), 2)

    def fetch_ltp_for_holdings(self, holdings: list[Holding]) -> dict[str, float]:
        """
        Fetch current LTP for all holdings from NSE.

        Args:
            holdings: List of holdings

        Returns:
            Dictionary mapping security_id to LTP
        """
        self._ltp_cache = {}

        for holding in holdings:
            try:
                ltp = self._nse_client.get_ltp(holding.trading_symbol)
                self._ltp_cache[holding.security_id] = ltp
                logger.info(f"LTP for {holding.trading_symbol}: ₹{ltp:.2f}")
            except NSEError as e:
                logger.warning(
                    f"Failed to get LTP for {holding.trading_symbol}: {e}")
                self._ltp_cache[holding.security_id] = 0.0

        return self._ltp_cache

    def get_existing_protection(self, holdings: list[Holding]) -> dict[str, SuperOrder]:
        """
        Get existing super orders for holdings.

        Args:
            holdings: List of holdings to check

        Returns:
            Dictionary mapping security_id to existing super order
        """
        security_ids = {h.security_id for h in holdings}
        super_orders = self.client.get_super_orders()

        existing = {}
        for order in super_orders:
            if (
                order.security_id in security_ids
                and order.transaction_type == "SELL"
                and order.order_status in ["PENDING", "TRANSIT", "PART_TRADED"]
            ):
                existing[order.security_id] = order

        return existing

    def cancel_existing_orders(self, holdings: list[Holding]) -> int:
        """
        Cancel all existing protective orders for holdings.

        Args:
            holdings: List of holdings

        Returns:
            Number of orders cancelled
        """
        existing = self.get_existing_protection(holdings)
        cancelled = 0

        for security_id, order in existing.items():
            try:
                self.client.cancel_super_order(order.order_id)
                logger.info(
                    f"Cancelled order {order.order_id} for {order.trading_symbol}")
                cancelled += 1
            except Exception as e:
                logger.warning(f"Failed to cancel order {order.order_id}: {e}")

        return cancelled

    def get_pending_amo_orders(self, holdings: list[Holding]) -> dict[str, dict]:
        """
        Get existing pending AMO SL orders for holdings.

        Args:
            holdings: List of holdings to check

        Returns:
            Dictionary of security_id -> order for pending AMO orders
        """
        security_ids = {h.security_id for h in holdings}
        orders = self.client.get_orders()

        pending_amo = {}
        for order in orders:
            security_id = order.get("securityId", "")
            order_status = order.get("orderStatus", "")
            order_type = order.get("orderType", "")
            transaction_type = order.get("transactionType", "")

            # Check if it's a pending SL SELL order (our protection order)
            if (
                security_id in security_ids
                and transaction_type == "SELL"
                and order_type in ["STOP_LOSS", "STOP_LOSS_MARKET"]
                and order_status in ["PENDING", "TRANSIT"]
            ):
                pending_amo[security_id] = order

        return pending_amo

    def modify_amo_order(
        self,
        order: dict,
        new_trigger_price: float,
    ) -> dict:
        """
        Modify an existing AMO SL order's trigger price.

        More efficient than cancel+replace - single API call, keeps order ID.

        Args:
            order: Existing order dict from get_orders()
            new_trigger_price: New stop loss trigger price

        Returns:
            Modified order response
        """
        order_id = order.get("orderId", "")
        order_type = order.get("orderType", "STOP_LOSS_MARKET")

        return self.client.modify_order(
            order_id=order_id,
            order_type=order_type,
            trigger_price=new_trigger_price,
        )

    def cancel_pending_amo_orders(self, holdings: list[Holding]) -> int:
        """
        Cancel all pending AMO SL orders for holdings.

        Call this before placing new AMO orders to update trigger prices.

        Args:
            holdings: List of holdings

        Returns:
            Number of orders cancelled
        """
        pending = self.get_pending_amo_orders(holdings)
        cancelled = 0

        for security_id, order in pending.items():
            try:
                order_id = order.get("orderId", "")
                symbol = order.get("tradingSymbol", security_id)
                self.client.cancel_order(order_id)
                logger.info(f"Cancelled AMO order {order_id} for {symbol}")
                cancelled += 1
            except Exception as e:
                logger.warning(f"Failed to cancel AMO order: {e}")

        return cancelled

    def create_protective_order(self, holding: Holding, ltp: float) -> ProtectiveOrder:
        """
        Create a protective order configuration for a holding based on LTP.

        Args:
            holding: Holding to protect
            ltp: Current Last Traded Price

        Returns:
            ProtectiveOrder configuration
        """
        stop_loss_price = self.calculate_stop_loss_price(ltp)
        target_price = self.calculate_target_price(ltp)

        return ProtectiveOrder(
            security_id=holding.security_id,
            trading_symbol=holding.trading_symbol,
            quantity=holding.available_qty,
            entry_price=ltp,  # Use current LTP as entry
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            trailing_jump=self.config.trailing_jump,
            exchange_segment=self.config.exchange_segment,
            product_type="CNC",
        )

    def protect_holding(
        self,
        holding: Holding,
        ltp: float,
        existing_orders: dict[str, SuperOrder],
        force: bool = False,
    ) -> ProtectionResult:
        """
        Place a protective super order for a single holding.

        Args:
            holding: Holding to protect
            ltp: Current LTP for the holding
            existing_orders: Dictionary of existing super orders
            force: If True, cancel existing order and place new one

        Returns:
            ProtectionResult with order details
        """
        # Check if holding meets minimum criteria
        if holding.available_qty < self.config.min_quantity:
            return ProtectionResult(
                holding=holding,
                success=False,
                ltp=ltp,
                message=f"Available quantity ({holding.available_qty}) below minimum ({self.config.min_quantity})"
            )

        holding_value = holding.available_qty * ltp
        if holding_value < self.config.min_value:
            return ProtectionResult(
                holding=holding,
                success=False,
                ltp=ltp,
                message=f"Holding value (₹{holding_value:.2f}) below minimum (₹{self.config.min_value})"
            )

        # Check if LTP is valid
        if ltp <= 0:
            return ProtectionResult(
                holding=holding,
                success=False,
                ltp=ltp,
                message="Could not fetch LTP for this security"
            )

        # Check for existing protection
        existing_order = existing_orders.get(holding.security_id)
        new_stop_loss = self.calculate_stop_loss_price(ltp)
        new_target = self.calculate_target_price(ltp)

        if existing_order and not force:
            sl_price = existing_order.stop_loss_leg.price if existing_order.stop_loss_leg else 0
            return ProtectionResult(
                holding=holding,
                success=True,
                ltp=ltp,
                order_id=existing_order.order_id,
                message=f"Already protected (order {existing_order.order_id})",
                stop_loss_price=sl_price,
            )

        # If existing order and force=True, MODIFY instead of cancel+replace
        if existing_order and force:
            try:
                # Modify the stop loss leg with new price based on current LTP
                response = self.client.modify_super_order(
                    order_id=existing_order.order_id,
                    leg_name="STOP_LOSS_LEG",
                    stop_loss_price=new_stop_loss,
                    trailing_jump=self.config.trailing_jump,
                )
                order_status = response.get("orderStatus", "")

                # Also modify target leg if needed
                if new_target > 0:
                    try:
                        self.client.modify_super_order(
                            order_id=existing_order.order_id,
                            leg_name="TARGET_LEG",
                            target_price=new_target,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to modify target leg: {e}")

                logger.info(
                    f"Modified order {existing_order.order_id} for {holding.trading_symbol}: "
                    f"SL ₹{existing_order.stop_loss_leg.price if existing_order.stop_loss_leg else 0:.2f} → ₹{new_stop_loss:.2f}"
                )

                return ProtectionResult(
                    holding=holding,
                    success=order_status in ["PENDING", "TRANSIT"],
                    ltp=ltp,
                    order_id=existing_order.order_id,
                    message=f"Order modified: SL updated to ₹{new_stop_loss:.2f}",
                    stop_loss_price=new_stop_loss,
                    target_price=new_target,
                )

            except Exception as e:
                logger.warning(f"Failed to modify order, will place new: {e}")
                # Fall through to place new order

        # Create and place protective order (only if no existing order or modify failed)

        # Create and place protective order
        protective_order = self.create_protective_order(holding, ltp)

        try:
            response = self.client.place_protective_order(protective_order)
            order_id = response.get("orderId", "")
            order_status = response.get("orderStatus", "")

            return ProtectionResult(
                holding=holding,
                success=order_status in ["PENDING", "TRANSIT"],
                ltp=ltp,
                order_id=order_id,
                message=f"Order placed: {order_status}",
                stop_loss_price=protective_order.stop_loss_price,
                target_price=protective_order.target_price,
            )

        except Exception as e:
            logger.error(
                f"Failed to place protective order for {holding.trading_symbol}: {e}")
            return ProtectionResult(
                holding=holding,
                success=False,
                ltp=ltp,
                message=str(e),
            )

    def protect_portfolio(
        self,
        holdings: list[Holding] | None = None,
        force: bool = False,
    ) -> list[ProtectionResult]:
        """
        Place protective orders for all eligible holdings.

        Args:
            holdings: Holdings to protect (fetches if None)
            force: If True, cancel existing orders and place new ones

        Returns:
            List of ProtectionResult for each holding
        """
        if holdings is None:
            holdings = self.client.get_holdings()

        # Filter to holdings with available quantity
        holdings = [h for h in holdings if h.available_qty > 0]

        if not holdings:
            logger.info("No holdings with available quantity to protect")
            return []

        # Fetch LTP for all holdings
        logger.info(f"Fetching LTP for {len(holdings)} holdings...")
        ltp_map = self.fetch_ltp_for_holdings(holdings)

        # Get existing orders
        existing_orders = self.get_existing_protection(holdings)

        results = []

        for holding in holdings:
            ltp = ltp_map.get(holding.security_id, 0.0)

            result = self.protect_holding(
                holding, ltp, existing_orders, force=force)
            results.append(result)

            if result.success:
                logger.info(
                    f"✓ Protected {holding.trading_symbol}: "
                    f"LTP=₹{ltp:.2f}, SL=₹{result.stop_loss_price:.2f} ({self.config.stop_loss_percent}% below)"
                )
            else:
                logger.warning(
                    f"✗ Failed to protect {holding.trading_symbol}: {result.message}")

        return results

    def get_protection_summary(self) -> dict:
        """
        Get summary of current portfolio protection status.

        Returns:
            Dictionary with protection statistics
        """
        holdings = self.client.get_holdings()
        holdings = [h for h in holdings if h.available_qty > 0]

        # Fetch LTP for current values
        ltp_map = self.fetch_ltp_for_holdings(holdings)

        super_orders = self.client.get_super_orders()

        # Find holdings with protection
        protected_securities = {
            o.security_id: o
            for o in super_orders
            if o.transaction_type == "SELL"
            and o.order_status in ["PENDING", "TRANSIT", "PART_TRADED"]
        }

        protected_holdings = []
        unprotected_holdings = []

        for h in holdings:
            if h.security_id in protected_securities:
                protected_holdings.append(h)
            else:
                unprotected_holdings.append(h)

        # Calculate values using LTP (current market value)
        def get_value(h: Holding) -> float:
            ltp = ltp_map.get(h.security_id, h.avg_cost_price)
            return h.available_qty * ltp

        total_value = sum(get_value(h) for h in holdings)
        protected_value = sum(get_value(h) for h in protected_holdings)
        unprotected_value = sum(get_value(h) for h in unprotected_holdings)

        return {
            "total_holdings": len(holdings),
            "protected_count": len(protected_holdings),
            "unprotected_count": len(unprotected_holdings),
            "total_value": total_value,
            "protected_value": protected_value,
            "unprotected_value": unprotected_value,
            "protection_percent": (protected_value / total_value * 100) if total_value > 0 else 0,
            "protected_holdings": protected_holdings,
            "unprotected_holdings": unprotected_holdings,
            "active_super_orders": super_orders,
            "ltp_map": ltp_map,
            "protected_securities": protected_securities,
        }

    def place_amo_sl_order(
        self,
        holding: Holding,
        ltp: float,
        amo_time: str = "OPEN",
    ) -> ProtectionResult:
        """
        Place an AMO (After Market Order) Stop Loss order for a holding.

        This places a regular SL-M order as AMO which will be active from market open.
        Use this when market is closed to ensure protection from the first trade.

        Args:
            holding: Holding to protect
            ltp: Current/last known LTP for stop loss calculation
            amo_time: When to inject the order: PRE_OPEN, OPEN, OPEN_30, OPEN_60

        Returns:
            ProtectionResult with order details
        """
        if ltp <= 0:
            return ProtectionResult(
                holding=holding,
                success=False,
                ltp=ltp,
                message="Invalid LTP for stop loss calculation",
            )

        stop_loss_price = self.calculate_stop_loss_price(ltp)
        correlation_id = f"amo_protect_{holding.security_id}_{datetime.now().strftime('%Y%m%d')}"

        try:
            response = self.client.place_sl_order(
                security_id=holding.security_id,
                quantity=holding.available_qty,
                trigger_price=stop_loss_price,
                price=0.0,  # Market order
                transaction_type="SELL",
                exchange_segment=self.config.exchange_segment,
                product_type="CNC",
                order_type="STOP_LOSS_MARKET",
                after_market_order=True,
                amo_time=amo_time,
                correlation_id=correlation_id,
            )

            order_id = response.get("orderId", "")
            order_status = response.get("orderStatus", "")

            return ProtectionResult(
                holding=holding,
                success=order_status in ["PENDING", "TRANSIT"],
                ltp=ltp,
                order_id=order_id,
                message=f"AMO order placed ({amo_time}): {order_status}",
                stop_loss_price=stop_loss_price,
                target_price=0.0,  # No target for SL order
            )

        except Exception as e:
            logger.error(
                f"Failed to place AMO SL order for {holding.trading_symbol}: {e}")
            return ProtectionResult(
                holding=holding,
                success=False,
                ltp=ltp,
                message=str(e),
            )

    def protect_portfolio_amo(
        self,
        holdings: list[Holding] | None = None,
        amo_time: str = "OPEN",
        force: bool = True,
    ) -> list[ProtectionResult]:
        """
        Place or update AMO Stop Loss orders for all eligible holdings.

        Use this when market is closed to place protection orders that will
        be active from market open. This ensures protection from gap downs.

        IMPORTANT: By default (force=True), this will:
        - MODIFY existing pending AMO orders with updated trigger prices
        - PLACE new orders only for holdings without existing protection

        This is more efficient than cancel+replace (1 API call vs 2).

        Args:
            holdings: Holdings to protect (fetches if None)
            amo_time: When to inject: PRE_OPEN, OPEN, OPEN_30, OPEN_60
                      - PRE_OPEN: At 9:00 AM pre-open session
                      - OPEN: At 9:15 AM market open
                      - OPEN_30: 30 mins after open (9:45 AM)
                      - OPEN_60: 60 mins after open (10:15 AM)
            force: If True (default), update existing orders with new trigger prices

        Returns:
            List of ProtectionResult for each holding
        """
        if holdings is None:
            holdings = self.client.get_holdings()

        # Filter to holdings with available quantity
        holdings = [h for h in holdings if h.available_qty > 0]

        if not holdings:
            logger.info("No holdings with available quantity to protect")
            return []

        # Fetch LTP for all holdings (last close price if market closed)
        logger.info(f"Fetching LTP for {len(holdings)} holdings...")
        ltp_map = self.fetch_ltp_for_holdings(holdings)

        # Get existing pending AMO orders
        existing_orders = self.get_pending_amo_orders(holdings)
        logger.info(
            f"Found {len(existing_orders)} existing pending AMO orders")

        results = []

        for holding in holdings:
            ltp = ltp_map.get(holding.security_id, 0.0)
            new_stop_loss = self.calculate_stop_loss_price(ltp)

            # Check if there's an existing order for this holding
            existing_order = existing_orders.get(holding.security_id)

            if existing_order and force:
                # MODIFY existing order instead of cancel+replace
                old_trigger = existing_order.get("triggerPrice", 0)
                order_id = existing_order.get("orderId", "")

                # Only modify if trigger price needs to change
                if abs(old_trigger - new_stop_loss) > 0.01:
                    try:
                        response = self.modify_amo_order(
                            existing_order, new_stop_loss)
                        order_status = response.get("orderStatus", "")

                        logger.info(
                            f"✓ Modified {holding.trading_symbol}: "
                            f"SL ₹{old_trigger:.2f} → ₹{new_stop_loss:.2f}"
                        )

                        results.append(ProtectionResult(
                            holding=holding,
                            success=order_status in ["PENDING", "TRANSIT"],
                            ltp=ltp,
                            order_id=order_id,
                            message=f"Order modified: SL ₹{old_trigger:.2f} → ₹{new_stop_loss:.2f}",
                            stop_loss_price=new_stop_loss,
                        ))
                        continue

                    except Exception as e:
                        logger.warning(
                            f"Failed to modify order, will place new: {e}")
                        # Cancel the old order and place new
                        try:
                            self.client.cancel_order(order_id)
                        except Exception:
                            pass
                else:
                    # No change needed
                    results.append(ProtectionResult(
                        holding=holding,
                        success=True,
                        ltp=ltp,
                        order_id=order_id,
                        message=f"Already protected at SL ₹{old_trigger:.2f} (no change needed)",
                        stop_loss_price=old_trigger,
                    ))
                    continue

            elif existing_order and not force:
                # Keep existing order as-is
                old_trigger = existing_order.get("triggerPrice", 0)
                order_id = existing_order.get("orderId", "")
                results.append(ProtectionResult(
                    holding=holding,
                    success=True,
                    ltp=ltp,
                    order_id=order_id,
                    message=f"Already protected (order {order_id})",
                    stop_loss_price=old_trigger,
                ))
                continue

            # Place new AMO order (no existing order)
            result = self.place_amo_sl_order(holding, ltp, amo_time)
            results.append(result)

            if result.success:
                logger.info(
                    f"✓ AMO Protected {holding.trading_symbol}: "
                    f"LTP=₹{ltp:.2f}, SL=₹{result.stop_loss_price:.2f}, Time={amo_time}"
                )
            else:
                logger.warning(
                    f"✗ Failed to AMO protect {holding.trading_symbol}: {result.message}")

        return results


def run_daily_protection(
    client: DhanClient,
    config: ProtectionConfig | None = None,
    force: bool = True,  # Default to force=True for daily refresh
) -> list[ProtectionResult]:
    """
    Run daily portfolio protection routine.

    This should be scheduled to run at market open each day.
    It cancels existing orders and places new ones with updated LTP-based triggers.

    Args:
        client: Dhan API client
        config: Protection configuration
        force: If True (default), replace existing orders with new ones

    Returns:
        List of protection results
    """
    logger.info(f"Starting daily protection run at {datetime.now()}")

    protector = PortfolioProtector(client, config)

    # Cancel all existing protection orders first
    holdings = client.get_holdings()
    holdings = [h for h in holdings if h.available_qty > 0]

    if force:
        cancelled = protector.cancel_existing_orders(holdings)
        logger.info(f"Cancelled {cancelled} existing protection orders")

    # Place new orders with current LTP
    results = protector.protect_portfolio(
        holdings, force=False)  # Already cancelled

    # Log summary
    success_count = sum(1 for r in results if r.success)
    fail_count = sum(1 for r in results if not r.success)

    logger.info(
        f"Daily protection complete: {success_count} protected, {fail_count} failed")

    return results
