"""
Exchange Data Models
====================
Pydantic models for exchange entities (orders, balances, tickers, etc.)
Provides type safety and validation across all exchange implementations.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================================
# ENUMS
# ============================================================================

class OrderSide(str, Enum):
    """Order side: BUY or SELL."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type: MARKET or LIMIT (spot only)."""
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    """Order status lifecycle."""
    PENDING = "pending"      # Order created but not sent
    OPEN = "open"            # Order active on exchange
    CLOSED = "closed"        # Order fully filled
    CANCELED = "canceled"    # Order canceled
    EXPIRED = "expired"      # Order expired (time-in-force)
    REJECTED = "rejected"    # Order rejected by exchange


class MarketType(str, Enum):
    """Market type - SPOT ONLY for halal compliance."""
    SPOT = "spot"
    # NO MARGIN, NO FUTURES, NO SWAPS


# ============================================================================
# CORE MODELS
# ============================================================================

class Ticker(BaseModel):
    """Current market ticker data."""
    symbol: str = Field(..., description="Symbol in BASE/QUOTE format (e.g., BTC/USDT)")
    timestamp: datetime = Field(..., description="Server timestamp")
    bid: Decimal = Field(..., description="Best bid price")
    ask: Decimal = Field(..., description="Best ask price")
    last: Decimal = Field(..., description="Last traded price")
    volume: Decimal = Field(..., description="24h volume in base currency")

    @field_validator('bid', 'ask', 'last', 'volume')
    @classmethod
    def must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Price/volume must be positive")
        return v

    @property
    def spread(self) -> Decimal:
        """Spread as a percentage of bid."""
        return (self.ask - self.bid) / self.bid * Decimal(100)

    @property
    def mid(self) -> Decimal:
        """Mid price (average of bid/ask)."""
        return (self.bid + self.ask) / Decimal(2)


class Balance(BaseModel):
    """Account balance for a single currency."""
    currency: str = Field(..., description="Currency code (e.g., BTC, USDT)")
    free: Decimal = Field(..., description="Available balance (not in orders)")
    used: Decimal = Field(..., description="Balance locked in open orders")
    total: Decimal = Field(..., description="Total balance (free + used)")

    @field_validator('free', 'used', 'total')
    @classmethod
    def must_be_non_negative(cls, v):
        if v < 0:
            raise ValueError("Balance cannot be negative")
        return v

    @model_validator(mode='after')
    def total_must_match(self):
        if self.total != self.free + self.used:
            raise ValueError(
                f"Total {self.total} != free {self.free} + used {self.used}"
            )
        return self


class Order(BaseModel):
    """Order representation."""
    id: str = Field(..., description="Exchange order ID")
    symbol: str = Field(..., description="Symbol in BASE/QUOTE format")
    side: OrderSide = Field(..., description="Buy or sell")
    type: OrderType = Field(..., description="Market or limit")
    status: OrderStatus = Field(..., description="Order status")

    amount: Decimal = Field(..., description="Order amount in base currency")
    filled: Decimal = Field(default=Decimal(0), description="Filled amount")
    remaining: Decimal = Field(..., description="Remaining amount")

    price: Optional[Decimal] = Field(None, description="Limit price (None for market orders)")
    average: Optional[Decimal] = Field(None, description="Average fill price")
    cost: Decimal = Field(default=Decimal(0), description="Total cost in quote currency")

    timestamp: datetime = Field(..., description="Order creation time")
    last_update: datetime = Field(..., description="Last update time")

    fee: Optional[Dict[str, Any]] = Field(None, description="Fee details")
    info: Dict[str, Any] = Field(default_factory=dict, description="Raw exchange response")

    @field_validator('amount', 'filled', 'remaining')
    @classmethod
    def must_be_non_negative(cls, v):
        if v < 0:
            raise ValueError("Amount/filled/remaining cannot be negative")
        return v

    @model_validator(mode='after')
    def remaining_must_match(self):
        expected = self.amount - self.filled
        if self.remaining != expected:
            raise ValueError(
                f"Remaining {self.remaining} != amount {self.amount} - filled {self.filled}"
            )
        return self

    @property
    def is_open(self) -> bool:
        """Check if order is still open."""
        return self.status == OrderStatus.OPEN

    @property
    def is_closed(self) -> bool:
        """Check if order is closed (filled)."""
        return self.status == OrderStatus.CLOSED

    @property
    def is_canceled(self) -> bool:
        """Check if order was canceled."""
        return self.status == OrderStatus.CANCELED


