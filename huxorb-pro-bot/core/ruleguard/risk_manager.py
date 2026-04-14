"""
Risk Manager
============
Position sizing, drawdown tracking, and trade count limits.

Ported from MT4 CRiskManager with crypto-specific adaptations:

- Forex "lot size" -> crypto "base quantity" (e.g. BTC)
- MT4 MODE_TICKVALUE math -> simple quote-currency risk math
- Forex pip stops -> price-based stops in quote currency
- Equity/balance tracked in quote currency (typically USDT/USD)

All calculations use Decimal for precision (no float rounding errors on money).

Halal note: this module is spot-only. Position sizing is based on how much
quote currency (e.g. USDT) you are willing to risk on a single trade, which
you already own. No leverage, no borrowed funds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Tuple

from core.ruleguard.reasons import RuleGuardReason
from core.utils.logging import get_logger

logger = get_logger(__name__)


# Floor to ROUND_DOWN so we never accidentally round UP into a bigger position
_DEFAULT_ROUND = ROUND_DOWN


@dataclass
class RiskManager:
    """
    Tracks balance, drawdown, and trade counts. Enforces hard risk limits.

    All balance values in quote currency (USDT for BTC/USDT markets).

    Attributes set at construction are config.
    Attributes beginning with `_` are mutable state (reset per-day).
    """

    # --- configuration (immutable after init) ---
    starting_balance: Decimal
    risk_per_trade_pct: Decimal = Decimal("0.5")
    max_quantity: Decimal = Decimal("1000")         # absolute cap on base qty
    max_open_trades: int = 3
    max_trades_per_day: int = 5
    daily_loss_limit_pct: Decimal = Decimal("5.0")
    max_drawdown_pct: Decimal = Decimal("10.0")
    daily_profit_cap_pct: Optional[Decimal] = None  # e.g. Decimal("40.0") for prop-style rules
    phase_target_amount: Optional[Decimal] = None   # used only if profit cap is set

    # --- mutable state ---
    _current_balance: Decimal = field(default=Decimal("0"))
    _peak_balance: Decimal = field(default=Decimal("0"))
    _daily_start_balance: Decimal = field(default=Decimal("0"))
    _current_day: Optional[date] = field(default=None)
    _trades_today: int = field(default=0)
    _open_trades: int = field(default=0)
    _trading_enabled: bool = field(default=True)
    _daily_trading_enabled: bool = field(default=True)
    _disabled_reason: Optional[str] = field(default=None)

    def __post_init__(self) -> None:
        if self.starting_balance <= 0:
            raise ValueError("starting_balance must be positive")
        if self.risk_per_trade_pct <= 0 or self.risk_per_trade_pct > 100:
            raise ValueError("risk_per_trade_pct must be in (0, 100]")
        if self.daily_loss_limit_pct <= 0 or self.daily_loss_limit_pct > 100:
            raise ValueError("daily_loss_limit_pct must be in (0, 100]")
        if self.max_drawdown_pct <= 0 or self.max_drawdown_pct > 100:
            raise ValueError("max_drawdown_pct must be in (0, 100]")
        if self.max_open_trades < 1:
            raise ValueError("max_open_trades must be >= 1")
        if self.max_trades_per_day < 1:
            raise ValueError("max_trades_per_day must be >= 1")

        self._current_balance = self.starting_balance
        self._peak_balance = self.starting_balance
        self._daily_start_balance = self.starting_balance
        self._current_day = datetime.now(timezone.utc).date()

        logger.info(
            "risk_manager_init",
            starting_balance=str(self.starting_balance),
            risk_per_trade_pct=str(self.risk_per_trade_pct),
            daily_loss_limit_pct=str(self.daily_loss_limit_pct),
            max_drawdown_pct=str(self.max_drawdown_pct),
        )

    # ------------------------------------------------------------------ #
    # Balance / day-rollover bookkeeping
    # ------------------------------------------------------------------ #

    def update_balance(self, new_balance: Decimal, *, now: Optional[datetime] = None) -> None:
        """
        Set the current quote-currency balance. Call this on every tick (or
        at least before each trade decision) so drawdown checks are fresh.
        """
        if new_balance < 0:
            raise ValueError("balance cannot be negative")

        now = now or datetime.now(timezone.utc)

        # Apply the new balance first so the day-rollover snapshots the
        # post-update equity (that is what "today started at X" means).
        self._current_balance = new_balance
        if new_balance > self._peak_balance:
            self._peak_balance = new_balance

        self._check_new_day(now)

        self.check_drawdown_limits()
        self.check_daily_profit_cap()

    def set_open_trades(self, count: int) -> None:
        """Called by the orchestrator with the live open-order count."""
        if count < 0:
            raise ValueError("open trades cannot be negative")
        self._open_trades = count

    def increment_trade_count(self) -> None:
        """Called once when a trade is actually placed."""
        self._trades_today += 1

    def _check_new_day(self, now: datetime) -> None:
        """Reset daily counters on UTC day boundary."""
        today = now.date()
        if self._current_day != today:
            logger.info(
                "risk_manager_new_day",
                previous_day=str(self._current_day),
                new_day=str(today),
                previous_trades=self._trades_today,
            )
            self._current_day = today
            self._trades_today = 0
            self._daily_start_balance = self._current_balance
            self._daily_trading_enabled = True

    # ------------------------------------------------------------------ #
    # Position sizing
    # ------------------------------------------------------------------ #

    def calculate_quantity(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        *,
        step_size: Optional[Decimal] = None,
        min_quantity: Optional[Decimal] = None,
        risk_pct: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Compute the base-currency quantity such that:

            quantity * |entry - stop_loss| == risk_amount

        where risk_amount = current_balance * risk_pct / 100.

        Args:
            entry_price: intended fill price (quote per base)
            stop_loss: price at which we will exit at a loss
            step_size: exchange's quantity step (will round DOWN)
            min_quantity: exchange's minimum order quantity
            risk_pct: override the instance's risk_per_trade_pct

        Returns:
            Quantity in base currency (e.g. BTC for BTC/USDT). May be 0
            if the calculated size is below exchange minimums or the SL
            is invalid.
        """
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if stop_loss <= 0:
            raise ValueError("stop_loss must be positive")

        pct = risk_pct if risk_pct is not None else self.risk_per_trade_pct
        risk_amount = self._current_balance * pct / Decimal("100")

        sl_distance = abs(entry_price - stop_loss)
        if sl_distance == 0:
            logger.warning("risk_sl_zero", entry=str(entry_price), sl=str(stop_loss))
            return Decimal("0")

        quantity = risk_amount / sl_distance

        # Apply step rounding (crypto exchanges have lot-step rules, e.g. 0.00001 BTC)
        if step_size and step_size > 0:
            quantity = (quantity / step_size).quantize(Decimal("1"), rounding=_DEFAULT_ROUND) * step_size

        # Cap at configured max
        if quantity > self.max_quantity:
            quantity = self.max_quantity

        # Enforce exchange minimum
        if min_quantity is not None and quantity < min_quantity:
            logger.info(
                "risk_below_min_quantity",
                calculated=str(quantity),
                min_quantity=str(min_quantity),
            )
            return Decimal("0")

        return quantity

    # ------------------------------------------------------------------ #
    # Validation (called by RuleGuard)
    # ------------------------------------------------------------------ #

    def can_open_trade(self, quantity: Decimal) -> Tuple[bool, RuleGuardReason, str]:
        """Return (allowed, reason_code, human_detail)."""
        if not self._trading_enabled:
            return False, RuleGuardReason.MAX_DRAWDOWN, self._disabled_reason or "trading disabled"
        if not self._daily_trading_enabled:
            return False, RuleGuardReason.DAILY_LOSS_LIMIT, self._disabled_reason or "daily limit"

        if quantity <= 0:
            return False, RuleGuardReason.INVALID_QUANTITY, f"quantity={quantity}"

        if quantity > self.max_quantity:
            return (
                False,
                RuleGuardReason.QUANTITY_CAP,
                f"{quantity} > max {self.max_quantity}",
            )

        if self._trades_today >= self.max_trades_per_day:
            return (
                False,
                RuleGuardReason.MAX_TRADES_TODAY,
                f"{self._trades_today}/{self.max_trades_per_day}",
            )

        if self._open_trades >= self.max_open_trades:
            return (
                False,
                RuleGuardReason.MAX_OPEN_TRADES,
                f"{self._open_trades}/{self.max_open_trades}",
            )

        return True, RuleGuardReason.OK, ""

    # ------------------------------------------------------------------ #
    # Limit enforcement
    # ------------------------------------------------------------------ #

    def check_drawdown_limits(self) -> None:
        """Disable trading if daily or max drawdown breached."""
        daily_dd = self.daily_drawdown_pct
        if daily_dd >= self.daily_loss_limit_pct and self._daily_trading_enabled:
            self._daily_trading_enabled = False
            self._disabled_reason = (
                f"daily DD {daily_dd:.2f}% >= {self.daily_loss_limit_pct}%"
            )
            logger.error("risk_daily_dd_hit", daily_dd_pct=str(daily_dd))

        max_dd = self.total_drawdown_pct
        if max_dd >= self.max_drawdown_pct and self._trading_enabled:
            self._trading_enabled = False
            self._disabled_reason = (
                f"max DD {max_dd:.2f}% >= {self.max_drawdown_pct}%"
            )
            logger.critical("risk_max_dd_hit", max_dd_pct=str(max_dd))

    def check_daily_profit_cap(self) -> None:
        """
        Optional: disable further trading once daily profit reaches a cap
        (useful for prop-firm-style consistency rules).
        """
        if self.daily_profit_cap_pct is None or self.phase_target_amount is None:
            return
        if not self._daily_trading_enabled:
            return

        profit_cap = (self.daily_profit_cap_pct / Decimal("100")) * self.phase_target_amount
        if self.daily_pnl >= profit_cap:
            self._daily_trading_enabled = False
            self._disabled_reason = (
                f"daily profit cap hit: {self.daily_pnl} >= {profit_cap}"
            )
            logger.warning("risk_profit_cap_hit", daily_pnl=str(self.daily_pnl))

    def disable_trading(self, reason: str) -> None:
        """Permanently disable trading (until process restart / reset)."""
        self._trading_enabled = False
        self._disabled_reason = reason
        logger.error("risk_trading_disabled", reason=reason)

    def reset_daily(self) -> None:
        """Manually reset daily counters (mostly used in tests)."""
        self._trades_today = 0
        self._daily_start_balance = self._current_balance
        self._daily_trading_enabled = True
        self._current_day = datetime.now(timezone.utc).date()

    # ------------------------------------------------------------------ #
    # Read-only accessors
    # ------------------------------------------------------------------ #

    @property
    def current_balance(self) -> Decimal:
        return self._current_balance

    @property
    def daily_pnl(self) -> Decimal:
        return self._current_balance - self._daily_start_balance

    @property
    def daily_drawdown_pct(self) -> Decimal:
        if self._daily_start_balance <= 0:
            return Decimal("0")
        dd = (self._daily_start_balance - self._current_balance) / self._daily_start_balance * Decimal("100")
        return max(dd, Decimal("0"))

    @property
    def total_drawdown_pct(self) -> Decimal:
        if self._peak_balance <= 0:
            return Decimal("0")
        dd = (self._peak_balance - self._current_balance) / self._peak_balance * Decimal("100")
        return max(dd, Decimal("0"))

    @property
    def trades_today(self) -> int:
        return self._trades_today

    @property
    def open_trades(self) -> int:
        return self._open_trades

    @property
    def trading_enabled(self) -> bool:
        return self._trading_enabled and self._daily_trading_enabled

    def status_snapshot(self) -> dict:
        return {
            "trading_enabled": self.trading_enabled,
            "current_balance": str(self._current_balance),
            "peak_balance": str(self._peak_balance),
            "daily_start_balance": str(self._daily_start_balance),
            "daily_pnl": str(self.daily_pnl),
            "daily_drawdown_pct": str(self.daily_drawdown_pct),
            "total_drawdown_pct": str(self.total_drawdown_pct),
            "trades_today": self._trades_today,
            "max_trades_per_day": self.max_trades_per_day,
            "open_trades": self._open_trades,
            "max_open_trades": self.max_open_trades,
            "disabled_reason": self._disabled_reason,
        }
