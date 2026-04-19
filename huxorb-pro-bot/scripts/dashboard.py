"""
Portfolio Dashboard
===================
View paper trading portfolio state with Rich terminal UI.

Usage:
    # One-shot snapshot
    python scripts/dashboard.py

    # Metrics only (Sharpe, Sortino, etc.)
    python scripts/dashboard.py --metrics

    # Export trade journal
    python scripts/dashboard.py --export csv
    python scripts/dashboard.py --export json
    python scripts/dashboard.py --export snapshot

    # Live refresh every 60s
    python scripts/dashboard.py --live

    # Live refresh custom interval
    python scripts/dashboard.py --live --interval 30
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.paper import PaperPortfolio
from core.dashboard import PortfolioDashboard, TradeExporter
from core.utils.logging import setup_logging, get_logger

setup_logging(level="WARNING", format="console")
logger = get_logger(__name__)

STATE_FILE = Path(__file__).parent.parent / "data" / "paper_state" / "portfolio.json"
EXPORT_DIR = Path(__file__).parent.parent / "data" / "exports"


def load_portfolio() -> PaperPortfolio:
    if not STATE_FILE.exists():
        print(f"\nNo paper trading state found at: {STATE_FILE}")
        print(f"Start paper trading first:\n  python scripts/paper_trade.py\n")
        sys.exit(1)
    return PaperPortfolio(state_file=STATE_FILE)


def parse_args():
    parser = argparse.ArgumentParser(description="Huxorb Pro portfolio dashboard")
    parser.add_argument("--metrics", action="store_true", help="Show extended analytics metrics")
    parser.add_argument("--live", action="store_true", help="Live refresh mode")
    parser.add_argument("--interval", type=int, default=60, help="Live refresh interval (seconds)")
    parser.add_argument(
        "--export",
        choices=["csv", "json", "snapshot"],
        help="Export trade journal",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    portfolio = load_portfolio()
    dashboard = PortfolioDashboard(refresh_seconds=args.interval)

    if args.export:
        exporter = TradeExporter()
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        if args.export == "csv":
            path = exporter.export_trades_csv(
                portfolio.closed_trades,
                EXPORT_DIR / "trades.csv",
            )
            print(f"\nExported {len(portfolio.closed_trades)} trades to: {path}\n")

        elif args.export == "json":
            path = exporter.export_trades_json(
                portfolio.closed_trades,
                EXPORT_DIR / "trades.json",
            )
            print(f"\nExported {len(portfolio.closed_trades)} trades to: {path}\n")

        elif args.export == "snapshot":
            path = exporter.export_portfolio_snapshot(
                portfolio,
                EXPORT_DIR / "portfolio_snapshot.json",
            )
            print(f"\nPortfolio snapshot exported to: {path}\n")

        return

    if args.live:
        print("\nLive dashboard — Ctrl+C to exit\n")
        dashboard.live_view(portfolio, lambda: {}).run()
        return

    if args.metrics:
        dashboard.print_metrics_only(portfolio)
        return

    # Default: full snapshot
    dashboard.print_portfolio(portfolio)


if __name__ == "__main__":
    main()
