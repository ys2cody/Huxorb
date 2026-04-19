"""
Performance Analytics
=====================
Financial metrics computed from a list of closed trades.

Works with both PaperTrade (core.paper) and BacktestTrade (core.backtest)
since both have: .pnl, .entry_time, .exit_time, .entry_price,
.exit_price, .quantity, .stop_loss, .strategy, .symbol attributes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal
from typing import List, Dict, Any, Sequence


# ------------------------------------------------------------------ #
# Types (structural typing — no import coupling)
# ------------------------------------------------------------------ #

class _Trade:
    """Duck-typed interface expected from trade objects."""
    pnl: Decimal
    entry_time: Any
    exit_time: Any
    entry_price: Decimal
    stop_loss: Decimal
    quantity: Decimal
    strategy: str
    symbol: str


# ------------------------------------------------------------------ #
# Core Building Blocks
# ------------------------------------------------------------------ #

def equity_curve(trades: Sequence, starting_balance: Decimal) -> List[Decimal]:
    """
    Return equity after each closed trade.

    Returns a list of length len(trades)+1 where index 0 is the
    starting balance and each subsequent value adds the trade PnL.
    """
    curve = [starting_balance]
    running = starting_balance
    for t in trades:
        running += t.pnl
        curve.append(running)
    return curve


def _period_returns(curve: List[Decimal]) -> List[float]:
    """Convert equity curve to per-trade return fractions."""
    returns = []
    for i in range(1, len(curve)):
        if curve[i - 1] != 0:
            r = float((curve[i] - curve[i - 1]) / curve[i - 1])
        else:
            r = 0.0
        returns.append(r)
    return returns


def _max_drawdown(curve: List[Decimal]) -> float:
    """Maximum peak-to-trough drawdown as a positive fraction."""
    peak = curve[0]
    max_dd = 0.0
    for val in curve:
        if val > peak:
            peak = val
        if peak > 0:
            dd = float((peak - val) / peak)
            if dd > max_dd:
                max_dd = dd
    return max_dd


# ------------------------------------------------------------------ #
# Individual Metrics
# ------------------------------------------------------------------ #

def sharpe_ratio(
    trades: Sequence,
    starting_balance: Decimal,
    risk_free_rate: float = 0.0,
    periods_per_year: float = 252.0,
) -> float:
    """
    Annualised Sharpe ratio using per-trade returns.

    periods_per_year defaults to 252 (daily-ish for crypto 24/7).
    Pass 365 if you prefer calendar days.
    """
    curve = equity_curve(trades, starting_balance)
    returns = _period_returns(curve)
    if len(returns) < 2:
        return 0.0

    n = len(returns)
    mean = sum(returns) / n
    excess = mean - risk_free_rate / periods_per_year
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance)

    if std == 0:
        return 0.0

    return excess / std * math.sqrt(periods_per_year)


def sortino_ratio(
    trades: Sequence,
    starting_balance: Decimal,
    risk_free_rate: float = 0.0,
    periods_per_year: float = 252.0,
) -> float:
    """
    Annualised Sortino ratio — penalises only downside volatility.
    """
    curve = equity_curve(trades, starting_balance)
    returns = _period_returns(curve)
    if len(returns) < 2:
        return 0.0

    n = len(returns)
    mean = sum(returns) / n
    excess = mean - risk_free_rate / periods_per_year
    downside = [min(r, 0.0) for r in returns]
    downside_var = sum(r ** 2 for r in downside) / n
    downside_std = math.sqrt(downside_var)

    if downside_std == 0:
        return 0.0 if excess <= 0 else float('inf')

    return excess / downside_std * math.sqrt(periods_per_year)


def calmar_ratio(
    trades: Sequence,
    starting_balance: Decimal,
) -> float:
    """
    Calmar ratio = annualised return / max drawdown.

    Returns 0 if there are no trades or no drawdown.
    """
    if not trades:
        return 0.0

    curve = equity_curve(trades, starting_balance)
    max_dd = _max_drawdown(curve)
    if max_dd == 0:
        return 0.0

    total_return = float((curve[-1] - curve[0]) / curve[0]) if curve[0] != 0 else 0.0

    # Estimate annualised return from time span
    first = trades[0].entry_time
    last = trades[-1].exit_time
    days = max((last - first).days, 1)
    ann_return = total_return * (365.0 / days)

    return ann_return / max_dd


def expectancy(trades: Sequence) -> float:
    """
    Average expected profit per trade in account currency.

    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    """
    if not trades:
        return 0.0

    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]
    n = len(trades)

    win_rate = len(winners) / n
    loss_rate = len(losers) / n

    avg_win = float(sum(t.pnl for t in winners) / len(winners)) if winners else 0.0
    avg_loss = abs(float(sum(t.pnl for t in losers) / len(losers))) if losers else 0.0

    return (win_rate * avg_win) - (loss_rate * avg_loss)


# ------------------------------------------------------------------ #
# Monthly Returns
# ------------------------------------------------------------------ #

def monthly_returns_table(
    trades: Sequence,
    starting_balance: Decimal,
) -> Dict[str, Dict[str, float]]:
    """
    Group returns by year-month.

    Returns:
        {
            "2025-01": {"pnl": 450.50, "trades": 8, "win_rate": 62.5},
            "2025-02": { ... },
            ...
        }
    """
    monthly: Dict[str, Dict] = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})

    for t in trades:
        key = t.exit_time.strftime("%Y-%m")
        monthly[key]["pnl"] += float(t.pnl)
        monthly[key]["trades"] += 1
        if t.pnl > 0:
            monthly[key]["wins"] += 1

    result = {}
    for month, data in sorted(monthly.items()):
        n = data["trades"]
        result[month] = {
            "pnl": round(data["pnl"], 2),
            "trades": n,
            "win_rate": round(data["wins"] / n * 100, 1) if n else 0.0,
        }
    return result


# ------------------------------------------------------------------ #
# Full Metrics Report
# ------------------------------------------------------------------ #

def compute_metrics(
    trades: Sequence,
    starting_balance: Decimal,
    risk_free_rate: float = 0.0,
) -> Dict[str, Any]:
    """
    Compute the full analytics report for a set of closed trades.

    Returns a flat dict suitable for display or JSON serialisation.
    """
    if not trades:
        return {
            "total_trades": 0,
            "starting_balance": str(starting_balance),
            "final_equity": str(starting_balance),
            "total_pnl": "0.00",
            "roi_pct": "0.00%",
            "win_rate_pct": "N/A",
            "profit_factor": "N/A",
            "expectancy": "0.00",
            "sharpe": "N/A",
            "sortino": "N/A",
            "calmar": "N/A",
            "max_drawdown_pct": "0.00%",
        }

    curve = equity_curve(trades, starting_balance)
    final_equity = curve[-1]
    total_pnl = final_equity - starting_balance
    roi = float(total_pnl / starting_balance * 100) if starting_balance != 0 else 0.0

    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]
    win_rate = len(winners) / len(trades) * 100

    gross_profit = sum(float(t.pnl) for t in winners)
    gross_loss = abs(sum(float(t.pnl) for t in losers))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    max_dd = _max_drawdown(curve)

    # Strategy breakdown
    by_strategy: Dict[str, Dict] = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
    for t in trades:
        s = t.strategy
        by_strategy[s]["trades"] += 1
        by_strategy[s]["pnl"] += float(t.pnl)
        if t.pnl > 0:
            by_strategy[s]["wins"] += 1

    strategy_summary = {}
    for strat, data in by_strategy.items():
        n = data["trades"]
        strategy_summary[strat] = {
            "trades": n,
            "pnl": round(data["pnl"], 2),
            "win_rate": round(data["wins"] / n * 100, 1) if n else 0.0,
        }

    return {
        "total_trades": len(trades),
        "starting_balance": str(starting_balance.quantize(Decimal("0.01"))),
        "final_equity": str(final_equity.quantize(Decimal("0.01"))),
        "total_pnl": f"{float(total_pnl):.2f}",
        "roi_pct": f"{roi:.2f}%",
        "win_rate_pct": f"{win_rate:.1f}%",
        "winners": len(winners),
        "losers": len(losers),
        "profit_factor": f"{profit_factor:.2f}" if profit_factor != float("inf") else "inf",
        "expectancy": f"{expectancy(trades):.2f}",
        "sharpe": f"{sharpe_ratio(trades, starting_balance, risk_free_rate):.2f}",
        "sortino": f"{sortino_ratio(trades, starting_balance, risk_free_rate):.2f}",
        "calmar": f"{calmar_ratio(trades, starting_balance):.2f}",
        "max_drawdown_pct": f"{max_dd * 100:.2f}%",
        "by_strategy": strategy_summary,
    }
