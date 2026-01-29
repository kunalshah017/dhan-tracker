"""Order trigger monitoring and logging service."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from dhan_tracker.client import DhanClient
from dhan_tracker.config import DhanConfig
from dhan_tracker.database import (
    save_order_trigger,
    get_order_triggers,
    mark_trigger_email_sent,
    is_database_available,
)
from dhan_tracker.notifications import send_sl_trigger_email, get_notifier

logger = logging.getLogger(__name__)


class TriggerMonitor:
    """Monitor and log order trigger executions."""

    def __init__(self, client: DhanClient | None = None):
        if client is None:
            config = DhanConfig.load()
            client = DhanClient(config)
        self.client = client
        self._processed_orders: set[str] = set()

    def check_triggered_orders(self) -> list[dict]:
        """
        Check for orders that have been triggered/executed.

        Looks for SELL orders with status TRADED that are stop loss orders.

        Returns:
            List of newly triggered orders that were logged
        """
        try:
            orders = self.client.get_orders()
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []

        triggered = []

        for order in orders:
            order_id = order.get("orderId", "")
            order_status = order.get("orderStatus", "")
            order_type = order.get("orderType", "")
            transaction_type = order.get("transactionType", "")

            # Skip if already processed
            if order_id in self._processed_orders:
                continue

            # Only process SELL orders that are SL types and TRADED
            if (
                transaction_type == "SELL"
                and order_type in ["STOP_LOSS", "STOP_LOSS_MARKET"]
                and order_status == "TRADED"
            ):
                self._processed_orders.add(order_id)

                # Log the trigger
                result = self._log_trigger(order)
                if result:
                    triggered.append(result)

        return triggered

    def _log_trigger(self, order: dict) -> dict | None:
        """
        Log a triggered order to database and send notification.

        Args:
            order: Order dict from Dhan API

        Returns:
            Logged trigger dict or None if failed
        """
        order_id = order.get("orderId", "")
        trading_symbol = order.get("tradingSymbol", "")
        security_id = order.get("securityId", "")
        quantity = order.get("tradedQty", order.get("quantity", 0))
        trigger_price = order.get("triggerPrice", 0)
        traded_price = order.get("tradedPrice", order.get("price", 0))
        order_type = order.get("orderType", "STOP_LOSS")
        order_status = order.get("orderStatus", "TRADED")

        # Try to get cost price from holdings for P&L calculation
        cost_price = None
        pnl_amount = None
        pnl_percent = None
        protection_tier = None
        isin = None

        try:
            holdings = self.client.get_holdings()
            for h in holdings:
                if h.security_id == security_id:
                    cost_price = h.avg_cost_price
                    isin = h.isin

                    # Calculate P&L
                    if cost_price > 0 and traded_price > 0:
                        pnl_amount = (traded_price - cost_price) * quantity
                        pnl_percent = (
                            (traded_price - cost_price) / cost_price) * 100

                        # Determine protection tier based on P&L
                        if pnl_percent >= 50:
                            protection_tier = "PROFIT LOCK +35%"
                        elif pnl_percent >= 30:
                            protection_tier = "PROFIT LOCK +20%"
                        elif pnl_percent >= 20:
                            protection_tier = "PROFIT LOCK +12%"
                        elif pnl_percent >= 10:
                            protection_tier = "PROFIT LOCK +5%"
                        elif pnl_percent >= 5:
                            protection_tier = "PROFIT LOCK +2%"
                        elif pnl_percent >= 0:
                            protection_tier = "CAPITAL PROTECT"
                        elif pnl_percent >= -10:
                            protection_tier = "RECOVERY ROOM"
                        else:
                            protection_tier = "DAMAGE LIMIT"
                    break
        except Exception as e:
            logger.warning(f"Could not get holdings for P&L calculation: {e}")

        # Save to database
        trigger_data = {
            "order_id": order_id,
            "trading_symbol": trading_symbol,
            "isin": isin,
            "security_id": security_id,
            "transaction_type": "SELL",
            "quantity": quantity,
            "trigger_price": trigger_price,
            "executed_price": traded_price,
            "order_type": order_type,
            "order_status": order_status,
            "trigger_type": "STOP_LOSS",
            "cost_price": cost_price,
            "pnl_amount": pnl_amount,
            "pnl_percent": pnl_percent,
            "protection_tier": protection_tier,
        }

        if is_database_available():
            saved = save_order_trigger(**trigger_data)
            if saved:
                logger.info(
                    f"✓ Logged trigger: {trading_symbol} x{quantity} @ ₹{trigger_price:.2f}"
                )
            else:
                logger.warning(f"Failed to save trigger to database")
        else:
            logger.warning("Database not available - trigger not persisted")

        # Send email notification
        notifier = get_notifier()
        if notifier.is_configured():
            email_sent = send_sl_trigger_email(
                trading_symbol=trading_symbol,
                quantity=quantity,
                trigger_price=trigger_price,
                order_id=order_id,
                order_status=order_status,
                executed_price=traded_price,
                cost_price=cost_price,
                pnl_amount=pnl_amount,
                pnl_percent=pnl_percent,
                protection_tier=protection_tier,
            )
            if email_sent:
                mark_trigger_email_sent(order_id)
                logger.info(f"✓ Email notification sent for {trading_symbol}")
        else:
            logger.debug("Email not configured - notification skipped")

        return trigger_data

    def get_trigger_history(
        self,
        limit: int = 50,
        symbol: Optional[str] = None,
        days: Optional[int] = None,
    ) -> list[dict]:
        """
        Get order trigger history from database.

        Args:
            limit: Maximum records to return
            symbol: Filter by trading symbol
            days: Filter to last N days

        Returns:
            List of trigger records
        """
        return get_order_triggers(limit=limit, symbol=symbol, days=days)

    def get_trigger_summary(self, days: int = 30) -> dict:
        """
        Get summary statistics for triggered orders.

        Args:
            days: Look back period in days

        Returns:
            Summary dict with stats
        """
        triggers = get_order_triggers(limit=1000, days=days)

        if not triggers:
            return {
                "period_days": days,
                "total_triggers": 0,
                "total_pnl": 0,
                "profit_triggers": 0,
                "loss_triggers": 0,
                "symbols": [],
            }

        total_pnl = sum(t.get("pnl_amount", 0) or 0 for t in triggers)
        profit_triggers = sum(1 for t in triggers if (
            t.get("pnl_amount", 0) or 0) >= 0)
        loss_triggers = len(triggers) - profit_triggers
        symbols = list(set(t["trading_symbol"] for t in triggers))

        return {
            "period_days": days,
            "total_triggers": len(triggers),
            "total_pnl": total_pnl,
            "profit_triggers": profit_triggers,
            "loss_triggers": loss_triggers,
            "symbols": symbols,
            "triggers": triggers,
        }


# Singleton instance
_monitor: TriggerMonitor | None = None


def get_trigger_monitor() -> TriggerMonitor:
    """Get the singleton trigger monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = TriggerMonitor()
    return _monitor


def check_and_log_triggers() -> list[dict]:
    """
    Convenience function to check and log triggered orders.

    Call this periodically (e.g., every few minutes during market hours)
    to detect and log SL triggers.

    Returns:
        List of newly triggered orders
    """
    monitor = get_trigger_monitor()
    return monitor.check_triggered_orders()
