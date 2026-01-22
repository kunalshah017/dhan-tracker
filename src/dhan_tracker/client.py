"""Dhan API Client for interacting with Dhan Trading APIs."""

import logging
import os
from typing import Optional

import httpx

from .config import DhanConfig
from .models import (
    Holding,
    Position,
    SuperOrder,
    ProtectiveOrder,
    OrderStatus,
)

logger = logging.getLogger(__name__)


class DhanAPIError(Exception):
    """Exception raised for Dhan API errors."""

    def __init__(self, message: str, status_code: int = 0, response: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.response = response or {}
        super().__init__(self.message)


class DhanClient:
    """Client for Dhan Trading APIs."""

    def __init__(self, config: DhanConfig):
        """Initialize Dhan client with configuration."""
        self.config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "access-token": config.access_token,
                "client-id": config.client_id,  # Required for market data APIs
            },
            timeout=30.0,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def _request(
        self,
        method: str,
        endpoint: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict | list:
        """Make an API request.
        
        Note: Token refresh on 401 is NOT implemented here because the Dhan API's
        /v2/RenewToken endpoint requires a VALID token. If we receive 401, the token
        has already expired and cannot be refreshed. Instead, tokens are proactively
        refreshed every 23 hours via scheduled job before they expire.
        """
        try:
            response = self._client.request(
                method=method,
                url=endpoint,
                json=json,
                params=params,
            )

            # Handle 202 Accepted (no content)
            if response.status_code == 202:
                return {"status": "accepted"}

            # Check for errors
            if response.status_code >= 400:
                error_msg = f"API Error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get(
                        "errorMessage", error_data.get("message", error_msg))
                    logger.error(f"API Error Response: {error_data}")
                    
                    # Special handling for token expiration
                    if response.status_code == 401:
                        logger.error("Token has expired! Please update DHAN_ACCESS_TOKEN in environment variables.")
                        logger.error("Tokens cannot be refreshed after expiry - they must be renewed BEFORE expiration.")
                except Exception:
                    error_msg = response.text or error_msg
                    logger.error(f"API Error Text: {response.text}")
                raise DhanAPIError(error_msg, response.status_code)

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise DhanAPIError(f"Request failed: {e}")

    # ==================== Market Data APIs ====================

    def get_ltp(self, security_ids: dict[str, list[str]]) -> dict[str, dict[str, float]]:
        """
        Get Last Traded Price (LTP) for multiple instruments.

        Args:
            security_ids: Dictionary mapping exchange segment to list of security IDs
                         e.g., {"NSE_EQ": ["11536", "1333"], "BSE_EQ": ["500325"]}

        Returns:
            Dictionary mapping exchange -> security_id -> LTP
            e.g., {"NSE_EQ": {"11536": 4520.0, "1333": 1660.0}}
        """
        # Convert string IDs to integers as required by API
        payload = {
            segment: [int(sid) for sid in ids]
            for segment, ids in security_ids.items()
        }

        response = self._request("POST", "/marketfeed/ltp", json=payload)

        if not isinstance(response, dict) or "data" not in response:
            logger.warning(f"Unexpected LTP response: {response}")
            return {}

        # Parse response and extract LTP values
        result = {}
        data = response.get("data", {})
        for segment, securities in data.items():
            result[segment] = {}
            for sec_id, info in securities.items():
                result[segment][sec_id] = info.get("last_price", 0.0)

        return result

    def get_ltp_for_holdings(self, holdings: list[Holding]) -> dict[str, float]:
        """
        Get LTP for a list of holdings.

        Args:
            holdings: List of Holding objects

        Returns:
            Dictionary mapping security_id to LTP
        """
        if not holdings:
            return {}

        # Group by exchange segment
        # Holdings have 'exchange' which is like 'NSE' or 'BSE', we need to map to NSE_EQ/BSE_EQ
        segments: dict[str, list[str]] = {}
        for h in holdings:
            # Map exchange to segment (assuming equity)
            if h.exchange in ("NSE", "ALL"):
                segment = "NSE_EQ"
            elif h.exchange == "BSE":
                segment = "BSE_EQ"
            else:
                segment = "NSE_EQ"  # Default to NSE

            if segment not in segments:
                segments[segment] = []
            segments[segment].append(h.security_id)

        ltp_data = self.get_ltp(segments)

        # Flatten to security_id -> LTP mapping
        result = {}
        for segment, securities in ltp_data.items():
            for sec_id, ltp in securities.items():
                result[sec_id] = ltp

        return result

    # ==================== Portfolio APIs ====================

    def get_holdings(self) -> list[Holding]:
        """
        Retrieve all holdings in demat account.

        Returns:
            List of Holding objects representing holdings in the portfolio.
        """
        response = self._request("GET", "/holdings")

        if not isinstance(response, list):
            logger.warning(f"Unexpected holdings response: {response}")
            return []

        holdings = [Holding.from_api_response(h) for h in response]
        logger.info(f"Retrieved {len(holdings)} holdings")
        return holdings

    def get_positions(self) -> list[Position]:
        """
        Retrieve all open positions.

        Returns:
            List of Position objects representing open positions.
        """
        response = self._request("GET", "/positions")

        if not isinstance(response, list):
            logger.warning(f"Unexpected positions response: {response}")
            return []

        positions = [Position.from_api_response(p) for p in response]
        logger.info(f"Retrieved {len(positions)} positions")
        return positions

    # ==================== Super Order APIs ====================

    def get_super_orders(self) -> list[SuperOrder]:
        """
        Retrieve all super orders for the day.

        Returns:
            List of SuperOrder objects.
        """
        response = self._request("GET", "/super/orders")

        if not isinstance(response, list):
            logger.warning(f"Unexpected super orders response: {response}")
            return []

        orders = [SuperOrder.from_api_response(o) for o in response]
        logger.info(f"Retrieved {len(orders)} super orders")
        return orders

    def place_super_order(
        self,
        security_id: str,
        quantity: int,
        price: float,
        target_price: float,
        stop_loss_price: float,
        transaction_type: str = "SELL",
        exchange_segment: str = "NSE_EQ",
        product_type: str = "CNC",
        order_type: str = "LIMIT",
        trailing_jump: float = 0.0,
        correlation_id: str | None = None,
    ) -> dict:
        """
        Place a super order with entry, target, and stop loss legs.

        Args:
            security_id: Exchange security ID
            quantity: Number of shares
            price: Entry price
            target_price: Target price for profit booking
            stop_loss_price: Stop loss price for protection
            transaction_type: BUY or SELL
            exchange_segment: Exchange segment (NSE_EQ, BSE_EQ, etc.)
            product_type: CNC, INTRADAY, MARGIN, MTF
            order_type: LIMIT or MARKET
            trailing_jump: Price jump for trailing stop loss
            correlation_id: Custom ID for tracking

        Returns:
            Order response with orderId and orderStatus
        """
        payload = {
            "dhanClientId": self.config.client_id,
            "transactionType": transaction_type,
            "exchangeSegment": exchange_segment,
            "productType": product_type,
            "orderType": order_type,
            "securityId": security_id,
            "quantity": quantity,
            "price": price,
            "targetPrice": target_price,
            "stopLossPrice": stop_loss_price,
            "trailingJump": trailing_jump,
        }

        if correlation_id:
            payload["correlationId"] = correlation_id

        logger.info(
            f"Placing super order for {security_id}: qty={quantity}, sl={stop_loss_price}")
        response = self._request("POST", "/super/orders", json=payload)
        logger.info(f"Super order response: {response}")
        return response

    def place_protective_order(self, order: ProtectiveOrder) -> dict:
        """
        Place a protective super order.

        Args:
            order: ProtectiveOrder configuration

        Returns:
            Order response with orderId and orderStatus
        """
        payload = order.to_super_order_request(self.config.client_id)
        logger.info(
            f"Placing protective order for {order.trading_symbol}: qty={order.quantity}")
        response = self._request("POST", "/super/orders", json=payload)
        return response

    def modify_super_order(
        self,
        order_id: str,
        leg_name: str,
        order_type: str | None = None,
        quantity: int | None = None,
        price: float | None = None,
        target_price: float | None = None,
        stop_loss_price: float | None = None,
        trailing_jump: float | None = None,
    ) -> dict:
        """
        Modify a pending super order.

        Args:
            order_id: Order ID to modify
            leg_name: ENTRY_LEG, TARGET_LEG, or STOP_LOSS_LEG
            order_type: Order type (for ENTRY_LEG)
            quantity: Quantity (for ENTRY_LEG)
            price: Entry price (for ENTRY_LEG)
            target_price: Target price
            stop_loss_price: Stop loss price
            trailing_jump: Trailing stop loss jump

        Returns:
            Order response with orderId and orderStatus
        """
        payload = {
            "dhanClientId": self.config.client_id,
            "orderId": order_id,
            "legName": leg_name,
        }

        if order_type:
            payload["orderType"] = order_type
        if quantity:
            payload["quantity"] = quantity
        if price:
            payload["price"] = price
        if target_price:
            payload["targetPrice"] = target_price
        if stop_loss_price:
            payload["stopLossPrice"] = stop_loss_price
        if trailing_jump is not None:
            payload["trailingJump"] = trailing_jump

        logger.info(f"Modifying super order {order_id}, leg={leg_name}")
        response = self._request(
            "PUT", f"/super/orders/{order_id}", json=payload)
        return response

    def cancel_super_order(self, order_id: str, leg_name: str = "ENTRY_LEG") -> dict:
        """
        Cancel a pending super order or specific leg.

        Args:
            order_id: Order ID to cancel
            leg_name: Leg to cancel (ENTRY_LEG cancels all legs)

        Returns:
            Cancellation response
        """
        logger.info(f"Cancelling super order {order_id}, leg={leg_name}")
        response = self._request(
            "DELETE", f"/super/orders/{order_id}/{leg_name}")
        return response

    # ==================== Regular Order APIs (for AMO) ====================

    def place_sl_order(
        self,
        security_id: str,
        quantity: int,
        trigger_price: float,
        price: float = 0.0,
        transaction_type: str = "SELL",
        exchange_segment: str = "NSE_EQ",
        product_type: str = "CNC",
        order_type: str = "STOP_LOSS_MARKET",
        after_market_order: bool = False,
        amo_time: str = "OPEN",
        correlation_id: str | None = None,
    ) -> dict:
        """
        Place a Stop Loss order (can be AMO).

        Args:
            security_id: Exchange security ID
            quantity: Number of shares
            trigger_price: Price at which order is triggered
            price: Limit price (0 for market order)
            transaction_type: BUY or SELL
            exchange_segment: Exchange segment (NSE_EQ, BSE_EQ, etc.)
            product_type: CNC, INTRADAY, MARGIN, MTF
            order_type: STOP_LOSS or STOP_LOSS_MARKET
            after_market_order: True for AMO orders
            amo_time: PRE_OPEN, OPEN, OPEN_30, OPEN_60
            correlation_id: Custom ID for tracking

        Returns:
            Order response with orderId and orderStatus
        """
        payload = {
            "dhanClientId": self.config.client_id,
            "transactionType": transaction_type,
            "exchangeSegment": exchange_segment,
            "productType": product_type,
            "orderType": order_type,
            "validity": "DAY",
            "securityId": security_id,
            "quantity": quantity,
            "price": price,
            "triggerPrice": trigger_price,
            "afterMarketOrder": after_market_order,
        }

        if after_market_order:
            payload["amoTime"] = amo_time

        if correlation_id:
            payload["correlationId"] = correlation_id

        logger.info(
            f"Placing SL order for {security_id}: qty={quantity}, trigger={trigger_price}, AMO={after_market_order}")
        response = self._request("POST", "/orders", json=payload)
        logger.info(f"SL order response: {response}")
        return response

    def get_orders(self) -> list[dict]:
        """
        Retrieve all orders for the day.

        Returns:
            List of order dictionaries.
        """
        response = self._request("GET", "/orders")

        if not isinstance(response, list):
            logger.warning(f"Unexpected orders response: {response}")
            return []

        logger.info(f"Retrieved {len(response)} orders")
        return response

    def cancel_order(self, order_id: str) -> dict:
        """
        Cancel a pending order.

        Args:
            order_id: Order ID to cancel

        Returns:
            Cancellation response
        """
        logger.info(f"Cancelling order {order_id}")
        response = self._request("DELETE", f"/orders/{order_id}")
        return response

    def modify_order(
        self,
        order_id: str,
        order_type: str | None = None,
        quantity: int | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
        validity: str = "DAY",
    ) -> dict:
        """
        Modify a pending order (including AMO orders).

        Args:
            order_id: Order ID to modify
            order_type: Order type (LIMIT, MARKET, STOP_LOSS, STOP_LOSS_MARKET)
            quantity: New quantity
            price: New price
            trigger_price: New trigger price (for SL orders)
            validity: Order validity (DAY, IOC)

        Returns:
            Modified order response with orderId and orderStatus
        """
        payload = {
            "dhanClientId": self.config.client_id,
            "orderId": order_id,
            "validity": validity,
        }

        if order_type:
            payload["orderType"] = order_type
        if quantity:
            payload["quantity"] = quantity
        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["triggerPrice"] = trigger_price

        logger.info(f"Modifying order {order_id}: trigger={trigger_price}")
        response = self._request("PUT", f"/orders/{order_id}", json=payload)
        logger.info(f"Modify order response: {response}")
        return response

    # ==================== Token Management ====================

    def _refresh_token_internal(self) -> dict:
        """
        Internal method to refresh the access token.
        Updates the client headers with the new token.
        
        IMPORTANT: This only works if the current token is still VALID.
        If the token has already expired (401), this will fail.
        Use scheduled proactive refresh (every 23 hours) instead.
        
        Returns:
            New token response dict
            
        Raises:
            DhanAPIError: If token refresh fails
        """
        # Use raw httpx for this since it's a different endpoint pattern
        response = httpx.post(
            "https://api.dhan.co/v2/RenewToken",
            headers={
                "access-token": self.config.access_token,
                "dhanClientId": self.config.client_id,
            },
        )

        if response.status_code >= 400:
            error_msg = f"Token refresh failed with status {response.status_code}: {response.text}"
            logger.error(error_msg)
            logger.error("This likely means the token has already expired.")
            logger.error("Tokens must be refreshed BEFORE they expire (within 24 hours of generation).")
            raise DhanAPIError(error_msg, response.status_code)

        token_data = response.json()
        
        # Extract the new access token from the response
        # The Dhan API may return the token in different formats
        new_token = None
        if isinstance(token_data, dict):
            # Try common key names for the access token
            new_token = token_data.get("access_token") or token_data.get("accessToken")
        
        if not new_token:
            logger.error(f"Unexpected token response format: {token_data}")
            raise DhanAPIError(
                f"Failed to extract new token from refresh response. Response: {token_data}")
            
        # Update the config and client headers with the new token
        self.config.access_token = new_token
        self._client.headers["access-token"] = new_token
        
        # Also update the environment variable so it persists across requests
        # This is important for Azure App Service where the config is loaded from env vars
        os.environ["DHAN_ACCESS_TOKEN"] = new_token
        
        logger.info("Access token refreshed and updated successfully")
        logger.info(f"New token will be valid for next 24 hours")
            
        return token_data

    def refresh_token(self) -> dict:
        """
        Refresh the access token for another 24 hours.

        Returns:
            New token response
        """
        return self._refresh_token_internal()
