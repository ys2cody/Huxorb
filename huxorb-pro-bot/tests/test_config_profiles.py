"""Tests for core.ruleguard.config_profiles."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal

from core.ruleguard.config_profiles import ConfigProfiles, AccountProfile


def _dt(year=2026, month=4, day=14, hour=12, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestPresets:
    def test_default(self):
        c = ConfigProfiles.default()
        assert c.profile.profile_name == "DEFAULT"
        assert c.profile.risk_per_trade_pct == Decimal("0.5")

    def test_conservative_is_tighter(self):
        c = ConfigProfiles.conservative()
        d = ConfigProfiles.default()
        assert c.profile.risk_per_trade_pct <= d.profile.risk_per_trade_pct
        assert c.profile.max_open_trades <= d.profile.max_open_trades

    def test_aggressive_is_looser(self):
        a = ConfigProfiles.aggressive()
        d = ConfigProfiles.default()
        assert a.profile.risk_per_trade_pct >= d.profile.risk_per_trade_pct
        assert a.profile.max_trades_per_day >= d.profile.max_trades_per_day


class TestSeedDetermination:
    def test_same_inputs_same_seed(self):
        a = ConfigProfiles(profile=AccountProfile(
            profile_name="X", instance_id=1, account_group="G",
        ))
        b = ConfigProfiles(profile=AccountProfile(
            profile_name="X", instance_id=1, account_group="G",
        ))
        assert a._account_seed == b._account_seed

    def test_different_instance_different_seed(self):
        a = ConfigProfiles(profile=AccountProfile(
            profile_name="X", instance_id=1, account_group="G",
        ))
        b = ConfigProfiles(profile=AccountProfile(
            profile_name="X", instance_id=2, account_group="G",
        ))
        assert a._account_seed != b._account_seed


class TestJitter:
    def test_no_jitter_when_disabled(self):
        c = ConfigProfiles(profile=AccountProfile(
            entry_delay_jitter_sec=0, entry_delay_base_sec=0,
        ))
        assert c.calculate_entry_delay_sec(now=_dt()) == 0

    def test_base_delay_always_applied(self):
        c = ConfigProfiles(profile=AccountProfile(
            entry_delay_jitter_sec=0, entry_delay_base_sec=5,
        ))
        assert c.calculate_entry_delay_sec(now=_dt()) == 5

    def test_jitter_within_bounds(self):
        c = ConfigProfiles(profile=AccountProfile(
            entry_delay_jitter_sec=30, entry_delay_base_sec=0,
        ))
        delay = c.calculate_entry_delay_sec(now=_dt())
        assert 0 <= delay <= 30

    def test_jitter_stable_within_5min(self):
        c = ConfigProfiles(profile=AccountProfile(
            entry_delay_jitter_sec=30,
        ))
        a = c.calculate_entry_delay_sec(now=_dt(hour=12, minute=0))
        b = c.calculate_entry_delay_sec(now=_dt(hour=12, minute=1))
        c_val = c.calculate_entry_delay_sec(now=_dt(hour=12, minute=4))
        assert a == b == c_val

    def test_should_delay_entry(self):
        c = ConfigProfiles(profile=AccountProfile(
            entry_delay_jitter_sec=0, entry_delay_base_sec=30,
        ))
        signal = _dt(hour=12, minute=0)
        # 10 seconds later: should still need 20s
        later = signal + timedelta(seconds=10)
        remaining = c.should_delay_entry(signal, now=later)
        assert remaining == 20

        # 35s later: no wait
        past = signal + timedelta(seconds=35)
        assert c.should_delay_entry(signal, now=past) == 0
