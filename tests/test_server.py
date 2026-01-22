"""
Tests for Dhan Tracker FastAPI Server

Run with: pytest tests/test_server.py -v
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from fastapi.testclient import TestClient

# Mock the config before importing server
import sys
from pathlib import Path

# Add project root to path for server import
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Set test password before importing server
TEST_PASSWORD = "test_password_123"
os.environ["APP_PASSWORD"] = TEST_PASSWORD


@pytest.fixture
def auth_headers():
    """Return headers with valid password."""
    return {"X-Password": TEST_PASSWORD}


@pytest.fixture
def mock_config():
    """Create a mock DhanConfig."""
    config = Mock()
    config.access_token = "test_token"
    config.client_id = "test_client"
    config.base_url = "https://api.dhan.co/v2"
    config.default_stop_loss_percent = 5.0
    return config


@pytest.fixture
def mock_holding():
    """Create a mock Holding."""
    from dhan_tracker.models import Holding
    return Holding(
        security_id="12345",
        trading_symbol="TATSILV",
        exchange="NSE",
        isin="INF277KA1984",
        total_qty=160,
        dp_qty=160,
        t1_qty=0,
        available_qty=160,
        avg_cost_price=24.80,
        collateral_qty=0,
    )


@pytest.fixture
def mock_holdings_list(mock_holding):
    """Create a list of mock Holdings."""
    from dhan_tracker.models import Holding
    return [
        mock_holding,
        Holding(
            security_id="12346",
            trading_symbol="MON100",
            exchange="NSE",
            isin="INF247L01AP7",
            total_qty=3,
            dp_qty=3,
            t1_qty=0,
            available_qty=3,
            avg_cost_price=234.54,
            collateral_qty=0,
        ),
        Holding(
            security_id="12347",
            trading_symbol="GOLDCASE",
            exchange="NSE",
            isin="INF204KB14I2",
            total_qty=48,
            dp_qty=48,
            t1_qty=0,
            available_qty=48,
            avg_cost_price=20.82,
            collateral_qty=0,
        ),
    ]


@pytest.fixture
def mock_super_order():
    """Create a mock SuperOrder."""
    from dhan_tracker.models import SuperOrder, LegDetail
    return SuperOrder(
        dhan_client_id="1234567890",
        order_id="ORD123456",
        correlation_id="COR123",
        order_status="PENDING",
        transaction_type="SELL",
        exchange_segment="NSE_EQ",
        product_type="CNC",
        order_type="LIMIT",
        trading_symbol="TATSILV",
        security_id="12345",
        quantity=160,
        remaining_quantity=160,
        ltp=31.31,
        price=29.74,
        leg_name="STOP_LOSS_LEG",
        create_time="2026-01-21T09:20:00",
        update_time="2026-01-21T09:20:00",
        average_traded_price=0.0,
        filled_qty=0,
        leg_details=[
            LegDetail(
                order_id="LEG123",
                leg_name="STOP_LOSS_LEG",
                transaction_type="SELL",
                total_quantity=160,
                remaining_quantity=160,
                triggered_quantity=0,
                price=29.74,
                order_status="PENDING",
            )
        ],
    )


@pytest.fixture
def client(mock_config):
    """Create a test client with mocked dependencies."""
    with patch("server.DhanConfig") as MockConfig:
        MockConfig.from_file.return_value = mock_config

        # Import app after patching
        from server import app

        yield TestClient(app)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_root_health_check(self, client):
        """Test root endpoint returns HTML UI."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_simple_health_check(self, client):
        """Test /health endpoint for load balancers (no password required)."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "scheduler_running" in data

    def test_health_check_with_password(self, client, auth_headers):
        """Test /health endpoint also works with password (for backward compatibility)."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestHoldingsEndpoint:
    """Tests for /api/holdings endpoint."""

    def test_get_holdings_success(self, client, mock_config, mock_holdings_list, auth_headers):
        """Test successful holdings retrieval."""
        with patch("server.DhanConfig") as MockConfig, \
                patch("server.DhanClient") as MockClient, \
                patch("server.NSEClient") as MockNSE:

            MockConfig.from_file.return_value = mock_config

            mock_client_instance = Mock()
            mock_client_instance.get_holdings.return_value = mock_holdings_list
            MockClient.return_value = mock_client_instance

            # Mock NSE client
            mock_nse_instance = MagicMock()
            mock_nse_instance.get_ltp.side_effect = [31.31, 231.18, 23.76]
            mock_nse_instance.__enter__ = Mock(return_value=mock_nse_instance)
            mock_nse_instance.__exit__ = Mock(return_value=False)
            MockNSE.return_value = mock_nse_instance

            response = client.get("/api/holdings", headers=auth_headers)
            assert response.status_code == 200

            data = response.json()
            assert len(data["holdings"]) == 3
            assert data["total_invested"] > 0
            assert data["total_current"] > 0

    def test_get_holdings_empty(self, client, mock_config, auth_headers):
        """Test holdings when portfolio is empty."""
        with patch("server.DhanConfig") as MockConfig, \
                patch("server.DhanClient") as MockClient:

            MockConfig.from_file.return_value = mock_config

            mock_client_instance = Mock()
            mock_client_instance.get_holdings.return_value = []
            MockClient.return_value = mock_client_instance

            response = client.get("/api/holdings", headers=auth_headers)
            assert response.status_code == 200

            data = response.json()
            assert data["holdings"] == []
            assert data["total_invested"] == 0

    def test_get_holdings_api_error(self, client, mock_config, auth_headers):
        """Test holdings when API returns error."""
        with patch("server.DhanConfig") as MockConfig, \
                patch("server.DhanClient") as MockClient:

            MockConfig.from_file.return_value = mock_config

            from dhan_tracker.client import DhanAPIError
            mock_client_instance = Mock()
            mock_client_instance.get_holdings.side_effect = DhanAPIError(
                "API Error", 401)
            MockClient.return_value = mock_client_instance

            response = client.get("/api/holdings", headers=auth_headers)
            assert response.status_code == 401


