"""
Alert System
============
Event-driven notifications for trade events, drawdown warnings, and
daily summaries. Handlers are pluggable — add console, webhook,
Telegram, or any other sink.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from core.utils.logging import get_logger

logger = get_logger(__name__)


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class Alert:
    """A single alert event."""
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


# ------------------------------------------------------------------ #
# Handlers (pluggable sinks)
# ------------------------------------------------------------------ #

class ConsoleAlertHandler:
    """Prints alerts to the terminal with colour via structlog."""

    LEVEL_COLOURS = {
        AlertLevel.INFO: "\033[36m",       # Cyan
        AlertLevel.WARNING: "\033[33m",    # Yellow
        AlertLevel.CRITICAL: "\033[91m",   # Bright red
    }
    RESET = "\033[0m"

    def handle(self, alert: Alert) -> None:
        colour = self.LEVEL_COLOURS.get(alert.level, "")
        ts = alert.timestamp.strftime("%H:%M:%S")
        print(
            f"{colour}[{ts}] [{alert.level.value}] {alert.title}: "
            f"{alert.message}{self.RESET}"
        )
        logger.info(
            "alert",
            level=alert.level.value,
            title=alert.title,
            message=alert.message,
        )


class WebhookAlertHandler:
    """
    Posts alerts as JSON to a webhook URL (Slack, Discord, custom).

    Only sends WARNING and CRITICAL alerts to avoid noise.
    Requires the `requests` library.
    """

    def __init__(self, url: str, min_level: AlertLevel = AlertLevel.WARNING):
        self.url = url
        self.min_level = min_level
        self._levels_order = [AlertLevel.INFO, AlertLevel.WARNING, AlertLevel.CRITICAL]

    def _level_rank(self, level: AlertLevel) -> int:
        try:
            return self._levels_order.index(level)
        except ValueError:
            return 0

    def handle(self, alert: Alert) -> None:
        if self._level_rank(alert.level) < self._level_rank(self.min_level):
            return
        try:
            import requests  # optional dependency
            payload = {"text": f"*[{alert.level.value}]* {alert.title}\n{alert.message}"}
            requests.post(self.url, json=payload, timeout=5)
        except Exception as exc:
            logger.warning("webhook_alert_failed", error=str(exc))


# ------------------------------------------------------------------ #
# AlertManager
# ------------------------------------------------------------------ #

class AlertManager:
    """
    Central alert dispatcher.

    Register handlers and then call the event methods as trades happen.
    Checks portfolio thresholds on each call to `check_thresholds()`.
    """

    def __init__(
        self,
        daily_drawdown_warn_pct: float = 2.0,
        total_drawdown_warn_pct: float = 5.0,
        total_drawdown_critical_pct: float = 10.0,
    ):
        self._handlers: List = []
        self._alerts: List[Alert] = []
        self.daily_dd_warn = daily_drawdown_warn_pct / 100
        self.total_dd_warn = total_drawdown_warn_pct / 100
        self.total_dd_critical = total_drawdown_critical_pct / 100

    def add_handler(self, handler) -> "AlertManager":
        """Chain-register a handler. Returns self for fluent API."""
        self._handlers.append(handler)
        return self

    @property
    def alerts(self) -> List[Alert]:
        return list(self._alerts)

    def _dispatch(self, alert: Alert) -> None:
        self._alerts.append(alert)
        for handler in self._handlers:
            try:
                handler.handle(alert)
            except Exception as exc:
                logger.warning("alert_handler_error", error=str(exc))

    # ------------------------------------------------------------------ #
    # Trade Events
    # ------------------------------------------------------------------ #

    def on_trade_entry(self, position) -> None:
        """Call when a new paper/live position is opened."""
        self._dispatch(Alert(
            level=AlertLevel.INFO,
            title="Trade Entry",
            message=(
                f"{position.symbol} {position.strategy.upper()} "
                f"@ {position.entry_price} | SL {position.stop_loss} | TP {position.take_profit}"
            ),
            metadata={
                "symbol": position.symbol,
                "strategy": position.strategy,
                "entry": str(position.entry_price),
                "sl": str(position.stop_loss),
                "tp": str(position.take_profit),
                "qty": str(position.quantity),
            },
        ))

    def on_trade_exit(self, trade) -> None:
        """Call when a position is closed."""
        pnl = float(trade.pnl)
        level = AlertLevel.INFO if pnl >= 0 else AlertLevel.WARNING
        sign = "+" if pnl >= 0 else ""
        self._dispatch(Alert(
            level=level,
            title="Trade Exit",
            message=(
                f"{trade.symbol} {trade.exit_reason.upper()} "
                f"{sign}{pnl:.2f} USDT"
            ),
            metadata={
                "symbol": trade.symbol,
                "exit_reason": trade.exit_reason,
                "pnl": str(trade.pnl),
            },
        ))

    def on_drawdown_warning(
        self,
        drawdown_pct: float,
        balance: Decimal,
        period: str = "total",
    ) -> None:
        """Call when drawdown threshold is breached."""
        level = AlertLevel.CRITICAL if drawdown_pct >= self.total_dd_critical * 100 else AlertLevel.WARNING
        self._dispatch(Alert(
            level=level,
            title=f"Drawdown Warning ({period})",
            message=f"{drawdown_pct:.1f}% drawdown — balance {balance:.2f} USDT",
            metadata={"drawdown_pct": drawdown_pct, "balance": str(balance), "period": period},
        ))

    def on_daily_summary(self, portfolio, prices: Optional[dict] = None) -> None:
        """Call at end of day to log a portfolio summary alert."""
        prices = prices or {}
        summary = portfolio.summary(prices)
        self._dispatch(Alert(
            level=AlertLevel.INFO,
            title="Daily Summary",
            message=(
                f"Equity {summary.get('equity', 'N/A')} USDT | "
                f"PnL {summary.get('total_pnl', '0')} | "
                f"Trades {summary.get('total_trades', 0)} | "
                f"Win rate {summary.get('win_rate', 'N/A')}"
            ),
            metadata=summary,
        ))

    # ------------------------------------------------------------------ #
    # Threshold Checks
    # ------------------------------------------------------------------ #

    def check_thresholds(self, portfolio, prices: Optional[dict] = None) -> None:
        """
        Inspect portfolio state and fire warnings if thresholds are breached.
        Call this once per trading cycle.
        """
        prices = prices or {}
        starting = portfolio.starting_balance
        equity = portfolio.equity(prices)

        if starting == 0:
            return

        total_dd = float((starting - equity) / starting)

        if total_dd >= self.total_dd_critical:
            self.on_drawdown_warning(total_dd * 100, equity, "total")
        elif total_dd >= self.total_dd_warn:
            self.on_drawdown_warning(total_dd * 100, equity, "total")

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def export_alerts(self, filepath) -> None:
        """Write all alerts to a JSON file."""
        from pathlib import Path
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([a.to_dict() for a in self._alerts], indent=2))
        logger.info("alerts_exported", path=str(path), count=len(self._alerts))
