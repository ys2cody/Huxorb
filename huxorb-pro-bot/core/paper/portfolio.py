"""
Paper Portfolio
===============
Virtual portfolio that simulates real trading without placing orders.

Tracks:
- Virtual balances (USDT, BTC, ETH, etc.)
- Open positions with entry/stop/tp
- PnL per position (mark-to-market)
- Trade history
- Equity curve

Persists state to JSON so you can stop/restart the bot without losing
your paper trading history.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PaperPosition:
    """An open paper position."""

    position_id: int
    symbol: str
    side: str  # "buy" only (long-only)
    quantity: Decimal
    entry_price: Decimal
    entry_time: datetime
    stop_loss: Decimal
    take_profit: Decimal
    strategy: str
    regime: str

    def unrealized_pnl(self, current_price: Decimal) -> Decimal:
        return (current_price - self.entry_price) * self.quantity

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": str(self.quantity),
            "entry_price": str(self.entry_price),
            "entry_time": self.entry_time.isoformat(),
            "stop_loss": str(self.stop_loss),
            "take_profit": str(self.take_profit),
            "strategy": self.strategy,
            "regime": self.regime,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PaperPosition":
        return cls(
            position_id=d["position_id"],
            symbol=d["symbol"],
            side=d["side"],
            quantity=Decimal(d["quantity"]),
            entry_price=Decimal(d["entry_price"]),
            entry_time=datetime.fromisoformat(d["entry_time"]),
            stop_loss=Decimal(d["stop_loss"]),
            take_profit=Decimal(d["take_profit"]),
            strategy=d["strategy"],
            regime=d["regime"],
        )


@dataclass
class PaperTrade:
    """A completed paper trade."""

    trade_id: int
    symbol: str
    strategy: str
    regime: str
    entry_time: datetime
    entry_price: Decimal
    exit_time: datetime
    exit_price: Decimal
    quantity: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    exit_reason: str
    pnl: Decimal

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "regime": self.regime,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": str(self.entry_price),
            "exit_time": self.exit_time.isoformat(),
            "exit_price": str(self.exit_price),
            "quantity": str(self.quantity),
            "stop_loss": str(self.stop_loss),
            "take_profit": str(self.take_profit),
            "exit_reason": self.exit_reason,
            "pnl": str(self.pnl),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PaperTrade":
        return cls(
            trade_id=d["trade_id"],
            symbol=d["symbol"],
            strategy=d["strategy"],
            regime=d["regime"],
            entry_time=datetime.fromisoformat(d["entry_time"]),
            entry_price=Decimal(d["entry_price"]),
            exit_time=datetime.fromisoformat(d["exit_time"]),
            exit_price=Decimal(d["exit_price"]),
            quantity=Decimal(d["quantity"]),
            stop_loss=Decimal(d["stop_loss"]),
            take_profit=Decimal(d["take_profit"]),
            exit_reason=d["exit_reason"],
            pnl=Decimal(d["pnl"]),
        )


class PaperPortfolio:
    """
    Virtual portfolio for paper trading.

    - Tracks open positions and closed trades
    - Checks stop/tp on every price update
    - Persists to JSON for restart resilience
    """

    def __init__(
        self,
        starting_balance: Decimal = Decimal("10000"),
        state_file: Optional[Path] = None,
    ):
        self.starting_balance = starting_balance
        self.state_file = state_file

        self._balance: Decimal = starting_balance
        self._positions: List[PaperPosition] = []
        self._trades: List[PaperTrade] = []
        self._next_id: int = 1

        # Try to load existing state
        if state_file and state_file.exists():
            self._load_state()

    # ------------------------------------------------------------------ #
    # Position Management
    # ------------------------------------------------------------------ #

    def open_position(
        self,
        *,
        symbol: str,
        quantity: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        strategy: str,
        regime: str,
    ) -> PaperPosition:
        """Open a new virtual position."""
        cost = quantity * entry_price
        if cost > self._balance:
            raise ValueError(
                f"Insufficient balance: need {cost}, have {self._balance}"
            )

        # Deduct cost from balance
        self._balance -= cost

        pos = PaperPosition(
            position_id=self._next_id,
            symbol=symbol,
            side="buy",
            quantity=quantity,
            entry_price=entry_price,
            entry_time=datetime.now(timezone.utc),
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=strategy,
            regime=regime,
        )
        self._next_id += 1
        self._positions.append(pos)

        logger.info(
            "paper_position_opened",
            id=pos.position_id,
            symbol=symbol,
            qty=str(quantity),
            entry=str(entry_price),
            sl=str(stop_loss),
            tp=str(take_profit),
        )

        self._save_state()
        return pos

    def close_position(
        self,
        position: PaperPosition,
        exit_price: Decimal,
        exit_reason: str,
    ) -> PaperTrade:
        """Close an open position and record the trade."""
        now = datetime.now(timezone.utc)
        pnl = (exit_price - position.entry_price) * position.quantity

        # Return proceeds to balance
        proceeds = position.quantity * exit_price
        self._balance += proceeds

        trade = PaperTrade(
            trade_id=position.position_id,
            symbol=position.symbol,
            strategy=position.strategy,
            regime=position.regime,
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            exit_time=now,
            exit_price=exit_price,
            quantity=position.quantity,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            exit_reason=exit_reason,
            pnl=pnl,
        )

        self._trades.append(trade)
        self._positions = [p for p in self._positions if p.position_id != position.position_id]

        logger.info(
            "paper_position_closed",
            id=trade.trade_id,
            symbol=trade.symbol,
            pnl=str(pnl),
            reason=exit_reason,
        )

        self._save_state()
        return trade

    def check_exits(self, prices: Dict[str, Decimal]) -> List[PaperTrade]:
        """
        Check all open positions against current prices for stop/tp hits.

        Args:
            prices: Dict of {symbol: current_price}

        Returns:
            List of trades that were closed this tick
        """
        closed = []
        for pos in list(self._positions):
            price = prices.get(pos.symbol)
            if price is None:
                continue

            if price <= pos.stop_loss:
                trade = self.close_position(pos, pos.stop_loss, "stop_loss")
                closed.append(trade)
            elif price >= pos.take_profit:
                trade = self.close_position(pos, pos.take_profit, "take_profit")
                closed.append(trade)

        return closed

    # ------------------------------------------------------------------ #
    # Accessors
    # ------------------------------------------------------------------ #

    @property
    def balance(self) -> Decimal:
        """Free cash balance."""
        return self._balance

    @property
    def open_positions(self) -> List[PaperPosition]:
        return list(self._positions)

    @property
    def closed_trades(self) -> List[PaperTrade]:
        return list(self._trades)

    @property
    def total_pnl(self) -> Decimal:
        return sum((t.pnl for t in self._trades), Decimal("0"))

    def equity(self, prices: Dict[str, Decimal]) -> Decimal:
        """Total equity = cash + mark-to-market positions."""
        mtm = sum(
            pos.quantity * prices.get(pos.symbol, pos.entry_price)
            for pos in self._positions
        )
        return self._balance + mtm

    def summary(self, prices: Optional[Dict[str, Decimal]] = None) -> dict:
        """Snapshot of portfolio state."""
        prices = prices or {}
        eq = self.equity(prices)
        winners = [t for t in self._trades if t.pnl > 0]
        losers = [t for t in self._trades if t.pnl <= 0]
        return {
            "balance": str(self._balance.quantize(Decimal("0.01"))),
            "equity": str(eq.quantize(Decimal("0.01"))),
            "open_positions": len(self._positions),
            "total_trades": len(self._trades),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": f"{len(winners)/len(self._trades)*100:.1f}%" if self._trades else "N/A",
            "total_pnl": str(self.total_pnl.quantize(Decimal("0.01"))),
            "roi": f"{(eq - self.starting_balance) / self.starting_balance * 100:.2f}%",
        }

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _save_state(self) -> None:
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "starting_balance": str(self.starting_balance),
            "balance": str(self._balance),
            "next_id": self._next_id,
            "positions": [p.to_dict() for p in self._positions],
            "trades": [t.to_dict() for t in self._trades],
        }
        self.state_file.write_text(json.dumps(state, indent=2))

    def _load_state(self) -> None:
        try:
            state = json.loads(self.state_file.read_text())
            self.starting_balance = Decimal(state["starting_balance"])
            self._balance = Decimal(state["balance"])
            self._next_id = state["next_id"]
            self._positions = [PaperPosition.from_dict(p) for p in state["positions"]]
            self._trades = [PaperTrade.from_dict(t) for t in state["trades"]]
            logger.info(
                "paper_state_loaded",
                balance=str(self._balance),
                open_positions=len(self._positions),
                trades=len(self._trades),
            )
        except Exception as exc:
            logger.warning("paper_state_load_failed", error=str(exc))
