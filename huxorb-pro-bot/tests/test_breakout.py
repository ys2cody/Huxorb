"""Tests for the breakout strategy."""

import numpy as np
import pandas as pd
import pytest
from decimal import Decimal

from core.strategy.breakout import BreakoutStrategy, BreakoutConfig


def _make_ohlcv(bars=100, base=50000.0, trend=0.0002, seed=1, vol=0.01):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=bars, freq="4h", tz="UTC")
    c = [base]
    for _ in range(1, bars):
        c.append(c[-1] * (1 + trend + vol * rng.randn()))
    c = np.array(c)
    return pd.DataFrame({
        "open":   c * (1 + rng.uniform(-0.003, 0.003, bars)),
        "high":   c * (1 + np.abs(rng.normal(0.005, 0.002, bars))),
        "low":    c * (1 - np.abs(rng.normal(0.005, 0.002, bars))),
        "close":  c,
        "volume": rng.uniform(500, 10000, bars),
    }, index=dates)


def _make_breakout_ohlcv():
    """Build a dataset with a clear volume-confirmed breakout on the last bar."""
    bars = 80
    dates = pd.date_range("2024-01-01", periods=bars, freq="4h", tz="UTC")
    base = 50000.0

    # Flat consolidation for first 79 bars
    rng = np.random.RandomState(10)
    c = [base + rng.uniform(-200, 200) for _ in range(bars - 1)]
    # Last bar: strong breakout
    breakout_close = max(c) * 1.025  # 2.5% above prior high
    c.append(breakout_close)
    c = np.array(c)

    # Normal volume for first 79, spike on last
    vol = [rng.uniform(800, 1200) for _ in range(bars - 1)]
    vol.append(5000)  # 4x average

    return pd.DataFrame({
        "open":   c * 0.998,
        "high":   c * 1.005,
        "low":    c * 0.994,
        "close":  c,
        "volume": vol,
    }, index=dates)


class TestBreakoutStrategy:
    def test_insufficient_data_no_signal(self):
        ohlcv = _make_ohlcv(bars=10)
        s = BreakoutStrategy()
        result = s.check_signal(ohlcv)
        assert not result.has_signal
        assert "insufficient_data" in result.reason

    def test_no_signal_when_below_prior_high(self):
        """No breakout when close < prior high."""
        ohlcv = _make_ohlcv(bars=60, trend=-0.001, seed=99)
        s = BreakoutStrategy()
        result = s.check_signal(ohlcv)
        if not result.has_signal:
            assert not result.breakout_confirmed

    def test_signal_on_clear_breakout(self):
        """Clear volume breakout should generate a signal."""
        ohlcv = _make_breakout_ohlcv()
        s = BreakoutStrategy()
        result = s.check_signal(ohlcv)
        assert result.has_signal
        assert result.breakout_confirmed
        assert result.volume_confirmed

    def test_signal_has_valid_prices(self):
        ohlcv = _make_breakout_ohlcv()
        s = BreakoutStrategy()
        result = s.check_signal(ohlcv)
        if result.has_signal:
            assert result.entry_price > 0
            assert result.stop_loss > 0
            assert result.take_profit > result.entry_price
            assert result.entry_price > result.stop_loss

    def test_risk_reward_ratio(self):
        """TP should be exactly RR * risk from entry."""
        config = BreakoutConfig(risk_reward_ratio=3.0)
        ohlcv = _make_breakout_ohlcv()
        s = BreakoutStrategy(config)
        result = s.check_signal(ohlcv)
        if result.has_signal:
            risk = result.entry_price - result.stop_loss
            expected_tp = result.entry_price + risk * Decimal("3.0")
            assert abs(result.take_profit - expected_tp) < Decimal("1")

    def test_no_signal_low_volume(self):
        """Breakout without volume spike should not signal."""
        ohlcv = _make_breakout_ohlcv()
        # Flatten all volume to same level (no spike on last bar)
        ohlcv["volume"] = 1000
        s = BreakoutStrategy(BreakoutConfig(volume_multiplier=1.5))
        result = s.check_signal(ohlcv)
        # breakout confirmed but volume not confirmed
        if result.breakout_confirmed:
            assert not result.volume_confirmed or not result.has_signal

    def test_custom_rr_config(self):
        config = BreakoutConfig(risk_reward_ratio=4.0)
        s = BreakoutStrategy(config)
        assert s.config.risk_reward_ratio == 4.0

    def test_stop_below_entry(self):
        """Stop loss must always be below entry price."""
        ohlcv = _make_breakout_ohlcv()
        s = BreakoutStrategy()
        result = s.check_signal(ohlcv)
        if result.has_signal:
            assert result.stop_loss < result.entry_price
