"""
Trade Tracker
=============
Records every trade and computes performance metrics after a backtest run.

Tracks:
- Entry/exit/stop/tp
- PnL per trade
- Running equity curve
- Win rate, profit factor, max drawdown, Sharpe, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

import pandas as pd

from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestTrade:
    """Single completed trade record."""

    trade_id: int
    symbol: str
    strategy: str
    regime: str

    # Entry
    entry_time: datetime
    entry_price: Decimal
    quantity: Decimal
    stop_loss: Decimal
    take_profit: Decimal

    # Exit
    exit_time: Optional[datetime] = None
    exit_price: Optional[Decimal] = None
    exit_reason: str = ""  # "stop_loss", "take_profit", "signal_exit", "end_of_data"

    @property
    def is_closed(self) -> bool:
        return self.exit_price is not None

    @property
    def pnl(self) -> Decimal:
        if not self.is_closed:
            return Decimal("0")
        return (self.exit_price - self.entry_price) * self.quantity

    @property
    def pnl_pct(self) -> Decimal:
        if not self.is_closed or self.entry_price == 0:
            return Decimal("0")
        return (self.exit_price - self.entry_price) / self.entry_price * Decimal("100")

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0

    @property
    def risk_amount(self) -> Decimal:
        """Amount of quote currency at risk."""
        return (self.entry_price - self.stop_loss) * self.quantity

    @property
    def reward_achieved(self) -> Optional[Decimal]:
        """R-multiple achieved."""
        risk = self.entry_price - self.stop_loss
        if risk <= 0 or not self.is_closed:
            return None
        return (self.exit_price - self.entry_price) / risk


@dataclass
class TradeTracker:
    """Tracks trades and computes metrics."""

    starting_balance: Decimal
    trades: List[BacktestTrade] = field(default_factory=list)
    _equity_curve: List[tuple] = field(default_factory=list)
    _next_id: int = field(default=1)

    def __post_init__(self):
        self._equity_curve.append((None, float(self.starting_balance)))

    def open_trade(
        self,
        *,
        symbol: str,
        strategy: str,
        regime: str,
        entry_time: datetime,
        entry_price: Decimal,
        quantity: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
    ) -> BacktestTrade:
        """Record a new trade entry."""
        trade = BacktestTrade(
            trade_id=self._next_id,
            symbol=symbol,
            strategy=strategy,
            regime=regime,
            entry_time=entry_time,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        self._next_id += 1
        self.trades.append(trade)
        return trade

    def close_trade(
        self,
        trade: BacktestTrade,
        exit_time: datetime,
        exit_price: Decimal,
        exit_reason: str,
    ) -> None:
        """Record a trade exit."""
        trade.exit_time = exit_time
        trade.exit_price = exit_price
        trade.exit_reason = exit_reason

        # Update equity curve
        current_equity = self.current_equity
        self._equity_curve.append((exit_time, float(current_equity)))

        logger.debug(
            "trade_closed",
            id=trade.trade_id,
            symbol=trade.symbol,
            pnl=str(trade.pnl),
            reason=exit_reason,
        )

    @property
    def open_trades(self) -> List[BacktestTrade]:
        return [t for t in self.trades if not t.is_closed]

    @property
    def closed_trades(self) -> List[BacktestTrade]:
        return [t for t in self.trades if t.is_closed]

    @property
    def current_equity(self) -> Decimal:
        total_pnl = sum(t.pnl for t in self.closed_trades)
        # Add unrealised PnL from open trades (mark to last known price)
        return self.starting_balance + total_pnl

    # ------------------------------------------------------------------ #
    # Performance Metrics
    # ------------------------------------------------------------------ #

    def compute_metrics(self) -> dict:
        """Compute comprehensive backtest metrics."""
        closed = self.closed_trades
        if not closed:
            return self._empty_metrics()

        winners = [t for t in closed if t.is_winner]
        losers = [t for t in closed if not t.is_winner]

        total_pnl = sum(t.pnl for t in closed)
        gross_profit = sum(t.pnl for t in winners) if winners else Decimal("0")
        gross_loss = abs(sum(t.pnl for t in losers)) if losers else Decimal("0")

        win_rate = len(winners) / len(closed) * 100 if closed else 0
        profit_factor = (
            float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        )

        # Average trade
        avg_pnl = total_pnl / len(closed)
        avg_winner = gross_profit / len(winners) if winners else Decimal("0")
        avg_loser = gross_loss / len(losers) if losers else Decimal("0")

        # R-multiples
        r_multiples = [t.reward_achieved for t in closed if t.reward_achieved is not None]
        avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else Decimal("0")

        # Max drawdown
        max_dd, max_dd_pct = self._max_drawdown()

        # Consecutive
        max_consec_wins, max_consec_losses = self._consecutive_streaks()

        # Return on investment
        roi_pct = total_pnl / self.starting_balance * Decimal("100")

        return {
            "total_trades": len(closed),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate_pct": round(win_rate, 1),
            "total_pnl": str(total_pnl.quantize(Decimal("0.01"))),
            "roi_pct": str(roi_pct.quantize(Decimal("0.01"))),
            "gross_profit": str(gross_profit.quantize(Decimal("0.01"))),
            "gross_loss": str(gross_loss.quantize(Decimal("0.01"))),
            "profit_factor": round(profit_factor, 2),
            "avg_pnl": str(avg_pnl.quantize(Decimal("0.01"))),
            "avg_winner": str(avg_winner.quantize(Decimal("0.01"))),
            "avg_loser": str(avg_loser.quantize(Decimal("0.01"))),
            "avg_r_multiple": str(avg_r.quantize(Decimal("0.01"))) if isinstance(avg_r, Decimal) else str(avg_r),
            "max_drawdown": str(max_dd.quantize(Decimal("0.01"))),
            "max_drawdown_pct": str(max_dd_pct.quantize(Decimal("0.01"))),
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "starting_balance": str(self.starting_balance),
            "ending_balance": str(self.current_equity.quantize(Decimal("0.01"))),
        }

    def _max_drawdown(self) -> tuple[Decimal, Decimal]:
        """Calculate max drawdown in absolute and percentage terms."""
        if not self.closed_trades:
            return Decimal("0"), Decimal("0")

        equity = float(self.starting_balance)
        peak = equity
        max_dd = 0.0
        max_dd_pct = 0.0

        for trade in self.closed_trades:
            equity += float(trade.pnl)
            if equity > peak:
                peak = equity
            dd = peak - equity
            dd_pct = dd / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct

        return Decimal(str(max_dd)), Decimal(str(max_dd_pct))

    def _consecutive_streaks(self) -> tuple[int, int]:
        """Find longest consecutive wins and losses."""
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in self.closed_trades:
            if trade.is_winner:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)

        return max_wins, max_losses

    def _empty_metrics(self) -> dict:
        return {
            "total_trades": 0,
            "winners": 0,
            "losers": 0,
            "win_rate_pct": 0,
            "total_pnl": "0.00",
            "roi_pct": "0.00",
            "gross_profit": "0.00",
            "gross_loss": "0.00",
            "profit_factor": 0,
            "avg_pnl": "0.00",
            "avg_winner": "0.00",
            "avg_loser": "0.00",
            "avg_r_multiple": "0.00",
            "max_drawdown": "0.00",
            "max_drawdown_pct": "0.00",
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "starting_balance": str(self.starting_balance),
            "ending_balance": str(self.starting_balance),
        }

    def trades_to_dataframe(self) -> pd.DataFrame:
        """Export trades as pandas DataFrame."""
        if not self.closed_trades:
            return pd.DataFrame()

        rows = []
        for t in self.closed_trades:
            rows.append({
                "trade_id": t.trade_id,
                "symbol": t.symbol,
                "strategy": t.strategy,
                "regime": t.regime,
                "entry_time": t.entry_time,
                "entry_price": float(t.entry_price),
                "exit_time": t.exit_time,
                "exit_price": float(t.exit_price) if t.exit_price else None,
                "quantity": float(t.quantity),
                "stop_loss": float(t.stop_loss),
                "take_profit": float(t.take_profit),
                "pnl": float(t.pnl),
                "pnl_pct": float(t.pnl_pct),
                "exit_reason": t.exit_reason,
                "r_multiple": float(t.reward_achieved) if t.reward_achieved else None,
            })

        return pd.DataFrame(rows)

    def print_summary(self) -> str:
        """Return a formatted summary string."""
        m = self.compute_metrics()
        lines = [
            "=" * 50,
            "         BACKTEST RESULTS",
            "=" * 50,
            f"  Total trades:        {m['total_trades']}",
            f"  Winners / Losers:    {m['winners']} / {m['losers']}",
            f"  Win rate:            {m['win_rate_pct']}%",
            f"  Profit factor:       {m['profit_factor']}",
            "",
            f"  Total PnL:           {m['total_pnl']} USDT",
            f"  ROI:                 {m['roi_pct']}%",
            f"  Avg trade:           {m['avg_pnl']} USDT",
            f"  Avg winner:          {m['avg_winner']} USDT",
            f"  Avg loser:          -{m['avg_loser']} USDT",
            f"  Avg R-multiple:      {m['avg_r_multiple']}R",
            "",
            f"  Max drawdown:        {m['max_drawdown']} USDT ({m['max_drawdown_pct']}%)",
            f"  Max consec. wins:    {m['max_consecutive_wins']}",
            f"  Max consec. losses:  {m['max_consecutive_losses']}",
            "",
            f"  Starting balance:    {m['starting_balance']} USDT",
            f"  Ending balance:      {m['ending_balance']} USDT",
            "=" * 50,
        ]
        return "\n".join(lines)