class Fill(BaseModel):
    """Trade fill (execution)."""
    id: str = Field(..., description="Fill/trade ID")
    order_id: str = Field(..., description="Parent order ID")
    symbol: str = Field(..., description="Symbol in BASE/QUOTE format")
    side: OrderSide = Field(..., description="Buy or sell")

    price: Decimal = Field(..., description="Fill price")
    amount: Decimal = Field(..., description="Fill amount in base currency")
    cost: Decimal = Field(..., description="Fill cost in quote currency")

    timestamp: datetime = Field(..., description="Fill timestamp")
    fee: Optional[Dict[str, Any]] = Field(None, description="Fee details")
    info: Dict[str, Any] = Field(default_factory=dict, description="Raw exchange response")


class Market(BaseModel):
    """Market (trading pair) information."""
    symbol: str = Field(..., description="Symbol in BASE/QUOTE format")
    base: str = Field(..., description="Base currency (e.g., BTC)")
    quote: str = Field(..., description="Quote currency (e.g., USDT)")

    market_type: MarketType = Field(..., description="Market type (SPOT only)")
    active: bool = Field(..., description="Is market active?")

    # Precision & limits
    precision_price: int = Field(..., description="Price decimal places")
    precision_amount: int = Field(..., description="Amount decimal places")

    min_amount: Decimal = Field(..., description="Minimum order amount (base)")
    max_amount: Optional[Decimal] = Field(None, description="Maximum order amount (base)")
    min_cost: Decimal = Field(..., description="Minimum order cost (quote)")
    max_cost: Optional[Decimal] = Field(None, description="Maximum order cost (quote)")

    maker_fee: Decimal = Field(..., description="Maker fee rate (e.g., 0.001 = 0.1%)")
    taker_fee: Decimal = Field(..., description="Taker fee rate")

    info: Dict[str, Any] = Field(default_factory=dict, description="Raw exchange data")

    @field_validator('market_type')
    @classmethod
    def must_be_spot(cls, v):
        """CRITICAL: Enforce spot-only for halal compliance."""
        if v != MarketType.SPOT:
            raise ValueError(f"Only SPOT markets allowed (halal compliance). Got: {v}")
        return v


class ExchangeInfo(BaseModel):
    """Exchange metadata."""
    name: str = Field(..., description="Exchange name (e.g., binance)")
    rate_limit: int = Field(..., description="Rate limit (requests per second)")
    has_spot: bool = Field(..., description="Supports spot trading")
    has_margin: bool = Field(..., description="Supports margin trading")
    has_futures: bool = Field(..., description="Supports futures trading")

    @field_validator('has_margin', 'has_futures')
    @classmethod
    def must_not_use_leverage(cls, v):
        """Warn if exchange has margin/futures (we won't use them)."""
        # Don't raise error - just informational
        # We enforce spot-only at runtime in the connector
        return v


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol to BASE/QUOTE format.
    Examples:
        BTCUSDT → BTC/USDT
        BTC-USDT → BTC/USDT
        BTC/USDT → BTC/USDT (unchanged)
    """
    symbol = symbol.upper().strip()

    # Already in BASE/QUOTE format
    if '/' in symbol:
        return symbol

    # Handle BTC-USDT format (common in KuCoin, Kraken, etc.)
    if '-' in symbol:
        return symbol.replace('-', '/')

    # Handle BTCUSDT format (common in Binance)
    # We need to split intelligently - assume quote is USDT, USDC, BUSD, USD, BTC, ETH
    quote_currencies = ['USDT', 'USDC', 'BUSD', 'USD', 'BTC', 'ETH', 'BNB', 'EUR', 'GBP']

    for quote in quote_currencies:
        if symbol.endswith(quote):
            base = symbol[:-len(quote)]
            return f"{base}/{quote}"

    # Fallback: assume last 4 chars are quote (USDT)
    if len(symbol) > 4:
        return f"{symbol[:-4]}/{symbol[-4:]}"

    return symbol


def denormalize_symbol(symbol: str, exchange_format: str = 'binance') -> str:
    """
    Convert BASE/QUOTE to exchange-specific format.
    Examples:
        BTC/USDT → BTCUSDT (binance)
        BTC/USDT → BTC-USDT (kraken)
    """
    if '/' not in symbol:
        return symbol  # Already denormalized

    base, quote = symbol.split('/')

    if exchange_format == 'binance':
        return f"{base}{quote}"
    elif exchange_format == 'kraken':
        return f"{base}-{quote}"
    elif exchange_format == 'coinbase':
        return f"{base}-{quote}"
    else:
        return f"{base}{quote}"  # Default