class TestOrdersEndpoint:
    """Tests for /api/orders endpoint."""

    def test_get_orders_success(self, client, mock_config, mock_super_order, auth_headers):
        """Test successful orders retrieval."""
        with patch("server.DhanConfig") as MockConfig, \
                patch("server.DhanClient") as MockClient:

            MockConfig.from_file.return_value = mock_config

            mock_client_instance = Mock()
            mock_client_instance.get_super_orders.return_value = [
                mock_super_order]
            MockClient.return_value = mock_client_instance

            response = client.get("/api/orders", headers=auth_headers)
            assert response.status_code == 200

            data = response.json()
            assert data["count"] == 1
            assert len(data["orders"]) == 1
            assert data["orders"][0]["symbol"] == "TATSILV"
            # stop_loss_leg property finds the leg with leg_name == "STOP_LOSS_LEG"
            assert data["orders"][0]["stop_loss"] == 29.74

    def test_get_orders_empty(self, client, mock_config, auth_headers):
        """Test orders when none exist."""
        with patch("server.DhanConfig") as MockConfig, \
                patch("server.DhanClient") as MockClient:

            MockConfig.from_file.return_value = mock_config

            mock_client_instance = Mock()
            mock_client_instance.get_super_orders.return_value = []
            MockClient.return_value = mock_client_instance

            response = client.get("/api/orders", headers=auth_headers)
            assert response.status_code == 200

            data = response.json()
            assert data["count"] == 0
            assert data["orders"] == []


class TestProtectionEndpoints:
    """Tests for protection-related endpoints."""

    def test_get_protection_status(self, client, mock_config, mock_holdings_list, auth_headers):
        """Test protection status endpoint."""
        with patch("server.DhanConfig") as MockConfig, \
                patch("server.DhanClient") as MockClient, \
                patch("server.PortfolioProtector") as MockProtector:

            MockConfig.from_file.return_value = mock_config

            mock_protector_instance = Mock()
            mock_protector_instance.get_protection_summary.return_value = {
                "total_holdings": 3,
                "protected_count": 1,
                "unprotected_count": 2,
                "total_value": 6843.62,
                "protected_value": 5009.60,
                "unprotected_value": 1834.02,
                "protection_percent": 73.2,
                "active_super_orders": [],
                "protected_holdings": [],
                "unprotected_holdings": [],
            }
            MockProtector.return_value = mock_protector_instance

            response = client.get(
                "/api/protection/status", headers=auth_headers)
            assert response.status_code == 200

            data = response.json()
            assert data["total_holdings"] == 3
            assert data["protected_count"] == 1
            assert data["protection_percent"] == 73.2

    def test_run_protection_success(self, client, mock_config, mock_holding, auth_headers):
        """Test manual protection run."""
        with patch("server.DhanConfig") as MockConfig, \
                patch("server.DhanClient") as MockClient, \
                patch("server.PortfolioProtector") as MockProtector:

            MockConfig.from_file.return_value = mock_config

            from dhan_tracker.protection import ProtectionResult
            mock_result = ProtectionResult(
                holding=mock_holding,
                success=True,
                ltp=31.31,
                order_id="ORD123456",
                message="Order placed",
                stop_loss_price=29.74,
                target_price=37.57,
            )

            mock_protector_instance = Mock()
            mock_protector_instance.protect_portfolio.return_value = [
                mock_result]
            MockProtector.return_value = mock_protector_instance

            response = client.post(
                "/api/protection/run?force=true", headers=auth_headers)
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "success"
            assert "Protected 1/1 holdings" in data["message"]
            assert len(data["results"]) == 1

    def test_cancel_protection(self, client, mock_config, mock_holdings_list, auth_headers):
        """Test cancel protection orders."""
        with patch("server.DhanConfig") as MockConfig, \
                patch("server.DhanClient") as MockClient, \
                patch("server.PortfolioProtector") as MockProtector:

            MockConfig.from_file.return_value = mock_config

            mock_client_instance = Mock()
            mock_client_instance.get_holdings.return_value = mock_holdings_list
            MockClient.return_value = mock_client_instance

            mock_protector_instance = Mock()
            mock_protector_instance.cancel_existing_orders.return_value = 2
            MockProtector.return_value = mock_protector_instance

            response = client.post(
                "/api/protection/cancel", headers=auth_headers)
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "success"
            assert data["cancelled_count"] == 2


