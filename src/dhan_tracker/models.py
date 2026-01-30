"""Data models for Dhan Tracker."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Exchange(str, Enum):
    """Exchange types."""
    NSE_EQ = "NSE_EQ"
    BSE_EQ = "BSE_EQ"
    NSE_FNO = "NSE_FNO"
    BSE_FNO = "BSE_FNO"
    NSE_CURRENCY = "NSE_CURRENCY"
    BSE_CURRENCY = "BSE_CURRENCY"
    MCX_COMM = "MCX_COMM"


class TransactionType(str, Enum):
    """Transaction types."""
    BUY = "BUY"
    SELL = "SELL"


class ProductType(str, Enum):
    """Product types."""
    CNC = "CNC"  # Cash and Carry (Delivery)
    INTRADAY = "INTRADAY"
    MARGIN = "MARGIN"
    MTF = "MTF"  # Margin Trading Facility


class OrderType(str, Enum):
    """Order types."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(str, Enum):
    """Order status types."""
    TRANSIT = "TRANSIT"
    PENDING = "PENDING"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    PART_TRADED = "PART_TRADED"
    TRADED = "TRADED"


class LegName(str, Enum):
    """Super order leg names."""
    ENTRY_LEG = "ENTRY_LEG"
    TARGET_LEG = "TARGET_LEG"
    STOP_LOSS_LEG = "STOP_LOSS_LEG"


@dataclass
class Holding:
    """Represents a holding in the portfolio."""

    exchange: str
    trading_symbol: str
    security_id: str
    isin: str
    total_qty: int
    dp_qty: int  # Quantity in demat
    t1_qty: int  # T+1 quantity
    available_qty: int
    collateral_qty: int
    avg_cost_price: float

    @classmethod
    def from_api_response(cls, data: dict) -> "Holding":
        """Create Holding from API response."""
        return cls(
            exchange=data.get("exchange", ""),
            trading_symbol=data.get("tradingSymbol", ""),
            security_id=data.get("securityId", ""),
            isin=data.get("isin", ""),
            total_qty=data.get("totalQty", 0),
            dp_qty=data.get("dpQty", 0),
            t1_qty=data.get("t1Qty", 0),
            available_qty=data.get("availableQty", 0),
            collateral_qty=data.get("collateralQty", 0),
            avg_cost_price=data.get("avgCostPrice", 0.0),
        )

    @property
    def current_value(self) -> float:
        """Calculate current value based on avg cost."""
        return self.total_qty * self.avg_cost_price


@dataclass
class Position:
    """Represents an open position."""

    dhan_client_id: str
    trading_symbol: str
    security_id: str
    position_type: str
    exchange_segment: str
    product_type: str
    buy_avg: float
    buy_qty: int
    cost_price: float
    sell_avg: float
    sell_qty: int
    net_qty: int
    realized_profit: float
    unrealized_profit: float
    ltp: float = 0.0

    @classmethod
    def from_api_response(cls, data: dict) -> "Position":
        """Create Position from API response."""
        return cls(
            dhan_client_id=data.get("dhanClientId", ""),
            trading_symbol=data.get("tradingSymbol", ""),
            security_id=data.get("securityId", ""),
            position_type=data.get("positionType", ""),
            exchange_segment=data.get("exchangeSegment", ""),
            product_type=data.get("productType", ""),
            buy_avg=data.get("buyAvg", 0.0),
            buy_qty=data.get("buyQty", 0),
            cost_price=data.get("costPrice", 0.0),
            sell_avg=data.get("sellAvg", 0.0),
            sell_qty=data.get("sellQty", 0),
            net_qty=data.get("netQty", 0),
            realized_profit=data.get("realizedProfit", 0.0),
            unrealized_profit=data.get("unrealizedProfit", 0.0),
        )


@dataclass
class LegDetail:
    """Details of a super order leg."""

    order_id: str
    leg_name: str
    transaction_type: str
    total_quantity: int
    remaining_quantity: int
    triggered_quantity: int
    price: float
    order_status: str
    trailing_jump: float = 0.0

    @classmethod
    def from_api_response(cls, data: dict) -> "LegDetail":
        """Create LegDetail from API response."""
        return cls(
            order_id=data.get("orderId", ""),
            leg_name=data.get("legName", ""),
            transaction_type=data.get("transactionType", ""),
            total_quantity=data.get("totalQuatity", 0),  # API has typo
            remaining_quantity=data.get("remainingQuantity", 0),
            triggered_quantity=data.get("triggeredQuantity", 0),
            price=data.get("price", 0.0),
            order_status=data.get("orderStatus", ""),
            trailing_jump=data.get("trailingJump", 0.0),
        )


