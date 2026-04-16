"""
Analytics Module
================
Extended performance metrics beyond the backtest TradeTracker.

Usage:
    from core.analytics import compute_metrics, monthly_returns_table

    metrics = compute_metrics(trades, starting_balance=Decimal("10000"))
    monthly = monthly_returns_table(trades, starting_balance=Decimal("10000"))
"""

from core.analytics.metrics import (
    compute_metrics,
    monthly_returns_table,
    sharpe_ratio,
    sortino_ratio,
    calmar_ratio,
    expectancy,
    equity_curve,
)

__all__ = [
    "compute_metrics",
    "monthly_returns_table",
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_ratio",
    "expectancy",
    "equity_curve",
]
