"""
Dhan Tracker FastAPI Server

A FastAPI server with scheduled portfolio protection.
Designed for deployment on Azure App Service.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add src to path - MUST be before dhan_tracker imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from dhan_tracker.client import DhanClient, DhanAPIError
from dhan_tracker.config import DhanConfig
from dhan_tracker.protection import PortfolioProtector, ProtectionConfig
from dhan_tracker.nse_client import NSEClient, NSEError, ETFData


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Indian timezone for market hours
IST = pytz.timezone("Asia/Kolkata")

# Scheduler instance
scheduler = AsyncIOScheduler(timezone=IST)

# Global state for tracking last run
last_protection_run: Optional[datetime] = None
last_protection_result: Optional[dict] = None
last_amo_run: Optional[datetime] = None
last_amo_result: Optional[dict] = None

# Load APP_PASSWORD from config


def get_app_password() -> str:
    """Get the app password from environment or config file."""
    # Try environment first
    password = os.getenv("APP_PASSWORD")
    if password:
        return password

    # Try loading from config file (for local development)
    try:
        DhanConfig.load()  # This loads from env vars or .env file
        password = os.getenv("APP_PASSWORD")
        if password:
            return password
    except Exception:
        pass

    # Default password (should be changed in production!)
    return "changeme"


APP_PASSWORD = get_app_password()
logger.info(f"App password configured (length: {len(APP_PASSWORD)})")


def run_daily_protection():
    """
    Run daily portfolio protection.
    This is called by the scheduler at market open.
    """
    global last_protection_run, last_protection_result

    logger.info("=" * 60)
    logger.info("SCHEDULED PROTECTION RUN STARTED")
    logger.info("=" * 60)

    try:
        config = DhanConfig.load()
        client = DhanClient(config)

        protection_config = ProtectionConfig(
            stop_loss_percent=config.default_stop_loss_percent,
        )

        protector = PortfolioProtector(client, protection_config)

        # Force replace existing orders with new LTP-based ones
        results = protector.protect_portfolio(force=True)

        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count

        last_protection_run = datetime.now(IST)
        last_protection_result = {
            "status": "success",
            "timestamp": last_protection_run.isoformat(),
            "total_holdings": len(results),
            "protected": success_count,
            "failed": fail_count,
            "details": [
                {
                    "symbol": r.holding.trading_symbol,
                    "quantity": r.holding.available_qty,
                    "ltp": r.ltp,
                    "stop_loss": r.stop_loss_price,
                    "target": r.target_price,
                    "success": r.success,
                    "message": r.message,
                }
                for r in results
            ],
        }

        logger.info(
            f"Protection completed: {success_count}/{len(results)} holdings protected")

    except Exception as e:
        logger.error(f"Protection run failed: {e}")
        last_protection_run = datetime.now(IST)
        last_protection_result = {
            "status": "error",
            "timestamp": last_protection_run.isoformat(),
            "error": str(e),
        }


def run_amo_protection():
    """
    Run AMO (After Market Order) protection.
    Called before market open to place SL orders that activate at open.
    Protects against gap-down scenarios.
    """
    global last_amo_run, last_amo_result

    logger.info("=" * 60)
    logger.info("SCHEDULED AMO PROTECTION RUN STARTED")
    logger.info("=" * 60)

    try:
        config = DhanConfig.load()
        client = DhanClient(config)

        protection_config = ProtectionConfig(
            stop_loss_percent=config.default_stop_loss_percent,
        )

        protector = PortfolioProtector(client, protection_config)

        # Place AMO SL orders that will be active at market open
        results = protector.protect_portfolio_amo(amo_time="OPEN")

        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count

        last_amo_run = datetime.now(IST)
        last_amo_result = {
            "status": "success",
            "timestamp": last_amo_run.isoformat(),
            "total_holdings": len(results),
            "protected": success_count,
            "failed": fail_count,
            "details": [
                {
                    "symbol": r.holding.trading_symbol,
                    "quantity": r.holding.available_qty,
                    "ltp": r.ltp,
                    "stop_loss": r.stop_loss_price,
                    "success": r.success,
                    "message": r.message,
                }
                for r in results
            ],
        }

        logger.info(
            f"AMO Protection completed: {success_count}/{len(results)} holdings protected")

    except Exception as e:
        logger.error(f"AMO Protection run failed: {e}")
        last_amo_run = datetime.now(IST)
        last_amo_result = {
            "status": "error",
            "timestamp": last_amo_run.isoformat(),
            "error": str(e),
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage scheduler lifecycle."""
    # Schedule AMO protection at 8:30 AM IST (before market opens)
    # This places SL orders that will be active from market open (9:15 AM)
    scheduler.add_job(
        run_amo_protection,
        CronTrigger(hour=8, minute=30, timezone=IST),
        id="amo_protection",
        name="Pre-Market AMO Protection",
        replace_existing=True,
    )

    # Schedule Super Order protection at 9:20 AM IST (after market opens at 9:15)
    # This can add target + trailing SL during market hours
    scheduler.add_job(
        run_daily_protection,
        CronTrigger(hour=9, minute=20, timezone=IST),
        id="daily_protection",
        name="Daily Portfolio Protection (Super Orders)",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started:")
    logger.info("  - AMO Protection: 8:30 AM IST (pre-market SL orders)")
    logger.info("  - Daily Protection: 9:20 AM IST (Super Orders with target)")

    yield

    scheduler.shutdown()
    logger.info("Scheduler stopped")


# Create FastAPI app
app = FastAPI(
    title="Dhan Portfolio Tracker",
    description="Portfolio tracking and protection with DDPI super orders",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)


# Password verification dependency
async def verify_password(request: Request):
    """Verify password from X-Password header."""
    password = request.headers.get("X-Password", "")
    if password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    return True


# Pydantic models for API responses
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    scheduler_running: bool
    next_protection_run: Optional[str] = None
    config_loaded: Optional[bool] = None
    config_warning: Optional[str] = None


class HoldingResponse(BaseModel):
    symbol: str
    quantity: int
    avg_cost: float
    ltp: float
    invested: float
    current_value: float
    pnl: float
    pnl_percent: float


class PortfolioResponse(BaseModel):
    holdings: list[HoldingResponse]
    total_invested: float
    total_current: float
    total_pnl: float
    total_pnl_percent: float


class ProtectionStatusResponse(BaseModel):
    total_holdings: int
    protected_count: int
    unprotected_count: int
    total_value: float
    protected_value: float
    protection_percent: float
    last_run: Optional[str] = None
    last_result: Optional[dict] = None


class ProtectionRunResponse(BaseModel):
    status: str
    message: str
    timestamp: str
    results: Optional[list[dict]] = None


# Static files directory
STATIC_DIR = Path(__file__).parent / "static"


# Root route - serve UI
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the main UI."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file, media_type="text/html")
    return HTMLResponse("<h1>Dhan Tracker</h1><p>UI not found. Check static/index.html</p>")


# Health check (no password required)
@app.get("/health", response_model=HealthResponse)
async def health():
    """
    Health check endpoint for load balancers and monitoring.
    No password required - checks if server and API services are working.
    """
    health_status = {
        "status": "ok",
        "timestamp": datetime.now(IST).isoformat(),
        "scheduler_running": scheduler.running,
    }
    
    # Check if next protection run is scheduled
    jobs = scheduler.get_jobs()
    if jobs:
        next_run_times = [job.next_run_time for job in jobs if job.next_run_time]
        if next_run_times:
            health_status["next_protection_run"] = min(next_run_times).isoformat()
    
    # Quick config file existence check (without loading full config)
    # This is fast and doesn't involve network calls
    try:
        from dhan_tracker.config import get_config_file
        
        if get_config_file() is not None:
            health_status["config_loaded"] = True
        else:
            health_status["config_loaded"] = False
            health_status["config_warning"] = "Config file not found"
    except Exception as e:
        # Config check failures are warnings, not critical errors
        # Log the detailed error but return a generic message
        logger.warning(f"Health check config validation failed: {e}")
        health_status["config_loaded"] = False
        health_status["config_warning"] = "Config check failed"
    
    return health_status


# API Endpoints (password protected)

@app.get("/api/holdings", response_model=PortfolioResponse, dependencies=[Depends(verify_password)])
async def get_holdings():
    """Get current portfolio holdings with LTP from NSE."""
    try:
        config = DhanConfig.load()
        client = DhanClient(config)
        holdings = client.get_holdings()

        if not holdings:
            return PortfolioResponse(
                holdings=[],
                total_invested=0,
                total_current=0,
                total_pnl=0,
                total_pnl_percent=0,
            )

        # Fetch LTP from NSE
        ltp_map = {}
        with NSEClient() as nse:
            for h in holdings:
                if h.total_qty > 0:
                    try:
                        ltp_map[h.security_id] = nse.get_ltp(h.trading_symbol)
                    except NSEError:
                        ltp_map[h.security_id] = h.avg_cost_price

        holding_responses = []
        total_invested = 0
        total_current = 0

        for h in holdings:
            if h.total_qty <= 0:
                continue

            invested = h.total_qty * h.avg_cost_price
            ltp = ltp_map.get(h.security_id, h.avg_cost_price)
            current = h.total_qty * ltp
            pnl = current - invested
            pnl_pct = (pnl / invested * 100) if invested > 0 else 0

            total_invested += invested
            total_current += current

            holding_responses.append(HoldingResponse(
                symbol=h.trading_symbol,
                quantity=h.total_qty,
                avg_cost=h.avg_cost_price,
                ltp=ltp,
                invested=round(invested, 2),
                current_value=round(current, 2),
                pnl=round(pnl, 2),
                pnl_percent=round(pnl_pct, 2),
            ))

        total_pnl = total_current - total_invested
        total_pnl_pct = (total_pnl / total_invested *
                         100) if total_invested > 0 else 0

        return PortfolioResponse(
            holdings=holding_responses,
            total_invested=round(total_invested, 2),
            total_current=round(total_current, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_percent=round(total_pnl_pct, 2),
        )

    except DhanAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching holdings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/protection/status", response_model=ProtectionStatusResponse, dependencies=[Depends(verify_password)])
async def get_protection_status():
    """Get current protection status."""
    try:
        config = DhanConfig.load()
        client = DhanClient(config)
        protection_config = ProtectionConfig(
            stop_loss_percent=config.default_stop_loss_percent,
        )

        protector = PortfolioProtector(client, protection_config)
        summary = protector.get_protection_summary()

        return ProtectionStatusResponse(
            total_holdings=summary["total_holdings"],
            protected_count=summary["protected_count"],
            unprotected_count=summary["unprotected_count"],
            total_value=round(summary["total_value"], 2),
            protected_value=round(summary["protected_value"], 2),
            protection_percent=round(summary["protection_percent"], 2),
            last_run=last_protection_run.isoformat() if last_protection_run else None,
            last_result=last_protection_result,
        )

    except Exception as e:
        logger.error(f"Error fetching protection status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protection/run", response_model=ProtectionRunResponse, dependencies=[Depends(verify_password)])
async def run_protection(force: bool = True, background_tasks: BackgroundTasks = None):
    """
    Manually trigger portfolio protection.

    Args:
        force: If True, replace existing orders with new ones (default: True)
    """
    global last_protection_run, last_protection_result

    try:
        config = DhanConfig.load()
        client = DhanClient(config)
        protection_config = ProtectionConfig(
            stop_loss_percent=config.default_stop_loss_percent,
        )

        protector = PortfolioProtector(client, protection_config)
        results = protector.protect_portfolio(force=force)

        success_count = sum(1 for r in results if r.success)

        last_protection_run = datetime.now(IST)
        result_details = [
            {
                "symbol": r.holding.trading_symbol,
                "quantity": r.holding.available_qty,
                "ltp": r.ltp,
                "stop_loss": r.stop_loss_price,
                "target": r.target_price,
                "success": r.success,
                "message": r.message,
            }
            for r in results
        ]

        last_protection_result = {
            "status": "success",
            "timestamp": last_protection_run.isoformat(),
            "protected": success_count,
            "total": len(results),
            "details": result_details,
        }

        return ProtectionRunResponse(
            status="success",
            message=f"Protected {success_count}/{len(results)} holdings",
            timestamp=last_protection_run.isoformat(),
            results=result_details,
        )

    except DhanAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error running protection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protection/cancel", dependencies=[Depends(verify_password)])
async def cancel_protection():
    """Cancel all existing protection orders."""
    try:
        config = DhanConfig.load()
        client = DhanClient(config)
        protection_config = ProtectionConfig()

        protector = PortfolioProtector(client, protection_config)
        holdings = client.get_holdings()
        cancelled = protector.cancel_existing_orders(holdings)

        return {
            "status": "success",
            "message": f"Cancelled {cancelled} protection orders",
            "cancelled_count": cancelled,
        }

    except DhanAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error cancelling orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/protection/run-amo", response_model=ProtectionRunResponse, dependencies=[Depends(verify_password)])
async def run_amo_protection_api(amo_time: str = "OPEN"):
    """
    Manually trigger AMO (After Market Order) protection.

    Place SL-M orders as AMO that will be active from market open.
    Use when market is closed to ensure protection from first trade.

    Args:
        amo_time: When to inject orders:
            - PRE_OPEN: At 9:00 AM pre-open session
            - OPEN: At 9:15 AM market open (default)
            - OPEN_30: 30 mins after open
            - OPEN_60: 60 mins after open
    """
    global last_amo_run, last_amo_result

    # Validate amo_time
    valid_times = ["PRE_OPEN", "OPEN", "OPEN_30", "OPEN_60"]
    if amo_time not in valid_times:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid amo_time. Must be one of: {valid_times}",
        )

    try:
        config = DhanConfig.load()
        client = DhanClient(config)
        protection_config = ProtectionConfig(
            stop_loss_percent=config.default_stop_loss_percent,
        )

        protector = PortfolioProtector(client, protection_config)
        results = protector.protect_portfolio_amo(amo_time=amo_time)

        success_count = sum(1 for r in results if r.success)

        last_amo_run = datetime.now(IST)
        result_details = [
            {
                "symbol": r.holding.trading_symbol,
                "quantity": r.holding.available_qty,
                "ltp": r.ltp,
                "stop_loss": r.stop_loss_price,
                "success": r.success,
                "message": r.message,
            }
            for r in results
        ]

        last_amo_result = {
            "status": "success",
            "timestamp": last_amo_run.isoformat(),
            "amo_time": amo_time,
            "protected": success_count,
            "total": len(results),
            "details": result_details,
        }

        return ProtectionRunResponse(
            status="success",
            message=f"AMO protected {success_count}/{len(results)} holdings (inject at {amo_time})",
            timestamp=last_amo_run.isoformat(),
            results=result_details,
        )

    except DhanAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error running AMO protection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders", dependencies=[Depends(verify_password)])
async def get_orders():
    """Get all super orders."""
    try:
        config = DhanConfig.load()
        client = DhanClient(config)
        orders = client.get_super_orders()

        return {
            "count": len(orders),
            "orders": [
                {
                    "order_id": o.order_id,
                    "symbol": o.trading_symbol,
                    "quantity": o.quantity,
                    "transaction_type": o.transaction_type,
                    "status": o.order_status,
                    "stop_loss": o.stop_loss_leg.price if o.stop_loss_leg else None,
                    "target": o.target_leg.price if o.target_leg else None,
                }
                for o in orders
            ],
        }

    except DhanAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders/regular", dependencies=[Depends(verify_password)])
async def get_regular_orders():
    """Get all regular orders (including AMO orders)."""
    try:
        config = DhanConfig.load()
        client = DhanClient(config)
        orders = client.get_orders()

        return {
            "count": len(orders),
            "orders": orders,
        }

    except DhanAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching regular orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scheduler/status", dependencies=[Depends(verify_password)])
async def scheduler_status():
    """Get scheduler status and scheduled jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })

    return {
        "running": scheduler.running,
        "jobs": jobs,
        "timezone": str(IST),
    }


@app.post("/api/scheduler/trigger", dependencies=[Depends(verify_password)])
async def trigger_scheduled_job(job_type: str = "super"):
    """
    Manually trigger a scheduled protection job.

    Args:
        job_type: 'super' for Super Orders, 'amo' for AMO orders
    """
    if job_type == "amo":
        run_amo_protection()
        return {
            "status": "triggered",
            "job": "amo_protection",
            "result": last_amo_result,
        }
    else:
        run_daily_protection()
        return {
            "status": "triggered",
            "job": "daily_protection",
            "result": last_protection_result,
        }


# ETF Endpoints

@app.get("/api/etf", dependencies=[Depends(verify_password)])
async def get_all_etfs():
    """
    Get all NSE ETFs with LTP, NAV, and discount/premium calculation.

    Returns all ETFs sorted by discount (best buy opportunities first).
    Negative discount = trading below NAV (good to buy).
    Positive discount = trading above NAV (premium - avoid).
    """
    try:
        with NSEClient() as nse:
            etfs = nse.get_etf_data()

        # Sort by discount (most negative first = best discount)
        etfs.sort(key=lambda x: x.discount_premium)

        return {
            "count": len(etfs),
            "etfs": [
                {
                    "symbol": e.symbol,
                    "underlying": e.underlying,
                    "ltp": e.ltp,
                    "nav": e.nav,
                    "discount_premium": e.discount_premium,
                    "change": e.change,
                    "pchange": e.pchange,
                    "volume": e.volume,
                    "turnover": e.turnover,
                    "week52_high": e.week52_high,
                    "week52_low": e.week52_low,
                    "isin": e.isin,
                }
                for e in etfs
            ],
        }

    except NSEError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching ETF data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/etf/best", dependencies=[Depends(verify_password)])
async def get_best_etfs(min_discount: float = 0, max_results: int = 50):
    """
    Get ETFs trading at a discount to NAV (best buy opportunities).

    Args:
        min_discount: Filter ETFs with discount <= this value (default: 0 = any discount)
        max_results: Maximum number of results (default: 50)

    Returns ETFs sorted by discount percentage (biggest discounts first).
    """
    try:
        with NSEClient() as nse:
            etfs = nse.get_etf_data()

        # Filter and sort by discount
        discounted = [
            e for e in etfs
            if e.nav > 0 and e.ltp > 0 and e.discount_premium <= min_discount
        ]
        discounted.sort(key=lambda x: x.discount_premium)

        return {
            "count": len(discounted[:max_results]),
            "total_available": len(discounted),
            "filter": {"min_discount": min_discount},
            "etfs": [
                {
                    "symbol": e.symbol,
                    "underlying": e.underlying,
                    "ltp": e.ltp,
                    "nav": e.nav,
                    "discount_premium": e.discount_premium,
                    "discount_amount": round(e.nav - e.ltp, 2),
                    "change": e.change,
                    "pchange": e.pchange,
                    "volume": e.volume,
                    "week52_high": e.week52_high,
                    "week52_low": e.week52_low,
                }
                for e in discounted[:max_results]
            ],
        }

    except NSEError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching best ETFs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BuyOrderRequest(BaseModel):
    """Request to buy an ETF."""
    symbol: str
    quantity: int
    order_type: str = "MARKET"  # MARKET or LIMIT
    price: Optional[float] = None  # Required for LIMIT orders


@app.post("/api/etf/buy", dependencies=[Depends(verify_password)])
async def buy_etf(order: BuyOrderRequest):
    """
    Place a buy order for an ETF.

    Args:
        symbol: ETF trading symbol
        quantity: Number of units to buy
        order_type: MARKET or LIMIT
        price: Price for LIMIT orders
    """
    try:
        config = DhanConfig.load()
        client = DhanClient(config)

        # First, get the security_id for the symbol
        # We'll need to look it up from existing holdings or search
        # For now, let's try to use the trading symbol directly

        # Place the order using Dhan API
        order_params = {
            "dhanClientId": config.client_id,
            "transactionType": "BUY",
            "exchangeSegment": "NSE_EQ",
            "productType": "CNC",  # Cash and Carry for ETF delivery
            "orderType": order.order_type,
            "quantity": order.quantity,
            "tradingSymbol": order.symbol,
            "validity": "DAY",
        }

        if order.order_type == "LIMIT":
            if not order.price:
                raise HTTPException(
                    status_code=400, detail="Price required for LIMIT orders")
            order_params["price"] = order.price
        else:
            order_params["price"] = 0  # Market order

        # Call Dhan API to place order
        response = client._request("POST", "/v2/orders", json=order_params)

        return {
            "status": "success",
            "message": f"Buy order placed for {order.quantity} units of {order.symbol}",
            "order_id": response.get("orderId"),
            "order_status": response.get("orderStatus"),
        }

    except DhanAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
    except Exception as e:
        logger.error(f"Error placing ETF buy order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Serve ETF page
@app.get("/etf", response_class=HTMLResponse)
async def serve_etf_page():
    """Serve the ETF recommendations page."""
    etf_file = STATIC_DIR / "etf.html"
    if etf_file.exists():
        return FileResponse(etf_file, media_type="text/html")
    return HTMLResponse("<h1>ETF Page Not Found</h1><p>Check static/etf.html</p>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
