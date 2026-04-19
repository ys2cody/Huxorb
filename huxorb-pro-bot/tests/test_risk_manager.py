"""Tests for core.ruleguard.risk_manager."""

from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest

from core.ruleguard.risk_manager import RiskManager
from core.ruleguard.reasons import RuleGuardReason


def _risk(**overrides) -> RiskManager:
    defaults = dict(
        starting_balance=Decimal("10000"),
        risk_per_trade_pct=Decimal("1.0"),
        max_quantity=Decimal("100"),
        max_open_trades=2,
        max_trades_per_day=3,
        daily_loss_limit_pct=Decimal("5.0"),
        max_drawdown_pct=Decimal("10.0"),
    )
    defaults.update(overrides)
    return RiskManager(**defaults)


class TestConstruction:
    def test_valid_construction(self):
        r = _risk()
        assert r.current_balance == Decimal("10000")
        assert r.trading_enabled is True
        assert r.trades_today == 0

    def test_negative_starting_balance_rejected(self):
        with pytest.raises(ValueError):
            _risk(starting_balance=Decimal("-1"))

    def test_zero_risk_pct_rejected(self):
        with pytest.raises(ValueError):
            _risk(risk_per_trade_pct=Decimal("0"))

    def test_risk_pct_over_100_rejected(self):
        with pytest.raises(ValueError):
            _risk(risk_per_trade_pct=Decimal("150"))

    def test_zero_max_open_trades_rejected(self):
        with pytest.raises(ValueError):
            _risk(max_open_trades=0)


class TestQuantityCalculation:
    def test_risks_exact_percent(self):
        # 1% risk of 10000 = 100 USDT.
        # SL distance 500 -> qty 100/500 = 0.2
        r = _risk(risk_per_trade_pct=Decimal("1.0"), max_quantity=Decimal("1000"))
        qty = r.calculate_quantity(Decimal("60000"), Decimal("59500"))
        assert qty == Decimal("0.2")

    def test_step_rounding_rounds_down(self):
        r = _risk(risk_per_trade_pct=Decimal("1.0"), max_quantity=Decimal("1000"))
        # 100/500 = 0.2; step 0.03 -> 0.18 (rounds down, never up)
        qty = r.calculate_quantity(
            Decimal("60000"), Decimal("59500"), step_size=Decimal("0.03")
        )
        assert qty == Decimal("0.18")

    def test_below_min_returns_zero(self):
        r = _risk(risk_per_trade_pct=Decimal("0.01"))
        # Tiny risk, huge SL -> qty below min
        qty = r.calculate_quantity(
            Decimal("60000"),
            Decimal("50000"),
            min_quantity=Decimal("0.01"),
        )
        assert qty == Decimal("0")

    def test_capped_at_max_quantity(self):
        r = _risk(risk_per_trade_pct=Decimal("50"), max_quantity=Decimal("0.5"))
        qty = r.calculate_quantity(Decimal("60000"), Decimal("59999"))
        assert qty == Decimal("0.5")

    def test_zero_sl_distance_returns_zero(self):
        r = _risk()
        qty = r.calculate_quantity(Decimal("60000"), Decimal("60000"))
        assert qty == Decimal("0")

    def test_negative_prices_rejected(self):
        r = _risk()
        with pytest.raises(ValueError):
            r.calculate_quantity(Decimal("-1"), Decimal("50"))


class TestCanOpenTrade:
    def test_allows_within_limits(self):
        r = _risk()
        ok, reason, _ = r.can_open_trade(Decimal("0.1"))
        assert ok
        assert reason == RuleGuardReason.OK

    def test_blocks_zero_quantity(self):
        r = _risk()
        ok, reason, _ = r.can_open_trade(Decimal("0"))
        assert not ok
        assert reason == RuleGuardReason.INVALID_QUANTITY

    def test_blocks_over_cap(self):
        r = _risk(max_quantity=Decimal("1"))
        ok, reason, _ = r.can_open_trade(Decimal("1.5"))
        assert not ok
        assert reason == RuleGuardReason.QUANTITY_CAP

    def test_blocks_max_trades_today(self):
        r = _risk(max_trades_per_day=2)
        r.increment_trade_count()
        r.increment_trade_count()
        ok, reason, _ = r.can_open_trade(Decimal("0.1"))
        assert not ok
        assert reason == RuleGuardReason.MAX_TRADES_TODAY

    def test_blocks_max_open_trades(self):
        r = _risk(max_open_trades=1)
        r.set_open_trades(1)
        ok, reason, _ = r.can_open_trade(Decimal("0.1"))
        assert not ok
        assert reason == RuleGuardReason.MAX_OPEN_TRADES


class TestDrawdown:
    def test_daily_dd_triggers_block(self):
        r = _risk(daily_loss_limit_pct=Decimal("5"))
        # Lose 6% of daily starting balance
        r.update_balance(Decimal("9400"))
        ok, reason, _ = r.can_open_trade(Decimal("0.1"))
        assert not ok
        assert reason == RuleGuardReason.DAILY_LOSS_LIMIT

    def test_max_dd_triggers_permanent_block(self):
        r = _risk(max_drawdown_pct=Decimal("10"))
        r.update_balance(Decimal("8900"))  # 11% drawdown
        assert r.trading_enabled is False
        assert r.total_drawdown_pct >= Decimal("10")

    def test_peak_tracks_upwards(self):
        r = _risk()
        r.update_balance(Decimal("12000"))
        r.update_balance(Decimal("11000"))
        assert r._peak_balance == Decimal("12000")
        assert r.total_drawdown_pct == pytest.approx(Decimal("8.333"), rel=Decimal("0.01"))

    def test_daily_pnl(self):
        r = _risk()
        r.update_balance(Decimal("10250"))
        assert r.daily_pnl == Decimal("250")


class TestProfitCap:
    def test_profit_cap_triggers(self):
        r = _risk(
            daily_profit_cap_pct=Decimal("40"),
            phase_target_amount=Decimal("1000"),
        )
        # daily profit >= 400
        r.update_balance(Decimal("10500"))
        assert r._daily_trading_enabled is False

    def test_no_cap_when_unset(self):
        r = _risk()
        r.update_balance(Decimal("12000"))
        assert r._daily_trading_enabled is True


class TestDayRollover:
    def test_new_day_resets_counters(self):
        r = _risk()
        r.increment_trade_count()
        assert r.trades_today == 1

        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        r.update_balance(Decimal("10100"), now=tomorrow)
        assert r.trades_today == 0
        assert r._daily_start_balance == Decimal("10100")
