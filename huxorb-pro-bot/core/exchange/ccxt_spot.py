"""
CCXT Spot Exchange Connector
=============================
Production-grade connector using CCXT library for spot trading.

ENFORCES:
- Spot markets only (no margin/futures/swaps)
- Rate limiting with exponential backoff
- Proper error handling
- Halal compliance checks

Supports: Binance, Bybit, Kraken, Coinbase, OKX, and 100+ exchanges via CCXT.
"""

import time
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

import ccxt
from ccxt.base.errors import (
    NetworkError as CCXTNetworkError,
    ExchangeError as CCXTExchangeError,
    AuthenticationError as CCXTAuthenticationError,
    InsufficientFunds as CCXTInsufficientFunds,
    InvalidOrder as CCXTInvalidOrder,
    RateLimitExceeded as CCXTRateLimitExceeded,
)

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


class CCXTSpotExchange(IExchange):
    """
    CCXT-based spot exchange connector.

    Wraps CCXT library to provide type-safe, spot-only interface.

    CRITICAL FEATURES:
    1. Spot-only enforcement (rejects margin/futures at runtime)
    2. Automatic retry with exponential backoff
    3. Rate limiting (respects exchange limits)
    4. Testnet support (Binance, Bybit)
    5. Dry-run mode (validates but doesn't send orders)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize CCXT connector.

        Args:
            config: Configuration dict:
                - exchange: Exchange name (binance, bybit, kraken, etc.)
                - api_key: API key (optional for public endpoints)
                - api_secret: API secret
                - password: API password (for some exchanges)
                - testnet: Use testnet/sandbox (default: False)
                - timeout: Request timeout in ms (default: 30000)
                - rate_limit: Enable rate limiting (default: True)
                - dry_run: Simulate orders (default: False)
                - max_retries: Max retry attempts (default: 3)
        """
        super().__init__(config)

        exchange_id = config.get('exchange', 'binance').lower()
        self.name = exchange_id

        # Get exchange class from CCXT
        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"Exchange '{exchange_id}' not supported by CCXT")

        exchange_class = getattr(ccxt, exchange_id)

        # Build CCXT config
        ccxt_config = {
            'apiKey': config.get('api_key'),
            'secret': config.get('api_secret'),
            'password': config.get('password'),  # For exchanges like KuCoin
            'timeout': config.get('timeout', 30000),
            'enableRateLimit': config.get('rate_limit', True),
        }

        # Testnet configuration (exchange-specific)
        if self.testnet:
            if exchange_id == 'binance':
                ccxt_config['options'] = {'defaultType': 'spot'}
                ccxt_config['urls'] = {
                    'api': {
                        'public': 'https://testnet.binance.vision/api',
                        'private': 'https://testnet.binance.vision/api',
                    }
                }
            elif exchange_id == 'bybit':
                ccxt_config['options'] = {'defaultType': 'spot'}
                ccxt_config['urls'] = {
                    'api': {
                        'public': 'https://api-testnet.bybit.com',
                        'private': 'https://api-testnet.bybit.com',
                    }
                }
            # Add more exchanges as needed

        # Initialize CCXT exchange
        self.exchange = exchange_class(ccxt_config)

        # Load markets (required for symbol normalization)
        self.exchange.load_markets()

        # Config
        self.max_retries = config.get('max_retries', 3)

        # Validate spot support
        if not self.exchange.has.get('spot', False):
            raise ValueError(f"Exchange {exchange_id} does not support spot trading")

    # ========================================================================
    # RETRY LOGIC
    # ========================================================================

    def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Execute function with exponential backoff retry.

        Retries on:
        - Network errors (timeout, connection refused)
        - Rate limit exceeded

        Does NOT retry on:
        - Authentication errors (bad API key)
        - Invalid parameters (wrong symbol, amount)
        - Insufficient funds

        Returns:
            Function result

        Raises:
            Last exception if all retries fail
        """
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)

            except CCXTRateLimitExceeded:
                if attempt < self.max_retries - 1:
                    # Exponential backoff: 2s, 4s, 8s
                    wait_time = 2 ** (attempt + 1)
                    time.sleep(wait_time)
                else:
                    raise

            except CCXTNetworkError as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    time.sleep(wait_time)
                else:
                    raise ConnectionError(f"Network error after {self.max_retries} retries: {e}")

            except (CCXTAuthenticationError, CCXTInsufficientFunds, CCXTInvalidOrder):
                # Don't retry these - they won't succeed
                raise

        raise RuntimeError("Retry logic failed unexpectedly")

    # ========================================================================
    # PUBLIC ENDPOINTS
    # ========================================================================

    def get_ticker(self, symbol: str) -> Ticker:
        """Get current ticker."""
        symbol = normalize_symbol(symbol)
        self.validate_spot_only(symbol)

        def _fetch():
            ticker_data = self.exchange.fetch_ticker(symbol)
            return Ticker(
                symbol=symbol,
                timestamp=datetime.fromtimestamp(ticker_data['timestamp'] / 1000),
                bid=Decimal(str(ticker_data['bid'])),
                ask=Decimal(str(ticker_data['ask'])),
                last=Decimal(str(ticker_data['last'])),
                volume=Decimal(str(ticker_data['baseVolume'])),
            )

        return self._retry_with_backoff(_fetch)

    def get_market(self, symbol: str) -> Market:
        """Get market information."""
        symbol = normalize_symbol(symbol)

        if symbol not in self.exchange.markets:
            raise ValueError(f"Symbol {symbol} not found on {self.name}")

        market_data = self.exchange.markets[symbol]

        # Determine market type
        if market_data.get('spot'):
            market_type = MarketType.SPOT
        else:
            # CRITICAL: Reject non-spot markets
            raise ValueError(
                f"Market {symbol} is not SPOT. Only spot trading allowed (halal compliance)."
            )

        return Market(
            symbol=symbol,
            base=market_data['base'],
            quote=market_data['quote'],
            market_type=market_type,
            active=market_data.get('active', True),
            precision_price=market_data['precision']['price'],
            precision_amount=market_data['precision']['amount'],
            min_amount=Decimal(str(market_data['limits']['amount']['min'])),
            max_amount=Decimal(str(market_data['limits']['amount'].get('max', 0))) if market_data['limits']['amount'].get('max') else None,
            min_cost=Decimal(str(market_data['limits']['cost']['min'])),
            max_cost=Decimal(str(market_data['limits']['cost'].get('max', 0))) if market_data['limits']['cost'].get('max') else None,
            maker_fee=Decimal(str(market_data.get('maker', 0.001))),
            taker_fee=Decimal(str(market_data.get('taker', 0.001))),
            info=market_data,
        )

    def get_markets(self) -> Dict[str, Market]:
        """Get all spot markets."""
        markets = {}

        for symbol, market_data in self.exchange.markets.items():
            # Filter: spot only
            if not market_data.get('spot'):
                continue

            try:
                markets[symbol] = self.get_market(symbol)
            except ValueError:
                # Skip invalid markets
                continue

        return markets

    def get_exchange_info(self) -> ExchangeInfo:
        """Get exchange metadata."""
        return ExchangeInfo(
            name=self.exchange.id,
            rate_limit=self.exchange.rateLimit,
            has_spot=self.exchange.has.get('spot', False),
            has_margin=self.exchange.has.get('margin', False),
            has_futures=self.exchange.has.get('futures', False),
        )

    # ========================================================================
    # PRIVATE ENDPOINTS
    # ========================================================================

    def get_balance(self, currency: Optional[str] = None) -> Dict[str, Balance]:
        """Get spot balances."""
        def _fetch():
            balance_data = self.exchange.fetch_balance({'type': 'spot'})
            balances = {}

            for curr, amounts in balance_data.items():
                if curr in ['info', 'free', 'used', 'total']:
                    continue  # Skip metadata

                # Filter by currency if specified
                if currency and curr != currency:
                    continue

                # Skip zero balances
                total = amounts.get('total', 0)
                if total == 0:
                    continue

                balances[curr] = Balance(
                    currency=curr,
                    free=Decimal(str(amounts['free'])),
                    used=Decimal(str(amounts['used'])),
                    total=Decimal(str(total)),
                )

            return balances

        return self._retry_with_backoff(_fetch)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get open orders."""
        if symbol:
            symbol = normalize_symbol(symbol)
            self.validate_spot_only(symbol)

        def _fetch():
            orders_data = self.exchange.fetch_open_orders(symbol)
            orders = []

            for order_data in orders_data:
                orders.append(self._parse_order(order_data))

            # Sort by timestamp (oldest first)
            orders.sort(key=lambda o: o.timestamp)
            return orders

        return self._retry_with_backoff(_fetch)

    def get_order(self, order_id: str, symbol: str) -> Order:
        """Get order by ID."""
        symbol = normalize_symbol(symbol)
        self.validate_spot_only(symbol)

        def _fetch():
            order_data = self.exchange.fetch_order(order_id, symbol)
            return self._parse_order(order_data)

        return self._retry_with_backoff(_fetch)

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
        Create spot order.

        CRITICAL VALIDATIONS:
        1. Spot market only
        2. No leverage/margin parameters
        3. Amount/price meet exchange requirements
        """
        symbol = normalize_symbol(symbol)
        params = params or {}

        # CRITICAL: Validate spot-only and parameters
        self.validate_order_params(symbol, side, order_type, amount, price, params)

        # Dry-run mode: validate but don't send
        if self.dry_run:
            return Order(
                id=f"DRY_RUN_{int(time.time() * 1000)}",
                symbol=symbol,
                side=side,
                type=order_type,
                status=OrderStatus.PENDING,
                amount=amount,
                filled=Decimal(0),
                remaining=amount,
                price=price,
                average=None,
                cost=Decimal(0),
                timestamp=datetime.now(),
                last_update=datetime.now(),
                info={'dry_run': True},
            )

        # Format amount and price
        amount = self.format_amount(amount, symbol)
        if price:
            price = self.format_price(price, symbol)

        def _send():
            order_data = self.exchange.create_order(
                symbol=symbol,
                type=order_type.value,
                side=side.value,
                amount=float(amount),
                price=float(price) if price else None,
                params=params,
            )
            return self._parse_order(order_data)

        return self._retry_with_backoff(_send)

    def cancel_order(self, order_id: str, symbol: str) -> Order:
        """Cancel order."""
        symbol = normalize_symbol(symbol)
        self.validate_spot_only(symbol)

        def _cancel():
            order_data = self.exchange.cancel_order(order_id, symbol)
            return self._parse_order(order_data)

        return self._retry_with_backoff(_cancel)

    def cancel_all_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Cancel all open orders."""
        if symbol:
            symbol = normalize_symbol(symbol)
            self.validate_spot_only(symbol)

        def _cancel_all():
            # Get open orders first
            open_orders = self.get_open_orders(symbol)
            canceled_orders = []

            for order in open_orders:
                try:
                    canceled = self.cancel_order(order.id, order.symbol)
                    canceled_orders.append(canceled)
                except Exception as e:
                    # Continue canceling other orders
                    print(f"Failed to cancel order {order.id}: {e}")

            return canceled_orders

        return self._retry_with_backoff(_cancel_all)

    def get_fills(self, symbol: Optional[str] = None, since: Optional[datetime] = None) -> List[Fill]:
        """Get trade fills."""
        if symbol:
            symbol = normalize_symbol(symbol)
            self.validate_spot_only(symbol)

        def _fetch():
            since_ms = int(since.timestamp() * 1000) if since else None
            trades_data = self.exchange.fetch_my_trades(symbol, since=since_ms)
            fills = []

            for trade_data in trades_data:
                fills.append(Fill(
                    id=str(trade_data['id']),
                    order_id=str(trade_data['order']),
                    symbol=trade_data['symbol'],
                    side=OrderSide(trade_data['side']),
                    price=Decimal(str(trade_data['price'])),
                    amount=Decimal(str(trade_data['amount'])),
                    cost=Decimal(str(trade_data['cost'])),
                    timestamp=datetime.fromtimestamp(trade_data['timestamp'] / 1000),
                    fee=trade_data.get('fee'),
                    info=trade_data,
                ))

            return fills

        return self._retry_with_backoff(_fetch)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _parse_order(self, order_data: Dict[str, Any]) -> Order:
        """Parse CCXT order response to Order model."""
        # Map CCXT status to our OrderStatus
        status_map = {
            'open': OrderStatus.OPEN,
            'closed': OrderStatus.CLOSED,
            'canceled': OrderStatus.CANCELED,
            'cancelled': OrderStatus.CANCELED,
            'expired': OrderStatus.EXPIRED,
            'rejected': OrderStatus.REJECTED,
        }

        status = status_map.get(order_data['status'], OrderStatus.PENDING)

        return Order(
            id=str(order_data['id']),
            symbol=order_data['symbol'],
            side=OrderSide(order_data['side']),
            type=OrderType(order_data['type']),
            status=status,
            amount=Decimal(str(order_data['amount'])),
            filled=Decimal(str(order_data.get('filled', 0))),
            remaining=Decimal(str(order_data.get('remaining', order_data['amount']))),
            price=Decimal(str(order_data['price'])) if order_data['price'] else None,
            average=Decimal(str(order_data['average'])) if order_data.get('average') else None,
            cost=Decimal(str(order_data.get('cost', 0))),
            timestamp=datetime.fromtimestamp(order_data['timestamp'] / 1000),
            last_update=datetime.fromtimestamp(order_data.get('lastTradeTimestamp', order_data['timestamp']) / 1000),
            fee=order_data.get('fee'),
            info=order_data,
        )
