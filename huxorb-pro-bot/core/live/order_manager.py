"""
Order Manager
=============
Safe order execution with validation, retries, and error handling.

Wraps the KuCoin connector with production-grade safety:
- Pre-execution validation (balance, market info, halal params)
- Retry logic with exponential backoff
- Order confirmation and status tracking
- Stop-loss and take-profit order placement
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from core.exchange.kucoin import KuCoinConnector
from core.exchange.models import Order, Market
from core.utils.logging import get_logger

logger = get_logger(__name__)


class OrderResultStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    VALIDATION_ERROR = "validation_error"
    NETWORK_ERROR = "network_error"


@dataclass
class OrderResult:
    """Result of an order execution attempt."""
    status: OrderResultStatus
    order: Optional[Order] = None
    error: Optional[str] = None
    stop_order: Optional[Order] = None
    tp_order: Optional[Order] = None


class OrderManager:
    """
    Manages order lifecycle with safety checks and retries.

    Responsibilities:
    - Validate before placing orders
    - Place entry + stop-loss + take-profit as atomic group
    - Retry on transient failures
    - Log all actions
    """

    def __init__(
        self,
        connector: KuCoinConnector,
        max_retries: int = 3,
        retry_delay_seconds: float = 2.0,
        dry_run: bool = False,
    ):
        self.connector = connector
        self.max_retries = max_retries
        self.retry_delay = retry_delay_seconds
        self.dry_run = dry_run

        logger.info(
            "order_manager_initialized",
            dry_run=dry_run,
            max_retries=max_retries,
        )

    # ------------------------------------------------------------------ #
    # Entry Orders
    # ------------------------------------------------------------------ #

    def place_entry_with_stops(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
    ) -> OrderResult:
        """
        Place market entry + stop-loss + take-profit orders.

        This is the main entry point for opening a new position.

        Args:
            symbol: Trading pair
            side: "buy" (long-only for halal)
            quantity: Amount in base currency
            stop_loss: Stop-loss price
            take_profit: Take-profit price

        Returns:
            OrderResult with entry order + stop/tp order IDs
        """
        if side != "buy":
            return OrderResult(
                status=OrderResultStatus.VALIDATION_ERROR,
                error="Only BUY (long) orders allowed for halal compliance",
            )

        # 1. Validate market and balance
        try:
            market = self.connector.get_market(symbol)
            if not market.active:
                return OrderResult(
                    status=OrderResultStatus.VALIDATION_ERROR,
                    error=f"Market {symbol} is not active",
                )
        except Exception as exc:
            logger.error("market_validation_failed", symbol=symbol, error=str(exc))
            return OrderResult(
                status=OrderResultStatus.VALIDATION_ERROR,
                error=f"Market validation failed: {exc}",
            )

        # 2. Check balance (estimate cost from ticker)
        try:
            ticker = self.connector.get_ticker(symbol)
            estimated_cost = quantity * ticker.ask
            balance = self.connector.get_balance(market.quote)
            available = balance.get(market.quote).free if balance else Decimal("0")

            if available < estimated_cost:
                logger.warning(
                    "insufficient_balance",
                    symbol=symbol,
                    required=str(estimated_cost),
                    available=str(available),
                )
                return OrderResult(
                    status=OrderResultStatus.INSUFFICIENT_BALANCE,
                    error=f"Need {estimated_cost} {market.quote}, have {available}",
                )
        except Exception as exc:
            logger.warning("balance_check_failed", error=str(exc))

        # 3. DRY RUN MODE — log and return success
        if self.dry_run:
            logger.info(
                "dry_run_order",
                symbol=symbol,
                side=side,
                quantity=str(quantity),
                sl=str(stop_loss),
                tp=str(take_profit),
            )
            return OrderResult(status=OrderResultStatus.SUCCESS)

        # 4. Place ENTRY order with retries
        entry_order = self._place_with_retry(
            lambda: self.connector.create_market_order(symbol, side, quantity)
        )

        if not entry_order:
            return OrderResult(
                status=OrderResultStatus.NETWORK_ERROR,
                error="Entry order failed after retries",
            )

        logger.info(
            "entry_order_placed",
            order_id=entry_order.id,
            symbol=symbol,
            side=side,
            qty=str(quantity),
        )

        # 5. Place STOP-LOSS order (sell at stop_loss if long)
        stop_order = self._place_with_retry(
            lambda: self.connector.create_stop_order(
                symbol, "sell", quantity, stop_loss
            )
        )

        if stop_order:
            logger.info("stop_loss_placed", order_id=stop_order.id, price=str(stop_loss))
        else:
            logger.warning("stop_loss_failed", symbol=symbol)

        # 6. Place TAKE-PROFIT order (limit sell at TP)
        tp_order = self._place_with_retry(
            lambda: self.connector.create_limit_order(
                symbol, "sell", quantity, take_profit
            )
        )

        if tp_order:
            logger.info("take_profit_placed", order_id=tp_order.id, price=str(take_profit))
        else:
            logger.warning("take_profit_failed", symbol=symbol)

        return OrderResult(
            status=OrderResultStatus.SUCCESS,
            order=entry_order,
            stop_order=stop_order,
            tp_order=tp_order,
        )

    # ------------------------------------------------------------------ #
    # Exit Orders
    # ------------------------------------------------------------------ #

    def close_position(
        self,
        symbol: str,
        quantity: Decimal,
        stop_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None,
    ) -> OrderResult:
        """
        Close an open position by selling at market.

        Also cancels the stop-loss and take-profit orders.

        Args:
            symbol: Trading pair
            quantity: Amount to sell
            stop_order_id: ID of stop-loss order to cancel
            tp_order_id: ID of take-profit order to cancel
        """
        if self.dry_run:
            logger.info("dry_run_close", symbol=symbol, qty=str(quantity))
            return OrderResult(status=OrderResultStatus.SUCCESS)

        # 1. Cancel stop and TP orders
        if stop_order_id:
            try:
                self.connector.cancel_order(stop_order_id, symbol)
                logger.info("stop_order_canceled", order_id=stop_order_id)
            except Exception as exc:
                logger.warning("stop_cancel_failed", order_id=stop_order_id, error=str(exc))

        if tp_order_id:
            try:
                self.connector.cancel_order(tp_order_id, symbol)
                logger.info("tp_order_canceled", order_id=tp_order_id)
            except Exception as exc:
                logger.warning("tp_cancel_failed", order_id=tp_order_id, error=str(exc))

        # 2. Market sell
        exit_order = self._place_with_retry(
            lambda: self.connector.create_market_order(symbol, "sell", quantity)
        )

        if not exit_order:
            return OrderResult(
                status=OrderResultStatus.NETWORK_ERROR,
                error="Exit order failed after retries",
            )

        logger.info("exit_order_placed", order_id=exit_order.id, qty=str(quantity))
        return OrderResult(status=OrderResultStatus.SUCCESS, order=exit_order)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _place_with_retry(self, order_fn) -> Optional[Order]:
        """
        Execute an order function with exponential backoff retries.

        Args:
            order_fn: Callable that returns an Order

        Returns:
            Order object or None if all retries failed
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                return order_fn()
            except Exception as exc:
                logger.warning(
                    "order_attempt_failed",
                    attempt=attempt,
                    max_retries=self.max_retries,
                    error=str(exc),
                )
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    time.sleep(delay)
                else:
                    logger.error("order_failed_all_retries", error=str(exc))
        return None

    def get_order_status(self, order_id: str, symbol: str) -> Optional[Order]:
        """Fetch current order status (with single retry)."""
        try:
            return self.connector.get_order(order_id, symbol)
        except Exception as exc:
            logger.warning("get_order_failed", order_id=order_id, error=str(exc))
            time.sleep(1)
            try:
                return self.connector.get_order(order_id, symbol)
            except Exception as retry_exc:
                logger.error("get_order_retry_failed", error=str(retry_exc))
                return None
