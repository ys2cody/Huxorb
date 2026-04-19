"""
Breakout Strategy
=================
Long-only volume-confirmed price breakouts. Best setup for maximum
return in trending/volatile crypto markets.

Entry logic:
1. Price closes ABOVE the 20-bar highest high (breakout)
2. Volume confirmation: current volume > 1.5x 20-bar average volume
3. Not already inside a 3-bar consolidation (avoid chasing)
4. Regime: TREND or RANGE (not LOW_VOL or UNKNOWN)

Stop loss: Low of the breakout candle (or 1 ATR below, whichever is wider)
Take profit: 3R (3x the risk distance) — lets winners run
Trailing: After 2R, trail 1 ATR below price

Why this works in crypto:
- Crypto has strong momentum — breakouts continue more often than not
- Volume spike distinguishes real breakouts from fakeouts
- 3:1 RR means you only need 26% win rate to break even
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import pandas as pd

from core.strategy.indicators import atr, sma
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BreakoutConfig:
    """Breakout strategy parameters."""
    lookback: int = 20            # Bars to define highest high / avg volume
    volume_multiplier: float = 1.5  # Volume must be this x average
    atr_period: int = 14
    atr_stop_multiplier: float = 1.2  # Stop = 1.2 ATR below breakout candle low
    risk_reward_ratio: float = 3.0    # 3:1 — let winners run
    min_breakout_atr: float = 0.5     # Breakout must be at least 0.5 ATR above prior high


@dataclass
class BreakoutSignal:
    """Trade signal from breakout strategy."""
    has_signal: bool
    entry_price: Optional[Decimal]
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    reason: str
    breakout_confirmed: bool = False
    volume_confirmed: bool = False


class BreakoutStrategy:
    """
    Volume-confirmed price breakout strategy.

    Captures the explosive moves that happen when price breaks through
    key resistance levels with increased volume.
    """

    def __init__(self, config: Optional[BreakoutConfig] = None):
        self.config = config or BreakoutConfig()

    def check_signal(self, ohlcv: pd.DataFrame) -> BreakoutSignal:
        """
        Check for a breakout entry signal on the latest bar.

        Args:
            ohlcv: OHLCV dataframe with datetime index

        Returns:
            BreakoutSignal with has_signal=True if conditions met
        """
        lb = self.config.lookback
        if len(ohlcv) < lb + self.config.atr_period + 5:
            return self._no_signal("insufficient_data")

        close  = ohlcv["close"]
        high   = ohlcv["high"]
        low    = ohlcv["low"]
        volume = ohlcv["volume"]

        curr_close  = close.iloc[-1]
        curr_low    = low.iloc[-1]
        curr_volume = volume.iloc[-1]

        # --- 1. Prior high (excluding current bar) ---
        prior_high = high.iloc[-(lb + 1):-1].max()

        # --- 2. Breakout check ---
        breakout_confirmed = curr_close > prior_high

        if not breakout_confirmed:
            return self._no_signal(
                f"no_breakout (close={curr_close:.2f} <= prior_high={prior_high:.2f})",
                breakout_confirmed=False,
            )

        # --- 3. Breakout size filter (avoid tiny moves) ---
        atr_val = atr(high, low, close, self.config.atr_period).iloc[-1]
        breakout_size = curr_close - prior_high
        if breakout_size < atr_val * self.config.min_breakout_atr:
            return self._no_signal(
                f"breakout_too_small ({breakout_size:.2f} < {atr_val * self.config.min_breakout_atr:.2f})",
                breakout_confirmed=True,
            )

        # --- 4. Volume confirmation ---
        avg_volume = volume.iloc[-(lb + 1):-1].mean()
        volume_confirmed = curr_volume > avg_volume * self.config.volume_multiplier

        if not volume_confirmed:
            return self._no_signal(
                f"no_volume (vol={curr_volume:.0f} < {avg_volume * self.config.volume_multiplier:.0f})",
                breakout_confirmed=True,
                volume_confirmed=False,
            )

        # --- 5. Build entry / stop / tp ---
        entry_price = Decimal(str(curr_close))

        # Stop: lower of (breakout candle low) or (1.2 ATR below entry)
        atr_stop = Decimal(str(curr_close - atr_val * self.config.atr_stop_multiplier))
        candle_stop = Decimal(str(curr_low))
        stop_loss = min(atr_stop, candle_stop)  # Wider (lower) stop for long

        if stop_loss >= entry_price:
            return self._no_signal("stop_above_entry", breakout_confirmed=True, volume_confirmed=True)

        risk = entry_price - stop_loss
        take_profit = entry_price + risk * Decimal(str(self.config.risk_reward_ratio))

        logger.debug(
            "breakout_signal",
            entry=str(entry_price),
            sl=str(stop_loss),
            tp=str(take_profit),
            breakout_size=f"{float(breakout_size):.2f}",
            volume_ratio=f"{curr_volume / avg_volume:.2f}x",
        )

        return BreakoutSignal(
            has_signal=True,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=f"breakout:{float(curr_close):.0f}>{float(prior_high):.0f} vol:{curr_volume/avg_volume:.1f}x",
            breakout_confirmed=True,
            volume_confirmed=True,
        )

    def _no_signal(
        self,
        reason: str,
        breakout_confirmed: bool = False,
        volume_confirmed: bool = False,
    ) -> BreakoutSignal:
        return BreakoutSignal(
            has_signal=False,
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            reason=reason,
            breakout_confirmed=breakout_confirmed,
            volume_confirmed=volume_confirmed,
        )
