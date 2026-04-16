"""Tests for live trading components."""

import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from core.live import LiveTradingConfig, OrderManager, OrderResult, OrderResultStatus
from core.live.order_manager import OrderManager


# ------------------------------------------------------------------ #
# LiveTradingConfig
# ------------------------------------------------------------------ #

class TestLiveTradingConfig:
    def test_from_env_missing_keys_raises(self):
        """Test that missing API keys raise ValueError."""
        with pytest.raises(ValueError, match="Missing KuCoin API credentials"):
            LiveTradingConfig(
                api_key="",
                api_secret="",
                passphrase="",
            )

    def test_from_env_with_file(self):
        """Test loading from .env file."""
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "KUCOIN_API_KEY=test_key\n"
                "KUCOIN_API_SECRET=test_secret\n"
                "KUCOIN_PASSPHRASE=test_pass\n"
                "KUCOIN_TESTNET=false\n"
                "DRY_RUN=false\n"
                "SYMBOLS=BTC/USDT\n"
                "STARTING_BALANCE=5000\n"
                "RISK_PER_TRADE_PCT=1.0\n"
            )

            config = LiveTradingConfig.from_env(env_file)
            assert config.api_key == "test_key"
            assert config.api_secret == "test_secret"
            assert config.passphrase == "test_pass"
            assert config.testnet is False
            assert config.dry_run is False
            assert config.symbols == ["BTC/USDT"]
            assert config.starting_balance == Decimal("5000")
            assert config.risk_per_trade_pct == Decimal("1.0")

    def test_default_values(self):
        """Test that defaults are applied."""
        config = LiveTradingConfig(
            api_key="k",
            api_secret="s",
            passphrase="p",
        )
        assert config.testnet is True  # Default
        assert config.dry_run is True  # Default
        assert config.symbols is None
        assert config.poll_interval_seconds == 3600

    def test_symbols_split_from_env(self):
        """Test that comma-separated symbols are split."""
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "KUCOIN_API_KEY=k\n"
                "KUCOIN_API_SECRET=s\n"
                "KUCOIN_PASSPHRASE=p\n"
                "SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT\n"
            )
            config = LiveTradingConfig.from_env(env_file)
            assert config.symbols == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


# ------------------------------------------------------------------ #
# OrderManager (mock connector tests)
# ------------------------------------------------------------------ #

class _MockConnector:
    """Minimal mock for KuCoinConnector."""
    def __init__(self, fail_order: bool = False):
        self.fail_order = fail_order
        self.orders_placed = []

    def get_market(self, symbol):
        class _M:
            active = True
            quote = "USDT"
            min_amount = Decimal("0.001")
        return _M()

    def get_ticker(self, symbol):
        class _T:
            ask = Decimal("60000")
        return _T()

    def get_balance(self, currency):
        class _B:
            free = Decimal("10000")
        return {currency: _B()}

    def create_market_order(self, symbol, side, quantity):
        if self.fail_order:
            raise Exception("Mock network error")
        class _O:
            id = "order_123"
            is_closed = False
        order = _O()
        self.orders_placed.append(("market", symbol, side, quantity))
        return order

    def create_stop_order(self, symbol, side, quantity, stop_price):
        if self.fail_order:
            raise Exception("Mock network error")
        class _O:
            id = "stop_456"
        order = _O()
        self.orders_placed.append(("stop", symbol, side, quantity, stop_price))
        return order

    def create_limit_order(self, symbol, side, quantity, price):
        if self.fail_order:
            raise Exception("Mock network error")
        class _O:
            id = "limit_789"
        order = _O()
        self.orders_placed.append(("limit", symbol, side, quantity, price))
        return order

    def get_order(self, order_id, symbol):
        class _O:
            is_closed = False
        return _O()

    def cancel_order(self, order_id, symbol):
        pass


