"""
Backtesting Module
==================
Test strategies on historical OHLCV data before deploying live.

Components:
- data_loader: Fetch and cache OHLCV from exchanges (KuCoin, etc.)
- trade_tracker: Record trades, compute performance metrics
- engine: Walk-forward backtest engine (no look-ahead bias)

Usage:
    from core.backtest import BacktestEngine, BacktestConfig

    config = BacktestConfig(
        symbols=["BTC/USDT", "ETH/USDT"],
        starting_balance=Decimal("10000"),
    )

    engine = BacktestEngine(config)
    tracker = engine.run(symbol_data={"BTC/USDT": btc_4h}, btc_daily=btc_1d)

    print(tracker.print_summary())
"""

from core.backtest.engine import BacktestEngine, BacktestConfig
from core.backtest.trade_tracker import TradeTracker, BacktestTrade
from core.backtest.data_loader import (
    load_ohlcv_csv,
    save_ohlcv_csv,
    fetch_ohlcv_ccxt,
    load_or_fetch,
)

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "TradeTracker",
    "BacktestTrade",
    "load_ohlcv_csv",
    "save_ohlcv_csv",
    "fetch_ohlcv_ccxt",
    "load_or_fetch",
]
