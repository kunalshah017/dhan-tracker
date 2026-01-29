"""Portfolio protection strategies using super orders."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .client import DhanClient
from .nse_client import NSEClient, NSEError
from .upstox_client import UpstoxClient, UpstoxAPIError, MarketData
from .models import Holding, SuperOrder, ProtectiveOrder

logger = logging.getLogger(__name__)


@dataclass
class ProtectionConfig:
    """Configuration for portfolio protection.

    Strategy: Progressive Tiered Protection
    ----------------------------------------
    Stop loss is calculated based on your cost price and current P&L:

    PROFIT TIERS (Progressive - locks more as profit grows):
    - P&L 0-5%:    SL at Cost           → Protect capital (breakeven)
    - P&L 5-10%:   SL at Cost + 2%      → Lock small profit
    - P&L 10-20%:  SL at Cost + 5%      → Lock decent profit
    - P&L 20-30%:  SL at Cost + 12%     → Lock good profit
    - P&L 30-50%:  SL at Cost + 20%     → Lock great profit
    - P&L 50%+:    SL at Cost + 35%     → Lock excellent profit

    LOSS TIERS:
    - P&L 0 to -10%:  SL at Cost - 10%  → Room to recover, max 10% loss
    - P&L < -10%:     SL at LTP - 5%    → Limit further damage

    Benefits:
    - Never let a winner become a loser
    - Locks increasing profits as stock rises
    - Limits max loss to 10% of invested capital
    - Gives room for normal volatility and recovery
    """

    # Max loss allowed (as % of cost price)
    max_loss_percent: float = 10.0

    # For deep loss positions, SL below current LTP
    deep_loss_sl_percent: float = 5.0

    # Progressive profit lock tiers: (min_pnl%, lock_percent)
    # Each tier: if P&L >= min_pnl%, then SL = Cost + lock_percent%
    profit_tiers: tuple = (
        (50.0, 35.0),  # P&L >= 50% → Lock 35%
        (30.0, 20.0),  # P&L >= 30% → Lock 20%
        (20.0, 12.0),  # P&L >= 20% → Lock 12%
        (10.0, 5.0),   # P&L >= 10% → Lock 5%
        (5.0, 2.0),    # P&L >= 5%  → Lock 2%
        (0.0, 0.0),    # P&L >= 0%  → Lock 0% (breakeven)
    )

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

    # DEPRECATED: Legacy settings kept for backward compatibility
    stop_loss_from_high_percent: float = 10.0
    stop_loss_percent: float = 5.0
    profit_lock_threshold: float = 10.0
    profit_lock_percent: float = 5.0


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

    Strategy: Trailing Stop from 52-Week High
    ------------------------------------------
    - Fetch 52-week high for all holdings
    - Place SELL super orders with stop loss at X% below 52-week high
    - If price falls and hits trigger → sells at market, protecting from further fall
    - If price rises to new high → update SL to trail the new high
    - This gives room for normal volatility while locking in real gains

    Benefits over LTP-based stop loss:
    - Won't trigger on normal daily fluctuations
    - Protects both profitable and losing positions uniformly
    - Locks in gains from actual peaks, not paper profits
    """

    def __init__(self, client: DhanClient, config: ProtectionConfig | None = None):
        """
        Initialize portfolio protector.

        Args:
            client: Dhan API client
            config: Protection configuration
        """
        self.client = client
        self.config = config or ProtectionConfig()
        self._ltp_cache: dict[str, float] = {}
        self._52week_high_cache: dict[str, float] = {}
        self._200dma_cache: dict[str, float | None] = {}
        self._nse_client = NSEClient()
        self._upstox_client = UpstoxClient()

    def calculate_tiered_stop_loss(
        self,
        cost_price: float,
        current_price: float,
    ) -> tuple[float, str]:
        """
        Calculate stop loss using tiered cost-based strategy.

        Strategy:
        - BIG PROFIT (>10%):   SL at Cost + 5%  → Lock in some gains
        - SMALL PROFIT (0-10%): SL at Cost       → Protect capital
        LOSS TIERS:
        - SMALL LOSS (0 to -10%):  SL at Cost - 10% → Max 10% loss allowed
        - DEEP LOSS (< -10%):      SL at LTP - 5%   → Limit further damage

        Args:
            cost_price: Average cost price (what you paid)
            current_price: Current market price (LTP)

        Returns:
            Tuple of (stop_loss_price, tier_description)
        """
        if cost_price <= 0:
            # Fallback to LTP-based
            sl = round(current_price *
                       (1 - self.config.deep_loss_sl_percent / 100), 2)
            return sl, "LTP-based (no cost data)"

        pnl_percent = ((current_price - cost_price) / cost_price) * 100

        # PROFIT: Use progressive tiers
        if pnl_percent >= 0:
            # Find the appropriate profit tier
            lock_percent = 0.0
            tier_name = "CAPITAL PROTECT"

            for min_pnl, lock_pct in self.config.profit_tiers:
                if pnl_percent >= min_pnl:
                    lock_percent = lock_pct
                    if lock_pct > 0:
                        tier_name = f"PROFIT LOCK +{lock_pct:.0f}%"
                    break

            sl = round(cost_price * (1 + lock_percent / 100), 2)
            tier = f"{tier_name} (P&L {pnl_percent:+.1f}%): SL at cost {'+' + str(lock_percent) + '%' if lock_percent > 0 else '(breakeven)'}"

        elif pnl_percent > -self.config.max_loss_percent:
            # SMALL LOSS: Allow recovery, max 10% loss
            sl = round(cost_price * (1 - self.config.max_loss_percent / 100), 2)
            tier = f"RECOVERY ROOM (P&L {pnl_percent:+.1f}%): SL at cost -{self.config.max_loss_percent}%"

        else:
            # DEEP LOSS: Limit further damage
            sl = round(current_price *
                       (1 - self.config.deep_loss_sl_percent / 100), 2)
            tier = f"DAMAGE LIMIT (P&L {pnl_percent:+.1f}%): SL at LTP -{self.config.deep_loss_sl_percent}%"

        return sl, tier

    def calculate_stop_loss_from_high(self, high_52week: float) -> float:
        """
        Calculate stop loss price based on 52-week high.
        DEPRECATED: Use calculate_tiered_stop_loss for better protection.

        Args:
            high_52week: 52-week high price

        Returns:
            Stop loss trigger price (X% below 52-week high)
        """
        return round(high_52week * (1 - self.config.stop_loss_from_high_percent / 100), 2)

    def calculate_stop_loss_price(self, ltp: float) -> float:
        """
        Calculate stop loss price based on current LTP.
        DEPRECATED: Use calculate_tiered_stop_loss for better protection.

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

    def fetch_52_week_highs(self, holdings: list[Holding]) -> dict[str, float]:
        """
        Fetch 52-week high for all holdings using Upstox API.

        Args:
            holdings: List of holdings

        Returns:
            Dictionary mapping security_id to 52-week high
        """
        logger.info(
            f"Fetching 52-week highs from Upstox for {len(holdings)} holdings...")
        self._52week_high_cache = {}

        for holding in holdings:
            try:
                high = self._upstox_client.get_52_week_high(
                    holding.isin, holding.exchange)
                self._52week_high_cache[holding.security_id] = high
                if high > 0:
                    logger.info(
                        f"52W High for {holding.trading_symbol}: ₹{high:.2f}")
            except Exception as e:
                logger.warning(
                    f"Failed to get 52W high for {holding.trading_symbol}: {e}")
                self._52week_high_cache[holding.security_id] = 0.0

        return self._52week_high_cache

    def fetch_ltp_for_holdings(self, holdings: list[Holding]) -> dict[str, float]:
        """
        Fetch current LTP for all holdings using Upstox latest close price.

        Uses Upstox historical API which works without authentication.
        Returns latest closing price as proxy for LTP (updated daily).

        Args:
            holdings: List of holdings

        Returns:
            Dictionary mapping security_id to LTP (latest close)
        """
        self._ltp_cache = {}

        for holding in holdings:
            try:
                # Use Upstox latest close as LTP proxy
                ltp = self._upstox_client.get_latest_close(
                    holding.isin, holding.exchange)
                self._ltp_cache[holding.security_id] = ltp
                logger.info(
                    f"LTP for {holding.trading_symbol}: ₹{ltp:.2f} (Upstox close)")
            except UpstoxAPIError as e:
                logger.warning(
                    f"Failed to get LTP from Upstox for {holding.trading_symbol}: {e}")
                # Fallback to NSE
                try:
                    ltp = self._nse_client.get_ltp(holding.trading_symbol)
                    self._ltp_cache[holding.security_id] = ltp
                    logger.info(
                        f"LTP for {holding.trading_symbol}: ₹{ltp:.2f} (NSE fallback)")
                except NSEError as nse_e:
                    logger.warning(f"NSE fallback also failed: {nse_e}")
                    self._ltp_cache[holding.security_id] = 0.0

        return self._ltp_cache

    def fetch_all_market_data(self, holdings: list[Holding]) -> dict[str, MarketData]:
        """
        Fetch all market data (LTP, 52W high, 200-DMA) for holdings in one batch.

        More efficient than separate calls as it caches the API responses.

        Args:
            holdings: List of holdings

        Returns:
            Dictionary mapping ISIN to MarketData
        """
        logger.info(
            f"Fetching market data from Upstox for {len(holdings)} holdings...")

        market_data = self._upstox_client.get_market_data_bulk(holdings)

        # Populate caches
        for holding in holdings:
            data = market_data.get(holding.isin)
            if data:
                self._ltp_cache[holding.security_id] = data.latest_close
                self._52week_high_cache[holding.security_id] = data.high_52_week
                self._200dma_cache[holding.security_id] = data.dma_200
                dma_str = f"₹{data.dma_200:.2f}" if data.dma_200 else "N/A"
                logger.info(
                    f"{holding.trading_symbol}: Close=₹{data.latest_close:.2f}, "
                    f"52WH=₹{data.high_52_week:.2f}, "
                    f"200DMA={dma_str}"
                )

        return market_data

    def fetch_200_dma(self, holdings: list[Holding]) -> dict[str, float | None]:
        """
        Fetch 200-day moving average for all holdings.

        Args:
            holdings: List of holdings

        Returns:
            Dictionary mapping security_id to 200-DMA (or None if insufficient data)
        """
        logger.info(
            f"Fetching 200-DMA from Upstox for {len(holdings)} holdings...")
        self._200dma_cache = {}

        for holding in holdings:
            try:
                dma = self._upstox_client.get_200_dma(
                    holding.isin, holding.exchange)
                self._200dma_cache[holding.security_id] = dma
                if dma:
                    logger.info(
                        f"200-DMA for {holding.trading_symbol}: ₹{dma:.2f}")
            except Exception as e:
                logger.warning(
                    f"Failed to get 200-DMA for {holding.trading_symbol}: {e}")
                self._200dma_cache[holding.security_id] = None

        return self._200dma_cache

    def check_200_dma_status(self, holdings: list[Holding] | None = None) -> list[dict]:
        """
        Check if holdings are above or below their 200-DMA.

        Useful for the Option C hybrid strategy to identify bearish trends.

        Args:
            holdings: List of holdings (fetches if None)

        Returns:
            List of dicts with holding info and 200-DMA status
        """
        if holdings is None:
            holdings = self.client.get_holdings()
            holdings = [h for h in holdings if h.available_qty > 0]

        if not holdings:
            return []

        # Fetch all market data at once
        market_data = self.fetch_all_market_data(holdings)

        results = []
        for holding in holdings:
            data = market_data.get(holding.isin)
            if not data:
                continue

            status = {
                "symbol": holding.trading_symbol,
                "isin": holding.isin,
                "quantity": holding.available_qty,
                "avg_cost": holding.avg_cost_price,
                "latest_close": data.latest_close,
                "high_52_week": data.high_52_week,
                "dma_200": data.dma_200,
                "above_200dma": data.latest_close > data.dma_200 if data.dma_200 else None,
                "pnl_percent": ((data.latest_close - holding.avg_cost_price) /
                                holding.avg_cost_price * 100) if holding.avg_cost_price > 0 else 0,
            }

            if data.dma_200:
                status["dma_diff_percent"] = ((data.latest_close - data.dma_200) /
                                              data.dma_200 * 100)

            results.append(status)

            # Log warning for holdings below 200-DMA
            if status.get("above_200dma") is False:
                logger.warning(
                    f"⚠ {holding.trading_symbol} is BELOW 200-DMA: "
                    f"Close=₹{data.latest_close:.2f}, 200-DMA=₹{data.dma_200:.2f}"
                )

        return results

    def get_protection_plan(self, holdings: list[Holding] | None = None) -> list[dict]:
        """
        Calculate protection plan for all holdings WITHOUT placing orders.

        Shows what stop loss would be placed for each holding based on
        the tiered cost-based strategy.

        Args:
            holdings: List of holdings (fetches if None)

        Returns:
            List of dicts with protection plan for each holding
        """
        if holdings is None:
            holdings = self.client.get_holdings()
            holdings = [h for h in holdings if h.available_qty > 0]

        if not holdings:
            logger.info("No holdings to protect")
            return []

        # Fetch market data
        logger.info(
            f"Calculating protection plan for {len(holdings)} holdings...")
        market_data = self.fetch_all_market_data(holdings)

        plan = []
        total_invested = 0
        total_current_value = 0
        total_protected_value = 0
        total_max_loss = 0

        for holding in holdings:
            data = market_data.get(holding.isin)
            if not data:
                # Use avg cost if no market data
                current_price = holding.avg_cost_price
            else:
                current_price = data.latest_close

            cost_price = holding.avg_cost_price
            quantity = holding.available_qty
            invested = cost_price * quantity
            current_value = current_price * quantity

            # Calculate tiered stop loss
            sl_price, tier = self.calculate_tiered_stop_loss(
                cost_price, current_price)
            protected_value = sl_price * quantity

            # Calculate potential loss if SL triggers
            loss_if_triggered = current_value - protected_value
            loss_percent_from_current = (
                loss_if_triggered / current_value * 100) if current_value > 0 else 0
            loss_from_cost = invested - protected_value
            loss_percent_from_cost = (
                loss_from_cost / invested * 100) if invested > 0 else 0

            # P&L
            pnl = current_value - invested
            pnl_percent = ((current_price - cost_price) /
                           cost_price * 100) if cost_price > 0 else 0

            holding_plan = {
                "symbol": holding.trading_symbol,
                "quantity": quantity,
                "cost_price": cost_price,
                "current_price": current_price,
                "invested": invested,
                "current_value": current_value,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "stop_loss": sl_price,
                "tier": tier,
                "protected_value": protected_value,
                "loss_if_triggered": loss_if_triggered,
                "loss_percent_from_current": loss_percent_from_current,
                "loss_from_cost": loss_from_cost,
                "loss_percent_from_cost": loss_percent_from_cost,
            }
            plan.append(holding_plan)

            total_invested += invested
            total_current_value += current_value
            total_protected_value += protected_value
            total_max_loss += max(0, invested - protected_value)

        # Add summary
        summary = {
            "total_invested": total_invested,
            "total_current_value": total_current_value,
            "total_pnl": total_current_value - total_invested,
            "total_pnl_percent": ((total_current_value - total_invested) / total_invested * 100) if total_invested > 0 else 0,
            "total_protected_value": total_protected_value,
            "total_max_loss": total_max_loss,
            "max_loss_percent": (total_max_loss / total_invested * 100) if total_invested > 0 else 0,
        }

        return {"holdings": plan, "summary": summary}

    def print_protection_plan(self, holdings: list[Holding] | None = None) -> None:
        """
        Print a formatted protection plan table.

        Args:
            holdings: List of holdings (fetches if None)
        """
        result = self.get_protection_plan(holdings)
        if not result:
            print("No holdings to protect")
            return

        plan = result["holdings"]
        summary = result["summary"]

        print("\n" + "=" * 80)
        print("PROTECTION PLAN (Progressive Profit Lock + 10% Max Loss)")
        print("=" * 80)
        print(
            f"Max Loss: {self.config.max_loss_percent}% | Deep Loss SL: LTP -{self.config.deep_loss_sl_percent}%")
        print("Profit Tiers:")
        for min_pnl, lock_pct in self.config.profit_tiers:
            if lock_pct > 0:
                print(
                    f"  P&L >= {min_pnl:>2.0f}% → Lock {lock_pct:.0f}% profit (SL at cost +{lock_pct}%)")
            else:
                print(
                    f"  P&L >= {min_pnl:>2.0f}% → Protect capital (SL at cost)")
        print("-" * 80)

        for h in plan:
            print(f"\n{h['symbol']}")
            print(
                f"  Qty: {h['quantity']} | Cost: ₹{h['cost_price']:.2f} | Current: ₹{h['current_price']:.2f}")
            print(
                f"  Invested: ₹{h['invested']:.2f} | Value: ₹{h['current_value']:.2f} | P&L: ₹{h['pnl']:.2f} ({h['pnl_percent']:+.1f}%)")
            print(f"  → Stop Loss: ₹{h['stop_loss']:.2f}")
            print(f"  → Strategy: {h['tier']}")
            if h['loss_from_cost'] > 0:
                print(
                    f"  → If SL triggers: Lose ₹{h['loss_from_cost']:.2f} ({h['loss_percent_from_cost']:.1f}% of invested)")
            else:
                print(
                    f"  → If SL triggers: Gain ₹{-h['loss_from_cost']:.2f} ({-h['loss_percent_from_cost']:.1f}% profit locked)")

        print("\n" + "-" * 80)
        print("SUMMARY")
        print("-" * 80)
        print(f"Total Invested:    ₹{summary['total_invested']:.2f}")
        print(f"Current Value:     ₹{summary['total_current_value']:.2f}")
        print(
            f"Total P&L:         ₹{summary['total_pnl']:.2f} ({summary['total_pnl_percent']:+.1f}%)")
        print(f"Protected Value:   ₹{summary['total_protected_value']:.2f}")
        print(
            f"Max Possible Loss: ₹{summary['total_max_loss']:.2f} ({summary['max_loss_percent']:.1f}% of invested)")
        print("=" * 80)

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

    def create_protective_order(
        self,
        holding: Holding,
        ltp: float,
        stop_loss_price: float | None = None,
    ) -> ProtectiveOrder:
        """
        Create a protective order configuration for a holding.

        Args:
            holding: Holding to protect
            ltp: Current Last Traded Price
            stop_loss_price: Pre-calculated stop loss (uses LTP-based if None)

        Returns:
            ProtectiveOrder configuration
        """
        if stop_loss_price is None:
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
        high_52week: float | None = None,
    ) -> ProtectionResult:
        """
        Place a protective super order for a single holding.

        Strategy: Tiered Cost-Based Protection
        ---------------------------------------
        - PROFIT: Progressive profit locking (more profit → more locked)
        - SMALL LOSS: SL at cost - max_loss_percent (10%)
        - DEEP LOSS: SL at LTP - deep_loss_sl_percent (5%)

        Args:
            holding: Holding to protect
            ltp: Current LTP for the holding
            existing_orders: Dictionary of existing super orders
            force: If True, update existing orders with new prices
            high_52week: (Unused, kept for compatibility)

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

        cost_price = holding.avg_cost_price

        # Calculate tiered stop loss based on cost and current price
        new_stop_loss, tier_description = self.calculate_tiered_stop_loss(
            cost_price, ltp)

        # Don't place SL if it's above current price (would trigger immediately)
        if new_stop_loss >= ltp:
            new_stop_loss = round(ltp * 0.95, 2)  # Fallback to 5% below LTP
            tier_description = f"SAFETY FALLBACK: SL at LTP -5% (original SL >= LTP)"

        new_target = self.calculate_target_price(ltp)

        # Calculate P&L for logging
        pnl_percent = ((ltp - cost_price) / cost_price *
                       100) if cost_price > 0 else 0

        # Check for existing protection
        existing_order = existing_orders.get(holding.security_id)

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
        protective_order = self.create_protective_order(
            holding, ltp, stop_loss_price=new_stop_loss
        )

        try:
            response = self.client.place_protective_order(protective_order)
            order_id = response.get("orderId", "")
            order_status = response.get("orderStatus", "")

            logger.info(
                f"✓ Protected {holding.trading_symbol}: "
                f"LTP=₹{ltp:.2f}, Cost=₹{cost_price:.2f}, SL=₹{new_stop_loss:.2f}, P&L={pnl_percent:+.1f}%"
            )
            logger.info(f"  → {tier_description}")

            return ProtectionResult(
                holding=holding,
                success=order_status in ["PENDING", "TRANSIT"],
                ltp=ltp,
                order_id=order_id,
                message=f"Protected: {tier_description}",
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

        Uses tiered cost-based strategy:
        - PROFIT: Progressive profit locking based on P&L percentage
        - SMALL LOSS: SL at cost - max_loss_percent (10%)
        - DEEP LOSS: SL at LTP - deep_loss_sl_percent (5%)

        Args:
            holdings: Holdings to protect (fetches if None)
            force: If True, update existing orders with new prices

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

        # Fetch all market data
        logger.info(f"Fetching market data for {len(holdings)} holdings...")
        self.fetch_all_market_data(holdings)

        # Get existing orders
        existing_orders = self.get_existing_protection(holdings)

        results = []

        for holding in holdings:
            ltp = self._ltp_cache.get(holding.security_id, 0.0)

            result = self.protect_holding(
                holding, ltp, existing_orders, force=force
            )
            results.append(result)

            if not result.success:
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
        stop_loss_price: float | None = None,
    ) -> ProtectionResult:
        """
        Place an AMO (After Market Order) Stop Loss order for a holding.

        This places a regular SL-M order as AMO which will be active from market open.
        Use this when market is closed to ensure protection from the first trade.

        Args:
            holding: Holding to protect
            ltp: Current/last known LTP for stop loss calculation
            amo_time: When to inject the order: PRE_OPEN, OPEN, OPEN_30, OPEN_60
            stop_loss_price: Pre-calculated stop loss price (uses LTP-based if None)

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

        # Use provided stop loss or calculate from LTP
        if stop_loss_price is None:
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

        Uses tiered cost-based strategy:
        - PROFIT: Progressive profit locking based on P&L percentage
        - SMALL LOSS: SL at cost - max_loss_percent (10%)
        - DEEP LOSS: SL at LTP - deep_loss_sl_percent (5%)

        Use this when market is closed to place protection orders that will
        be active from market open. This ensures protection from gap downs.

        IMPORTANT: By default (force=True), this will:
        - MODIFY existing pending AMO orders with updated trigger prices
        - PLACE new orders only for holdings without existing protection

        Args:
            holdings: Holdings to protect (fetches if None)
            amo_time: When to inject: PRE_OPEN, OPEN, OPEN_30, OPEN_60
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

        # Fetch all market data (LTP, 52W high, 200-DMA)
        logger.info(f"Fetching market data for {len(holdings)} holdings...")
        self.fetch_all_market_data(holdings)

        # Get existing pending AMO orders
        existing_orders = self.get_pending_amo_orders(holdings)
        logger.info(
            f"Found {len(existing_orders)} existing pending AMO orders")

        results = []

        for holding in holdings:
            ltp = self._ltp_cache.get(holding.security_id, 0.0)
            cost_price = holding.avg_cost_price

            if ltp <= 0:
                results.append(ProtectionResult(
                    holding=holding,
                    success=False,
                    ltp=ltp,
                    message="Invalid LTP"
                ))
                continue

            # Calculate tiered stop loss based on cost and current price
            new_stop_loss, tier_description = self.calculate_tiered_stop_loss(
                cost_price, ltp)

            # Don't place SL if it's above current price (would trigger immediately)
            if new_stop_loss >= ltp:
                # Fallback to 5% below LTP
                new_stop_loss = round(ltp * 0.95, 2)
                tier_description = f"SAFETY FALLBACK: SL at LTP -5% (original SL >= LTP)"

            # Calculate P&L for logging
            pnl_percent = ((ltp - cost_price) / cost_price *
                           100) if cost_price > 0 else 0

            # Check if there's an existing order for this holding
            existing_order = existing_orders.get(holding.security_id)

            if existing_order and force:
                # MODIFY existing order instead of cancel+replace
                old_trigger = existing_order.get("triggerPrice", 0)
                order_id = existing_order.get("orderId", "")

                # Only modify if trigger price needs to change significantly
                if abs(old_trigger - new_stop_loss) > 0.05:
                    try:
                        response = self.modify_amo_order(
                            existing_order, new_stop_loss)
                        order_status = response.get("orderStatus", "")

                        logger.info(
                            f"✓ Modified {holding.trading_symbol}: "
                            f"SL ₹{old_trigger:.2f} → ₹{new_stop_loss:.2f} | {tier_description}"
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
            result = self.place_amo_sl_order(
                holding, ltp, amo_time, stop_loss_price=new_stop_loss
            )
            results.append(result)

            if result.success:
                logger.info(
                    f"✓ AMO Protected {holding.trading_symbol}: "
                    f"LTP=₹{ltp:.2f}, Cost=₹{cost_price:.2f}, SL=₹{result.stop_loss_price:.2f}, P&L={pnl_percent:+.1f}%"
                )
                logger.info(f"  → {tier_description}")
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
