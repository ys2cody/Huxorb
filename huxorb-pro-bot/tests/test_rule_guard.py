"""Tests for core.ruleguard.rule_guard (orchestrator)."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from core.ruleguard import (
    RuleGuard,
    RiskManager,
    SessionFilter,
    TradingSession,
    NewsFilter,
    ConfigProfiles,
    RuleGuardReason,
)


def _dt(year=2026, month=4, day=14, hour=12, minute=0) -> datetime:
    # Tuesday
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _build_guard(**overrides) -> RuleGuard:
    """Build a guard with permissive defaults."""
    risk = overrides.pop("risk", RiskManager(
        starting_balance=Decimal("10000"),
        risk_per_trade_pct=Decimal("1"),
        max_quantity=Decimal("1"),
        max_open_trades=3,
        max_trades_per_day=10,
    ))
    sessions = overrides.pop("sessions", SessionFilter.all_day())
    news = overrides.pop("news", NewsFilter(enabled=False))
    config = overrides.pop("config", ConfigProfiles.default())
    dry_run = overrides.pop("dry_run", False)
    return RuleGuard(risk, sessions, news, config, dry_run=dry_run)


def _good_order():
    return dict(
        symbol="BTC/USDT",
        side="buy",
        quantity=Decimal("0.01"),
        entry_price=Decimal("60000"),
        stop_loss=Decimal("59400"),
        take_profit=Decimal("61500"),
    )


class TestHappyPath:
    def test_allows_valid_buy(self):
        g = _build_guard()
        d = g.can_open_trade(**_good_order(), now=_dt())
        assert d.allowed, d.detail
        assert d.reason == RuleGuardReason.OK

    def test_allows_valid_sell(self):
        g = _build_guard()
        d = g.can_open_trade(
            symbol="BTC/USDT", side="sell",
            quantity=Decimal("0.01"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("60600"),
            take_profit=Decimal("58500"),
            now=_dt(),
        )
        assert d.allowed, d.detail


class TestDryRun:
    def test_dry_run_blocks_open(self):
        g = _build_guard(dry_run=True)
        d = g.can_open_trade(**_good_order(), now=_dt())
        assert not d.allowed
        assert d.reason == RuleGuardReason.DRY_RUN_MODE

    def test_dry_run_blocks_modify(self):
        g = _build_guard(dry_run=True)
        d = g.can_modify_stops(order_id="123", new_stop_loss=Decimal("59000"))
        assert not d.allowed
        assert d.reason == RuleGuardReason.DRY_RUN_MODE

    def test_dry_run_blocks_close(self):
        g = _build_guard(dry_run=True)
        d = g.can_close_trade(order_id="123")
        assert not d.allowed
        assert d.reason == RuleGuardReason.DRY_RUN_MODE


class TestParamValidation:
    def test_wrong_sl_side_buy(self):
        g = _build_guard()
        o = _good_order()
        o["stop_loss"] = Decimal("60500")  # above entry on a buy
        d = g.can_open_trade(**o, now=_dt())
        assert not d.allowed
        assert d.reason == RuleGuardReason.WRONG_SL_SIDE

    def test_wrong_tp_side_sell(self):
        g = _build_guard()
        d = g.can_open_trade(
            symbol="BTC/USDT", side="sell",
            quantity=Decimal("0.01"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("61000"),
            take_profit=Decimal("62000"),  # TP above entry on sell
            now=_dt(),
        )
        assert not d.allowed
        assert d.reason == RuleGuardReason.WRONG_TP_SIDE

    def test_invalid_side(self):
        g = _build_guard()
        d = g.can_open_trade(
            symbol="BTC/USDT", side="bogus",
            quantity=Decimal("0.01"), entry_price=Decimal("60000"),
            now=_dt(),
        )
        assert not d.allowed
        assert d.reason == RuleGuardReason.INVALID_PARAMS

    def test_invalid_entry(self):
        g = _build_guard()
        d = g.can_open_trade(
            symbol="BTC/USDT", side="buy",
            quantity=Decimal("0.01"), entry_price=Decimal("0"),
            now=_dt(),
        )
        assert not d.allowed
        assert d.reason == RuleGuardReason.INVALID_PRICE

    def test_sl_too_close(self):
        g = _build_guard()
        o = _good_order()
        o["stop_loss"] = Decimal("59999")  # 0.00167% away - too tight
        d = g.can_open_trade(**o, now=_dt())
        assert not d.allowed
        assert d.reason == RuleGuardReason.SL_TP_TOO_CLOSE


class TestForbiddenParams:
    def test_leverage_blocked(self):
        g = _build_guard()
        d = g.can_open_trade(
            **_good_order(),
            params={"leverage": 10},
            now=_dt(),
        )
        assert not d.allowed
        assert d.reason == RuleGuardReason.FORBIDDEN_PARAM

    def test_margin_blocked(self):
        g = _build_guard()
        d = g.can_open_trade(
            **_good_order(),
            params={"marginMode": "isolated"},
            now=_dt(),
        )
        assert not d.allowed
        assert d.reason == RuleGuardReason.FORBIDDEN_PARAM

    def test_reduce_only_blocked(self):
        g = _build_guard()
        d = g.can_open_trade(
            **_good_order(),
            params={"reduceOnly": True},
            now=_dt(),
        )
        assert not d.allowed
        assert d.reason == RuleGuardReason.FORBIDDEN_PARAM

    def test_benign_params_allowed(self):
        g = _build_guard()
        d = g.can_open_trade(
            **_good_order(),
            params={"timeInForce": "GTC", "clientOrderId": "abc"},
            now=_dt(),
        )
        assert d.allowed


class TestSessionIntegration:
    def test_blocks_outside_us_hours(self):
        # 3am UTC on tuesday - outside US
        g = _build_guard(sessions=SessionFilter.us_hours())
        d = g.can_open_trade(**_good_order(), now=_dt(hour=3))
        assert not d.allowed
        assert d.reason == RuleGuardReason.OUTSIDE_SESSION


class TestNewsIntegration:
    def test_blocks_during_fomc(self):
        news = NewsFilter(enabled=True)
        news.add_blackout(
            start=_dt(hour=11),
            end=_dt(hour=13),
            asset="USD",
            impact="HIGH",
            title="FOMC",
        )
        g = _build_guard(news=news)
        d = g.can_open_trade(**_good_order(), now=_dt(hour=12))
        assert not d.allowed
        assert d.reason == RuleGuardReason.NEWS_BLACKOUT

    def test_allows_outside_blackout(self):
        news = NewsFilter(enabled=True)
        news.add_blackout(
            start=_dt(hour=11), end=_dt(hour=12),
            asset="USD", impact="HIGH", title="FOMC",
        )
        g = _build_guard(news=news)
        d = g.can_open_trade(**_good_order(), now=_dt(hour=14))
        assert d.allowed


class TestRiskIntegration:
    def test_blocks_when_quantity_over_cap(self):
        risk = RiskManager(
            starting_balance=Decimal("10000"),
            max_quantity=Decimal("0.005"),
        )
        g = _build_guard(risk=risk)
        d = g.can_open_trade(**_good_order(), now=_dt())
        assert not d.allowed
        assert d.reason == RuleGuardReason.QUANTITY_CAP

    def test_blocks_after_max_trades(self):
        risk = RiskManager(
            starting_balance=Decimal("10000"),
            max_quantity=Decimal("1"),
            max_trades_per_day=1,
        )
        risk.increment_trade_count()
        g = _build_guard(risk=risk)
        d = g.can_open_trade(**_good_order(), now=_dt())
        assert not d.allowed
        assert d.reason == RuleGuardReason.MAX_TRADES_TODAY


class TestSpreadCheck:
    def test_blocks_wide_spread(self):
        g = _build_guard()
        d = g.can_open_trade(
            **_good_order(),
            bid=Decimal("60000"),
            ask=Decimal("61000"),  # ~1.67% spread
            now=_dt(),
        )
        assert not d.allowed
        assert d.reason == RuleGuardReason.SPREAD_TOO_HIGH

    def test_allows_tight_spread(self):
        g = _build_guard()
        d = g.can_open_trade(
            **_good_order(),
            bid=Decimal("60000"),
            ask=Decimal("60030"),  # 0.05% spread
            now=_dt(),
        )
        assert d.allowed


class TestJitter:
    def test_pending_signal_blocks_entry(self):
        cfg = ConfigProfiles(profile=ConfigProfiles.default().profile)
        cfg.profile.entry_delay_base_sec = 30
        cfg.profile.entry_delay_jitter_sec = 0
        g = _build_guard(config=cfg)
        signal = _dt()
        g.register_signal(signal)
        d = g.can_open_trade(
            **_good_order(),
            now=signal + timedelta(seconds=10),
        )
        assert not d.allowed
        assert d.reason == RuleGuardReason.ENTRY_DELAY_JITTER

    def test_after_delay_allows(self):
        cfg = ConfigProfiles(profile=ConfigProfiles.default().profile)
        cfg.profile.entry_delay_base_sec = 5
        cfg.profile.entry_delay_jitter_sec = 0
        g = _build_guard(config=cfg)
        signal = _dt()
        g.register_signal(signal)
        d = g.can_open_trade(
            **_good_order(),
            now=signal + timedelta(seconds=10),
        )
        assert d.allowed


class TestStatus:
    def test_status_snapshot(self):
        g = _build_guard()
        s = g.status(symbol="BTC/USDT", now=_dt())
        assert s.trading_enabled
        assert s.in_session
        assert not s.in_news_blackout
        assert s.current_balance == Decimal("10000")
