"""
RuleGuard Reason Codes
======================
Stable string codes used for block reasons in logs, metrics, and API responses.

Never change these values - downstream alerting may match on them.
"""

from enum import Enum


class RuleGuardReason(str, Enum):
    """Machine-readable reason codes for allow/deny decisions."""

    # Success
    OK = "OK"

    # Mode
    DRY_RUN_MODE = "DRY_RUN_MODE"
    TRADING_DISABLED = "TRADING_DISABLED"

    # Parameter validation
    INVALID_PARAMS = "INVALID_PARAMS"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    SL_TP_TOO_CLOSE = "SL_TP_TOO_CLOSE"
    WRONG_SL_SIDE = "WRONG_SL_SIDE"
    WRONG_TP_SIDE = "WRONG_TP_SIDE"

    # Spread
    SPREAD_TOO_HIGH = "SPREAD_TOO_HIGH"

    # Session
    OUTSIDE_SESSION = "OUTSIDE_SESSION"

    # News
    NEWS_BLACKOUT = "NEWS_BLACKOUT"

    # Risk
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    DAILY_PROFIT_CAP = "DAILY_PROFIT_CAP"
    MAX_OPEN_TRADES = "MAX_OPEN_TRADES"
    MAX_TRADES_TODAY = "MAX_TRADES_TODAY"
    QUANTITY_CAP = "QUANTITY_CAP"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"

    # Timing
    ENTRY_DELAY_JITTER = "ENTRY_DELAY_JITTER"

    # Halal compliance
    NOT_SPOT_MARKET = "NOT_SPOT_MARKET"
    FORBIDDEN_PARAM = "FORBIDDEN_PARAM"

    def __str__(self) -> str:
        return self.value
