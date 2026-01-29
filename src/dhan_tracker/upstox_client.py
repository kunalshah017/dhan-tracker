"""Upstox API client for market data (no authentication required for historical data)."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)


class UpstoxAPIError(Exception):
    """Upstox API error."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class MarketData:
    """Market data for a security."""

    instrument_key: str
    latest_close: float
    high_52_week: float
    low_52_week: float
    dma_200: float | None
    data_points: int
    last_updated: str  # Date of latest data


class UpstoxClient:
    """
    Client for Upstox Market Data APIs.

    Historical candle data API works without authentication.
    This client is used for:
    - 52-week high/low calculation
    - 200-DMA calculation
    - Latest close price (as LTP proxy)
    """

    BASE_URL = "https://api.upstox.com/v2"

    def __init__(self):
        """Initialize Upstox client."""
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "Accept": "application/json",
                # Historical API works with any token or even without proper auth
                "Authorization": "Bearer dummy_token",
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

    def _build_instrument_key(self, isin: str, exchange: str = "NSE") -> str:
        """
        Build Upstox instrument key from ISIN.

        Args:
            isin: ISIN code (e.g., INF200KA16D8)
            exchange: Exchange (NSE or BSE)

        Returns:
            Instrument key (e.g., NSE_EQ|INF200KA16D8)
        """
        segment = "NSE_EQ" if exchange.upper() in ("NSE", "ALL") else "BSE_EQ"
        return f"{segment}|{isin}"

    def get_historical_data(
        self,
        instrument_key: str,
        interval: str = "day",
        days: int = 365,
    ) -> dict:
        """
        Get historical OHLC data for a security.

        Args:
            instrument_key: Upstox instrument key (e.g., NSE_EQ|INF200KA16D8)
            interval: Candle interval (1minute, 30minute, day, week, month)
            days: Number of days of historical data

        Returns:
            Dict with candles array and status
        """
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days)
                     ).strftime("%Y-%m-%d")

        # URL encode the pipe character
        encoded_key = instrument_key.replace("|", "%7C")
        endpoint = f"/historical-candle/{encoded_key}/{interval}/{to_date}/{from_date}"

        try:
            response = self._client.get(endpoint)

            if response.status_code >= 400:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    errors = error_data.get("errors", [])
                    if errors:
                        error_msg = errors[0].get("message", error_msg)
                except Exception:
                    error_msg = response.text or error_msg
                raise UpstoxAPIError(error_msg, response.status_code)

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise UpstoxAPIError(f"Request failed: {e}")

    def get_market_data(
        self,
        isin: str,
        exchange: str = "NSE",
    ) -> MarketData:
        """
        Get comprehensive market data for a security.

        Args:
            isin: ISIN code
            exchange: Exchange (NSE or BSE)

        Returns:
            MarketData with 52W high/low, 200-DMA, latest close
        """
        instrument_key = self._build_instrument_key(isin, exchange)

        try:
            response = self.get_historical_data(instrument_key, days=365)

            if response.get("status") != "success":
                raise UpstoxAPIError(f"API returned non-success: {response}")

            candles = response.get("data", {}).get("candles", [])

            if not candles:
                raise UpstoxAPIError(f"No candle data for {instrument_key}")

            # Candle format: [timestamp, open, high, low, close, volume, oi]
            highs = [c[2] for c in candles]
            lows = [c[3] for c in candles]
            closes = [c[4] for c in candles]

            high_52w = max(highs)
            low_52w = min(lows)
            latest_close = closes[0]  # Most recent is first
            # Extract date from timestamp
            last_date = candles[0][0].split("T")[0]

            # Calculate 200-DMA if enough data
            dma_200 = None
            if len(closes) >= 200:
                dma_200 = sum(closes[:200]) / 200

            return MarketData(
                instrument_key=instrument_key,
                latest_close=latest_close,
                high_52_week=high_52w,
                low_52_week=low_52w,
                dma_200=dma_200,
                data_points=len(candles),
                last_updated=last_date,
            )

        except UpstoxAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to get market data for {isin}: {e}")
            raise UpstoxAPIError(f"Failed to get market data: {e}")

    def get_52_week_high(self, isin: str, exchange: str = "NSE") -> float:
        """
        Get 52-week high price for a security.

        Args:
            isin: ISIN code
            exchange: Exchange

        Returns:
            52-week high price
        """
        try:
            data = self.get_market_data(isin, exchange)
            return data.high_52_week
        except Exception as e:
            logger.warning(f"Failed to get 52-week high for {isin}: {e}")
            return 0.0

    def get_latest_close(self, isin: str, exchange: str = "NSE") -> float:
        """
        Get latest closing price (proxy for LTP).

        Args:
            isin: ISIN code
            exchange: Exchange

        Returns:
            Latest closing price
        """
        try:
            data = self.get_market_data(isin, exchange)
            return data.latest_close
        except Exception as e:
            logger.warning(f"Failed to get latest close for {isin}: {e}")
            return 0.0

    def get_200_dma(self, isin: str, exchange: str = "NSE") -> float | None:
        """
        Get 200-day moving average.

        Args:
            isin: ISIN code
            exchange: Exchange

        Returns:
            200-DMA or None if insufficient data
        """
        try:
            data = self.get_market_data(isin, exchange)
            return data.dma_200
        except Exception as e:
            logger.warning(f"Failed to get 200-DMA for {isin}: {e}")
            return None

    def get_market_data_bulk(
        self,
        holdings: list,  # List of Holding objects with isin and exchange
    ) -> dict[str, MarketData]:
        """
        Get market data for multiple securities.

        Args:
            holdings: List of Holding objects

        Returns:
            Dict mapping ISIN to MarketData
        """
        result = {}
        for holding in holdings:
            try:
                exchange = holding.exchange if hasattr(
                    holding, 'exchange') else 'NSE'
                data = self.get_market_data(holding.isin, exchange)
                result[holding.isin] = data
                logger.debug(f"Got market data for {holding.trading_symbol}: "
                             f"close={data.latest_close}, 52WH={data.high_52_week}")
            except Exception as e:
                logger.warning(
                    f"Failed to get market data for {holding.isin}: {e}")

        return result
