"""NSE India API client for fetching market data."""

import logging
import httpx
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class NSEError(Exception):
    """NSE API error."""
    pass


@dataclass
class NSEQuote:
    """NSE quote data."""
    symbol: str
    last_price: float
    close_price: float
    previous_close: float
    open_price: float
    day_high: float
    day_low: float
    change: float
    pchange: float
    company_name: str
    isin: str


@dataclass
class ETFData:
    """ETF data from NSE."""
    symbol: str
    underlying: str
    ltp: float
    nav: float
    change: float
    pchange: float
    volume: int
    turnover: float
    week52_high: float
    week52_low: float
    discount_premium: float  # Negative = discount (buy opportunity)
    isin: str = ""


class NSEClient:
    """Client for NSE India API."""

    BASE_URL = "https://www.nseindia.com"
    QUOTE_API = "/api/NextApi/apiClient/GetQuoteApi"

    def __init__(self):
        """Initialize NSE client with proper headers."""
        # Don't request brotli encoding to avoid decoding issues
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",  # Exclude br (brotli)
                "Referer": "https://www.nseindia.com/",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        self._initialized = False

    def _init_session(self):
        """Initialize session by visiting the main page to get cookies."""
        if self._initialized:
            return

        try:
            # Visit main page to get session cookies
            response = self._client.get("/")
            if response.status_code == 200:
                self._initialized = True
                logger.debug("NSE session initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize NSE session: {e}")

    def get_quote(self, symbol: str, series: str = "EQ", market_type: str = "N") -> NSEQuote:
        """
        Get quote data for a symbol.

        Args:
            symbol: Trading symbol (e.g., TATSILV, RELIANCE)
            series: Series type (default: EQ for equity)
            market_type: Market type (default: N for NSE)

        Returns:
            NSEQuote with current market data
        """
        self._init_session()

        params = {
            "functionName": "getSymbolData",
            "marketType": market_type,
            "series": series,
            "symbol": symbol.upper(),
        }

        try:
            response = self._client.get(self.QUOTE_API, params=params)

            if response.status_code != 200:
                raise NSEError(f"NSE API returned {response.status_code}")

            data = response.json()

            if not data.get("equityResponse"):
                raise NSEError(f"No data found for symbol: {symbol}")

            equity = data["equityResponse"][0]
            order_book = equity.get("orderBook", {})
            meta_data = equity.get("metaData", {})

            return NSEQuote(
                symbol=symbol.upper(),
                last_price=float(order_book.get("lastPrice", 0)),
                close_price=float(meta_data.get("closePrice", 0)),
                previous_close=float(meta_data.get("previousClose", 0)),
                open_price=float(meta_data.get("open", 0)),
                day_high=float(meta_data.get("dayHigh", 0)),
                day_low=float(meta_data.get("dayLow", 0)),
                change=float(meta_data.get("change", 0)),
                pchange=float(meta_data.get("pChange", 0)),
                company_name=meta_data.get("companyName", ""),
                isin=meta_data.get("isinCode", ""),
            )

        except httpx.RequestError as e:
            logger.error(f"NSE request error: {e}")
            raise NSEError(f"Failed to fetch quote: {e}")
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"NSE response parsing error: {e}")
            raise NSEError(f"Failed to parse quote response: {e}")

    def get_ltp(self, symbol: str, series: str = "EQ") -> float:
        """
        Get just the last traded price for a symbol.

        Args:
            symbol: Trading symbol
            series: Series type (default: EQ)

        Returns:
            Last traded price as float (uses closePrice for accuracy)
        """
        quote = self.get_quote(symbol, series)
        # Use close_price as it matches what Dhan shows
        # fall back to last_price if close_price is 0
        return quote.close_price if quote.close_price > 0 else quote.last_price

    def get_ltp_batch(self, symbols: list[str]) -> dict[str, float]:
        """
        Get LTP for multiple symbols.

        Args:
            symbols: List of trading symbols

        Returns:
            Dict mapping symbol to LTP
        """
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = self.get_ltp(symbol)
            except NSEError as e:
                logger.warning(f"Failed to get LTP for {symbol}: {e}")
                result[symbol] = 0.0
        return result

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get_etf_data(self) -> list[ETFData]:
        """
        Get all ETF data from NSE including NAV for discount/premium calculation.

        Returns:
            List of ETFData with discount/premium calculated
        """
        self._init_session()

        try:
            # Fetch ETF data from NSE API
            response = self._client.get("/api/etf")

            if response.status_code != 200:
                raise NSEError(f"NSE ETF API returned {response.status_code}")

            data = response.json()
            etf_list = data.get("data", [])

            result = []
            for etf in etf_list:
                try:
                    ltp = float(etf.get("ltP", 0) or 0)
                    nav = float(etf.get("nav", 0) or 0)

                    # Calculate discount/premium percentage
                    # Negative = discount (good to buy), Positive = premium (avoid)
                    if nav > 0:
                        discount_premium = ((ltp - nav) / nav) * 100
                    else:
                        discount_premium = 0

                    # Parse volume - can be string with commas or int
                    qty_raw = etf.get("qty", "0")
                    if isinstance(qty_raw, str):
                        qty_raw = qty_raw.replace(",", "")
                    volume = int(float(qty_raw) if qty_raw else 0)

                    # Parse turnover (traded value) - convert from raw value to Crores
                    trd_val_raw = etf.get("trdVal", 0)
                    if isinstance(trd_val_raw, str):
                        trd_val_raw = trd_val_raw.replace(",", "")
                    # Convert to Cr
                    turnover = float(trd_val_raw) / \
                        10000000 if trd_val_raw else 0

                    result.append(ETFData(
                        symbol=etf.get("symbol", ""),
                        underlying=etf.get("assets", "") or etf.get(
                            "underlying", ""),
                        ltp=ltp,
                        nav=nav,
                        change=float(etf.get("chn", 0) or 0),
                        pchange=float(etf.get("per", 0) or 0),
                        volume=volume,
                        turnover=round(turnover, 2),
                        week52_high=float(etf.get("wkhi", 0) or 0),
                        week52_low=float(etf.get("wklo", 0) or 0),
                        discount_premium=round(discount_premium, 2),
                        isin=etf.get("meta", {}).get(
                            "isin", "") or etf.get("isinCode", ""),
                    ))
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(
                        f"Failed to parse ETF: {etf.get('symbol', 'unknown')}: {e}")
                    continue

            return result

        except httpx.RequestError as e:
            logger.error(f"NSE ETF request error: {e}")
            raise NSEError(f"Failed to fetch ETF data: {e}")
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"NSE ETF response parsing error: {e}")
            raise NSEError(f"Failed to parse ETF response: {e}")

    def get_best_etfs(self, min_discount: float = -5.0, max_results: int = 20) -> list[ETFData]:
        """
        Get ETFs trading at a discount to NAV (good buy opportunities).

        Args:
            min_discount: Minimum discount percentage (negative value, e.g., -5.0)
            max_results: Maximum number of results to return

        Returns:
            List of ETFs sorted by discount (best discounts first)
        """
        all_etfs = self.get_etf_data()

        # Filter ETFs with valid NAV and trading at discount
        discounted = [
            etf for etf in all_etfs
            if etf.nav > 0 and etf.ltp > 0 and etf.discount_premium <= min_discount
        ]

        # Sort by discount (most negative first = best discount)
        discounted.sort(key=lambda x: x.discount_premium)

        return discounted[:max_results]
