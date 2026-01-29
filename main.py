"""
Dhan Tracker - Portfolio tracking and protection CLI.

A tool to track your Dhan portfolio holdings and place protective
super orders with stop-loss to protect against market falls.
"""

from dhan_tracker.nse_client import NSEClient, NSEError
from dhan_tracker.config import DhanConfig, create_sample_config, PROJECT_ENV_FILE
from dhan_tracker.client import DhanClient, DhanAPIError
from dhan_tracker.protection import PortfolioProtector, ProtectionConfig, run_daily_protection
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent / "src"))


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def format_currency(value: float) -> str:
    """Format value as Indian Rupees."""
    return f"₹{value:,.2f}"


def print_holdings(client: DhanClient, show_ltp: bool = False) -> None:
    """Print portfolio holdings in a table format."""
    holdings = client.get_holdings()

    if not holdings:
        print("\n📊 No holdings found in your portfolio.")
        return

    # Fetch LTP from NSE if requested
    ltp_map = {}
    if show_ltp:
        with NSEClient() as nse:
            for h in holdings:
                if h.total_qty > 0:
                    try:
                        ltp_map[h.security_id] = nse.get_ltp(h.trading_symbol)
                    except NSEError as e:
                        logger.warning(
                            f"Failed to get LTP for {h.trading_symbol}: {e}")
                        ltp_map[h.security_id] = h.avg_cost_price

    print("\n" + "=" * 100)
    print("📊 PORTFOLIO HOLDINGS")
    print("=" * 100)

    total_invested = 0
    total_current = 0
    total_pnl = 0

    if show_ltp:
        print(f"{'Symbol':<12} {'Qty':>6} {'Avg Cost':>10} {'LTP':>10} {'Invested':>12} {'Current':>12} {'P&L':>12} {'%':>7}")
    else:
        print(
            f"{'Symbol':<15} {'Qty':>8} {'Avg Cost':>12} {'Value':>14} {'Available':>10}")
    print("-" * 100)

    for h in holdings:
        if h.total_qty <= 0:
            continue

        invested = h.total_qty * h.avg_cost_price
        total_invested += invested

        if show_ltp:
            ltp = ltp_map.get(h.security_id, h.avg_cost_price)
            current = h.total_qty * ltp
            pnl = current - invested
            pnl_pct = (pnl / invested * 100) if invested > 0 else 0
            total_current += current
            total_pnl += pnl

            pnl_str = f"+{format_currency(pnl)}" if pnl >= 0 else format_currency(pnl)
            pct_str = f"+{pnl_pct:.1f}%" if pnl_pct >= 0 else f"{pnl_pct:.1f}%"

            print(
                f"{h.trading_symbol:<12} "
                f"{h.total_qty:>6} "
                f"{format_currency(h.avg_cost_price):>10} "
                f"{format_currency(ltp):>10} "
                f"{format_currency(invested):>12} "
                f"{format_currency(current):>12} "
                f"{pnl_str:>12} "
                f"{pct_str:>7}"
            )
        else:
            print(
                f"{h.trading_symbol:<15} "
                f"{h.total_qty:>8} "
                f"{format_currency(h.avg_cost_price):>12} "
                f"{format_currency(invested):>14} "
                f"{h.available_qty:>10}"
            )

    print("-" * 100)
    if show_ltp:
        total_pnl_str = f"+{format_currency(total_pnl)}" if total_pnl >= 0 else format_currency(
            total_pnl)
        total_pct = (total_pnl / total_invested *
                     100) if total_invested > 0 else 0
        total_pct_str = f"+{total_pct:.1f}%" if total_pct >= 0 else f"{total_pct:.1f}%"
        print(f"{'TOTAL':<12} {'':<6} {'':<10} {'':<10} {format_currency(total_invested):>12} {format_currency(total_current):>12} {total_pnl_str:>12} {total_pct_str:>7}")
    else:
        print(f"{'Total Value:':<36} {format_currency(total_invested):>14}")
    print("=" * 100)


