"""
Trade Journal Exporter
======================
Export closed trades and portfolio snapshots to CSV or JSON.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

from core.utils.logging import get_logger

logger = get_logger(__name__)


class TradeExporter:
    """
    Exports trade history and portfolio snapshots to disk.

    Works with PaperPortfolio.closed_trades or any iterable of
    objects with: trade_id, symbol, strategy, regime, entry_time,
    exit_time, entry_price, exit_price, quantity, stop_loss,
    take_profit, exit_reason, pnl attributes.
    """

    CSV_FIELDS = [
        "trade_id", "symbol", "strategy", "regime",
        "entry_time", "entry_price",
        "exit_time", "exit_price",
        "quantity", "stop_loss", "take_profit",
        "exit_reason", "pnl",
    ]

    def export_trades_csv(self, trades, filepath) -> Path:
        """Write trades to a CSV file. Returns the written path."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_FIELDS)
            writer.writeheader()
            for t in trades:
                writer.writerow({
                    "trade_id":   t.trade_id,
                    "symbol":     t.symbol,
                    "strategy":   t.strategy,
                    "regime":     t.regime,
                    "entry_time": t.entry_time.isoformat(),
                    "entry_price": str(t.entry_price),
                    "exit_time":  t.exit_time.isoformat(),
                    "exit_price": str(t.exit_price),
                    "quantity":   str(t.quantity),
                    "stop_loss":  str(t.stop_loss),
                    "take_profit": str(t.take_profit),
                    "exit_reason": t.exit_reason,
                    "pnl":        str(t.pnl),
                })

        logger.info("trades_exported_csv", path=str(path), count=len(trades))
        return path

    def export_trades_json(self, trades, filepath) -> Path:
        """Write trades to a JSON file. Returns the written path."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        records = []
        for t in trades:
            records.append({
                "trade_id":    t.trade_id,
                "symbol":      t.symbol,
                "strategy":    t.strategy,
                "regime":      t.regime,
                "entry_time":  t.entry_time.isoformat(),
                "entry_price": str(t.entry_price),
                "exit_time":   t.exit_time.isoformat(),
                "exit_price":  str(t.exit_price),
                "quantity":    str(t.quantity),
                "stop_loss":   str(t.stop_loss),
                "take_profit": str(t.take_profit),
                "exit_reason": t.exit_reason,
                "pnl":         str(t.pnl),
            })

        path.write_text(json.dumps(records, indent=2))
        logger.info("trades_exported_json", path=str(path), count=len(trades))
        return path

    def export_portfolio_snapshot(self, portfolio, filepath, prices: Optional[dict] = None) -> Path:
        """
        Write a full portfolio snapshot (summary + positions + metrics) to JSON.
        """
        from core.analytics.metrics import compute_metrics

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        prices = prices or {}

        snapshot = {
            "summary": portfolio.summary(prices),
            "open_positions": [p.to_dict() for p in portfolio.open_positions],
            "closed_trades_count": len(portfolio.closed_trades),
        }

        if portfolio.closed_trades:
            snapshot["analytics"] = compute_metrics(
                portfolio.closed_trades,
                portfolio.starting_balance,
            )

        path.write_text(json.dumps(snapshot, indent=2))
        logger.info("portfolio_snapshot_exported", path=str(path))
        return path
