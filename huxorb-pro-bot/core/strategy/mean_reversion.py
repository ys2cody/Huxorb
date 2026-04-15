"""
Mean-Reversion Strategy
========================
Long-only bounce trades in range-bound markets.

Entry logic:
1. ADX < 20 (range condition, checked by regime filter)
2. Price touches or goes below lower Bollinger Band
3. RSI < 30 (oversold)
4. BTC macro not strongly bearish
5. Price closes back inside Bollinger Band (bounce confirmation)

Stop loss: below recent swing low or ATR-based
Take profit: middle Bollinger Band or 1.5-2R
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import pandas as pd

from core.strategy.indicators import (
    bollinger_bands,
    rsi,
    atr,
    swing_low,
)
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MeanReversionConfig:
    """Mean-reversion strategy parameters."""

    # Bollinger Bands
    bb_period: int = 20
    bb_std_dev: float = 2.0

    # RSI
    rsi_period: int = 14
    rsi_oversold: float = 30.0

    # Stop loss
    atr_period: int = 14
    atr_stop_multiplier: float = 1.5
    swing_lookback: int = 5

    # Target
    risk_reward_ratio: float = 1.5  # Conservative for mean-reversion


@dataclass
class MeanReversionSignal:
    """Trade signal from mean-reversion strategy."""

    has_signal: bool
    entry_price: Optional[Decimal]
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    reason: str
    # Diagnostics
    below_bb: bool
    rsi_oversold: bool
    bounced_inside: bool


class MeanReversionStrategy:
    """Detect long entries on oversold bounces in range markets."""

    def __init__(self, config: Optional[MeanReversionConfig] = None):
        self.config = config or MeanReversionConfig()

    def check_signal(
        self,
        ohlcv: pd.DataFrame,
        btc_macro_bearish: bool = False,
    ) -> MeanReversionSignal:
        """
        Check for mean-reversion entry signal.

        Args:
            ohlcv: OHLCV dataframe (datetime index)
            btc_macro_bearish: If True, skip (macro headwind too strong)

        Returns:
            MeanReversionSignal (has_signal=True if entry conditions met)
        """
        if len(ohlcv) < self.config.bb_period + 10:
            return self._no_signal("insufficient_data")

        if btc_macro_bearish:
            return self._no_signal("btc_macro_bearish")

        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]

        # Calculate indicators
        bb_upper, bb_mid, bb_lower = bollinger_bands(
            close,
            period=self.config.bb_period,
            std_dev=self.config.bb_std_dev,
        )

        rsi_series = rsi(close, period=self.config.rsi_period)

        # Current bar
        curr_close = close.iloc[-1]
        curr_low = low.iloc[-1]
        curr_bb_lower = bb_lower.iloc[-1]
        curr_bb_mid = bb_mid.iloc[-1]
        curr_rsi = rsi_series.iloc[-1]

        # Previous bar
        prev_close = close.iloc[-2]
        prev_bb_lower = bb_lower.iloc[-2]

        # --- Condition 1: Touched or went below lower BB ---
        below_bb_now = curr_low <= curr_bb_lower
        below_bb_prev = prev_close < prev_bb_lower

        touched_bb = below_bb_now or below_bb_prev

        if not touched_bb:
            return self._no_signal("no_bb_touch")

        # --- Condition 2: RSI oversold ---
        is_oversold = curr_rsi < self.config.rsi_oversold

        if not is_oversold:
            return self._no_signal(
                f"rsi_not_oversold ({curr_rsi:.1f})",
                below_bb=touched_bb,
            )

        # --- Condition 3: Price closed back inside BB (bounce confirmation) ---
        bounced = curr_close > curr_bb_lower

        if not bounced:
            return self._no_signal(
                "waiting_for_bounce",
                below_bb=touched_bb,
                rsi_oversold=is_oversold,
            )

        # --- Calculate entry/stop/tp ---
        entry = Decimal(str(curr_close))

        # Stop loss: below swing low or ATR-based
        atr_series = atr(high, low, close, period=self.config.atr_period)
        curr_atr = atr_series.iloc[-1]

        atr_stop = curr_close - (curr_atr * self.config.atr_stop_multiplier)

        # Find recent swing low
        swing_lows = swing_low(low, lookback=self.config.swing_lookback)
        recent_swings = swing_lows.dropna().tail(3)
        if not recent_swings.empty:
            swing_stop = recent_swings.min()
        else:
            swing_stop = atr_stop

        # Use wider stop
        stop = min(atr_stop, swing_stop)
        stop_loss = Decimal(str(stop))

        # Take profit: mid BB or R:R
        tp_from_bb = Decimal(str(curr_bb_mid))
        risk = entry - stop_loss
        tp_from_rr = entry + (risk * Decimal(str(self.config.risk_reward_ratio)))

        # Use whichever is closer (more conservative)
        take_profit = min(tp_from_bb, tp_from_rr)

        logger.info(
            "meanrev_signal_detected",
            entry=str(entry),
            stop=str(stop_loss),
            tp=str(take_profit),
            rsi=f"{curr_rsi:.1f}",
        )

        return MeanReversionSignal(
            has_signal=True,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=f"oversold_bounce (rsi={curr_rsi:.1f})",
            below_bb=touched_bb,
            rsi_oversold=is_oversold,
            bounced_inside=bounced,
        )

    def _no_signal(
        self,
        reason: str,
        below_bb: bool = False,
        rsi_oversold: bool = False,
        bounced_inside: bool = False,
    ) -> MeanReversionSignal:
        return MeanReversionSignal(
            has_signal=False,
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            reason=reason,
            below_bb=below_bb,
            rsi_oversold=rsi_oversold,
            bounced_inside=bounced_inside,
        )