@dataclass
class SuperOrder:
    """Represents a super order."""

    dhan_client_id: str
    order_id: str
    correlation_id: str
    order_status: str
    transaction_type: str
    exchange_segment: str
    product_type: str
    order_type: str
    trading_symbol: str
    security_id: str
    quantity: int
    remaining_quantity: int
    ltp: float
    price: float
    leg_name: str
    create_time: str
    update_time: str
    average_traded_price: float
    filled_qty: int
    leg_details: list[LegDetail] = field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict) -> "SuperOrder":
        """Create SuperOrder from API response."""
        leg_details = [
            LegDetail.from_api_response(leg)
            for leg in data.get("legDetails", [])
        ]

        return cls(
            dhan_client_id=data.get("dhanClientId", ""),
            order_id=data.get("orderId", ""),
            correlation_id=data.get("correlationId", ""),
            order_status=data.get("orderStatus", ""),
            transaction_type=data.get("transactionType", ""),
            exchange_segment=data.get("exchangeSegment", ""),
            product_type=data.get("productType", ""),
            order_type=data.get("orderType", ""),
            trading_symbol=data.get("tradingSymbol", ""),
            security_id=data.get("securityId", ""),
            quantity=data.get("quantity", 0),
            remaining_quantity=data.get("remainingQuantity", 0),
            ltp=data.get("ltp", 0.0),
            price=data.get("price", 0.0),
            leg_name=data.get("legName", ""),
            create_time=data.get("createTime", ""),
            update_time=data.get("updateTime", ""),
            average_traded_price=data.get("averageTradedPrice", 0.0),
            filled_qty=data.get("filledQty", 0),
            leg_details=leg_details,
        )

    @property
    def stop_loss_leg(self) -> Optional[LegDetail]:
        """Get stop loss leg if exists."""
        for leg in self.leg_details:
            if leg.leg_name == LegName.STOP_LOSS_LEG.value:
                return leg
        return None

    @property
    def target_leg(self) -> Optional[LegDetail]:
        """Get target leg if exists."""
        for leg in self.leg_details:
            if leg.leg_name == LegName.TARGET_LEG.value:
                return leg
        return None


@dataclass
class ProtectiveOrder:
    """Configuration for a protective sell order."""

    security_id: str
    trading_symbol: str
    quantity: int
    entry_price: float  # Current price / avg cost
    stop_loss_price: float
    target_price: float
    trailing_jump: float = 0.0
    exchange_segment: str = "NSE_EQ"
    product_type: str = "CNC"

    def to_super_order_request(self, client_id: str) -> dict:
        """Convert to super order API request.

        For protective SELL orders on existing holdings:
        - Use STOP_LOSS_MARKET: triggers when price DROPS to stop_loss_price
        - No target needed (targetPrice = 0)
        - price = 0 for market execution after trigger
        """
        return {
            "dhanClientId": client_id,
            "correlationId": f"protect_{self.security_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "transactionType": "SELL",
            "exchangeSegment": self.exchange_segment,
            "productType": self.product_type,
            "orderType": "STOP_LOSS_MARKET",
            "securityId": self.security_id,
            "quantity": self.quantity,
            "price": 0,  # Market order after trigger
            "triggerPrice": self.stop_loss_price,  # Trigger when price drops to this
            "targetPrice": 0,  # Disabled for protective orders
            "stopLossPrice": 0,  # Not used for SL-M entry
            "trailingJump": self.trailing_jump,
        }


@dataclass
class ForeverOrder:
    """Represents a Forever Order (GTT - Good Till Triggered).

    Forever Orders are trigger-based orders that wait until price hits
    the trigger level before becoming active. Perfect for protective
    stop losses on existing holdings without bracket order constraints.
    """

    dhan_client_id: str
    order_id: str
    order_flag: str  # SINGLE or OCO
    order_status: str
    transaction_type: str
    exchange_segment: str
    product_type: str
    order_type: str
    trading_symbol: str
    security_id: str
    quantity: int
    price: float  # Execution price (0 for market)
    trigger_price: float  # Trigger level
    create_time: str = ""
    update_time: str = ""

    @classmethod
    def from_api_response(cls, data: dict) -> "ForeverOrder":
        """Create ForeverOrder from API response."""
        return cls(
            dhan_client_id=data.get("dhanClientId", ""),
            order_id=data.get("orderId", ""),
            order_flag=data.get("orderFlag", "SINGLE"),
            order_status=data.get("orderStatus", ""),
            transaction_type=data.get("transactionType", ""),
            exchange_segment=data.get("exchangeSegment", ""),
            product_type=data.get("productType", ""),
            order_type=data.get("orderType", ""),
            trading_symbol=data.get("tradingSymbol", ""),
            security_id=data.get("securityId", ""),
            quantity=data.get("quantity", 0),
            price=data.get("price", 0.0),
            trigger_price=data.get("triggerPrice", 0.0),
            create_time=data.get("createTime", ""),
            update_time=data.get("updateTime", ""),
        )
