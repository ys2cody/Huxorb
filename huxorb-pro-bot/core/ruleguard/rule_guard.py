"""
RuleGuard Orchestrator
======================
Single chokepoint for all order decisions. Every `create_order()` call in
the strategy MUST be gated by `guard.can_open_trade(...)`.

Validation order (fail-fast):

1. Dry-run mode (always blocks, logs intended action)
2. Trading globally disabled (drawdown, manual halt)
3. Parameter sanity (prices > 0, SL/TP on correct side, not too close)
4. Spread check
5. Session check
6. News blackout check
7. Risk limits (quantity cap, daily trades, open trades, DD)
8. Entry delay jitter

If any step fails, we return a RuleGuardDecision with `allowed=False` and a
RuleGuardReason code.

Halal enforcement
-----------------
This orchestrator does NOT attempt to verify that the symbol is spot-only;
that invariant is already enforced by Pydantic at the Market model level
and by the exchange connector. We DO however refuse any `params` dict that
smells like leverage ("leverage", "margin", "reduceOnly", etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from core.ruleguard.config_profiles import ConfigProfiles
from core.ruleguard.news_filter import NewsFilter
from core.ruleguard.reasons import RuleGuardReason
from core.ruleguard.risk_manager import RiskManager
from core.ruleguard.session_filter import SessionFilter
from core.utils.logging import get_logger

logger = get_logger(__name__)


FORBIDDEN_ORDER_PARAMS = {
    "leverage",
    "margin",
    "marginmode",
    "margin_mode",
    "reduceonly",
    "reduce_only",
    "isolated",
    "cross",
    "positionside",
    "position_side",
}


@dataclass
class RuleGuardDecision:
    """Result of a RuleGuard gate check."""

    allowed: bool
    reason: RuleGuardReason = RuleGuardReason.OK
    detail: str = ""

    def __bool__(self) -> bool:
        return self.allowed

    def as_dict(self) -> Dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason.value, "detail": self.detail}


@dataclass
class RuleGuardStatus:
    """Human-friendly snapshot of every subsystem."""

    dry_run: bool
    trading_enabled: bool
    in_session: bool
    current_session: str
    in_news_blackout: bool
    news_detail: str
    next_news_event_utc: Optional[datetime]
    trades_today: int
    max_trades_per_day: int
    open_trades: int
    max_open_trades: int
    current_balance: Decimal
    daily_pnl: Decimal
    daily_drawdown_pct: Decimal
    total_drawdown_pct: Decimal
    current_jitter_sec: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "trading_enabled": self.trading_enabled,
            "in_session": self.in_session,
            "current_session": self.current_session,
            "in_news_blackout": self.in_news_blackout,
            "news_detail": self.news_detail,
            "next_news_event_utc": (
                self.next_news_event_utc.isoformat() if self.next_news_event_utc else None
            ),
            "trades_today": self.trades_today,
            "max_trades_per_day": self.max_trades_per_day,
            "open_trades": self.open_trades,
            "max_open_trades": self.max_open_trades,
            "current_balance": str(self.current_balance),
            "daily_pnl": str(self.daily_pnl),
            "daily_drawdown_pct": str(self.daily_drawdown_pct),
            "total_drawdown_pct": str(self.total_drawdown_pct),
            "current_jitter_sec": self.current_jitter_sec,
        }


@dataclass
class RuleGuard:
    """
    Ties together RiskManager, SessionFilter, NewsFilter, and ConfigProfiles.

    One RuleGuard instance per bot-process per account.
    """

    risk_manager: RiskManager
    session_filter: SessionFilter
    news_filter: NewsFilter
    config: ConfigProfiles
    dry_run: bool = False

    # Internal: track the time a signal was registered, for jitter delay.
    _pending_signal_time: Optional[datetime] = field(default=None)

    # ------------------------------------------------------------------ #
    # Signal/jitter plumbing
    # ------------------------------------------------------------------ #

    def register_signal(self, signal_time: Optional[datetime] = None) -> int:
        """
        Notify the guard that a new signal has fired. Returns the current
        jitter delay in seconds (so caller can log / schedule retry).
        """
        now = signal_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        self._pending_signal_time = now
        delay = self.config.calculate_entry_delay_sec(now=now)
        if delay > 0:
            logger.info("ruleguard_signal_registered", delay_sec=delay)
        return delay

    def clear_signal(self) -> None:
        self._pending_signal_time = None
        self.config.reset_jitter()

    # ------------------------------------------------------------------ #
    # Primary gate
    # ------------------------------------------------------------------ #

    def can_open_trade(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        entry_price: Decimal,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        bid: Optional[Decimal] = None,
        ask: Optional[Decimal] = None,
        params: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> RuleGuardDecision:
        """
        Check every precondition for opening a new trade.

        Args:
            symbol: e.g. "BTC/USDT"
            side: "buy" or "sell" (case-insensitive)
            quantity: intended base-currency qty
            entry_price: intended fill price
            stop_loss: optional SL price (recommended; required by most checks)
            take_profit: optional TP price
            bid/ask: current book (for spread check); if either is missing
                     the spread check is skipped
            params: extra order params (leverage/margin kwargs will be rejected)
            now: override current UTC time (testing)

        Returns:
            RuleGuardDecision. When False, `reason` is the machine code and
            `detail` is a human-readable explanation.
        """
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        side_norm = side.lower().strip()

        # 1. Dry run
        if self.dry_run:
            return self._block(
                RuleGuardReason.DRY_RUN_MODE,
                f"{side_norm} {quantity} {symbol} @ {entry_price}",
            )

        # 2. Forbidden params (halal compliance)
        if params:
            for key in params:
                if key.lower().replace("-", "_") in FORBIDDEN_ORDER_PARAMS:
                    return self._block(
                        RuleGuardReason.FORBIDDEN_PARAM,
                        f"param '{key}' not allowed (spot-only)",
                    )

        # 3. Parameter sanity
        ok, reason, detail = self._validate_params(
            side=side_norm,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        if not ok:
            return self._block(reason, detail)

        # 4. Spread
        if bid is not None and ask is not None:
            ok, reason, detail = self._validate_spread(bid=bid, ask=ask)
            if not ok:
                return self._block(reason, detail)

        # 5. Session
        in_session, session_name = self.session_filter.is_in_session(now=now)
        if not in_session:
            return self._block(RuleGuardReason.OUTSIDE_SESSION, session_name)

        # 6. News blackout
        blackout, news_detail = self.news_filter.is_blackout(symbol, now=now)
        if blackout:
            return self._block(RuleGuardReason.NEWS_BLACKOUT, news_detail)

        # 7. Risk
        ok, reason, detail = self.risk_manager.can_open_trade(quantity)
        if not ok:
            return self._block(reason, detail)

        # 8. Entry delay / jitter
        if self._pending_signal_time is not None:
            remaining = self.config.should_delay_entry(
                self._pending_signal_time, now=now
            )
            if remaining > 0:
                return self._block(
                    RuleGuardReason.ENTRY_DELAY_JITTER,
                    f"wait {remaining}s",
                )

        logger.info(
            "ruleguard_allow",
            symbol=symbol,
            side=side_norm,
            quantity=str(quantity),
            entry=str(entry_price),
            session=session_name,
        )
        return RuleGuardDecision(allowed=True, reason=RuleGuardReason.OK, detail="")

    # ------------------------------------------------------------------ #
    # Secondary gates
    # ------------------------------------------------------------------ #

    def can_modify_stops(
        self,
        *,
        order_id: str,
        new_stop_loss: Optional[Decimal] = None,
        new_take_profit: Optional[Decimal] = None,
    ) -> RuleGuardDecision:
        if self.dry_run:
            return self._block(
                RuleGuardReason.DRY_RUN_MODE,
                f"modify_stops(id={order_id})",
            )
        if not self.risk_manager.trading_enabled:
            return self._block(RuleGuardReason.TRADING_DISABLED, "risk disabled")

        if new_stop_loss is not None and new_stop_loss <= 0:
            return self._block(RuleGuardReason.INVALID_PRICE, f"sl={new_stop_loss}")
        if new_take_profit is not None and new_take_profit <= 0:
            return self._block(RuleGuardReason.INVALID_PRICE, f"tp={new_take_profit}")

        return RuleGuardDecision(allowed=True)

    def can_close_trade(self, *, order_id: str) -> RuleGuardDecision:
        if self.dry_run:
            return self._block(
                RuleGuardReason.DRY_RUN_MODE,
                f"close(id={order_id})",
            )
        # Always allow closing live positions (emergency exit path).
        return RuleGuardDecision(allowed=True)

    # ------------------------------------------------------------------ #
    # Status / reporting
    # ------------------------------------------------------------------ #

    def status(self, *, symbol: str, now: Optional[datetime] = None) -> RuleGuardStatus:
        now = now or datetime.now(timezone.utc)

        in_session, session_name = self.session_filter.is_in_session(now=now)
        blackout, news_detail = self.news_filter.is_blackout(symbol, now=now)

        next_event = self.news_filter.next_event(symbol=symbol, now=now)

        return RuleGuardStatus(
            dry_run=self.dry_run,
            trading_enabled=self.risk_manager.trading_enabled,
            in_session=in_session,
            current_session=session_name,
            in_news_blackout=blackout,
            news_detail=news_detail,
            next_news_event_utc=next_event.event_time_utc if next_event else None,
            trades_today=self.risk_manager.trades_today,
            max_trades_per_day=self.risk_manager.max_trades_per_day,
            open_trades=self.risk_manager.open_trades,
            max_open_trades=self.risk_manager.max_open_trades,
            current_balance=self.risk_manager.current_balance,
            daily_pnl=self.risk_manager.daily_pnl,
            daily_drawdown_pct=self.risk_manager.daily_drawdown_pct,
            total_drawdown_pct=self.risk_manager.total_drawdown_pct,
            current_jitter_sec=self.config._current_jitter_sec,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _block(self, reason: RuleGuardReason, detail: str) -> RuleGuardDecision:
        logger.info("ruleguard_block", reason=reason.value, detail=detail)
        return RuleGuardDecision(allowed=False, reason=reason, detail=detail)

    def _validate_params(
        self,
        *,
        side: str,
        quantity: Decimal,
        entry_price: Decimal,
        stop_loss: Optional[Decimal],
        take_profit: Optional[Decimal],
    ) -> tuple[bool, RuleGuardReason, str]:
        if side not in {"buy", "sell"}:
            return False, RuleGuardReason.INVALID_PARAMS, f"side={side}"
        if entry_price <= 0:
            return False, RuleGuardReason.INVALID_PRICE, f"entry={entry_price}"
        if quantity <= 0:
            return False, RuleGuardReason.INVALID_QUANTITY, f"qty={quantity}"

        if stop_loss is not None:
            if stop_loss <= 0:
                return False, RuleGuardReason.INVALID_PRICE, f"sl={stop_loss}"
            if side == "buy" and stop_loss >= entry_price:
                return (
                    False,
                    RuleGuardReason.WRONG_SL_SIDE,
                    f"buy sl {stop_loss} >= entry {entry_price}",
                )
            if side == "sell" and stop_loss <= entry_price:
                return (
                    False,
                    RuleGuardReason.WRONG_SL_SIDE,
                    f"sell sl {stop_loss} <= entry {entry_price}",
                )
            # SL must be at least 0.05% away from entry (sanity)
            min_distance = entry_price * Decimal("0.0005")
            if abs(entry_price - stop_loss) < min_distance:
                return (
                    False,
                    RuleGuardReason.SL_TP_TOO_CLOSE,
                    f"sl within 0.05% of entry",
                )

        if take_profit is not None:
            if take_profit <= 0:
                return False, RuleGuardReason.INVALID_PRICE, f"tp={take_profit}"
            if side == "buy" and take_profit <= entry_price:
                return (
                    False,
                    RuleGuardReason.WRONG_TP_SIDE,
                    f"buy tp {take_profit} <= entry {entry_price}",
                )
            if side == "sell" and take_profit >= entry_price:
                return (
                    False,
                    RuleGuardReason.WRONG_TP_SIDE,
                    f"sell tp {take_profit} >= entry {entry_price}",
                )

        return True, RuleGuardReason.OK, ""

    def _validate_spread(
        self,
        *,
        bid: Decimal,
        ask: Decimal,
    ) -> tuple[bool, RuleGuardReason, str]:
        if bid <= 0 or ask <= 0 or ask < bid:
            return False, RuleGuardReason.INVALID_PRICE, f"bid={bid} ask={ask}"

        spread_pct = (ask - bid) / bid * Decimal("100")
        max_pct = self.config.profile.max_spread_pct
        if spread_pct > max_pct:
            return (
                False,
                RuleGuardReason.SPREAD_TOO_HIGH,
                f"spread {spread_pct:.4f}% > {max_pct}%",
            )
        return True, RuleGuardReason.OK, ""
