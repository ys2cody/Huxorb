"""
Live Trading Runner
===================
Start live trading with real KuCoin API.

CRITICAL SAFETY CHECKS:
- Uses DRY_RUN=true by default (set to false for real execution)
- Requires KUCOIN_TESTNET=false for production (default is sandbox)
- Validates API credentials before starting
- All trades pass through RuleGuard halal enforcement

Usage:
    # Dry run (logs only, no real orders)
    python scripts/live_trade.py

    # Load from custom .env file
    python scripts/live_trade.py --env config/.env

    # Test connection only
    python scripts/live_trade.py --test-connection

    # Run N cycles then exit (for testing)
    python scripts/live_trade.py --max-cycles 3

BEFORE GOING LIVE:
1. Test with DRY_RUN=true first
2. Test on KUCOIN_TESTNET=true (sandbox)
3. Start with small STARTING_BALANCE
4. Monitor closely for first 24 hours
5. Review all alert logs
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.live import LiveTradingEngine, LiveTradingConfig
from core.utils.logging import setup_logging, get_logger

setup_logging(level="INFO", format="console")
logger = get_logger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Huxorb Pro live trading")
    parser.add_argument(
        "--env",
        type=Path,
        default=Path("config/.env"),
        help="Path to .env config file (default: config/.env)",
    )
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Test API connection and exit",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Stop after N cycles (default: run forever)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def confirm_live_mode(config: LiveTradingConfig) -> bool:
    """
    Prompt user for confirmation if running in live (non-dry-run) mode.

    Returns:
        True if user confirms, False otherwise
    """
    if config.dry_run:
        return True  # Dry run always allowed

    print()
    print("=" * 70)
    print("   ⚠️  LIVE TRADING MODE — REAL MONEY AT RISK")
    print("=" * 70)
    print(f"  Testnet:    {config.testnet}")
    print(f"  Dry run:    {config.dry_run}")
    print(f"  Symbols:    {', '.join(config.symbols)}")
    print(f"  Risk/trade: {config.risk_per_trade_pct}%")
    print(f"  Max trades: {config.max_open_trades}")
    print("=" * 70)
    print()
    print("  This will place REAL ORDERS on KuCoin.")
    print("  Type 'START LIVE TRADING' to confirm:")
    print()

    response = input("  > ").strip()
    return response == "START LIVE TRADING"


def main():
    args = parse_args()

    if args.verbose:
        setup_logging(level="DEBUG", format="console")

    # Load config
    try:
        config = LiveTradingConfig.from_env(args.env)
    except ValueError as exc:
        logger.error("config_error", error=str(exc))
        print()
        print(f"ERROR: {exc}")
        print()
        print("Create a .env file from config/live_trading.example.env:")
        print(f"  cp config/live_trading.example.env {args.env}")
        print(f"  # Edit {args.env} with your KuCoin API credentials")
        print()
        sys.exit(1)

    # Initialize engine
    try:
        engine = LiveTradingEngine(config)
    except ConnectionError as exc:
        logger.error("connection_failed", error=str(exc))
        print()
        print(f"ERROR: {exc}")
        print()
        print("Check your KuCoin API credentials and network connection.")
        sys.exit(1)

    # Test connection mode
    if args.test_connection:
        print()
        print("✅ KuCoin API connection successful!")
        print(f"   Testnet: {config.testnet}")
        print(f"   Dry run: {config.dry_run}")
        print()
        balance = engine.connector.get_balance()
        print("Account balance:")
        for curr, bal in balance.items():
            if bal.total > 0:
                print(f"  {curr}: {bal.free} free, {bal.used} locked, {bal.total} total")
        print()
        return

    # Confirm live mode
    if not confirm_live_mode(config):
        print()
        print("Aborted. To run in dry-run mode, set DRY_RUN=true in your .env file.")
        print()
        sys.exit(0)

    # Run
    try:
        engine.run(max_cycles=args.max_cycles)
    except KeyboardInterrupt:
        print("\n  Stopping live trading...")
        engine.stop()

    print()
    print("Live trading session ended.")
    print()


if __name__ == "__main__":
    main()
