"""Tests for core.analytics metrics."""

import tempfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from core.analytics.metrics import (
    equity_curve,
    sharpe_ratio,
    sortino_ratio,
    calmar_ratio,
    expectancy,
    monthly_returns_table,
    compute_metrics,
)
from core.paper.portfolio import PaperPortfolio


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_trade(pnl: float, days_offset: int = 0, strategy: str = "trend"):
    """Create a minimal duck-typed trade object."""

    class _T:
        pass

    t = _T()
    t.trade_id = 1
    t.symbol = "BTC/USDT"
    t.strategy = strategy
    t.regime = "trend"
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    t.entry_time = base + timedelta(days=days_offset)
    t.exit_time = base + timedelta(days=days_offset + 1)
    t.entry_price = Decimal("60000")
    t.exit_price = Decimal("62000") if pnl > 0 else Decimal("59000")
    t.quantity = Decimal("0.1")
    t.stop_loss = Decimal("59000")
    t.take_profit = Decimal("62000")
    t.exit_reason = "take_profit" if pnl >= 0 else "stop_loss"
    t.pnl = Decimal(str(pnl))
    return t


# ------------------------------------------------------------------ #
# equity_curve
# ------------------------------------------------------------------ #

class TestEquityCurve:
    def test_empty_trades(self):
        curve = equity_curve([], Decimal("10000"))
        assert curve == [Decimal("10000")]

    def test_single_win(self):
        t = _make_trade(200)
        curve = equity_curve([t], Decimal("10000"))
        assert len(curve) == 2
        assert curve[0] == Decimal("10000")
        assert curve[1] == Decimal("10200")

    def test_win_then_loss(self):
        trades = [_make_trade(200), _make_trade(-100)]
        curve = equity_curve(trades, Decimal("10000"))
        assert curve == [Decimal("10000"), Decimal("10200"), Decimal("10100")]


# ------------------------------------------------------------------ #
# sharpe_ratio
# ------------------------------------------------------------------ #

class TestSharpeRatio:
    def test_empty(self):
        assert sharpe_ratio([], Decimal("10000")) == 0.0

    def test_single_trade(self):
        # Only 1 return — not enough for std dev, returns 0
        t = _make_trade(100)
        assert sharpe_ratio([t], Decimal("10000")) == 0.0

    def test_all_wins_positive_sharpe(self):
        trades = [_make_trade(100, i) for i in range(20)]
        ratio = sharpe_ratio(trades, Decimal("10000"))
        assert ratio > 0

    def test_all_losses_negative_sharpe(self):
        trades = [_make_trade(-100, i) for i in range(20)]
        ratio = sharpe_ratio(trades, Decimal("10000"))
        assert ratio < 0

    def test_flat_returns_zero(self):
        trades = [_make_trade(0, i) for i in range(10)]
        ratio = sharpe_ratio(trades, Decimal("10000"))
        assert ratio == 0.0


# ------------------------------------------------------------------ #
# sortino_ratio
# ------------------------------------------------------------------ #

class TestSortinoRatio:
    def test_empty(self):
        assert sortino_ratio([], Decimal("10000")) == 0.0

    def test_no_losses_returns_inf(self):
        trades = [_make_trade(100, i) for i in range(10)]
        # All wins means downside_std=0 and excess>0 → inf
        ratio = sortino_ratio(trades, Decimal("10000"))
        assert ratio == float("inf") or ratio > 0

    def test_mixed_trades(self):
        trades = [_make_trade(100, i) if i % 2 == 0 else _make_trade(-50, i) for i in range(20)]
        ratio = sortino_ratio(trades, Decimal("10000"))
        assert isinstance(ratio, float)


# ------------------------------------------------------------------ #
# calmar_ratio
# ------------------------------------------------------------------ #

class TestCalmarRatio:
    def test_empty(self):
        assert calmar_ratio([], Decimal("10000")) == 0.0

    def test_no_drawdown(self):
        # All wins, no drawdown → 0 (division by zero handled)
        trades = [_make_trade(100, i) for i in range(10)]
        # There's no drawdown so calmar returns 0
        result = calmar_ratio(trades, Decimal("10000"))
        assert result == 0.0

    def test_positive_calmar(self):
        # Win, then loss, then wins (produces a drawdown)
        trades = [
            _make_trade(500, 0),
            _make_trade(-300, 30),
            _make_trade(200, 60),
            _make_trade(200, 90),
        ]
        result = calmar_ratio(trades, Decimal("10000"))
        assert isinstance(result, float)


# ------------------------------------------------------------------ #
# expectancy
# ------------------------------------------------------------------ #

