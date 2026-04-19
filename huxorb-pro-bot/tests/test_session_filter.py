"""Tests for core.ruleguard.session_filter."""

from datetime import datetime, timezone

import pytest

from core.ruleguard.session_filter import SessionFilter, TradingSession


def _dt(year=2026, month=4, day=14, hour=12, minute=0) -> datetime:
    # 2026-04-14 is a Tuesday (isoweekday=2)
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestTradingSession:
    def test_simple_window(self):
        s = TradingSession(
            name="US", start_hour=13, start_minute=30,
            end_hour=20, end_minute=0, days={1, 2, 3, 4, 5},
        )
        assert s.contains(_dt(hour=14))
        assert not s.contains(_dt(hour=13, minute=29))
        assert not s.contains(_dt(hour=20))

    def test_day_mask(self):
        s = TradingSession(
            name="weekdays", start_hour=0, start_minute=0,
            end_hour=24, end_minute=0, days={1, 2, 3, 4, 5},
        )
        # Saturday = isoweekday 6
        saturday = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
        assert not s.contains(saturday)

    def test_crosses_midnight(self):
        s = TradingSession(
            name="overnight", start_hour=22, start_minute=0,
            end_hour=2, end_minute=0, days={1, 2, 3, 4, 5, 6, 7},
        )
        assert s.crosses_midnight
        assert s.contains(_dt(hour=23))
        assert s.contains(_dt(hour=1))
        assert not s.contains(_dt(hour=3))

    def test_disabled_never_matches(self):
        s = TradingSession(
            name="off", start_hour=0, start_minute=0,
            end_hour=24, end_minute=0, days={1, 2, 3, 4, 5, 6, 7},
            enabled=False,
        )
        assert not s.contains(_dt())

    def test_invalid_hour(self):
        with pytest.raises(ValueError):
            TradingSession(name="x", start_hour=25, start_minute=0,
                           end_hour=10, end_minute=0)

    def test_invalid_day(self):
        with pytest.raises(ValueError):
            TradingSession(name="x", start_hour=0, start_minute=0,
                           end_hour=10, end_minute=0, days={8})


class TestSessionFilter:
    def test_all_day(self):
        f = SessionFilter.all_day()
        ok, name = f.is_in_session(now=_dt(hour=3))
        assert ok
        assert name == "24/7"

    def test_empty_without_allow_is_closed(self):
        f = SessionFilter()
        ok, _ = f.is_in_session(now=_dt())
        assert not ok

    def test_weekdays_only_blocks_saturday(self):
        f = SessionFilter.weekdays_only()
        sat = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
        ok, _ = f.is_in_session(now=sat)
        assert not ok

    def test_weekdays_only_allows_tuesday(self):
        f = SessionFilter.weekdays_only()
        ok, _ = f.is_in_session(now=_dt())
        assert ok

    def test_us_hours_preset(self):
        f = SessionFilter.us_hours()
        assert f.is_in_session(now=_dt(hour=14))[0]
        assert not f.is_in_session(now=_dt(hour=10))[0]
        assert not f.is_in_session(now=_dt(hour=21))[0]

    def test_multiple_sessions_ORd(self):
        f = SessionFilter()
        f.add_session(TradingSession(
            name="A", start_hour=1, start_minute=0,
            end_hour=2, end_minute=0, days={1, 2, 3, 4, 5, 6, 7},
        ))
        f.add_session(TradingSession(
            name="B", start_hour=15, start_minute=0,
            end_hour=16, end_minute=0, days={1, 2, 3, 4, 5, 6, 7},
        ))
        assert f.is_in_session(now=_dt(hour=1, minute=30))[0]
        assert f.is_in_session(now=_dt(hour=15, minute=30))[0]
        assert not f.is_in_session(now=_dt(hour=10))[0]

    def test_returns_matching_session_name(self):
        f = SessionFilter.us_hours()
        _, name = f.is_in_session(now=_dt(hour=14))
        assert name == "us_hours"
