"""
Paper Trading Runner
=====================
Start a paper trading session with live KuCoin data.

Usage:
    # Default (BTC/USDT + ETH/USDT, 10k balance, 1h poll)
    python scripts/paper_trade.py

    # Custom
    python scripts/paper_trade.py --symbols BTC/USDT ETH/USDT SOL/USDT --balance 50000

    # Quick test (3 cycles, 10s interval, synthetic prices)
    python scripts/paper_trade.py --test

    # Resume from saved state
    python scripts/paper_trade.py --resume
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.paper import PaperTradingLoop, PaperTradingConfig, PaperPortfolio
from core.utils.logging import setup_logging, get_logger

setup_logging(level="INFO", format="console")
logger = get_logger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Paper trading with live KuCoin data")
    parser.add_argument("--exchange", default="kucoin", help="Exchange (default: kucoin)")
    parser.add_argument("--symbols", nargs="+", default=["BTC/USDT", "ETH/USDT"])
    parser.add_argument("--balance", type=float, default=10000, help="Starting balance (USDT)")
    parser.add_argument("--risk", type=float, default=0.5, help="Risk per trade (%%)")
    parser.add_argument("--interval", type=int, default=3600, help="Poll interval (seconds)")
    parser.add_argument("--max-cycles", type=int, default=None, help="Stop after N cycles")
    parser.add_argument("--test", action="store_true", help="Quick test mode (3 cycles)")
    parser.add_argument("--resume", action="store_true", help="Resume from saved state")
    parser.add_argument("--status", action="store_true", help="Show current paper state")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def show_status():
    """Show current paper trading portfolio status."""
    state_dir = Path(__file__).parent.parent / "data" / "paper_state"
    state_file = state_dir / "portfolio.json"

    if not state_file.exists():
        print("No paper trading state found.")
        print(f"Start with: python {__file__}")
        return

    portfolio = PaperPortfolio(state_file=state_file)
    summary = portfolio.summary()

    print()
    print("=" * 50)
    print("   PAPER PORTFOLIO STATUS")
    print("=" * 50)
    for key, val in summary.items():
        print(f"  {key}: {val}")
    print()

    if portfolio.open_positions:
        print("  OPEN POSITIONS:")
        for pos in portfolio.open_positions:
            print(f"    #{pos.position_id} {pos.symbol} {pos.strategy}")
            print(f"      Entry: {pos.entry_price} | SL: {pos.stop_loss} | TP: {pos.take_profit}")
            print(f"      Qty: {pos.quantity} | Since: {pos.entry_time}")
        print()

    if portfolio.closed_trades:
        print(f"  RECENT TRADES (last 10 of {len(portfolio.closed_trades)}):")
        for trade in portfolio.closed_trades[-10:]:
            sign = "+" if trade.pnl > 0 else ""
            print(
                f"    #{trade.trade_id} {trade.symbol} {trade.strategy} "
                f"-> {trade.exit_reason} {sign}{trade.pnl:.2f} USDT"
            )
        print()

    print("=" * 50)


def main():
    args = parse_args()

    if args.verbose:
        setup_logging(level="DEBUG", format="console")

    if args.status:
        show_status()
        return

    # Configure
    config = PaperTradingConfig(
        exchange_id=args.exchange,
        symbols=args.symbols,
        starting_balance=Decimal(str(args.balance)),
        risk_per_trade_pct=Decimal(str(args.risk)),
        poll_interval_seconds=10 if args.test else args.interval,
    )

    max_cycles = 3 if args.test else args.max_cycles

    print()
    print("=" * 50)
    print("   HUXORB PRO - PAPER TRADING")
    print("=" * 50)
    print(f"  Exchange:    {config.exchange_id}")
    print(f"  Symbols:     {', '.join(config.symbols)}")
    print(f"  Balance:     {config.starting_balance} USDT")
    print(f"  Risk/trade:  {config.risk_per_trade_pct}%")
    print(f"  Poll:        {config.poll_interval_seconds}s")
    print(f"  Mode:        {'TEST' if args.test else 'LIVE DATA'}")
    print(f"  State:       {config.state_dir}")
    print("=" * 50)
    print()
    print("  Press Ctrl+C to stop")
    print()

    # Run
    loop = PaperTradingLoop(config)

    try:
        loop.run(max_cycles=max_cycles)
    except KeyboardInterrupt:
        print("\n  Stopping paper trading...")
        loop.stop()

    print()
    show_status()


if __name__ == "__main__":
    main()