class TestExpectancy:
    def test_empty(self):
        assert expectancy([]) == 0.0

    def test_all_wins(self):
        trades = [_make_trade(100)] * 5
        # 100% win rate, avg win 100, avg loss 0 → expectancy = 100
        assert expectancy(trades) == pytest.approx(100.0, abs=0.01)

    def test_mixed(self):
        # 50% win rate, avg win=200, avg loss=100
        # expectancy = 0.5*200 - 0.5*100 = 50
        trades = [_make_trade(200), _make_trade(-100)]
        result = expectancy(trades)
        assert result == pytest.approx(50.0, abs=0.01)

    def test_all_losses(self):
        trades = [_make_trade(-100)] * 3
        result = expectancy(trades)
        assert result == pytest.approx(-100.0, abs=0.01)


# ------------------------------------------------------------------ #
# monthly_returns_table
# ------------------------------------------------------------------ #

class TestMonthlyReturns:
    def test_empty(self):
        result = monthly_returns_table([], Decimal("10000"))
        assert result == {}

    def test_single_month(self):
        trades = [_make_trade(100, 0), _make_trade(200, 5), _make_trade(-50, 10)]
        result = monthly_returns_table(trades, Decimal("10000"))
        assert "2025-01" in result
        data = result["2025-01"]
        assert data["trades"] == 3
        assert data["pnl"] == pytest.approx(250.0)
        assert data["win_rate"] == pytest.approx(66.7, abs=0.1)

    def test_multiple_months(self):
        jan = [_make_trade(100, 0), _make_trade(100, 5)]
        feb = [_make_trade(-50, 35), _make_trade(-50, 40)]
        result = monthly_returns_table(jan + feb, Decimal("10000"))
        assert "2025-01" in result
        assert "2025-02" in result
        assert result["2025-01"]["pnl"] == pytest.approx(200.0)
        assert result["2025-02"]["pnl"] == pytest.approx(-100.0)

    def test_months_sorted(self):
        trades = [_make_trade(100, 35), _make_trade(100, 0)]  # Feb first, then Jan
        result = monthly_returns_table(trades, Decimal("10000"))
        keys = list(result.keys())
        assert keys == sorted(keys)


# ------------------------------------------------------------------ #
# compute_metrics
# ------------------------------------------------------------------ #

class TestComputeMetrics:
    def test_empty_returns_zeros(self):
        m = compute_metrics([], Decimal("10000"))
        assert m["total_trades"] == 0
        assert m["roi_pct"] == "0.00%"
        assert m["win_rate_pct"] == "N/A"

    def test_single_win(self):
        t = _make_trade(200)
        m = compute_metrics([t], Decimal("10000"))
        assert m["total_trades"] == 1
        assert m["winners"] == 1
        assert m["losers"] == 0
        assert m["win_rate_pct"] == "100.0%"
        assert m["total_pnl"] == "200.00"

    def test_profit_factor(self):
        trades = [_make_trade(200), _make_trade(-100)]
        m = compute_metrics(trades, Decimal("10000"))
        # profit_factor = 200 / 100 = 2.0
        assert m["profit_factor"] == "2.00"

    def test_max_drawdown_positive(self):
        trades = [_make_trade(500, 0), _make_trade(-400, 30), _make_trade(200, 60)]
        m = compute_metrics(trades, Decimal("10000"))
        dd = float(m["max_drawdown_pct"].replace("%", ""))
        assert dd > 0

    def test_by_strategy_breakdown(self):
        trades = [
            _make_trade(100, 0, strategy="trend_following"),
            _make_trade(100, 5, strategy="trend_following"),
            _make_trade(-50, 10, strategy="mean_reversion"),
        ]
        m = compute_metrics(trades, Decimal("10000"))
        assert "trend_following" in m["by_strategy"]
        assert "mean_reversion" in m["by_strategy"]
        assert m["by_strategy"]["trend_following"]["trades"] == 2
        assert m["by_strategy"]["mean_reversion"]["trades"] == 1

    def test_roi_correct(self):
        trades = [_make_trade(1000)]
        m = compute_metrics(trades, Decimal("10000"))
        assert m["roi_pct"] == "10.00%"


# ------------------------------------------------------------------ #
# Integration: PaperPortfolio → compute_metrics
# ------------------------------------------------------------------ #

class TestPortfolioAnalyticsIntegration:
    def test_full_pipeline(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        pos1 = p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.01"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        p.close_position(pos1, Decimal("62000"), "take_profit")

        pos2 = p.open_position(
            symbol="ETH/USDT",
            quantity=Decimal("1"),
            entry_price=Decimal("3000"),
            stop_loss=Decimal("2900"),
            take_profit=Decimal("3200"),
            strategy="mean_reversion",
            regime="range",
        )
        p.close_position(pos2, Decimal("2900"), "stop_loss")

        m = compute_metrics(p.closed_trades, p.starting_balance)
        assert m["total_trades"] == 2
        assert m["winners"] == 1
        assert m["losers"] == 1
        assert m["win_rate_pct"] == "50.0%"
        assert "trend_following" in m["by_strategy"]
        assert "mean_reversion" in m["by_strategy"]
