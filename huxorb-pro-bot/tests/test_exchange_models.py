"""
Unit Tests for Exchange Models
===============================
Tests for data models (Ticker, Balance, Order, etc.)
"""

import pytest
from datetime import datetime
from decimal import Decimal

from core.exchange.models import (
    Ticker,
    Balance,
    Order,
    Market,
    OrderSide,
    OrderType,
    OrderStatus,
    MarketType,
    normalize_symbol,
    denormalize_symbol,
)


class TestTicker:
    """Tests for Ticker model."""

    def test_ticker_creation(self):
        """Test creating a valid ticker."""
        ticker = Ticker(
            symbol="BTC/USDT",
            timestamp=datetime.now(),
            bid=Decimal("50000"),
            ask=Decimal("50010"),
            last=Decimal("50005"),
            volume=Decimal("1000"),
        )

        assert ticker.symbol == "BTC/USDT"
        assert ticker.bid == Decimal("50000")
        assert ticker.ask == Decimal("50010")

    def test_ticker_spread(self):
        """Test spread calculation."""
        ticker = Ticker(
            symbol="BTC/USDT",
            timestamp=datetime.now(),
            bid=Decimal("50000"),
            ask=Decimal("50010"),
            last=Decimal("50005"),
            volume=Decimal("1000"),
        )

        # Spread = (50010 - 50000) / 50000 * 100 = 0.02%
        assert abs(ticker.spread - Decimal("0.02")) < Decimal("0.0001")

    def test_ticker_mid(self):
        """Test mid price calculation."""
        ticker = Ticker(
            symbol="BTC/USDT",
            timestamp=datetime.now(),
            bid=Decimal("50000"),
            ask=Decimal("50010"),
            last=Decimal("50005"),
            volume=Decimal("1000"),
        )

        assert ticker.mid == Decimal("50005")

    def test_ticker_negative_price_rejected(self):
        """Test that negative prices are rejected."""
        with pytest.raises(ValueError, match="Price/volume must be positive"):
            Ticker(
                symbol="BTC/USDT",
                timestamp=datetime.now(),
                bid=Decimal("-50000"),  # Invalid
                ask=Decimal("50010"),
                last=Decimal("50005"),
                volume=Decimal("1000"),
            )


class TestBalance:
    """Tests for Balance model."""

    def test_balance_creation(self):
        """Test creating a valid balance."""
        balance = Balance(
            currency="BTC",
            free=Decimal("0.5"),
            used=Decimal("0.1"),
            total=Decimal("0.6"),
        )

        assert balance.currency == "BTC"
        assert balance.free == Decimal("0.5")
        assert balance.used == Decimal("0.1")
        assert balance.total == Decimal("0.6")

    def test_balance_total_must_match(self):
        """Test that total = free + used."""
        with pytest.raises(ValueError, match="Total .* != free .* \\+ used"):
            Balance(
                currency="BTC",
                free=Decimal("0.5"),
                used=Decimal("0.1"),
                total=Decimal("0.5"),  # Wrong! Should be 0.6
            )

    def test_balance_negative_rejected(self):
        """Test that negative balances are rejected."""
        with pytest.raises(ValueError, match="Balance cannot be negative"):
            Balance(
                currency="BTC",
                free=Decimal("-0.5"),
                used=Decimal("0"),
                total=Decimal("-0.5"),
            )


class TestOrder:
    """Tests for Order model."""

    def test_order_creation(self):
        """Test creating a valid order."""
        order = Order(
            id="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.OPEN,
            amount=Decimal("0.01"),
            filled=Decimal("0"),
            remaining=Decimal("0.01"),
            price=Decimal("50000"),
            average=None,
            cost=Decimal("0"),
            timestamp=datetime.now(),
            last_update=datetime.now(),
        )

        assert order.id == "12345"
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.is_open

    def test_order_remaining_must_match(self):
        """Test that remaining = amount - filled."""
        with pytest.raises(ValueError, match="Remaining .* != amount .* - filled"):
            Order(
                id="12345",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                status=OrderStatus.OPEN,
                amount=Decimal("0.01"),
                filled=Decimal("0.005"),
                remaining=Decimal("0.01"),  # Wrong! Should be 0.005
                timestamp=datetime.now(),
                last_update=datetime.now(),
            )

    def test_order_status_helpers(self):
        """Test order status helper properties."""
        order = Order(
            id="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.CLOSED,
            amount=Decimal("0.01"),
            filled=Decimal("0.01"),
            remaining=Decimal("0"),
            timestamp=datetime.now(),
            last_update=datetime.now(),
        )

        assert order.is_closed
        assert not order.is_open
        assert not order.is_canceled


class TestMarket:
    """Tests for Market model."""

    def test_market_creation(self):
        """Test creating a valid market."""
        market = Market(
            symbol="BTC/USDT",
            base="BTC",
            quote="USDT",
            market_type=MarketType.SPOT,
            active=True,
            precision_price=2,
            precision_amount=8,
            min_amount=Decimal("0.0001"),
            max_amount=Decimal("10000"),
            min_cost=Decimal("10"),
            max_cost=None,
            maker_fee=Decimal("0.001"),
            taker_fee=Decimal("0.001"),
        )

        assert market.symbol == "BTC/USDT"
        assert market.market_type == MarketType.SPOT

    def test_market_non_spot_rejected(self):
        """Test that non-spot markets are rejected (CRITICAL for halal compliance)."""
        with pytest.raises(ValueError):
            Market(
                symbol="BTC/USDT",
                base="BTC",
                quote="USDT",
                market_type="futures",  # Non-SPOT must be rejected
                active=True,
                precision_price=2,
                precision_amount=8,
                min_amount=Decimal("0.0001"),
                max_amount=Decimal("10000"),
                min_cost=Decimal("10"),
                max_cost=None,
                maker_fee=Decimal("0.001"),
                taker_fee=Decimal("0.001"),
            )


class TestSymbolNormalization:
    """Tests for symbol normalization helpers."""

    def test_normalize_btcusdt(self):
        """Test normalizing BTCUSDT → BTC/USDT."""
        assert normalize_symbol("BTCUSDT") == "BTC/USDT"

    def test_normalize_with_dash(self):
        """Test normalizing BTC-USDT → BTC/USDT."""
        assert normalize_symbol("BTC-USDT") == "BTC/USDT"

    def test_normalize_already_normalized(self):
        """Test that already normalized symbols pass through."""
        assert normalize_symbol("BTC/USDT") == "BTC/USDT"

    def test_normalize_lowercase(self):
        """Test that lowercase symbols are uppercased."""
        assert normalize_symbol("btcusdt") == "BTC/USDT"

    def test_denormalize_binance(self):
        """Test denormalizing BTC/USDT → BTCUSDT (Binance format)."""
        assert denormalize_symbol("BTC/USDT", "binance") == "BTCUSDT"

    def test_denormalize_kraken(self):
        """Test denormalizing BTC/USDT → BTC-USDT (Kraken format)."""
        assert denormalize_symbol("BTC/USDT", "kraken") == "BTC-USDT"

    def test_denormalize_already_denormalized(self):
        """Test that already denormalized symbols pass through."""
        assert denormalize_symbol("BTCUSDT", "binance") == "BTCUSDT"
