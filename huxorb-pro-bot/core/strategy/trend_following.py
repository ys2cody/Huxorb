"""
Trend-Following Strategy
=========================
Long-only pullback entries in established uptrends.

Entry logic:
1. Price above 200 EMA (trend filter)
2. 50 EMA > 200 EMA (momentum alignment)
3. Price pulls back to 20/50 EMA support
4. Confirmation pattern (engulfing / rejection wick / break of prior high)

Stop loss: below swing low or ATR-based
Take profit: 2R default
Position management: move to breakeven at +1R, optional trail
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import pandas as pd

from core.strategy.indicators import (
    ema,
    atr,
    swing_low,
    is_bullish_engulfing,
    has_rejection_wick,
    higher_high,
)
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TrendFollowingConfig:
    """Trend-following strategy parameters."""

    # Trend EMAs
    ema_fast: int = 50
    ema_slow: int = 200
    ema_entry: int = 20  # Pullback target

    # Stop loss
    atr_period: int = 14
    atr_stop_multiplier: float = 1.5
    swing_lookback: int = 5

    # Confirmation
    require_confirmation: bool = True
    rejection_wick_ratio: float = 2.0

    # Targets
    risk_reward_ratio: float = 2.0


@dataclass
class TrendSignal:
    """Trade signal from trend-following strategy."""

    has_signal: bool
    entry_price: Optional[Decimal]
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    reason: str
    # Diagnostics
    price_above_200: bool
    ema_alignment: bool
    pullback_detected: bool
    confirmation: Optional[str]


class TrendFollowingStrategy:
    """Detect long entries on pullbacks in uptrends."""

    def __init__(self, config: Optional[TrendFollowingConfig] = None):
        self.config = config or TrendFollowingConfig()

    def check_signal(
        self,
        ohlcv: pd.DataFrame,
    ) -> TrendSignal:
        """
        Check for trend-following entry signal.

        Args:
            ohlcv: OHLCV dataframe (datetime index, columns: open/high/low/close/volume)

        Returns:
            TrendSignal (has_signal=True if entry conditions met)
        """
        if len(ohlcv) < self.config.ema_slow + 10:
            return self._no_signal("insufficient_data")

        open_ = ohlcv["open"]
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]

        # Calculate EMAs
        ema20 = ema(close, self.config.ema_entry)
        ema50 = ema(close, self.config.ema_fast)
        ema200 = ema(close, self.config.ema_slow)

        # Current bar values
        curr_close = close.iloc[-1]
        curr_ema20 = ema20.iloc[-1]
        curr_ema50 = ema50.iloc[-1]
        curr_ema200 = ema200.iloc[-1]

        # --- Condition 1: Trend alignment ---
        price_above_200 = curr_close > curr_ema200
        ema_alignment = curr_ema50 > curr_ema200

        if not price_above_200:
            return self._no_signal("price_below_200ema", price_above_200, ema_alignment)
        if not ema_alignment:
            return self._no_signal("50ema_below_200ema", price_above_200, ema_alignment)

        # --- Condition 2: Pullback detection ---
        # Price should be near 20 EMA or 50 EMA (within 3%)
        # 1% was too tight for 4h crypto bars (~1.5-2% avg range per bar)
        dist_to_20 = abs(curr_close - curr_ema20) / curr_close
        dist_to_50 = abs(curr_close - curr_ema50) / curr_close

        near_support = (dist_to_20 < 0.03) or (dist_to_50 < 0.03)

        if not near_support:
            return self._no_signal(
                f"no_pullback (dist_20={dist_to_20:.3f}, dist_50={dist_to_50:.3f})",
                price_above_200,
                ema_alignment,
            )

        # --- Condition 3: Confirmation pattern ---
        confirmation_type = None

        if self.config.require_confirmation:
            # a) Bullish engulfing
            engulfing = is_bullish_engulfing(open_, high, low, close)
            if engulfing.iloc[-1]:
                confirmation_type = "bullish_engulfing"

            # b) Rejection wick
            if confirmation_type is None:
                rej_wick = has_rejection_wick(
                    open_, high, low, close,
                    min_wick_ratio=self.config.rejection_wick_ratio,
                )
                if rej_wick.iloc[-1]:
                    confirmation_type = "rejection_wick"

            # c) Higher high
            if confirmation_type is None:
                hh = higher_high(close, lookback=1)
                if hh.iloc[-1]:
                    confirmation_type = "higher_high"

            if confirmation_type is None:
                return self._no_signal(
                    "no_confirmation",
                    price_above_200,
                    ema_alignment,
                    pullback_detected=True,
                )

        # --- Calculate stop loss and take profit ---
        entry = Decimal(str(curr_close))

        # Stop loss: max(swing low, ATR-based)
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

        # Use the wider (safer) stop
        stop = min(atr_stop, swing_stop)
        stop_loss = Decimal(str(stop))

        # Take profit: R:R ratio
        risk = entry - stop_loss
        reward = risk * Decimal(str(self.config.risk_reward_ratio))
        take_profit = entry + reward

        logger.info(
            "trend_signal_detected",
            entry=str(entry),
            stop=str(stop_loss),
            tp=str(take_profit),
            confirmation=confirmation_type or "none",
        )

        return TrendSignal(
            has_signal=True,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=f"pullback_confirmed:{confirmation_type or 'forced'}",
            price_above_200=price_above_200,
            ema_alignment=ema_alignment,
            pullback_detected=True,
            confirmation=confirmation_type,
        )

    def _no_signal(
        self,
        reason: str,
        price_above_200: bool = False,
        ema_alignment: bool = False,
        pullback_detected: bool = False,
    ) -> TrendSignal:
        return TrendSignal(
            has_signal=False,
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            reason=reason,
            price_above_200=price_above_200,
            ema_alignment=ema_alignment,
            pullback_detected=pullback_detected,
            confirmation=None,
        )
