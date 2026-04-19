"""
Run Backtest
=============
CLI script to run a backtest with configurable parameters.

Usage:
    # With live KuCoin data (fetches and caches)
    python scripts/run_backtest.py --exchange kucoin --symbols BTC/USDT ETH/USDT

    # With cached data (no internet needed)
    python scripts/run_backtest.py --cached

    # With synthetic data (for testing)
    python scripts/run_backtest.py --synthetic

    # Custom parameters
    python scripts/run_backtest.py --synthetic --balance 50000 --risk 1.0
"""

import argparse
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from core.backtest import BacktestEngine, BacktestConfig, load_or_fetch
from core.utils.logging import setup_logging, get_logger

setup_logging(level="INFO", format="console")
logger = get_logger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "data" / "ohlcv_cache"


def parse_args():
    parser = argparse.ArgumentParser(description="Run strategy backtest")
    parser.add_argument("--exchange", default="kucoin", help="Exchange ID (default: kucoin)")
    parser.add_argument("--symbols", nargs="+", default=["BTC/USDT", "ETH/USDT"])
    parser.add_argument("--timeframe", default="4h", help="Trading timeframe")
    parser.add_argument("--balance", type=float, default=10000, help="Starting balance (USDT)")
    parser.add_argument("--risk", type=float, default=0.5, help="Risk per trade (%)")
    parser.add_argument("--days", type=int, default=365, help="Days of history")
    parser.add_argument("--cached", action="store_true", help="Use cached data only")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic data")
    parser.add_argument("--refresh", action="store_true", help="Force re-download")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    return parser.parse_args()


def generate_synthetic_ohlcv(
    bars: int = 2000,
    freq: str = "4h",
    base_price: float = 60000.0,
    volatility: float = 0.02,
    trend: float = 0.0001,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate realistic synthetic OHLCV data.

    Creates a random walk with configurable trend and volatility
    that includes:
    - Trending periods
    - Mean-reverting periods
    - Volatility clusters
    """
    rng = np.random.RandomState(seed)

    dates = pd.date_range("2025-01-01", periods=bars, freq=freq, tz="UTC")

    closes = [base_price]
    for i in range(1, bars):
        # Regime changes every ~200 bars
        if (i // 200) % 3 == 0:
            # Trending up
            drift = trend * 3
            vol = volatility * 0.8
        elif (i // 200) % 3 == 1:
            # Ranging
            drift = 0
            vol = volatility * 0.6
        else:
            # Trending down then recovering
            drift = -trend * 1.5 if i % 200 < 100 else trend * 2
            vol = volatility * 1.2

        ret = drift + vol * rng.randn()
        closes.append(closes[-1] * (1 + ret))

    closes = np.array(closes)

    # Generate OHLC from close
    high_noise = rng.uniform(0, volatility * 0.5, bars)
    low_noise = rng.uniform(0, volatility * 0.5, bars)

    highs = closes * (1 + high_noise)
    lows = closes * (1 - low_noise)
    opens = closes * (1 + rng.uniform(-volatility * 0.3, volatility * 0.3, bars))

    # Ensure OHLC consistency
    highs = np.maximum(highs, np.maximum(opens, closes))
    lows = np.minimum(lows, np.minimum(opens, closes))

    volumes = rng.uniform(100, 10000, bars) * (closes / base_price)

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    }, index=dates)


def main():
    args = parse_args()

    if args.verbose:
        setup_logging(level="DEBUG", format="console")

    logger.info("=" * 50)
    logger.info("     HUXORB PRO BACKTEST")
    logger.info("=" * 50)

    # --- Configure ---
    config = BacktestConfig(
        symbols=args.symbols,
        starting_balance=Decimal(str(args.balance)),
        risk_per_trade_pct=Decimal(str(args.risk)),
    )

    engine = BacktestEngine(config)

    # --- Load Data ---
    if args.synthetic:
        logger.info("data_mode", mode="synthetic")
        symbol_data = {}
        for sym in args.symbols:
            base_price = 60000 if "BTC" in sym else 3500
            symbol_data[sym] = generate_synthetic_ohlcv(
                bars=2000,
                freq=args.timeframe,
                base_price=base_price,
                seed=hash(sym) % 10000,
            )
            logger.info("synthetic_data", symbol=sym, bars=len(symbol_data[sym]))

        btc_daily = generate_synthetic_ohlcv(
            bars=500,
            freq="1D",
            base_price=60000,
            trend=0.0002,  # Bullish bias
            seed=99,
        )
        logger.info("synthetic_btc_daily", bars=len(btc_daily))

    elif args.cached:
        logger.info("data_mode", mode="cached")
        symbol_data = {}
        for sym in args.symbols:
            safe = sym.replace("/", "_")
            path = CACHE_DIR / f"{args.exchange}_{safe}_{args.timeframe}.csv"
            if not path.exists():
                logger.error("cache_missing", symbol=sym, path=str(path))
                sys.exit(1)
            from core.backtest import load_ohlcv_csv
            symbol_data[sym] = load_ohlcv_csv(path)

        btc_path = CACHE_DIR / f"{args.exchange}_BTC_USDT_1d.csv"
        if not btc_path.exists():
            logger.error("cache_missing", symbol="BTC/USDT 1d", path=str(btc_path))
            sys.exit(1)
        from core.backtest import load_ohlcv_csv
        btc_daily = load_ohlcv_csv(btc_path)

    else:
        logger.info("data_mode", mode="live_fetch", exchange=args.exchange)
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        symbol_data = {}
        for sym in args.symbols:
            symbol_data[sym] = load_or_fetch(
                args.exchange, sym, args.timeframe,
                cache_dir=CACHE_DIR,
                since=since,
                force_refresh=args.refresh,
            )

        btc_daily = load_or_fetch(
            args.exchange, "BTC/USDT", "1d",
            cache_dir=CACHE_DIR,
            since=since - timedelta(days=300),
            force_refresh=args.refresh,
        )

    # --- Run Backtest ---
    logger.info("backtest_starting",
                symbols=args.symbols,
                balance=args.balance,
                risk_pct=args.risk)

    tracker = engine.run(symbol_data=symbol_data, btc_daily=btc_daily)

    # --- Results ---
    print()
    print(tracker.print_summary())
    print()

    # Trade log
    df = tracker.trades_to_dataframe()
    if not df.empty:
        print("TRADE LOG (last 10):")
        print("-" * 80)
        cols = ["trade_id", "symbol", "strategy", "entry_price", "exit_price",
                "pnl", "exit_reason", "r_multiple"]
        print(df[cols].tail(10).to_string(index=False))
        print()

        # Save CSV
        output_path = Path(__file__).parent.parent / "data" / "backtest_results.csv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info("results_saved", path=str(output_path))


if __name__ == "__main__":
    main()