def print_positions(client: DhanClient) -> None:
    """Print open positions."""
    positions = client.get_positions()

    if not positions:
        print("\n📈 No open positions.")
        return

    print("\n" + "=" * 80)
    print("📈 OPEN POSITIONS")
    print("=" * 80)

    print(f"{'Symbol':<15} {'Type':<6} {'Qty':>8} {'Buy Avg':>12} {'P&L':>14}")
    print("-" * 80)

    total_pnl = 0

    for p in positions:
        if p.net_qty == 0:
            continue

        pnl = p.unrealized_profit
        total_pnl += pnl
        pnl_str = f"+{format_currency(pnl)}" if pnl >= 0 else format_currency(pnl)

        print(
            f"{p.trading_symbol:<15} "
            f"{p.position_type:<6} "
            f"{p.net_qty:>8} "
            f"{format_currency(p.buy_avg):>12} "
            f"{pnl_str:>14}"
        )

    print("-" * 80)
    pnl_str = f"+{format_currency(total_pnl)}" if total_pnl >= 0 else format_currency(
        total_pnl)
    print(f"{'Total P&L:':<36} {pnl_str:>14}")
    print("=" * 80)


def print_super_orders(client: DhanClient) -> None:
    """Print all super orders."""
    orders = client.get_super_orders()

    if not orders:
        print("\n🛡️  No super orders found.")
        return

    print("\n" + "=" * 90)
    print("🛡️  SUPER ORDERS (Protection Orders)")
    print("=" * 90)

    print(f"{'Symbol':<15} {'Type':<5} {'Qty':>6} {'Status':<12} {'SL Price':>10} {'Target':>10} {'Order ID':<15}")
    print("-" * 90)

    for o in orders:
        sl_price = ""
        target_price = ""

        if o.stop_loss_leg:
            sl_price = format_currency(o.stop_loss_leg.price)
        if o.target_leg:
            target_price = format_currency(o.target_leg.price)

        print(
            f"{o.trading_symbol:<15} "
            f"{o.transaction_type:<5} "
            f"{o.quantity:>6} "
            f"{o.order_status:<12} "
            f"{sl_price:>10} "
            f"{target_price:>10} "
            f"{o.order_id:<15}"
        )

    print("=" * 90)


def print_protection_summary(client: DhanClient, config: ProtectionConfig) -> None:
    """Print portfolio protection summary with LTP-based values."""
    protector = PortfolioProtector(client, config)
    summary = protector.get_protection_summary()

    ltp_map = summary.get('ltp_map', {})
    protected_securities = summary.get('protected_securities', {})

    print("\n" + "=" * 80)
    print("🛡️  PROTECTION SUMMARY (based on current LTP)")
    print("=" * 80)

    print(f"Total Holdings:        {summary['total_holdings']}")
    print(f"Protected Holdings:    {summary['protected_count']}")
    print(f"Unprotected Holdings:  {summary['unprotected_count']}")
    print("-" * 80)
    print(f"Total Market Value:    {format_currency(summary['total_value'])}")
    print(
        f"Protected Value:       {format_currency(summary['protected_value'])}")
    print(
        f"Unprotected Value:     {format_currency(summary['unprotected_value'])}")
    print(f"Protection Coverage:   {summary['protection_percent']:.1f}%")
    print("-" * 80)
    print(f"Active Super Orders:   {len(summary['active_super_orders'])}")
    print("=" * 80)

    # Show protected holdings with their stop loss prices
    if summary['protected_holdings']:
        print("\n✅ Protected Holdings:")
        for h in summary['protected_holdings']:
            ltp = ltp_map.get(h.security_id, h.avg_cost_price)
            order = protected_securities.get(h.security_id)
            sl_price = order.stop_loss_leg.price if order and order.stop_loss_leg else 0
            value = h.available_qty * ltp
            print(
                f"   - {h.trading_symbol}: {h.available_qty} qty, "
                f"LTP={format_currency(ltp)}, SL={format_currency(sl_price)}"
            )

    if summary['unprotected_holdings']:
        print("\n⚠️  Unprotected Holdings:")
        for h in summary['unprotected_holdings']:
            ltp = ltp_map.get(h.security_id, h.avg_cost_price)
            value = h.available_qty * ltp
            suggested_sl = round(ltp * (1 - config.stop_loss_percent / 100), 2)
            print(
                f"   - {h.trading_symbol}: {h.available_qty} qty, "
                f"LTP={format_currency(ltp)}, Suggested SL={format_currency(suggested_sl)}"
            )