class TestSchedulerEndpoints:
    """Tests for scheduler-related endpoints."""

    def test_scheduler_status(self, client, auth_headers):
        """Test scheduler status endpoint."""
        response = client.get("/api/scheduler/status", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert "running" in data
        assert "jobs" in data
        assert data["timezone"] == "Asia/Kolkata"

    def test_scheduler_trigger(self, client, mock_config, auth_headers):
        """Test manual scheduler trigger."""
        with patch("server.DhanConfig") as MockConfig, \
                patch("server.DhanClient") as MockClient, \
                patch("server.PortfolioProtector") as MockProtector:

            MockConfig.from_file.return_value = mock_config

            mock_client_instance = Mock()
            mock_client_instance.get_holdings.return_value = []
            MockClient.return_value = mock_client_instance

            mock_protector_instance = Mock()
            mock_protector_instance.protect_portfolio.return_value = []
            MockProtector.return_value = mock_protector_instance

            response = client.post(
                "/api/scheduler/trigger", headers=auth_headers)
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "triggered"


class TestNSEClient:
    """Tests for NSE Client."""

    def test_get_quote_success(self):
        """Test successful quote fetch from NSE."""
        with patch("httpx.Client") as MockHttpClient:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "equityResponse": [{
                    "orderBook": {"lastPrice": 31.5},
                    "metaData": {
                        "closePrice": 31.31,
                        "previousClose": 29.0,
                        "open": 28.27,
                        "dayHigh": 32.35,
                        "dayLow": 28.27,
                        "change": 2.5,
                        "pChange": 8.62,
                        "companyName": "Tata Silver ETF",
                        "isinCode": "INF277KA1984",
                    }
                }]
            }

            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            MockHttpClient.return_value = mock_client_instance

            from dhan_tracker.nse_client import NSEClient

            nse = NSEClient()
            nse._initialized = True  # Skip session init
            nse._client = mock_client_instance

            quote = nse.get_quote("TATSILV")

            assert quote.symbol == "TATSILV"
            assert quote.close_price == 31.31
            assert quote.last_price == 31.5

    def test_get_ltp_uses_close_price(self):
        """Test that get_ltp returns closePrice (not lastPrice)."""
        with patch("httpx.Client") as MockHttpClient:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "equityResponse": [{
                    "orderBook": {"lastPrice": 31.5},
                    "metaData": {
                        "closePrice": 31.31,
                        "previousClose": 29.0,
                        "open": 28.27,
                        "dayHigh": 32.35,
                        "dayLow": 28.27,
                        "change": 2.5,
                        "pChange": 8.62,
                        "companyName": "Tata Silver ETF",
                        "isinCode": "INF277KA1984",
                    }
                }]
            }

            mock_client_instance = MagicMock()
            mock_client_instance.get.return_value = mock_response
            MockHttpClient.return_value = mock_client_instance

            from dhan_tracker.nse_client import NSEClient

            nse = NSEClient()
            nse._initialized = True
            nse._client = mock_client_instance

            ltp = nse.get_ltp("TATSILV")

            # Should use closePrice, not lastPrice
            assert ltp == 31.31


class TestProtectionLogic:
    """Tests for protection calculation logic."""

    def test_calculate_stop_loss_price(self, mock_config):
        """Test stop loss calculation."""
        from dhan_tracker.protection import ProtectionConfig

        config = ProtectionConfig(stop_loss_percent=5.0)

        # 5% below 100 = 95
        from dhan_tracker.protection import PortfolioProtector
        from dhan_tracker.client import DhanClient

        with patch.object(DhanClient, "__init__", lambda self, config: None):
            protector = PortfolioProtector.__new__(PortfolioProtector)
            protector.config = config

            assert protector.calculate_stop_loss_price(100.0) == 95.0
            assert protector.calculate_stop_loss_price(
                31.31) == 29.74  # 5% below

    def test_calculate_target_price(self, mock_config):
        """Test target price calculation."""
        from dhan_tracker.protection import ProtectionConfig

        config = ProtectionConfig(target_percent=20.0)

        from dhan_tracker.protection import PortfolioProtector
        from dhan_tracker.client import DhanClient

        with patch.object(DhanClient, "__init__", lambda self, config: None):
            protector = PortfolioProtector.__new__(PortfolioProtector)
            protector.config = config

            assert protector.calculate_target_price(100.0) == 120.0
            assert protector.calculate_target_price(
                31.31) == 37.57  # 20% above


