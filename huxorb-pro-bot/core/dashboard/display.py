"""
Portfolio Dashboard
===================
Rich-based terminal display for paper/live portfolio state.

Usage (one-shot render):
    dashboard = PortfolioDashboard()
    dashboard.print_portfolio(portfolio, prices)

Usage (live refresh):
    with dashboard.live_view(portfolio, prices_fn) as live:
        live.start()  # polls every refresh_seconds
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Callable, Dict, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from core.analytics.metrics import compute_metrics, monthly_returns_table
from core.utils.logging import get_logger

logger = get_logger(__name__)

console = Console()


def _pnl_colour(value: float) -> str:
    return "green" if value >= 0 else "red"


def _pnl_str(value: float, prefix: str = "") -> Text:
    sign = "+" if value >= 0 else ""
    colour = _pnl_colour(value)
    return Text(f"{prefix}{sign}{value:.2f}", style=colour)


class PortfolioDashboard:
    """
    Renders portfolio state to the terminal using Rich.

    Works with PaperPortfolio (and any duck-typed portfolio with the
    same .balance, .open_positions, .closed_trades, .equity(),
    .starting_balance, .summary() interface).
    """

    def __init__(self, refresh_seconds: int = 60):
        self.refresh_seconds = refresh_seconds

    # ------------------------------------------------------------------ #
    # Individual Panels
    # ------------------------------------------------------------------ #

    def build_summary_panel(self, portfolio, prices: Dict[str, Decimal]) -> Panel:
        """Top-level equity/balance/metrics panel."""
        summary = portfolio.summary(prices)
        eq = portfolio.equity(prices)
        pnl_float = float(portfolio.total_pnl)

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column(no_wrap=True)

        table.add_row(
            "Balance",  str(portfolio.balance.quantize(Decimal("0.01"))) + " USDT",
            "Equity",   str(eq.quantize(Decimal("0.01"))) + " USDT",
        )
        table.add_row(
            "PnL",      _pnl_str(pnl_float, ""),
            "ROI",      summary.get("roi", "N/A"),
        )
        table.add_row(
            "Win rate", summary.get("win_rate", "N/A"),
            "Trades",   str(summary.get("total_trades", 0)),
        )
        table.add_row(
            "Open",     str(summary.get("open_positions", 0)),
            "Closed",   str(summary.get("total_trades", 0)),
        )

        # Extended analytics if trades exist
        trades = portfolio.closed_trades
        if trades:
            metrics = compute_metrics(trades, portfolio.starting_balance)
            table.add_row("", "", "", "")
            table.add_row(
                "Sharpe",   metrics.get("sharpe", "N/A"),
                "Sortino",  metrics.get("sortino", "N/A"),
            )
            table.add_row(
                "Max DD",   metrics.get("max_drawdown_pct", "N/A"),
                "Calmar",   metrics.get("calmar", "N/A"),
            )
            table.add_row(
                "Expectancy", metrics.get("expectancy", "N/A") + " USDT",
                "P-Factor", metrics.get("profit_factor", "N/A"),
            )

        return Panel(table, title="[bold white]HUXORB PRO — PORTFOLIO SUMMARY[/bold white]",
                     border_style="blue", box=box.ROUNDED)

    def build_positions_panel(self, portfolio, prices: Dict[str, Decimal]) -> Panel:
        """Open positions table."""
        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
        table.add_column("#", width=4)
        table.add_column("Symbol", width=10)
        table.add_column("Strategy", width=16)
        table.add_column("Entry", width=10)
        table.add_column("SL", width=10)
        table.add_column("TP", width=10)
        table.add_column("Qty", width=10)
        table.add_column("Price", width=10)
        table.add_column("uPnL", width=10)

        for pos in portfolio.open_positions:
            price = prices.get(pos.symbol, pos.entry_price)
            upnl = pos.unrealized_pnl(price)
            table.add_row(
                str(pos.position_id),
                pos.symbol,
                pos.strategy,
                str(pos.entry_price),
                str(pos.stop_loss),
                str(pos.take_profit),
                str(pos.quantity),
                str(price),
                _pnl_str(float(upnl)),
            )

        if not portfolio.open_positions:
            table.add_row("—", "No open positions", "", "", "", "", "", "", "")

        return Panel(table, title="[bold white]OPEN POSITIONS[/bold white]",
                     border_style="green", box=box.ROUNDED)

    def build_trades_panel(self, portfolio, n: int = 15) -> Panel:
        """Recent closed trades table."""
        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
        table.add_column("#", width=4)
        table.add_column("Symbol", width=10)
        table.add_column("Strategy", width=16)
        table.add_column("Entry", width=10)
        table.add_column("Exit", width=10)
        table.add_column("Reason", width=12)
        table.add_column("PnL", width=10)

        trades = portfolio.closed_trades[-n:]
        for trade in reversed(trades):
            table.add_row(
                str(trade.trade_id),
                trade.symbol,
                trade.strategy,
                str(trade.entry_price),
                str(trade.exit_price),
                trade.exit_reason,
                _pnl_str(float(trade.pnl)),
            )

        if not trades:
            table.add_row("—", "No closed trades", "", "", "", "", "")

        return Panel(table, title=f"[bold white]RECENT TRADES (last {n})[/bold white]",
                     border_style="yellow", box=box.ROUNDED)

    def build_monthly_panel(self, portfolio) -> Optional[Panel]:
        """Monthly returns breakdown — returns None if no trades."""
        trades = portfolio.closed_trades
        if not trades:
            return None

        monthly = monthly_returns_table(trades, portfolio.starting_balance)
        if not monthly:
            return None

        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
        table.add_column("Month", width=10)
        table.add_column("PnL", width=12)
        table.add_column("Trades", width=8)
        table.add_column("Win%", width=8)

        for month, data in sorted(monthly.items()):
            pnl = data["pnl"]
            table.add_row(
                month,
                _pnl_str(pnl),
                str(data["trades"]),
                f"{data['win_rate']}%",
            )

        return Panel(table, title="[bold white]MONTHLY RETURNS[/bold white]",
                     border_style="cyan", box=box.ROUNDED)

    # ------------------------------------------------------------------ #
    # Full Render
    # ------------------------------------------------------------------ #

    def print_portfolio(
        self,
        portfolio,
        prices: Optional[Dict[str, Decimal]] = None,
    ) -> None:
        """Print a full portfolio snapshot to the terminal."""
        prices = prices or {}
        console.print(self.build_summary_panel(portfolio, prices))
        console.print(self.build_positions_panel(portfolio, prices))
        console.print(self.build_trades_panel(portfolio))
        monthly = self.build_monthly_panel(portfolio)
        if monthly:
            console.print(monthly)

    def print_metrics_only(self, portfolio) -> None:
        """Print only the extended analytics metrics panel."""
        trades = portfolio.closed_trades
        if not trades:
            console.print("[yellow]No closed trades yet.[/yellow]")
            return

        metrics = compute_metrics(trades, portfolio.starting_balance)

        table = Table(box=box.SIMPLE_HEAD, header_style="bold magenta")
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", width=14)

        for key, val in metrics.items():
            if key in ("by_strategy", "starting_balance"):
                continue
            table.add_row(key.replace("_", " ").title(), str(val))

        console.print(Panel(table, title="[bold white]ANALYTICS[/bold white]",
                            border_style="blue", box=box.ROUNDED))

        # Strategy breakdown
        by_strat = metrics.get("by_strategy", {})
        if by_strat:
            strat_table = Table(box=box.SIMPLE_HEAD, header_style="bold magenta")
            strat_table.add_column("Strategy", style="cyan", width=18)
            strat_table.add_column("Trades", width=8)
            strat_table.add_column("PnL", width=12)
            strat_table.add_column("Win%", width=8)
            for strat, data in by_strat.items():
                strat_table.add_row(
                    strat,
                    str(data["trades"]),
                    _pnl_str(data["pnl"]),
                    f"{data['win_rate']}%",
                )
            console.print(Panel(strat_table, title="[bold white]BY STRATEGY[/bold white]",
                                border_style="magenta", box=box.ROUNDED))

    # ------------------------------------------------------------------ #
    # Live Refresh View
    # ------------------------------------------------------------------ #

    def live_view(
        self,
        portfolio,
        prices_fn: Callable[[], Dict[str, Decimal]],
    ) -> "_LiveRunner":
        """
        Context manager for a live-refreshing terminal dashboard.

        Usage:
            runner = dashboard.live_view(portfolio, lambda: fetch_prices())
            runner.run()  # blocks; Ctrl+C to stop
        """
        return _LiveRunner(self, portfolio, prices_fn, self.refresh_seconds)


class _LiveRunner:
    """Drives the Rich Live display with periodic refresh."""

    def __init__(self, dashboard: PortfolioDashboard, portfolio, prices_fn, refresh_seconds: int):
        self._dashboard = dashboard
        self._portfolio = portfolio
        self._prices_fn = prices_fn
        self._refresh_seconds = refresh_seconds

    def _build_layout(self, prices: Dict[str, Decimal]) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(self._dashboard.build_summary_panel(self._portfolio, prices), name="summary", size=12),
            Layout(self._dashboard.build_positions_panel(self._portfolio, prices), name="positions", size=10),
            Layout(self._dashboard.build_trades_panel(self._portfolio, n=10), name="trades"),
        )
        return layout

    def run(self) -> None:
        """Block and refresh until Ctrl+C."""
        with Live(console=console, refresh_per_second=1, screen=True) as live:
            try:
                while True:
                    prices = self._prices_fn()
                    live.update(self._build_layout(prices))
                    time.sleep(self._refresh_seconds)
            except KeyboardInterrupt:
                pass
