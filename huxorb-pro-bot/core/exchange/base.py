"""
Base Exchange Interface
=======================
Abstract base class defining the contract that all exchange implementations must follow.
Ensures consistency across Binance, Bybit, Kraken, etc.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

from .models import (
    Ticker,
    Balance,
    Order,
    Fill,
    Market,
    ExchangeInfo,
    OrderSide,
    OrderType,
    MarketType,
)


class IExchange(ABC):
    """
    Abstract exchange interface.

    All exchange implementations (CCXT, custom REST, mock) must implement these methods.

    CRITICAL RULES:
    1. SPOT TRADING ONLY - reject any margin/futures/leverage operations
    2. All symbols use BASE/QUOTE format internally (e.g., BTC/USDT)
    3. All prices/amounts use Decimal for precision
    4. All timestamps use datetime objects
    5. Rate limiting and retries handled internally
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize exchange connector.

        Args:
            config: Configuration dict with keys:
                - api_key: API key (optional for public endpoints)
                - api_secret: API secret (optional for public endpoints)
                - testnet: Use testnet/sandbox (default: False)
                - timeout: Request timeout in milliseconds (default: 30000)
                - rate_limit: Enable rate limiting (default: True)
                - dry_run: Simulate orders without sending (default: False)
        """
        self.config = config
        self.name = "base"
        self.testnet = config.get('testnet', False)
        self.dry_run = config.get('dry_run', False)

    # ========================================================================
    # PUBLIC ENDPOINTS (no authentication required)
    # ========================================================================

    @abstractmethod
    def get_ticker(self, symbol: str) -> Ticker:
        """
        Get current ticker for a symbol.

        Args:
            symbol: Symbol in BASE/QUOTE format (e.g., BTC/USDT)

        Returns:
            Ticker with current bid/ask/last/volume

        Raises:
            ValueError: Invalid symbol or not a spot market
            ConnectionError: Network/API error
        """
        pass

    @abstractmethod
    def get_market(self, symbol: str) -> Market:
        """
        Get market information (trading rules, precision, limits).

        Args:
            symbol: Symbol in BASE/QUOTE format

        Returns:
            Market with precision, limits, fees

        Raises:
            ValueError: Invalid symbol or not a spot market
        """
        pass

    @abstractmethod
    def get_markets(self) -> Dict[str, Market]:
        """
        Get all available spot markets.

        Returns:
            Dict mapping symbol → Market
            Only includes SPOT markets (no margin/futures)
        """
        pass

    @abstractmethod
    def get_exchange_info(self) -> ExchangeInfo:
        """
        Get exchange metadata.

        Returns:
            ExchangeInfo with name, rate limits, capabilities
        """
        pass

    # ========================================================================
    # PRIVATE ENDPOINTS (authentication required)
    # ========================================================================

    @abstractmethod
    def get_balance(self, currency: Optional[str] = None) -> Dict[str, Balance]:
        """
        Get account balances.

        Args:
            currency: Optional currency filter (e.g., "BTC", "USDT")
                     If None, returns all non-zero balances

        Returns:
            Dict mapping currency → Balance
            Only includes SPOT balances (no margin accounts)

        Raises:
            AuthenticationError: Invalid API credentials
            ConnectionError: Network/API error
        """
        pass

    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all open orders.

        Args:
            symbol: Optional symbol filter (BASE/QUOTE format)
                   If None, returns open orders for all symbols

        Returns:
            List of open orders, sorted by timestamp (oldest first)
            Only includes SPOT orders
        """
        pass

    @abstractmethod
    def get_order(self, order_id: str, symbol: str) -> Order:
        """
        Get order details by ID.

        Args:
            order_id: Exchange order ID
            symbol: Symbol (required by some exchanges)

        Returns:
            Order with current status

        Raises:
            ValueError: Order not found
        """
        pass

    @abstractmethod
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
        Create a new spot order.

        Args:
            symbol: Symbol in BASE/QUOTE format (e.g., BTC/USDT)
            side: OrderSide.BUY or OrderSide.SELL
            order_type: OrderType.MARKET or OrderType.LIMIT
            amount: Order amount in base currency
            price: Limit price (required for LIMIT orders, ignored for MARKET)
            params: Additional exchange-specific parameters (optional)

        Returns:
            Order object with exchange order ID

        Raises:
            ValueError: Invalid parameters or not a spot market
            InsufficientFundsError: Not enough balance
            InvalidOrderError: Order rejected by exchange

        CRITICAL VALIDATIONS:
        1. Market must be SPOT only
        2. Amount must meet min/max requirements
        3. Price must have correct precision
        4. No margin/leverage parameters allowed
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> Order:
        """
        Cancel an open order.

        Args:
            order_id: Exchange order ID
            symbol: Symbol (required by some exchanges)

        Returns:
            Order with status=CANCELED

        Raises:
            ValueError: Order not found or already closed
        """
        pass

    @abstractmethod
    def cancel_all_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Cancel all open orders.

        Args:
            symbol: Optional symbol filter
                   If None, cancels ALL open orders (use with caution!)

        Returns:
            List of canceled orders
        """
        pass

    @abstractmethod
    def get_fills(self, symbol: Optional[str] = None, since: Optional[datetime] = None) -> List[Fill]:
        """
        Get trade fills (executions).

        Args:
            symbol: Optional symbol filter
            since: Optional time filter (fills after this timestamp)

        Returns:
            List of fills, sorted by timestamp
        """
        pass

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def validate_spot_only(self, symbol: str) -> None:
        """
        Validate that a symbol is a spot market.

        Args:
            symbol: Symbol to validate

        Raises:
            ValueError: If market is not SPOT

        CRITICAL: This enforces halal compliance (no leverage/margin)
        """
        market = self.get_market(symbol)
        if market.market_type != MarketType.SPOT:
            raise ValueError(
                f"Market {symbol} is not SPOT (got {market.market_type}). "
                f"Only spot trading allowed for halal compliance."
            )

    def validate_order_params(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Optional[Decimal] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Validate order parameters before submission.

        Raises:
            ValueError: Invalid parameters

        Checks:
        1. Market is SPOT only
        2. Amount meets min/max requirements
        3. Price is provided for LIMIT orders
        4. Price has correct precision
        5. No leverage/margin parameters
        """
        # 1. Validate spot only
        self.validate_spot_only(symbol)

        # 2. Get market info
        market = self.get_market(symbol)

        # 3. Validate amount
        if amount < market.min_amount:
            raise ValueError(
                f"Amount {amount} below minimum {market.min_amount} for {symbol}"
            )

        if market.max_amount and amount > market.max_amount:
            raise ValueError(
                f"Amount {amount} exceeds maximum {market.max_amount} for {symbol}"
            )

        # 4. Validate price for LIMIT orders
        if order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Price required for LIMIT orders")

            if price <= 0:
                raise ValueError("Price must be positive")

        # 5. Check for forbidden parameters (leverage/margin)
        if params:
            forbidden = ['leverage', 'margin', 'marginMode', 'reduceOnly', 'isolated', 'cross']
            for key in forbidden:
                if key in params:
                    raise ValueError(
                        f"Parameter '{key}' not allowed. Spot trading only (halal compliance)."
                    )

    def format_amount(self, amount: Decimal, symbol: str) -> Decimal:
        """
        Format amount to exchange precision.

        Args:
            amount: Raw amount
            symbol: Symbol to get precision from

        Returns:
            Rounded amount with correct precision
        """
        market = self.get_market(symbol)
        precision = market.precision_amount
        return Decimal(f"{amount:.{precision}f}")

    def format_price(self, price: Decimal, symbol: str) -> Decimal:
        """
        Format price to exchange precision.

        Args:
            price: Raw price
            symbol: Symbol to get precision from

        Returns:
            Rounded price with correct precision
        """
        market = self.get_market(symbol)
        precision = market.precision_price
        return Decimal(f"{price:.{precision}f}")

    def calculate_cost(self, amount: Decimal, price: Decimal) -> Decimal:
        """
        Calculate order cost (amount * price).

        Args:
            amount: Amount in base currency
            price: Price in quote currency

        Returns:
            Cost in quote currency
        """
        return amount * price

    def is_testnet(self) -> bool:
        """Check if using testnet/sandbox."""
        return self.testnet

    def is_dry_run(self) -> bool:
        """Check if in dry-run mode (no real orders)."""
        return self.dry_run
