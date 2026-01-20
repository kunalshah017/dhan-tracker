"""Scheduler for daily portfolio protection."""

import logging
import sched
import time
from datetime import datetime, timedelta
from typing import Callable

from .client import DhanClient
from .config import DhanConfig
from .protection import PortfolioProtector, ProtectionConfig, run_daily_protection

logger = logging.getLogger(__name__)


# Indian market timings (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30


def is_market_day() -> bool:
    """Check if today is a market trading day (Mon-Fri)."""
    today = datetime.now()
    # 0 = Monday, 6 = Sunday
    return today.weekday() < 5


def get_next_market_open() -> datetime:
    """Get the next market opening time."""
    now = datetime.now()

    # Start with today's market open
    market_open = now.replace(
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0,
    )

    # If we've passed today's open, move to tomorrow
    if now >= market_open:
        market_open += timedelta(days=1)

    # Skip weekends
    while market_open.weekday() >= 5:  # Saturday or Sunday
        market_open += timedelta(days=1)

    return market_open


def schedule_daily_protection(
    config: DhanConfig,
    protection_config: ProtectionConfig | None = None,
    run_immediately: bool = False,
) -> None:
    """
    Schedule daily protection to run at market open.

    This function blocks and runs indefinitely.

    Args:
        config: Dhan API configuration
        protection_config: Protection settings
        run_immediately: If True, run protection immediately before scheduling
    """
    protection_config = protection_config or ProtectionConfig(
        stop_loss_percent=config.default_stop_loss_percent
    )

    def run_protection_job():
        """Execute the protection job."""
        try:
            logger.info("Starting scheduled protection run...")

            with DhanClient(config) as client:
                results = run_daily_protection(client, protection_config)

                success = sum(1 for r in results if r.success)
                failed = sum(1 for r in results if not r.success)

                logger.info(
                    f"Protection complete: {success} protected, {failed} failed")

        except Exception as e:
            logger.error(f"Protection run failed: {e}")

    # Run immediately if requested
    if run_immediately:
        logger.info("Running immediate protection...")
        run_protection_job()

    # Schedule loop
    scheduler = sched.scheduler(time.time, time.sleep)

    def schedule_next():
        """Schedule the next run."""
        next_run = get_next_market_open()
        delay = (next_run - datetime.now()).total_seconds()

        logger.info(f"Next protection run scheduled for: {next_run}")

        scheduler.enter(delay, 1, run_and_reschedule)

    def run_and_reschedule():
        """Run protection and schedule next run."""
        if is_market_day():
            run_protection_job()
        else:
            logger.info("Skipping - not a market day")

        schedule_next()

    # Start the schedule
    schedule_next()

    logger.info("Scheduler started. Press Ctrl+C to stop.")

    try:
        scheduler.run()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user.")


def run_once_at_market_open(
    config: DhanConfig,
    protection_config: ProtectionConfig | None = None,
) -> None:
    """
    Wait until market open and run protection once.

    Args:
        config: Dhan API configuration
        protection_config: Protection settings
    """
    protection_config = protection_config or ProtectionConfig(
        stop_loss_percent=config.default_stop_loss_percent
    )

    next_open = get_next_market_open()
    now = datetime.now()

    if next_open > now:
        wait_seconds = (next_open - now).total_seconds()
        logger.info(f"Waiting for market open at {next_open}...")
        logger.info(f"Sleeping for {wait_seconds / 3600:.1f} hours...")
        time.sleep(wait_seconds)

    if is_market_day():
        logger.info("Market is open! Running protection...")

        with DhanClient(config) as client:
            run_daily_protection(client, protection_config)
    else:
        logger.info("Today is not a market day.")
