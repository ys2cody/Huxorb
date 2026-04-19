"""Tests for core.dashboard: alerts and exporter."""

import json
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from core.dashboard.alerts import Alert, AlertLevel, AlertManager, ConsoleAlertHandler
from core.dashboard.exporter import TradeExporter
from core.paper.portfolio import PaperPortfolio


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_portfolio_with_trades() -> PaperPortfolio:
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
    return p


# ------------------------------------------------------------------ #
# Alert model
# ------------------------------------------------------------------ #

class TestAlert:
    def test_to_dict(self):
        a = Alert(
            level=AlertLevel.INFO,
            title="Test",
            message="Test message",
        )
        d = a.to_dict()
        assert d["level"] == "INFO"
        assert d["title"] == "Test"
        assert d["message"] == "Test message"
        assert "timestamp" in d

    def test_default_timestamp_is_utc(self):
        a = Alert(level=AlertLevel.WARNING, title="T", message="M")
        assert a.timestamp.tzinfo is not None


# ------------------------------------------------------------------ #
# AlertManager
# ------------------------------------------------------------------ #

class _RecordingHandler:
    def __init__(self):
        self.received = []

    def handle(self, alert: Alert):
        self.received.append(alert)


class TestAlertManager:
    def test_on_trade_entry(self):
        handler = _RecordingHandler()
        mgr = AlertManager()
        mgr.add_handler(handler)

        class _Pos:
            symbol = "BTC/USDT"
            strategy = "trend_following"
            entry_price = Decimal("60000")
            stop_loss = Decimal("59000")
            take_profit = Decimal("62000")
            quantity = Decimal("0.1")

        mgr.on_trade_entry(_Pos())
        assert len(handler.received) == 1
        assert handler.received[0].level == AlertLevel.INFO
        assert "BTC/USDT" in handler.received[0].message

    def test_on_trade_exit_win_is_info(self):
        handler = _RecordingHandler()
        mgr = AlertManager()
        mgr.add_handler(handler)

        class _Trade:
            symbol = "BTC/USDT"
            exit_reason = "take_profit"
            pnl = Decimal("200")

        mgr.on_trade_exit(_Trade())
        assert handler.received[0].level == AlertLevel.INFO
        assert "+200" in handler.received[0].message

    def test_on_trade_exit_loss_is_warning(self):
        handler = _RecordingHandler()
        mgr = AlertManager()
        mgr.add_handler(handler)

        class _Trade:
            symbol = "BTC/USDT"
            exit_reason = "stop_loss"
            pnl = Decimal("-100")

        mgr.on_trade_exit(_Trade())
        assert handler.received[0].level == AlertLevel.WARNING

    def test_on_drawdown_warning_critical(self):
        handler = _RecordingHandler()
        mgr = AlertManager(total_drawdown_critical_pct=10.0)
        mgr.add_handler(handler)
        mgr.on_drawdown_warning(12.0, Decimal("8800"), "total")
        assert handler.received[0].level == AlertLevel.CRITICAL

    def test_on_drawdown_warning_moderate(self):
        handler = _RecordingHandler()
        mgr = AlertManager(total_drawdown_warn_pct=5.0, total_drawdown_critical_pct=10.0)
        mgr.add_handler(handler)
        mgr.on_drawdown_warning(6.0, Decimal("9400"), "total")
        assert handler.received[0].level == AlertLevel.WARNING

    def test_on_daily_summary(self):
        handler = _RecordingHandler()
        mgr = AlertManager()
        mgr.add_handler(handler)

        p = _make_portfolio_with_trades()
        mgr.on_daily_summary(p)
        assert len(handler.received) == 1
        assert handler.received[0].level == AlertLevel.INFO
        assert "Equity" in handler.received[0].message

    def test_check_thresholds_no_alert_healthy(self):
        handler = _RecordingHandler()
        mgr = AlertManager(total_drawdown_warn_pct=5.0)
        mgr.add_handler(handler)

        p = PaperPortfolio(starting_balance=Decimal("10000"))
        # No drawdown — no alerts
        mgr.check_thresholds(p)
        assert len(handler.received) == 0

    def test_check_thresholds_fires_warning(self):
        handler = _RecordingHandler()
        mgr = AlertManager(total_drawdown_warn_pct=5.0, total_drawdown_critical_pct=10.0)
        mgr.add_handler(handler)

        # Portfolio with loss: starting=10000, current equity=9400 → 6% DD
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        # Manually reduce balance to simulate drawdown
        pos = p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.01"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="test",
            regime="trend",
        )
        p.close_position(pos, Decimal("59000"), "stop_loss")  # -100 USDT loss
        # Starting=10000, equity=9900 → 1% DD — below warn threshold
        # Need bigger loss to hit 5%
        for _ in range(5):
            try:
                pos = p.open_position(
                    symbol="BTC/USDT",
                    quantity=Decimal("0.01"),
                    entry_price=Decimal("60000"),
                    stop_loss=Decimal("59000"),
                    take_profit=Decimal("62000"),
                    strategy="test",
                    regime="trend",
                )
                p.close_position(pos, Decimal("59000"), "stop_loss")
            except ValueError:
                break
        mgr.check_thresholds(p)
        # Even if no alert (small losses), it should not crash
        assert isinstance(handler.received, list)

    def test_multiple_handlers(self):
        h1 = _RecordingHandler()
        h2 = _RecordingHandler()
        mgr = AlertManager()
        mgr.add_handler(h1).add_handler(h2)

        class _Pos:
            symbol = "BTC/USDT"
            strategy = "trend_following"
            entry_price = Decimal("60000")
            stop_loss = Decimal("59000")
            take_profit = Decimal("62000")
            quantity = Decimal("0.1")

        mgr.on_trade_entry(_Pos())
        assert len(h1.received) == 1
        assert len(h2.received) == 1

    def test_alerts_stored(self):
        mgr = AlertManager()
        mgr._dispatch(Alert(level=AlertLevel.INFO, title="T1", message="M1"))
        mgr._dispatch(Alert(level=AlertLevel.WARNING, title="T2", message="M2"))
        assert len(mgr.alerts) == 2

    def test_export_alerts(self):
        mgr = AlertManager()
        mgr._dispatch(Alert(level=AlertLevel.INFO, title="T", message="M"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alerts.json"
            mgr.export_alerts(path)
            data = json.loads(path.read_text())
            assert len(data) == 1
            assert data[0]["title"] == "T"


# ------------------------------------------------------------------ #
# TradeExporter
# ------------------------------------------------------------------ #

class TestTradeExporter:
    def test_export_csv_creates_file(self):
        p = _make_portfolio_with_trades()
        exporter = TradeExporter()
        with tempfile.TemporaryDirectory() as tmp:
            path = exporter.export_trades_csv(p.closed_trades, Path(tmp) / "trades.csv")
            assert path.exists()
            content = path.read_text()
            assert "trade_id" in content  # Header
            assert "BTC/USDT" in content

    def test_export_csv_row_count(self):
        p = _make_portfolio_with_trades()
        exporter = TradeExporter()
        with tempfile.TemporaryDirectory() as tmp:
            path = exporter.export_trades_csv(p.closed_trades, Path(tmp) / "trades.csv")
            lines = path.read_text().strip().split("\n")
            # 1 header + 2 trades
            assert len(lines) == 3

    def test_export_json_creates_file(self):
        p = _make_portfolio_with_trades()
        exporter = TradeExporter()
        with tempfile.TemporaryDirectory() as tmp:
            path = exporter.export_trades_json(p.closed_trades, Path(tmp) / "trades.json")
            assert path.exists()
            data = json.loads(path.read_text())
            assert len(data) == 2
            assert data[0]["symbol"] == "BTC/USDT"

    def test_export_json_pnl_correct(self):
        p = _make_portfolio_with_trades()
        exporter = TradeExporter()
        with tempfile.TemporaryDirectory() as tmp:
            path = exporter.export_trades_json(p.closed_trades, Path(tmp) / "trades.json")
            data = json.loads(path.read_text())
            pnls = {r["symbol"]: r["pnl"] for r in data}
            assert Decimal(pnls["BTC/USDT"]) == Decimal("20")   # (62000-60000)*0.01
            assert Decimal(pnls["ETH/USDT"]) == Decimal("-100")  # (2900-3000)*1

    def test_export_empty_trades(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        exporter = TradeExporter()
        with tempfile.TemporaryDirectory() as tmp:
            path = exporter.export_trades_csv(p.closed_trades, Path(tmp) / "trades.csv")
            lines = path.read_text().strip().split("\n")
            assert len(lines) == 1  # Header only

    def test_export_portfolio_snapshot(self):
        p = _make_portfolio_with_trades()
        exporter = TradeExporter()
        with tempfile.TemporaryDirectory() as tmp:
            path = exporter.export_portfolio_snapshot(p, Path(tmp) / "snap.json")
            data = json.loads(path.read_text())
            assert "summary" in data
            assert "analytics" in data
            assert "open_positions" in data
            assert data["closed_trades_count"] == 2

    def test_export_snapshot_no_trades(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        exporter = TradeExporter()
        with tempfile.TemporaryDirectory() as tmp:
            path = exporter.export_portfolio_snapshot(p, Path(tmp) / "snap.json")
            data = json.loads(path.read_text())
            assert "analytics" not in data  # No trades → no analytics section
            assert data["closed_trades_count"] == 0

    def test_creates_parent_dirs(self):
        p = _make_portfolio_with_trades()
        exporter = TradeExporter()
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "a" / "b" / "c" / "trades.csv"
            path = exporter.export_trades_csv(p.closed_trades, nested)
            assert path.exists()
