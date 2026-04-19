"""
KuCoin CCXT Connector
=====================
Production-ready KuCoin Spot connector with halal enforcement.

CRITICAL: Spot-only, no margin, no futures, no leverage.
API keys are read from environment variables for security.

Usage:
    from core.exchange.kucoin import KuCoinConnector

    connector = KuCoinConnector(
        api_key=os.getenv("KUCOIN_API_KEY"),
        api_secret=os.getenv("KUCOIN_API_SECRET"),
        passphrase=os.getenv("KUCOIN_PASSPHRASE"),
        testnet=False,  # Set True for sandbox
    )

    ticker = connector.get_ticker("BTC/USDT")
    balance = connector.get_balance()
    order = connector.create_market_order("BTC/USDT", "buy", Decimal("0.001"))
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timezone

import ccxt

from core.exchange.models import (
    Ticker,
    Balance,
    Order,
    Market,
    MarketType,
    OrderSide,
    OrderType,
    OrderStatus,
)
from core.utils.logging import get_logger

logger = get_logger(__name__)


class KuCoinConnector:
    """
    Production KuCoin CCXT connector.

    Enforces spot-only trading for halal compliance.
    Validates all parameters before sending to exchange.
    """

    FORBIDDEN_PARAMS = {
        "leverage",
        "margin",
        "marginMode",
        "reduceOnly",
        "isolated",
        "cross",
        "positionSide",
        "stopLoss",  # We use stop-loss via separate stop order, not via params
        "takeProfit",  # Same for TP
    }

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        testnet: bool = False,
        rate_limit: bool = True,
    ):
        """
        Initialize KuCoin connector.

        Args:
            api_key: KuCoin API key
            api_secret: KuCoin API secret
            passphrase: KuCoin API passphrase
            testnet: Use sandbox environment
            rate_limit: Enable CCXT rate limiting
        """
        self.testnet = testnet

        options = {
            "defaultType": "spot",  # CRITICAL: spot-only
            "adjustForTimeDifference": True,
            "recvWindow": 60000,
        }

        if testnet:
            # KuCoin sandbox
            self._exchange = ccxt.kucoinfutures({
                "apiKey": api_key,
                "secret": api_secret,
                "password": passphrase,
                "enableRateLimit": rate_limit,
                "options": options,
                "urls": {
                    "api": {
                        "public": "https://api-sandbox.kucoin.com",
                        "private": "https://api-sandbox.kucoin.com",
                    }
                },
            })
        else:
            self._exchange = ccxt.kucoin({
                "apiKey": api_key,
                "secret": api_secret,
                "password": passphrase,
                "enableRateLimit": rate_limit,
                "options": options,
            })

        # Force spot market type
        self._exchange.options["defaultType"] = "spot"

        logger.info(
            "kucoin_connector_initialized",
            testnet=testnet,
            exchange=self._exchange.id,
        )

    # ------------------------------------------------------------------ #
    # Public Data
    # ------------------------------------------------------------------ #

    def get_ticker(self, symbol: str) -> Ticker:
        """Fetch current ticker for a symbol."""
        raw = self._exchange.fetch_ticker(symbol)
        return Ticker(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(raw["timestamp"] / 1000, tz=timezone.utc),
            bid=Decimal(str(raw["bid"])),
            ask=Decimal(str(raw["ask"])),
            last=Decimal(str(raw["last"])),
            volume=Decimal(str(raw["baseVolume"])),
        )

    def get_market(self, symbol: str) -> Market:
        """Fetch market (trading pair) info."""
        markets = self._exchange.load_markets()
        raw = markets[symbol]

        # CRITICAL: enforce spot-only
        if raw.get("type") != "spot":
            raise ValueError(f"Only SPOT markets allowed (halal). Got: {raw.get('type')}")

        return Market(
            symbol=symbol,
            base=raw["base"],
            quote=raw["quote"],
            market_type=MarketType.SPOT,
            active=raw["active"],
            precision_price=raw["precision"]["price"],
            precision_amount=raw["precision"]["amount"],
            min_amount=Decimal(str(raw["limits"]["amount"]["min"])),
            max_amount=Decimal(str(raw["limits"]["amount"].get("max", 0))) if raw["limits"]["amount"].get("max") else None,
            min_cost=Decimal(str(raw["limits"]["cost"]["min"])),
            max_cost=Decimal(str(raw["limits"]["cost"].get("max", 0))) if raw["limits"]["cost"].get("max") else None,
            maker_fee=Decimal(str(raw.get("maker", 0.001))),
            taker_fee=Decimal(str(raw.get("taker", 0.001))),
            info=raw,
        )

    # ------------------------------------------------------------------ #
    # Account
    # ------------------------------------------------------------------ #

    def get_balance(self, currency: Optional[str] = None) -> Dict[str, Balance]:
        """
        Fetch account balance.

        Returns:
            Dict mapping currency code to Balance object.
            If currency is specified, returns single-item dict.
        """
        raw = self._exchange.fetch_balance({"type": "spot"})
        result = {}

        if currency:
            currencies = [currency]
        else:
            currencies = [c for c in raw["total"] if raw["total"][c] > 0]

        for curr in currencies:
            free = Decimal(str(raw["free"].get(curr, 0)))
            used = Decimal(str(raw["used"].get(curr, 0)))
            total = Decimal(str(raw["total"].get(curr, 0)))
            result[curr] = Balance(
                currency=curr,
                free=free,
                used=used,
                total=total,
            )

        return result

    # ------------------------------------------------------------------ #
    # Orders
    # ------------------------------------------------------------------ #

    def create_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        params: Optional[dict] = None,
    ) -> Order:
        """
        Create a market order (SPOT only).

        Args:
            symbol: Trading pair (e.g., BTC/USDT)
            side: "buy" or "sell"
            quantity: Amount in base currency
            params: Additional CCXT params (validated for halal compliance)

        Returns:
            Order object with exchange response
        """
        params = params or {}
        self._validate_order_params(params)

        raw = self._exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=float(quantity),
            params=params,
        )

        return self._parse_order(raw)

    def create_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        params: Optional[dict] = None,
    ) -> Order:
        """Create a limit order (SPOT only)."""
        params = params or {}
        self._validate_order_params(params)

        raw = self._exchange.create_limit_order(
            symbol=symbol,
            side=side,
            amount=float(quantity),
            price=float(price),
            params=params,
        )

        return self._parse_order(raw)

    def create_stop_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_price: Decimal,
        params: Optional[dict] = None,
    ) -> Order:
        """
        Create a stop-market order (triggers at stop_price, executes as market).

        KuCoin uses "stopPrice" param for stop orders.
        """
        params = params or {}
        params["stopPrice"] = float(stop_price)
        params["stop"] = "loss" if side == "sell" else "entry"
        self._validate_order_params(params)

        raw = self._exchange.create_order(
            symbol=symbol,
            type="market",
            side=side,
            amount=float(quantity),
            params=params,
        )

        return self._parse_order(raw)

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        """Cancel an open order."""
        return self._exchange.cancel_order(order_id, symbol)

    def get_order(self, order_id: str, symbol: str) -> Order:
        """Fetch order status."""
        raw = self._exchange.fetch_order(order_id, symbol)
        return self._parse_order(raw)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Fetch all open orders (optionally filtered by symbol)."""
        raw_orders = self._exchange.fetch_open_orders(symbol)
        return [self._parse_order(o) for o in raw_orders]

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    def _validate_order_params(self, params: dict) -> None:
        """
        Validate order params for halal compliance.

        Raises:
            ValueError: If forbidden params are present
        """
        forbidden_found = set(params.keys()) & self.FORBIDDEN_PARAMS
        if forbidden_found:
            raise ValueError(
                f"Halal compliance violation: forbidden order params {forbidden_found}"
            )

    def _parse_order(self, raw: dict) -> Order:
        """Convert CCXT order dict to our Order model."""
        return Order(
            id=raw["id"],
            symbol=raw["symbol"],
            side=OrderSide(raw["side"]),
            type=OrderType(raw["type"]),
            status=self._map_status(raw["status"]),
            amount=Decimal(str(raw["amount"])),
            filled=Decimal(str(raw.get("filled", 0))),
            remaining=Decimal(str(raw.get("remaining", raw["amount"]))),
            price=Decimal(str(raw["price"])) if raw.get("price") else None,
            average=Decimal(str(raw["average"])) if raw.get("average") else None,
            cost=Decimal(str(raw.get("cost", 0))),
            timestamp=datetime.fromtimestamp(raw["timestamp"] / 1000, tz=timezone.utc),
            last_update=datetime.fromtimestamp(
                raw.get("lastTradeTimestamp", raw["timestamp"]) / 1000,
                tz=timezone.utc,
            ),
            fee=raw.get("fee"),
            info=raw,
        )

    def _map_status(self, ccxt_status: str) -> OrderStatus:
        """Map CCXT status to our enum."""
        mapping = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.CLOSED,
            "canceled": OrderStatus.CANCELED,
            "cancelled": OrderStatus.CANCELED,
            "expired": OrderStatus.EXPIRED,
            "rejected": OrderStatus.REJECTED,
        }
        return mapping.get(ccxt_status, OrderStatus.PENDING)

    # ------------------------------------------------------------------ #
    # Health Check
    # ------------------------------------------------------------------ #

    def test_connection(self) -> bool:
        """Test API connectivity and authentication."""
        try:
            self._exchange.fetch_balance({"type": "spot"})
            logger.info("kucoin_connection_test_success")
            return True
        except Exception as exc:
            logger.error("kucoin_connection_test_failed", error=str(exc))
            return False