def run_protection(client: DhanClient, config: ProtectionConfig, force: bool = False) -> None:
    """Run portfolio protection."""
    print("\n" + "=" * 70)
    print("🛡️  RUNNING PORTFOLIO PROTECTION (DDPI Super Orders)")
    print("=" * 70)
    print(f"Stop Loss: {config.stop_loss_percent}% below current LTP")
    print(f"Target: {config.target_percent}% above current LTP")
    print(f"Trailing Jump: {config.trailing_jump}")
    print(
        f"Mode: {'Replace existing orders' if force else 'Keep existing orders'}")
    print("-" * 70)

    protector = PortfolioProtector(client, config)
    results = protector.protect_portfolio(force=force)

    if not results:
        print("No holdings to protect.")
        return

    success_count = 0
    fail_count = 0

    print(f"\n{'Symbol':<12} {'Qty':>6} {'LTP':>10} {'Stop Loss':>12} {'Target':>12} {'Status':<15}")
    print("-" * 70)

    for r in results:
        if r.success:
            success_count += 1
            status = f"✓ {r.message[:12]}"
            print(
                f"{r.holding.trading_symbol:<12} "
                f"{r.holding.available_qty:>6} "
                f"{format_currency(r.ltp):>10} "
                f"{format_currency(r.stop_loss_price):>12} "
                f"{format_currency(r.target_price):>12} "
                f"{status:<15}"
            )
        else:
            fail_count += 1
            print(
                f"{r.holding.trading_symbol:<12} "
                f"{r.holding.available_qty:>6} "
                f"{format_currency(r.ltp):>10} "
                f"{'--':>12} "
                f"{'--':>12} "
                f"✗ {r.message[:20]}"
            )

    print("-" * 70)
    print(f"Summary: {success_count} protected, {fail_count} failed")
    print("=" * 70)


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize configuration."""
    config_path = create_sample_config(in_project=True)
    print(f"\n✓ Sample configuration created at: {config_path}")
    print("\nPlease edit the .env file and add your:")
    print("  - DHAN_CLIENT_ID")
    print("\n⚠️  Add .env to your .gitignore to avoid committing secrets!")


def cmd_holdings(args: argparse.Namespace) -> None:
    """Show holdings command."""
    config = DhanConfig.from_file()
    with DhanClient(config) as client:
        print_holdings(client, show_ltp=args.ltp)


def cmd_positions(args: argparse.Namespace) -> None:
    """Show positions command."""
    config = DhanConfig.from_file()
    with DhanClient(config) as client:
        print_positions(client)


def cmd_orders(args: argparse.Namespace) -> None:
    """Show super orders command."""
    config = DhanConfig.from_file()
    with DhanClient(config) as client:
        print_super_orders(client)


def cmd_status(args: argparse.Namespace) -> None:
    """Show protection status command."""
    config = DhanConfig.from_file()
    protection_config = ProtectionConfig(
        stop_loss_from_high_percent=config.default_stop_loss_from_high_percent,
        stop_loss_percent=config.default_stop_loss_percent,
    )

    with DhanClient(config) as client:
        print_holdings(client, show_ltp=True)
        print_protection_summary(client, protection_config)


def cmd_protect(args: argparse.Namespace) -> None:
    """Run protection command."""
    config = DhanConfig.from_file()
    protection_config = ProtectionConfig(
        stop_loss_from_high_percent=args.stop_loss_from_high or config.default_stop_loss_from_high_percent,
        stop_loss_percent=args.stop_loss or config.default_stop_loss_percent,
        target_percent=args.target or 20.0,
        trailing_jump=args.trail or 0.0,
    )

    with DhanClient(config) as client:
        run_protection(client, protection_config, force=args.force)


def cmd_cancel(args: argparse.Namespace) -> None:
    """Cancel super orders command."""
    config = DhanConfig.from_file()

    with DhanClient(config) as client:
        if args.order_id:
            # Cancel specific order
            try:
                client.cancel_super_order(args.order_id)
                print(f"✓ Cancelled order: {args.order_id}")
            except DhanAPIError as e:
                print(f"✗ Failed to cancel order: {e.message}")
        else:
            # Cancel all super orders
            orders = client.get_super_orders()
            cancelled = 0
            for order in orders:
                if order.order_status in ["PENDING", "TRANSIT"]:
                    try:
                        client.cancel_super_order(order.order_id)
                        print(
                            f"✓ Cancelled {order.trading_symbol} ({order.order_id})")
                        cancelled += 1
                    except DhanAPIError as e:
                        print(
                            f"✗ Failed to cancel {order.trading_symbol}: {e.message}")

            print(f"\nTotal cancelled: {cancelled}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Dhan Tracker - Portfolio tracking and protection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py init              # Create config file
  python main.py status            # Show holdings with LTP and protection status
  python main.py holdings          # Show all holdings
  python main.py holdings --ltp    # Show holdings with current LTP and P&L
  python main.py protect           # Place protective orders (keeps existing)
  python main.py protect --force   # Cancel old orders & place new ones
  python main.py protect --sl 3    # Place orders with 3% stop loss
  python main.py orders            # Show all super orders
  python main.py cancel            # Cancel all protection orders
        """
    )

    subparsers = parser.add_subparsers(
        dest="command", help="Available commands")

    # Init command
    init_parser = subparsers.add_parser(
        "init", help="Initialize configuration")
    init_parser.set_defaults(func=cmd_init)

    # Holdings command
    holdings_parser = subparsers.add_parser(
        "holdings", help="Show portfolio holdings")
    holdings_parser.add_argument(
        "--ltp",
        action="store_true",
        help="Show current LTP and P&L for each holding",
    )
    holdings_parser.set_defaults(func=cmd_holdings)

    # Positions command
    positions_parser = subparsers.add_parser(
        "positions", help="Show open positions")
    positions_parser.set_defaults(func=cmd_positions)

    # Orders command
    orders_parser = subparsers.add_parser("orders", help="Show super orders")
    orders_parser.set_defaults(func=cmd_orders)

    # Status command
    status_parser = subparsers.add_parser(
        "status", help="Show protection status with LTP")
    status_parser.set_defaults(func=cmd_status)

    # Protect command
    protect_parser = subparsers.add_parser(
        "protect", help="Place protective DDPI super orders")
    protect_parser.add_argument(
        "--sl-from-high", "--stop-loss-from-high",
        type=float,
        dest="stop_loss_from_high",
        help="Stop loss percentage below 52-week high (default: from config or 10%%)",
    )
    protect_parser.add_argument(
        "--sl", "--stop-loss",
        type=float,
        dest="stop_loss",
        help="Fallback stop loss percentage below LTP (default: from config or 5%%)",
    )
    protect_parser.add_argument(
        "--target",
        type=float,
        help="Target percentage above LTP (default: 20%%)",
    )
    protect_parser.add_argument(
        "--trail",
        type=float,
        help="Trailing stop loss jump (default: 0)",
    )
    protect_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing protective orders",
    )
    protect_parser.set_defaults(func=cmd_protect)

    # Cancel command
    cancel_parser = subparsers.add_parser("cancel", help="Cancel super orders")
    cancel_parser.add_argument(
        "--order-id",
        help="Specific order ID to cancel (cancels all if not specified)",
    )
    cancel_parser.set_defaults(func=cmd_cancel)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        args.func(args)
    except FileNotFoundError as e:
        print(f"\n❌ Configuration not found!")
        print(f"\nRun 'python main.py init' to create .env in your project folder")
        print(f"   Expected: {PROJECT_ENV_FILE}")
    except DhanAPIError as e:
        print(f"\n❌ API Error: {e.message}")
        if e.status_code:
            print(f"   Status Code: {e.status_code}")
    except Exception as e:
        logger.exception("Unexpected error")
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
