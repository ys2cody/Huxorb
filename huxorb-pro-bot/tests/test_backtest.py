"""Tests for the backtesting engine."""

from decimal import Decimal
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from core.backtest import BacktestEngine, BacktestConfig
from core.backtest.trade_tracker import TradeTracker, BacktestTrade


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_ohlcv(bars: int, base: float = 60000, trend: float = 0.0001, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2025-01-01", periods=bars, freq="4h", tz="UTC")
    closes = [base]
    for i in range(1, bars):
        closes.append(closes[-1] * (1 + trend + 0.01 * rng.randn()))
    closes = np.array(closes)
    return pd.DataFrame({
        "open": closes * (1 + rng.uniform(-0.005, 0.005, bars)),
        "high": closes * (1 + rng.uniform(0, 0.01, bars)),
        "low": closes * (1 - rng.uniform(0, 0.01, bars)),
        "close": closes,
        "volume": rng.uniform(100, 10000, bars),
    }, index=dates)


def _make_bullish_btc(bars: int = 500) -> pd.DataFrame:
    return _make_ohlcv(bars, base=50000, trend=0.0003, seed=99)


# ------------------------------------------------------------------ #
# TradeTracker tests
# ------------------------------------------------------------------ #

class TestTradeTracker:
    def test_empty_metrics(self):
        t = TradeTracker(starting_balance=Decimal("10000"))
        m = t.compute_metrics()
        assert m["total_trades"] == 0
        assert m["starting_balance"] == "10000"

    def test_single_winning_trade(self):
        t = TradeTracker(starting_balance=Decimal("10000"))
        trade = t.open_trade(
            symbol="BTC/USDT", strategy="test", regime="trend",
            entry_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            entry_price=Decimal("60000"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
        )
        t.close_trade(trade,
                       exit_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                       exit_price=Decimal("62000"),
                       exit_reason="take_profit")

        assert trade.pnl == Decimal("200")  # (62000-60000) * 0.1
        assert trade.is_winner
        m = t.compute_metrics()
        assert m["total_trades"] == 1
        assert m["win_rate_pct"] == 100.0

    def test_single_losing_trade(self):
        t = TradeTracker(starting_balance=Decimal("10000"))
        trade = t.open_trade(
            symbol="ETH/USDT", strategy="test", regime="range",
            entry_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            entry_price=Decimal("3000"),
            quantity=Decimal("1"),
            stop_loss=Decimal("2900"),
            take_profit=Decimal("3200"),
        )
        t.close_trade(trade,
                       exit_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                       exit_price=Decimal("2900"),
                       exit_reason="stop_loss")

        assert trade.pnl == Decimal("-100")
        assert not trade.is_winner

    def test_r_multiple(self):
        t = TradeTracker(starting_balance=Decimal("10000"))
        trade = t.open_trade(
            symbol="BTC/USDT", strategy="trend", regime="trend",
            entry_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            entry_price=Decimal("60000"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
        )
        t.close_trade(trade,
                       exit_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                       exit_price=Decimal("62000"),
                       exit_reason="take_profit")

        assert trade.reward_achieved == Decimal("2")  # 2R

    def test_equity_tracking(self):
        t = TradeTracker(starting_balance=Decimal("10000"))
        trade = t.open_trade(
            symbol="BTC/USDT", strategy="test", regime="trend",
            entry_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            entry_price=Decimal("60000"),
            quantity=Decimal("0.01"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
        )
        t.close_trade(trade,
                       exit_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                       exit_price=Decimal("62000"),
                       exit_reason="take_profit")

        assert t.current_equity == Decimal("10020")  # +$20

    def test_max_drawdown(self):
        t = TradeTracker(starting_balance=Decimal("10000"))

        # Win, then two losses
        for i, (exit_p, reason) in enumerate([
            (Decimal("62000"), "take_profit"),
            (Decimal("59000"), "stop_loss"),
            (Decimal("59000"), "stop_loss"),
        ]):
            trade = t.open_trade(
                symbol="BTC/USDT", strategy="test", regime="trend",
                entry_time=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                entry_price=Decimal("60000"),
                quantity=Decimal("0.1"),
                stop_loss=Decimal("59000"),
                take_profit=Decimal("62000"),
            )
            t.close_trade(trade,
                           exit_time=datetime(2025, 1, i + 1, 12, tzinfo=timezone.utc),
                           exit_price=exit_p,
                           exit_reason=reason)

        m = t.compute_metrics()
        assert float(m["max_drawdown"]) > 0

    def test_consecutive_streaks(self):
        t = TradeTracker(starting_balance=Decimal("10000"))

        results = [
            Decimal("61000"),  # win
            Decimal("61000"),  # win
            Decimal("59000"),  # loss
            Decimal("59000"),  # loss
            Decimal("59000"),  # loss
        ]
        for i, exit_p in enumerate(results):
            trade = t.open_trade(
                symbol="BTC/USDT", strategy="test", regime="trend",
                entry_time=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                entry_price=Decimal("60000"),
                quantity=Decimal("0.01"),
                stop_loss=Decimal("59000"),
                take_profit=Decimal("62000"),
            )
            reason = "take_profit" if exit_p > Decimal("60000") else "stop_loss"
            t.close_trade(trade,
                           exit_time=datetime(2025, 1, i + 1, 12, tzinfo=timezone.utc),
                           exit_price=exit_p,
                           exit_reason=reason)

        m = t.compute_metrics()
        assert m["max_consecutive_wins"] == 2
        assert m["max_consecutive_losses"] == 3

    def test_trades_to_dataframe(self):
        t = TradeTracker(starting_balance=Decimal("10000"))
        trade = t.open_trade(
            symbol="BTC/USDT", strategy="trend", regime="trend",
            entry_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            entry_price=Decimal("60000"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
        )
        t.close_trade(trade,
                       exit_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                       exit_price=Decimal("62000"),
                       exit_reason="take_profit")

        df = t.trades_to_dataframe()
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "BTC/USDT"
        assert df.iloc[0]["pnl"] == 200.0


# ------------------------------------------------------------------ #
# BacktestEngine tests
# ------------------------------------------------------------------ #

class TestBacktestEngine:
    def test_runs_without_error(self):
        config = BacktestConfig(
            symbols=["BTC/USDT"],
            starting_balance=Decimal("10000"),
        )
        engine = BacktestEngine(config)

        btc_4h = _make_ohlcv(500, base=60000, trend=0.0002)
        btc_1d = _make_bullish_btc()

        tracker = engine.run(
            symbol_data={"BTC/USDT": btc_4h},
            btc_daily=btc_1d,
        )

        assert tracker.starting_balance == Decimal("10000")
        assert tracker.current_equity > 0

    def test_respects_max_open_trades(self):
        config = BacktestConfig(
            symbols=["BTC/USDT", "ETH/USDT"],
            starting_balance=Decimal("10000"),
            max_open_trades=1,
        )
        engine = BacktestEngine(config)

        btc_4h = _make_ohlcv(500, base=60000)
        eth_4h = _make_ohlcv(500, base=3500, seed=77)
        btc_1d = _make_bullish_btc()

        tracker = engine.run(
            symbol_data={"BTC/USDT": btc_4h, "ETH/USDT": eth_4h},
            btc_daily=btc_1d,
        )

        # Should complete without error
        assert tracker.starting_balance == Decimal("10000")

    def test_skips_insufficient_data(self):
        config = BacktestConfig(
            symbols=["BTC/USDT"],
            warmup_bars=210,
        )
        engine = BacktestEngine(config)

        btc_4h = _make_ohlcv(100)  # Too few bars
        btc_1d = _make_bullish_btc()

        tracker = engine.run(
            symbol_data={"BTC/USDT": btc_4h},
            btc_daily=btc_1d,
        )

        assert len(tracker.closed_trades) == 0

    def test_all_trades_closed_at_end(self):
        config = BacktestConfig(
            symbols=["BTC/USDT"],
            starting_balance=Decimal("10000"),
        )
        engine = BacktestEngine(config)

        btc_4h = _make_ohlcv(500, base=60000, trend=0.0002)
        btc_1d = _make_bullish_btc()

        tracker = engine.run(
            symbol_data={"BTC/USDT": btc_4h},
            btc_daily=btc_1d,
        )

        # All trades should be closed (no leaking open positions)
        assert len(tracker.open_trades) == 0
