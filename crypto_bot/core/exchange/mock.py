"""
Mock Exchange for Testing
==========================
In-memory exchange simulator for unit tests and development.

NO REAL API CALLS - Everything simulated locally.

Features:
- Realistic order lifecycle (open → filled → closed)
- Simulated balances and order fills
- Deterministic pricing (no randomness unless needed)
- Fast (no network latency)
"""

import time
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from copy import deepcopy

from .base import IExchange
from .models import (
    Ticker,
    Balance,
    Order,
    Fill,
    Market,
    ExchangeInfo,
    OrderSide,
    OrderType,
    OrderStatus,
    MarketType,
    normalize_symbol,
)


class MockExchange(IExchange):
    """
    Mock exchange for testing.

    Simulates a spot exchange without making real API calls.
    All data stored in memory.

    Usage:
        exchange = MockExchange({
            'initial_balances': {'USDT': 10000, 'BTC': 0.5},
            'testnet': True,
        })
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize mock exchange.

        Args:
            config: Configuration dict:
                - initial_balances: Dict of currency → amount (default: {'USDT': 10000})
                - markets: List of symbols to support (default: ['BTC/USDT', 'ETH/USDT'])
                - base_prices: Dict of symbol → price (default: BTC=50000, ETH=3000)
                - testnet: Always True for mock
                - dry_run: Simulate even the simulation (default: False)
        """
        super().__init__(config)
        self.name = "mock"
        self.testnet = True  # Mock is always testnet

        # Initialize state
        self._balances = self._init_balances(config.get('initial_balances', {'USDT': Decimal(10000)}))
        self._markets = self._init_markets(config.get('markets', ['BTC/USDT', 'ETH/USDT']))
        self._base_prices = config.get('base_prices', {'BTC/USDT': Decimal(50000), 'ETH/USDT': Decimal(3000)})

        self._orders: Dict[str, Order] = {}  # order_id → Order
        self._fills: List[Fill] = []
        self._order_counter = 0

    # ========================================================================
    # INITIALIZATION
    # ========================================================================

    def _init_balances(self, initial: Dict[str, Decimal]) -> Dict[str, Balance]:
        """Initialize balances from config."""
        balances = {}
        for currency, amount in initial.items():
            amount = Decimal(str(amount))
            balances[currency] = Balance(
                currency=currency,
                free=amount,
                used=Decimal(0),
                total=amount,
            )
        return balances

    def _init_markets(self, symbols: List[str]) -> Dict[str, Market]:
        """Initialize markets from config."""
        markets = {}

        for symbol in symbols:
            symbol = normalize_symbol(symbol)
            base, quote = symbol.split('/')

            markets[symbol] = Market(
                symbol=symbol,
                base=base,
                quote=quote,
                market_type=MarketType.SPOT,
                active=True,
                precision_price=2,
                precision_amount=8,
                min_amount=Decimal('0.0001'),
                max_amount=Decimal('10000'),
                min_cost=Decimal('10'),
                max_cost=None,
                maker_fee=Decimal('0.001'),
                taker_fee=Decimal('0.001'),
                info={},
            )

        return markets

    # ========================================================================
    # PUBLIC ENDPOINTS
    # ========================================================================

    def get_ticker(self, symbol: str) -> Ticker:
        """Get simulated ticker."""
        symbol = normalize_symbol(symbol)
        self.validate_spot_only(symbol)

        base_price = self._base_prices.get(symbol, Decimal(1000))

        # Simulate bid/ask spread (0.1%)
        spread_pct = Decimal('0.001')
        mid = base_price
        bid = mid * (1 - spread_pct / 2)
        ask = mid * (1 + spread_pct / 2)

        return Ticker(
            symbol=symbol,
            timestamp=datetime.now(),
            bid=bid,
            ask=ask,
            last=mid,
            volume=Decimal(1000),  # Fake volume
        )

    def get_market(self, symbol: str) -> Market:
        """Get market info."""
        symbol = normalize_symbol(symbol)

        if symbol not in self._markets:
            raise ValueError(f"Symbol {symbol} not found in mock exchange")

        return self._markets[symbol]

    def get_markets(self) -> Dict[str, Market]:
        """Get all markets."""
        return deepcopy(self._markets)

    def get_exchange_info(self) -> ExchangeInfo:
        """Get exchange metadata."""
        return ExchangeInfo(
            name="mock",
            rate_limit=1000,
            has_spot=True,
            has_margin=False,
            has_futures=False,
        )

    # ========================================================================
    # PRIVATE ENDPOINTS
    # ========================================================================

    def get_balance(self, currency: Optional[str] = None) -> Dict[str, Balance]:
        """Get balances."""
        if currency:
            if currency not in self._balances:
                return {}
            return {currency: self._balances[currency]}

        # Return all non-zero balances
        return {
            curr: bal
            for curr, bal in self._balances.items()
            if bal.total > 0
        }

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get open orders."""
        if symbol:
            symbol = normalize_symbol(symbol)

        orders = []
        for order in self._orders.values():
            if order.status == OrderStatus.OPEN:
                if symbol is None or order.symbol == symbol:
                    orders.append(order)

        orders.sort(key=lambda o: o.timestamp)
        return orders

    def get_order(self, order_id: str, symbol: str) -> Order:
        """Get order by ID."""
        if order_id not in self._orders:
            raise ValueError(f"Order {order_id} not found")

        return self._orders[order_id]

    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Optional[Decimal] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Order:
        """
        Create simulated order.

        Behavior:
        - MARKET orders: Fill immediately at current price
        - LIMIT orders: Create as OPEN, fill when price reached (not implemented yet)
        """
        symbol = normalize_symbol(symbol)
        params = params or {}

        # Validate
        self.validate_order_params(symbol, side, order_type, amount, price, params)

        # Generate order ID
        self._order_counter += 1
        order_id = f"MOCK_{self._order_counter}"

        # Get market info
        market = self.get_market(symbol)
        base, quote = market.base, market.quote

        # Determine fill price
        if order_type == OrderType.MARKET:
            ticker = self.get_ticker(symbol)
            fill_price = ticker.ask if side == OrderSide.BUY else ticker.bid
        else:
            fill_price = price  # LIMIT order

        # Calculate cost
        cost = amount * fill_price

        # Check balance
        if side == OrderSide.BUY:
            # Buying: need quote currency (USDT)
            required = cost
            if quote not in self._balances or self._balances[quote].free < required:
                raise ValueError(f"Insufficient {quote} balance. Need {required}, have {self._balances.get(quote, Balance(currency=quote, free=Decimal(0), used=Decimal(0), total=Decimal(0))).free}")

            # Lock quote balance
            self._balances[quote].free -= required
            self._balances[quote].used += required

        else:  # SELL
            # Selling: need base currency (BTC)
            required = amount
            if base not in self._balances or self._balances[base].free < required:
                raise ValueError(f"Insufficient {base} balance. Need {required}, have {self._balances.get(base, Balance(currency=base, free=Decimal(0), used=Decimal(0), total=Decimal(0))).free}")

            # Lock base balance
            self._balances[base].free -= required
            self._balances[base].used += required

        # Create order
        now = datetime.now()
        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            type=order_type,
            status=OrderStatus.OPEN,
            amount=amount,
            filled=Decimal(0),
            remaining=amount,
            price=price,
            average=None,
            cost=Decimal(0),
            timestamp=now,
            last_update=now,
            info={'mock': True},
        )

        # Store order
        self._orders[order_id] = order

        # MARKET orders fill immediately
        if order_type == OrderType.MARKET:
            self._fill_order(order_id, fill_price, amount)

        return self._orders[order_id]

    def cancel_order(self, order_id: str, symbol: str) -> Order:
        """Cancel order."""
        if order_id not in self._orders:
            raise ValueError(f"Order {order_id} not found")

        order = self._orders[order_id]

        if order.status != OrderStatus.OPEN:
            raise ValueError(f"Order {order_id} is not open (status: {order.status})")

        # Release locked balance
        market = self.get_market(order.symbol)
        base, quote = market.base, market.quote

        if order.side == OrderSide.BUY:
            # Release locked quote currency
            locked = order.remaining * (order.price if order.price else Decimal(1))
            self._balances[quote].used -= locked
            self._balances[quote].free += locked
        else:  # SELL
            # Release locked base currency
            self._balances[base].used -= order.remaining
            self._balances[base].free += order.remaining

        # Update order status
        order.status = OrderStatus.CANCELED
        order.last_update = datetime.now()

        return order

    def cancel_all_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Cancel all open orders."""
        open_orders = self.get_open_orders(symbol)
        canceled = []

        for order in open_orders:
            try:
                canceled.append(self.cancel_order(order.id, order.symbol))
            except Exception:
                pass  # Continue canceling

        return canceled

    def get_fills(self, symbol: Optional[str] = None, since: Optional[datetime] = None) -> List[Fill]:
        """Get fills."""
        fills = self._fills.copy()

        if symbol:
            symbol = normalize_symbol(symbol)
            fills = [f for f in fills if f.symbol == symbol]

        if since:
            fills = [f for f in fills if f.timestamp >= since]

        return fills

    # ========================================================================
    # SIMULATION HELPERS
    # ========================================================================

    def _fill_order(self, order_id: str, price: Decimal, amount: Decimal):
        """
        Simulate order fill.

        Updates:
        - Order status → CLOSED
        - Order filled/remaining
        - Balances (release locked, credit filled)
        - Create Fill record
        """
        order = self._orders[order_id]
        market = self.get_market(order.symbol)
        base, quote = market.base, market.quote

        # Update order
        order.filled = amount
        order.remaining = Decimal(0)
        order.status = OrderStatus.CLOSED
        order.average = price
        order.cost = amount * price
        order.last_update = datetime.now()

        # Update balances
        if order.side == OrderSide.BUY:
            # Release locked quote, credit base
            locked_quote = amount * price
            self._balances[quote].used -= locked_quote
            self._balances[quote].total -= locked_quote

            # Credit base (BTC)
            if base not in self._balances:
                self._balances[base] = Balance(currency=base, free=Decimal(0), used=Decimal(0), total=Decimal(0))

            self._balances[base].free += amount
            self._balances[base].total += amount

        else:  # SELL
            # Release locked base, credit quote
            self._balances[base].used -= amount
            self._balances[base].total -= amount

            # Credit quote (USDT)
            received_quote = amount * price
            self._balances[quote].free += received_quote
            self._balances[quote].total += received_quote

        # Create fill record
        fill = Fill(
            id=f"FILL_{order_id}",
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            price=price,
            amount=amount,
            cost=amount * price,
            timestamp=datetime.now(),
            fee={'cost': amount * price * Decimal('0.001'), 'currency': quote},
            info={'mock': True},
        )

        self._fills.append(fill)

    def set_price(self, symbol: str, price: Decimal):
        """
        Set base price for a symbol (testing helper).

        Args:
            symbol: Symbol (e.g., BTC/USDT)
            price: New price
        """
        symbol = normalize_symbol(symbol)
        self._base_prices[symbol] = price

    def add_balance(self, currency: str, amount: Decimal):
        """
        Add balance (testing helper).

        Args:
            currency: Currency code
            amount: Amount to add
        """
        if currency not in self._balances:
            self._balances[currency] = Balance(
                currency=currency,
                free=Decimal(0),
                used=Decimal(0),
                total=Decimal(0),
            )

        self._balances[currency].free += amount
        self._balances[currency].total += amount

    def reset(self):
        """Reset exchange state (testing helper)."""
        self._orders.clear()
        self._fills.clear()
        self._order_counter = 0
        self._balances = self._init_balances({'USDT': Decimal(10000)})
