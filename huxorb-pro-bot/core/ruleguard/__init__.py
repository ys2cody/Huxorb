"""
RuleGuard System
================
Validation layer that protects every order from being placed unless ALL
preconditions pass.

Components:
- RiskManager: Position sizing, drawdown, daily limits
- SessionFilter: Optional trading hours (crypto is 24/7, but you may prefer quiet hours)
- NewsFilter: Block trading around high-impact events (FOMC, CPI, etc.)
- ConfigProfiles: Multi-account profiles with per-account jitter
- RuleGuard: Orchestrator that runs every check in order

Usage:
    from core.ruleguard import RuleGuard, RiskManager, SessionFilter, NewsFilter, ConfigProfiles

    risk = RiskManager(starting_balance=Decimal("10000"))
    sessions = SessionFilter.all_day()
    news = NewsFilter(enabled=False)
    profile = ConfigProfiles.default()

    guard = RuleGuard(
        risk_manager=risk,
        session_filter=sessions,
        news_filter=news,
        config=profile,
        dry_run=True,
    )

    decision = guard.can_open_trade(
        symbol="BTC/USDT",
        side="buy",
        quantity=Decimal("0.01"),
        entry_price=Decimal("60000"),
        stop_loss=Decimal("59000"),
        take_profit=Decimal("62000"),
    )

    if decision.allowed:
        # place order
        ...
    else:
        logger.warning("blocked", reason=decision.reason, detail=decision.detail)
"""

from core.ruleguard.reasons import RuleGuardReason
from core.ruleguard.risk_manager import RiskManager
from core.ruleguard.session_filter import SessionFilter, TradingSession
from core.ruleguard.news_filter import NewsFilter, NewsEvent
from core.ruleguard.config_profiles import ConfigProfiles, AccountProfile
from core.ruleguard.rule_guard import RuleGuard, RuleGuardDecision, RuleGuardStatus

__all__ = [
    "RuleGuardReason",
    "RiskManager",
    "SessionFilter",
    "TradingSession",
    "NewsFilter",
    "NewsEvent",
    "ConfigProfiles",
    "AccountProfile",
    "RuleGuard",
    "RuleGuardDecision",
    "RuleGuardStatus",
]