class TestOrderManager:
    def test_place_entry_with_stops_dry_run(self):
        """Test that dry run logs but doesn't execute."""
        connector = _MockConnector()
        mgr = OrderManager(connector, dry_run=True)

        result = mgr.place_entry_with_stops(
            symbol="BTC/USDT",
            side="buy",
            quantity=Decimal("0.01"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
        )

        assert result.status == OrderResultStatus.SUCCESS
        assert result.order is None  # Dry run doesn't return order
        assert len(connector.orders_placed) == 0  # No orders placed

    def test_place_entry_with_stops_success(self):
        """Test successful order placement."""
        connector = _MockConnector()
        mgr = OrderManager(connector, dry_run=False, max_retries=1)

        result = mgr.place_entry_with_stops(
            symbol="BTC/USDT",
            side="buy",
            quantity=Decimal("0.01"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
        )

        assert result.status == OrderResultStatus.SUCCESS
        assert result.order is not None
        assert result.order.id == "order_123"
        assert result.stop_order is not None
        assert result.tp_order is not None
        assert len(connector.orders_placed) == 3  # Entry + SL + TP

    def test_place_entry_sell_rejected(self):
        """Test that SELL orders are rejected (long-only)."""
        connector = _MockConnector()
        mgr = OrderManager(connector)

        result = mgr.place_entry_with_stops(
            symbol="BTC/USDT",
            side="sell",
            quantity=Decimal("0.01"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
        )

        assert result.status == OrderResultStatus.VALIDATION_ERROR
        assert "long" in result.error.lower()

    def test_place_entry_insufficient_balance(self):
        """Test insufficient balance detection."""
        connector = _MockConnector()
        # Make balance zero
        def get_balance_zero(currency):
            class _B:
                free = Decimal("0")
            return {currency: _B()}
        connector.get_balance = get_balance_zero

        mgr = OrderManager(connector, dry_run=False)

        result = mgr.place_entry_with_stops(
            symbol="BTC/USDT",
            side="buy",
            quantity=Decimal("1.0"),  # Large amount
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
        )

        assert result.status == OrderResultStatus.INSUFFICIENT_BALANCE

    def test_place_entry_network_error_retries(self):
        """Test that network errors trigger retries."""
        connector = _MockConnector(fail_order=True)
        mgr = OrderManager(connector, dry_run=False, max_retries=3, retry_delay_seconds=0.01)

        result = mgr.place_entry_with_stops(
            symbol="BTC/USDT",
            side="buy",
            quantity=Decimal("0.01"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
        )

        assert result.status == OrderResultStatus.NETWORK_ERROR
        # Should have tried 3 times
        assert len(connector.orders_placed) == 0  # All failed

    def test_close_position_dry_run(self):
        """Test closing position in dry run."""
        connector = _MockConnector()
        mgr = OrderManager(connector, dry_run=True)

        result = mgr.close_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.01"),
            stop_order_id="stop_123",
            tp_order_id="tp_456",
        )

        assert result.status == OrderResultStatus.SUCCESS
        assert len(connector.orders_placed) == 0

    def test_close_position_success(self):
        """Test successful position close."""
        connector = _MockConnector()
        mgr = OrderManager(connector, dry_run=False, max_retries=1)

        result = mgr.close_position(
            symbol="BTC/USDT",
            quantity=Decimal("0.01"),
            stop_order_id="stop_123",
            tp_order_id="tp_456",
        )

        assert result.status == OrderResultStatus.SUCCESS
        assert result.order is not None
        # Should place 1 market sell order
        assert any(o[0] == "market" and o[2] == "sell" for o in connector.orders_placed)


# ------------------------------------------------------------------ #
# Integration: Config + OrderManager
# ------------------------------------------------------------------ #

class TestLiveIntegration:
    def test_config_and_order_manager_init(self):
        """Test that config loads and order manager initializes."""
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "KUCOIN_API_KEY=test\n"
                "KUCOIN_API_SECRET=test\n"
                "KUCOIN_PASSPHRASE=test\n"
                "DRY_RUN=true\n"
            )

            config = LiveTradingConfig.from_env(env_file)
            connector = _MockConnector()
            mgr = OrderManager(connector, dry_run=config.dry_run)

            assert mgr.dry_run is True

    def test_full_entry_flow_dry_run(self):
        """Test end-to-end entry flow in dry run."""
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "KUCOIN_API_KEY=k\n"
                "KUCOIN_API_SECRET=s\n"
                "KUCOIN_PASSPHRASE=p\n"
                "DRY_RUN=true\n"
                "SYMBOLS=BTC/USDT\n"
            )

            config = LiveTradingConfig.from_env(env_file)
            connector = _MockConnector()
            mgr = OrderManager(connector, dry_run=config.dry_run)

            result = mgr.place_entry_with_stops(
                symbol="BTC/USDT",
                side="buy",
                quantity=Decimal("0.01"),
                stop_loss=Decimal("59000"),
                take_profit=Decimal("62000"),
            )

            assert result.status == OrderResultStatus.SUCCESS
            assert len(connector.orders_placed) == 0  # Dry run
