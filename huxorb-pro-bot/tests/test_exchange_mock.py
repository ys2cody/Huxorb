"""
Unit Tests for MockExchange
============================
Tests for in-memory exchange simulator.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from core.exchange import (
    MockExchange,
    OrderSide,
    OrderType,
    OrderStatus,
    MarketType,
)


class TestMockExchangeInit:
    """Tests for MockExchange initialization."""

    def test_init_default(self):
        """Test initialization with defaults."""
        exchange = MockExchange({})

        assert exchange.name == "mock"
        assert exchange.testnet is True

        # Should have default markets
        markets = exchange.get_markets()
        assert "BTC/USDT" in markets
        assert "ETH/USDT" in markets

    def test_init_custom_balances(self):
        """Test initialization with custom balances."""
        exchange = MockExchange({
            'initial_balances': {'USDT': Decimal(5000), 'BTC': Decimal(1.0)}
        })

        balances = exchange.get_balance()
        assert balances['USDT'].total == Decimal(5000)
        assert balances['BTC'].total == Decimal(1.0)

    def test_init_custom_markets(self):
        """Test initialization with custom markets."""
        exchange = MockExchange({
            'markets': ['ETH/USDT', 'SOL/USDT']
        })

        markets = exchange.get_markets()
        assert "ETH/USDT" in markets
        assert "SOL/USDT" in markets
        assert "BTC/USDT" not in markets


class TestMockExchangePublicEndpoints:
    """Tests for public endpoints (no auth required)."""

    @pytest.fixture
    def exchange(self):
        """Create mock exchange for testing."""
        return MockExchange({
            'initial_balances': {'USDT': Decimal(10000)},
            'base_prices': {'BTC/USDT': Decimal(50000), 'ETH/USDT': Decimal(3000)},
        })

    def test_get_ticker(self, exchange):
        """Test fetching ticker."""
        ticker = exchange.get_ticker("BTC/USDT")

        assert ticker.symbol == "BTC/USDT"
        assert ticker.bid > 0
        assert ticker.ask > ticker.bid
        assert ticker.last > 0
        assert ticker.spread < Decimal("1")  # Spread should be < 1%

    def test_get_market(self, exchange):
        """Test fetching market info."""
        market = exchange.get_market("BTC/USDT")

        assert market.symbol == "BTC/USDT"
        assert market.base == "BTC"
        assert market.quote == "USDT"
        assert market.market_type == MarketType.SPOT
        assert market.active is True

    def test_get_markets(self, exchange):
        """Test fetching all markets."""
        markets = exchange.get_markets()

        assert len(markets) >= 2
        assert "BTC/USDT" in markets
        assert "ETH/USDT" in markets

        # All markets should be spot
        for market in markets.values():
            assert market.market_type == MarketType.SPOT

    def test_get_exchange_info(self, exchange):
        """Test fetching exchange info."""
        info = exchange.get_exchange_info()

        assert info.name == "mock"
        assert info.has_spot is True
        assert info.has_margin is False
        assert info.has_futures is False


class TestMockExchangeBalance:
    """Tests for balance management."""

    @pytest.fixture
    def exchange(self):
        """Create mock exchange for testing."""
        return MockExchange({
            'initial_balances': {'USDT': Decimal(10000), 'BTC': Decimal(0.5)},
        })

    def test_get_balance_all(self, exchange):
        """Test fetching all balances."""
        balances = exchange.get_balance()

        assert 'USDT' in balances
        assert 'BTC' in balances

        assert balances['USDT'].total == Decimal(10000)
        assert balances['BTC'].total == Decimal(0.5)

    def test_get_balance_single_currency(self, exchange):
        """Test fetching balance for single currency."""
        balances = exchange.get_balance('USDT')

        assert len(balances) == 1
        assert 'USDT' in balances
        assert balances['USDT'].total == Decimal(10000)

    def test_add_balance(self, exchange):
        """Test adding balance (helper method)."""
        exchange.add_balance('ETH', Decimal(10))

        balances = exchange.get_balance('ETH')
        assert balances['ETH'].total == Decimal(10)


class TestMockExchangeOrders:
    """Tests for order management."""

    @pytest.fixture
    def exchange(self):
        """Create mock exchange for testing."""
        return MockExchange({
            'initial_balances': {'USDT': Decimal(10000), 'BTC': Decimal(0.5)},
            'base_prices': {'BTC/USDT': Decimal(50000)},
        })

    def test_create_market_buy_order(self, exchange):
        """Test creating a market buy order."""
        order = exchange.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )

        assert order.id.startswith("MOCK_")
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.status == OrderStatus.CLOSED  # Market orders fill immediately
        assert order.filled == Decimal("0.01")
        assert order.remaining == Decimal("0")

        # Check balance updated
        balances = exchange.get_balance()
        assert balances['BTC'].total > Decimal("0.5")  # Should have more BTC
        assert balances['USDT'].total < Decimal(10000)  # Should have less USDT

    def test_create_market_sell_order(self, exchange):
        """Test creating a market sell order."""
        order = exchange.create_order(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )

        assert order.status == OrderStatus.CLOSED
        assert order.filled == Decimal("0.1")

        # Check balance updated
        balances = exchange.get_balance()
        assert balances['BTC'].total < Decimal("0.5")  # Should have less BTC
        assert balances['USDT'].total > Decimal(10000)  # Should have more USDT

    def test_create_limit_buy_order(self, exchange):
        """Test creating a limit buy order (stays open)."""
        order = exchange.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("45000"),  # Below market
        )

        assert order.status == OrderStatus.OPEN  # Limit orders stay open
        assert order.filled == Decimal("0")
        assert order.remaining == Decimal("0.01")

        # Check balance locked
        balances = exchange.get_balance()
        assert balances['USDT'].used > 0  # Quote currency locked
        assert balances['USDT'].free < Decimal(10000)

    def test_insufficient_balance_buy(self, exchange):
        """Test that buying with insufficient balance raises error."""
        with pytest.raises(ValueError, match="Insufficient USDT balance"):
            exchange.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("1000"),  # Way too much
            )

    def test_insufficient_balance_sell(self, exchange):
        """Test that selling with insufficient balance raises error."""
        with pytest.raises(ValueError, match="Insufficient BTC balance"):
            exchange.create_order(
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=Decimal("100"),  # Don't have this much BTC
            )

    def test_get_open_orders(self, exchange):
        """Test fetching open orders."""
        # Create a limit order (stays open)
        order1 = exchange.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("45000"),
        )

        # Get open orders
        open_orders = exchange.get_open_orders()
        assert len(open_orders) == 1
        assert open_orders[0].id == order1.id

        # Create market order (fills immediately)
        exchange.create_order(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )

        # Still only 1 open order (market order closed)
        open_orders = exchange.get_open_orders()
        assert len(open_orders) == 1

    def test_cancel_order(self, exchange):
        """Test canceling an order."""
        # Create limit order
        order = exchange.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("45000"),
        )

        # Check balance locked
        balances_before = exchange.get_balance()
        assert balances_before['USDT'].used > 0

        # Cancel order
        canceled = exchange.cancel_order(order.id, "BTC/USDT")
        assert canceled.status == OrderStatus.CANCELED

        # Check balance released
        balances_after = exchange.get_balance()
        assert balances_after['USDT'].used == 0
        assert balances_after['USDT'].free == balances_after['USDT'].total

    def test_cancel_nonexistent_order(self, exchange):
        """Test canceling non-existent order raises error."""
        with pytest.raises(ValueError, match="Order .* not found"):
            exchange.cancel_order("FAKE_123", "BTC/USDT")

    def test_cancel_closed_order(self, exchange):
        """Test canceling closed order raises error."""
        # Create and fill market order
        order = exchange.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )

        # Try to cancel (should fail)
        with pytest.raises(ValueError, match="is not open"):
            exchange.cancel_order(order.id, "BTC/USDT")

    def test_cancel_all_orders(self, exchange):
        """Test canceling all orders."""
        # Create 3 limit orders
        for i in range(3):
            exchange.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=Decimal(45000 - i * 1000),
            )

        # Check 3 open orders
        assert len(exchange.get_open_orders()) == 3

        # Cancel all
        canceled = exchange.cancel_all_orders()
        assert len(canceled) == 3

        # Check no open orders
        assert len(exchange.get_open_orders()) == 0


class TestMockExchangeValidation:
    """Tests for spot-only validation."""

    @pytest.fixture
    def exchange(self):
        """Create mock exchange for testing."""
        return MockExchange({
            'initial_balances': {'USDT': Decimal(10000)},
        })

    def test_validate_spot_only(self, exchange):
        """Test that spot-only validation passes for spot markets."""
        # Should not raise
        exchange.validate_spot_only("BTC/USDT")

    def test_validate_order_params_min_amount(self, exchange):
        """Test that orders below min amount are rejected."""
        with pytest.raises(ValueError, match="below minimum"):
            exchange.validate_order_params(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("0.00001"),  # Too small
            )

    def test_validate_order_params_limit_requires_price(self, exchange):
        """Test that LIMIT orders require price."""
        with pytest.raises(ValueError, match="Price required for LIMIT orders"):
            exchange.validate_order_params(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=None,  # Missing!
            )

    def test_validate_order_params_forbidden_leverage(self, exchange):
        """Test that leverage parameters are rejected (halal compliance)."""
        with pytest.raises(ValueError, match="not allowed.*halal compliance"):
            exchange.validate_order_params(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("0.01"),
                params={'leverage': 10},  # NOT ALLOWED
            )


class TestMockExchangeHelpers:
    """Tests for helper methods."""

    @pytest.fixture
    def exchange(self):
        """Create mock exchange for testing."""
        return MockExchange({})

    def test_set_price(self, exchange):
        """Test setting price (helper)."""
        exchange.set_price("BTC/USDT", Decimal(60000))

        ticker = exchange.get_ticker("BTC/USDT")
        # Price should be ~60000 (with small spread)
        assert abs(ticker.last - Decimal(60000)) < Decimal(100)

    def test_reset(self, exchange):
        """Test resetting exchange state."""
        # Create some orders
        exchange.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("45000"),
        )

        # Reset
        exchange.reset()

        # Should have no orders
        assert len(exchange.get_open_orders()) == 0

        # Should have default balance
        balances = exchange.get_balance()
        assert balances['USDT'].total == Decimal(10000)