class TestDhanClient:
    """Tests for Dhan API Client."""

    def test_get_holdings_success(self, mock_config):
        """Test successful holdings fetch."""
        with patch("httpx.Client") as MockHttpClient:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {
                    "securityId": "12345",
                    "tradingSymbol": "TATSILV",
                    "exchange": "NSE",
                    "isin": "INF277KA1984",
                    "totalQty": 160,
                    "availableQty": 160,
                    "avgCostPrice": 24.80,
                    "collateralQty": 0,
                }
            ]

            mock_client_instance = MagicMock()
            mock_client_instance.request.return_value = mock_response
            MockHttpClient.return_value = mock_client_instance

            from dhan_tracker.client import DhanClient

            client = DhanClient(mock_config)
            client._client = mock_client_instance

            holdings = client.get_holdings()

            assert len(holdings) == 1
            assert holdings[0].trading_symbol == "TATSILV"
            assert holdings[0].total_qty == 160

    def test_api_error_handling(self, mock_config):
        """Test API error handling."""
        with patch("httpx.Client") as MockHttpClient:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"errorMessage": "Invalid token"}
            mock_response.text = "Unauthorized"

            mock_client_instance = MagicMock()
            mock_client_instance.request.return_value = mock_response
            MockHttpClient.return_value = mock_client_instance

            from dhan_tracker.client import DhanClient, DhanAPIError

            client = DhanClient(mock_config)
            client._client = mock_client_instance

            with pytest.raises(DhanAPIError) as exc_info:
                client.get_holdings()

            assert exc_info.value.status_code == 401

    def test_auto_token_refresh_on_401(self, mock_config):
        """Test automatic token refresh on 401 error."""
        with patch("httpx.Client") as MockHttpClient, \
                patch("httpx.post") as mock_post:
            
            # First request returns 401
            mock_401_response = Mock()
            mock_401_response.status_code = 401
            mock_401_response.json.return_value = {"errorMessage": "Token expired"}
            mock_401_response.text = "Unauthorized"

            # Second request (after token refresh) returns success
            mock_success_response = Mock()
            mock_success_response.status_code = 200
            mock_success_response.json.return_value = [
                {
                    "securityId": "12345",
                    "tradingSymbol": "TATSILV",
                    "exchange": "NSE",
                    "isin": "INF277KA1984",
                    "totalQty": 160,
                    "availableQty": 160,
                    "avgCostPrice": 24.80,
                    "collateralQty": 0,
                }
            ]

            # Token refresh response
            mock_refresh_response = Mock()
            mock_refresh_response.status_code = 200
            mock_refresh_response.json.return_value = {"access_token": "new_token_123"}
            mock_post.return_value = mock_refresh_response

            # Mock client with proper headers dict
            mock_client_instance = MagicMock()
            mock_client_instance.headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "access-token": "old_token",
                "client-id": "test_client",
            }
            mock_client_instance.request.side_effect = [mock_401_response, mock_success_response]
            MockHttpClient.return_value = mock_client_instance

            from dhan_tracker.client import DhanClient

            client = DhanClient(mock_config)
            client._client = mock_client_instance

            # This should trigger token refresh and retry
            holdings = client.get_holdings()

            # Verify token was refreshed
            assert mock_post.called
            assert client.config.access_token == "new_token_123"
            assert client._client.headers["access-token"] == "new_token_123"
            
            # Verify the request was retried and succeeded
            assert len(holdings) == 1
            assert holdings[0].trading_symbol == "TATSILV"


# Integration test (requires real credentials)
class TestIntegration:
    """Integration tests - require real API credentials."""

    @pytest.mark.skip(reason="Requires real API credentials")
    def test_real_holdings_fetch(self):
        """Test with real Dhan API."""
        from dhan_tracker.config import DhanConfig
        from dhan_tracker.client import DhanClient

        config = DhanConfig.from_file()
        client = DhanClient(config)
        holdings = client.get_holdings()

        assert isinstance(holdings, list)

    @pytest.mark.skip(reason="Requires real API credentials")
    def test_real_nse_ltp(self):
        """Test with real NSE API."""
        from dhan_tracker.nse_client import NSEClient

        with NSEClient() as nse:
            ltp = nse.get_ltp("TATSILV")
            assert ltp > 0
