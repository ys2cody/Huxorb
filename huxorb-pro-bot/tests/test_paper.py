"""Tests for the paper trading module."""

import json
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from core.paper.portfolio import PaperPortfolio, PaperPosition, PaperTrade


# ------------------------------------------------------------------ #
# PaperPosition tests
# ------------------------------------------------------------------ #

class TestPaperPosition:
    def _make_position(self, **overrides) -> PaperPosition:
        defaults = dict(
            position_id=1,
            symbol="BTC/USDT",
            side="buy",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            entry_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        defaults.update(overrides)
        return PaperPosition(**defaults)

    def test_unrealized_pnl_profit(self):
        pos = self._make_position()
        pnl = pos.unrealized_pnl(Decimal("61000"))
        assert pnl == Decimal("100")  # (61000-60000) * 0.1

    def test_unrealized_pnl_loss(self):
        pos = self._make_position()
        pnl = pos.unrealized_pnl(Decimal("59500"))
        assert pnl == Decimal("-50")  # (59500-60000) * 0.1

    def test_unrealized_pnl_flat(self):
        pos = self._make_position()
        pnl = pos.unrealized_pnl(Decimal("60000"))
        assert pnl == Decimal("0")

    def test_to_dict_roundtrip(self):
        pos = self._make_position()
        d = pos.to_dict()
        restored = PaperPosition.from_dict(d)
        assert restored.position_id == pos.position_id
        assert restored.symbol == pos.symbol
        assert restored.quantity == pos.quantity
        assert restored.entry_price == pos.entry_price
        assert restored.stop_loss == pos.stop_loss
        assert restored.take_profit == pos.take_profit
        assert restored.strategy == pos.strategy
        assert restored.regime == pos.regime


# ------------------------------------------------------------------ #
# PaperTrade tests
# ------------------------------------------------------------------ #

class TestPaperTrade:
    def _make_trade(self, **overrides) -> PaperTrade:
        defaults = dict(
            trade_id=1,
            symbol="BTC/USDT",
            strategy="trend_following",
            regime="trend",
            entry_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
            entry_price=Decimal("60000"),
            exit_time=datetime(2025, 6, 2, tzinfo=timezone.utc),
            exit_price=Decimal("62000"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            exit_reason="take_profit",
            pnl=Decimal("200"),
        )
        defaults.update(overrides)
        return PaperTrade(**defaults)

    def test_to_dict_roundtrip(self):
        trade = self._make_trade()
        d = trade.to_dict()
        restored = PaperTrade.from_dict(d)
        assert restored.trade_id == trade.trade_id
        assert restored.pnl == trade.pnl
        assert restored.exit_reason == trade.exit_reason
        assert restored.symbol == trade.symbol
        assert restored.quantity == trade.quantity


# ------------------------------------------------------------------ #
# PaperPortfolio tests
# ------------------------------------------------------------------ #

class TestPaperPortfolio:
    def test_initial_state(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        assert p.balance == Decimal("10000")
        assert p.open_positions == []
        assert p.closed_trades == []
        assert p.total_pnl == Decimal("0")

    def test_open_position(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        pos = p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        assert pos.position_id == 1
        assert pos.symbol == "BTC/USDT"
        assert len(p.open_positions) == 1
        # Balance reduced by cost: 0.1 * 60000 = 6000
        assert p.balance == Decimal("4000")

    def test_open_position_insufficient_balance(self):
        p = PaperPortfolio(starting_balance=Decimal("1000"))
        with pytest.raises(ValueError, match="Insufficient balance"):
            p.open_position(
                symbol="BTC/USDT",
                quantity=Decimal("0.1"),
                entry_price=Decimal("60000"),
                stop_loss=Decimal("59000"),
                take_profit=Decimal("62000"),
                strategy="trend_following",
                regime="trend",
            )

    def test_close_position(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        pos = p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        trade = p.close_position(pos, Decimal("62000"), "take_profit")
        assert trade.pnl == Decimal("200")  # (62000-60000)*0.1
        assert len(p.open_positions) == 0
        assert len(p.closed_trades) == 1
        # Balance: 4000 + 0.1*62000 = 4000 + 6200 = 10200
        assert p.balance == Decimal("10200")

    def test_close_position_loss(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        pos = p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        trade = p.close_position(pos, Decimal("59000"), "stop_loss")
        assert trade.pnl == Decimal("-100")  # (59000-60000)*0.1
        assert p.balance == Decimal("9900")  # 4000 + 0.1*59000

    def test_check_exits_stop_loss(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        # Price hits stop loss
        closed = p.check_exits({"BTC/USDT": Decimal("58500")})
        assert len(closed) == 1
        assert closed[0].exit_reason == "stop_loss"
        assert closed[0].exit_price == Decimal("59000")
        assert len(p.open_positions) == 0

    def test_check_exits_take_profit(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        # Price hits take profit
        closed = p.check_exits({"BTC/USDT": Decimal("63000")})
        assert len(closed) == 1
        assert closed[0].exit_reason == "take_profit"
        assert closed[0].exit_price == Decimal("62000")

    def test_check_exits_no_hit(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        # Price between SL and TP
        closed = p.check_exits({"BTC/USDT": Decimal("60500")})
        assert len(closed) == 0
        assert len(p.open_positions) == 1

    def test_check_exits_no_price(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        # No price for this symbol
        closed = p.check_exits({"ETH/USDT": Decimal("3000")})
        assert len(closed) == 0
        assert len(p.open_positions) == 1

    def test_equity_no_positions(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        eq = p.equity({})
        assert eq == Decimal("10000")

    def test_equity_with_position(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        # Cash=4000, position MTM=0.1*61000=6100
        eq = p.equity({"BTC/USDT": Decimal("61000")})
        assert eq == Decimal("10100")

    def test_equity_position_no_price_uses_entry(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        # No price provided — falls back to entry price
        eq = p.equity({})
        assert eq == Decimal("10000")  # 4000 + 0.1*60000

    def test_total_pnl(self):
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

        # PnL: +20 - 100 = -80
        assert p.total_pnl == Decimal("-80")

    def test_summary(self):
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        pos = p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.01"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        p.close_position(pos, Decimal("62000"), "take_profit")

        s = p.summary()
        assert s["total_trades"] == 1
        assert s["winners"] == 1
        assert s["losers"] == 0
        assert s["win_rate"] == "100.0%"
        assert s["total_pnl"] == "20.00"

    def test_multiple_positions(self):
        p = PaperPortfolio(starting_balance=Decimal("100000"))
        pos1 = p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="trend_following",
            regime="trend",
        )
        pos2 = p.open_position(
            symbol="ETH/USDT",
            quantity=Decimal("10"),
            entry_price=Decimal("3000"),
            stop_loss=Decimal("2900"),
            take_profit=Decimal("3200"),
            strategy="mean_reversion",
            regime="range",
        )
        assert len(p.open_positions) == 2
        # Balance: 100000 - 6000 - 30000 = 64000
        assert p.balance == Decimal("64000")

        # Check exits: BTC hits TP, ETH hits SL
        closed = p.check_exits({
            "BTC/USDT": Decimal("63000"),
            "ETH/USDT": Decimal("2800"),
        })
        assert len(closed) == 2
        assert len(p.open_positions) == 0

    def test_position_id_increment(self):
        p = PaperPortfolio(starting_balance=Decimal("100000"))
        pos1 = p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.01"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="test",
            regime="trend",
        )
        pos2 = p.open_position(
            symbol="ETH/USDT",
            quantity=Decimal("1"),
            entry_price=Decimal("3000"),
            stop_loss=Decimal("2900"),
            take_profit=Decimal("3200"),
            strategy="test",
            regime="range",
        )
        assert pos1.position_id == 1
        assert pos2.position_id == 2


# ------------------------------------------------------------------ #
# JSON persistence tests
# ------------------------------------------------------------------ #

class TestPaperPortfolioPersistence:
    def test_save_and_load_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            p1 = PaperPortfolio(starting_balance=Decimal("10000"), state_file=state_file)
            p1._save_state()

            p2 = PaperPortfolio(starting_balance=Decimal("5000"), state_file=state_file)
            # Should load the saved state, overriding the 5000 balance
            assert p2.balance == Decimal("10000")

    def test_save_and_load_with_positions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            p1 = PaperPortfolio(starting_balance=Decimal("10000"), state_file=state_file)
            p1.open_position(
                symbol="BTC/USDT",
                quantity=Decimal("0.1"),
                entry_price=Decimal("60000"),
                stop_loss=Decimal("59000"),
                take_profit=Decimal("62000"),
                strategy="trend_following",
                regime="trend",
            )

            # Reload from disk
            p2 = PaperPortfolio(state_file=state_file)
            assert len(p2.open_positions) == 1
            assert p2.open_positions[0].symbol == "BTC/USDT"
            assert p2.open_positions[0].quantity == Decimal("0.1")
            assert p2.balance == Decimal("4000")

    def test_save_and_load_with_trades(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            p1 = PaperPortfolio(starting_balance=Decimal("10000"), state_file=state_file)
            pos = p1.open_position(
                symbol="BTC/USDT",
                quantity=Decimal("0.1"),
                entry_price=Decimal("60000"),
                stop_loss=Decimal("59000"),
                take_profit=Decimal("62000"),
                strategy="trend_following",
                regime="trend",
            )
            p1.close_position(pos, Decimal("62000"), "take_profit")

            # Reload
            p2 = PaperPortfolio(state_file=state_file)
            assert len(p2.closed_trades) == 1
            assert p2.closed_trades[0].pnl == Decimal("200")
            assert p2.balance == Decimal("10200")
            assert len(p2.open_positions) == 0

    def test_next_id_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            p1 = PaperPortfolio(starting_balance=Decimal("100000"), state_file=state_file)
            p1.open_position(
                symbol="BTC/USDT",
                quantity=Decimal("0.01"),
                entry_price=Decimal("60000"),
                stop_loss=Decimal("59000"),
                take_profit=Decimal("62000"),
                strategy="test",
                regime="trend",
            )
            p1.open_position(
                symbol="ETH/USDT",
                quantity=Decimal("1"),
                entry_price=Decimal("3000"),
                stop_loss=Decimal("2900"),
                take_profit=Decimal("3200"),
                strategy="test",
                regime="range",
            )

            # Reload and open another position
            p2 = PaperPortfolio(state_file=state_file)
            pos3 = p2.open_position(
                symbol="SOL/USDT",
                quantity=Decimal("10"),
                entry_price=Decimal("150"),
                stop_loss=Decimal("145"),
                take_profit=Decimal("160"),
                strategy="test",
                regime="trend",
            )
            assert pos3.position_id == 3

    def test_no_state_file_no_error(self):
        """Portfolio without state_file should work, just not persist."""
        p = PaperPortfolio(starting_balance=Decimal("10000"))
        pos = p.open_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.01"),
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            strategy="test",
            regime="trend",
        )
        p.close_position(pos, Decimal("62000"), "take_profit")
        assert len(p.closed_trades) == 1

    def test_state_file_json_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            p = PaperPortfolio(starting_balance=Decimal("10000"), state_file=state_file)
            p.open_position(
                symbol="BTC/USDT",
                quantity=Decimal("0.1"),
                entry_price=Decimal("60000"),
                stop_loss=Decimal("59000"),
                take_profit=Decimal("62000"),
                strategy="trend_following",
                regime="trend",
            )

            data = json.loads(state_file.read_text())
            assert "starting_balance" in data
            assert "balance" in data
            assert "next_id" in data
            assert "positions" in data
            assert "trades" in data
            assert len(data["positions"]) == 1
