"""Tests for core.ruleguard.news_filter."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from core.ruleguard.news_filter import NewsFilter, NewsEvent, _split_symbol


def _dt(year=2026, month=4, day=14, hour=12, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestSymbolSplit:
    def test_slash_format(self):
        assert _split_symbol("BTC/USDT") == ("BTC", "USDT")

    def test_no_slash(self):
        assert _split_symbol("BTCUSDT") == ("BTC", "USDT")

    def test_eth_usd(self):
        assert _split_symbol("ETHUSDC") == ("ETH", "USDC")

    def test_btc_quote(self):
        assert _split_symbol("ETH/BTC") == ("ETH", "BTC")


class TestNewsEventAffectsSymbol:
    def test_quote_match(self):
        e = NewsEvent(
            event_time_utc=_dt(), asset="USDT", impact="HIGH", title="t",
            blackout_start=_dt(hour=11), blackout_end=_dt(hour=13),
        )
        assert e.affects_symbol("BTC/USDT")

    def test_base_match(self):
        e = NewsEvent(
            event_time_utc=_dt(), asset="BTC", impact="HIGH", title="Halving",
            blackout_start=_dt(hour=11), blackout_end=_dt(hour=13),
        )
        assert e.affects_symbol("BTC/USDT")
        assert not e.affects_symbol("ETH/USDT")

    def test_usd_covers_all_stablecoins(self):
        e = NewsEvent(
            event_time_utc=_dt(), asset="USD", impact="HIGH", title="FOMC",
            blackout_start=_dt(hour=11), blackout_end=_dt(hour=13),
        )
        assert e.affects_symbol("BTC/USDT")
        assert e.affects_symbol("ETH/USDC")
        assert e.affects_symbol("SOL/BUSD")
        assert not e.affects_symbol("ETH/BTC")

    def test_invalid_impact_rejected(self):
        with pytest.raises(ValueError):
            NewsEvent(
                event_time_utc=_dt(), asset="USD", impact="FOO", title="t",
                blackout_start=_dt(hour=11), blackout_end=_dt(hour=13),
            )

    def test_end_before_start_rejected(self):
        with pytest.raises(ValueError):
            NewsEvent(
                event_time_utc=_dt(), asset="USD", impact="HIGH", title="t",
                blackout_start=_dt(hour=13), blackout_end=_dt(hour=11),
            )


class TestNewsFilter:
    def test_disabled_never_blocks(self):
        f = NewsFilter(enabled=False)
        block, _ = f.is_blackout("BTC/USDT", now=_dt())
        assert not block

    def test_manual_blackout_blocks(self):
        f = NewsFilter(enabled=True)
        f.add_blackout(
            start=_dt(hour=11),
            end=_dt(hour=13),
            asset="USD",
            impact="HIGH",
            title="FOMC",
        )
        block, detail = f.is_blackout("BTC/USDT", now=_dt(hour=12))
        assert block
        assert "FOMC" in detail

    def test_outside_window_not_blocked(self):
        f = NewsFilter(enabled=True)
        f.add_blackout(
            start=_dt(hour=11), end=_dt(hour=12),
            asset="USD", impact="HIGH", title="FOMC",
        )
        block, _ = f.is_blackout("BTC/USDT", now=_dt(hour=13))
        assert not block

    def test_symbol_filter_skips_unaffected(self):
        f = NewsFilter(enabled=True, filter_by_symbol=True)
        f.add_blackout(
            start=_dt(hour=11), end=_dt(hour=13),
            asset="EUR", impact="HIGH", title="ECB",
        )
        block, _ = f.is_blackout("BTC/USDT", now=_dt(hour=12))
        assert not block

    def test_high_impact_only(self):
        f = NewsFilter(enabled=True, high_impact_only=True)
        f.add_blackout(
            start=_dt(hour=11), end=_dt(hour=13),
            asset="USD", impact="MEDIUM", title="Beige Book",
        )
        block, _ = f.is_blackout("BTC/USDT", now=_dt(hour=12))
        assert not block

    def test_next_event(self):
        f = NewsFilter(enabled=True)
        f.add_blackout(
            start=_dt(hour=15), end=_dt(hour=16),
            asset="USD", impact="HIGH", title="CPI",
        )
        f.add_blackout(
            start=_dt(hour=20), end=_dt(hour=21),
            asset="USD", impact="HIGH", title="FOMC",
        )
        nxt = f.next_event("BTC/USDT", now=_dt(hour=12))
        assert nxt is not None
        assert nxt.title == "CPI"

    def test_csv_loading(self, tmp_path: Path):
        csv_file = tmp_path / "cal.csv"
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        csv_file.write_text(
            "datetime_utc,asset,impact,title\n"
            f"{future.strftime('%Y-%m-%d %H:%M:%S')},USD,HIGH,FOMC\n"
        )
        f = NewsFilter(enabled=True, csv_path=csv_file)
        assert f.event_count == 1

    def test_csv_skips_past(self, tmp_path: Path):
        csv_file = tmp_path / "cal.csv"
        past = datetime.now(timezone.utc) - timedelta(days=2)
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        csv_file.write_text(
            "datetime_utc,asset,impact,title\n"
            f"{past.strftime('%Y-%m-%d %H:%M:%S')},USD,HIGH,OldEvent\n"
            f"{future.strftime('%Y-%m-%d %H:%M:%S')},USD,HIGH,FutureEvent\n"
        )
        f = NewsFilter(enabled=True, csv_path=csv_file)
        assert f.event_count == 1
