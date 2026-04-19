"""
Regime Filter
=============
Classifies market conditions to decide which strategy (if any) to deploy.

Three regimes:
- TREND: Strong directional movement (use trend-following)
- RANGE: Choppy, mean-reverting (use mean-reversion)
- LOW_VOL: Too quiet, skip (no trades)

Uses BTC daily for macro regime + trading timeframe ADX/ATR for micro.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from core.strategy.indicators import ema, adx, atr
from core.utils.logging import get_logger

logger = get_logger(__name__)


class Regime(str, Enum):
    """Market regime classification."""

    TREND = "trend"
    RANGE = "range"
    LOW_VOL = "low_vol"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


@dataclass
class RegimeConfig:
    """Regime detection parameters."""

    # Trend regime thresholds
    btc_daily_ema_fast: int = 50
    btc_daily_ema_slow: int = 200

    # Range regime threshold
    adx_range_threshold: float = 20.0

    # Low-vol threshold (relative to recent ATR mean)
    atr_period: int = 14
    atr_low_vol_percentile: float = 25.0  # Bottom quartile

    # Aggressive mode: loosen BTC macro gate
    # - Normal mode: requires BOTH (BTC > 200MA AND golden cross)
    # - Aggressive mode: requires EITHER, OR lets strong per-symbol ADX override
    aggressive_mode: bool = False
    aggressive_adx_override: float = 30.0  # In aggressive mode, allow TREND when per-symbol ADX exceeds this


@dataclass
class RegimeState:
    """Result of regime classification."""

    regime: Regime
    reason: str
    btc_above_200d: bool
    btc_ema_golden: bool  # 50D > 200D
    adx_value: Optional[float]
    atr_value: Optional[float]
    atr_threshold: Optional[float]

    def is_tradeable(self) -> bool:
        """Can we trade in this regime?"""
        return self.regime in {Regime.TREND, Regime.RANGE}


class RegimeFilter:
    """
    Classifies market regime using BTC macro + symbol micro indicators.

    Design:
    - BTC daily (1D) determines macro trend/no-trend
    - Symbol's trading TF (4H) determines range vs trend via ADX
    - Symbol's ATR detects low-volatility (skip trading)
    """

    def __init__(self, config: Optional[RegimeConfig] = None):
        self.config = config or RegimeConfig()

    def classify(
        self,
        btc_daily: pd.DataFrame,
        symbol_tf: pd.DataFrame,
    ) -> RegimeState:
        """
        Classify current regime.

        Args:
            btc_daily: BTC/USDT daily OHLCV (columns: open, high, low, close, volume)
            symbol_tf: Symbol's trading timeframe OHLCV

        Returns:
            RegimeState with classification + supporting data

        Both DataFrames must have datetime index and be sorted ascending.
        """
        if btc_daily.empty or symbol_tf.empty:
            return RegimeState(
                regime=Regime.UNKNOWN,
                reason="insufficient_data",
                btc_above_200d=False,
                btc_ema_golden=False,
                adx_value=None,
                atr_value=None,
                atr_threshold=None,
            )

        # --- BTC MACRO (daily) ---
        btc_close = btc_daily["close"]
        btc_ema50 = ema(btc_close, self.config.btc_daily_ema_fast)
        btc_ema200 = ema(btc_close, self.config.btc_daily_ema_slow)

        btc_above_200 = btc_close.iloc[-1] > btc_ema200.iloc[-1]
        btc_golden = btc_ema50.iloc[-1] > btc_ema200.iloc[-1]

        # --- SYMBOL MICRO (trading TF) ---
        sym_high = symbol_tf["high"]
        sym_low = symbol_tf["low"]
        sym_close = symbol_tf["close"]

        # ADX (range vs trend)
        adx_series = adx(sym_high, sym_low, sym_close, period=14)
        current_adx = adx_series.iloc[-1] if not adx_series.empty else None

        # ATR (volatility gate)
        atr_series = atr(sym_high, sym_low, sym_close, period=self.config.atr_period)
        current_atr = atr_series.iloc[-1] if not atr_series.empty else None

        # Compute ATR low-vol threshold (bottom quartile of recent ATR)
        atr_lookback = min(100, len(atr_series))
        atr_recent = atr_series.iloc[-atr_lookback:]
        atr_threshold = atr_recent.quantile(self.config.atr_low_vol_percentile / 100.0)

        # --- CLASSIFY ---
        regime, reason = self._determine_regime(
            btc_above_200=btc_above_200,
            btc_golden=btc_golden,
            adx_val=current_adx,
            atr_val=current_atr,
            atr_thresh=atr_threshold,
        )

        state = RegimeState(
            regime=regime,
            reason=reason,
            btc_above_200d=btc_above_200,
            btc_ema_golden=btc_golden,
            adx_value=current_adx,
            atr_value=current_atr,
            atr_threshold=atr_threshold,
        )

        logger.info(
            "regime_classified",
            regime=regime.value,
            reason=reason,
            btc_above_200d=btc_above_200,
            btc_golden=btc_golden,
            adx=f"{current_adx:.1f}" if current_adx else "N/A",
            atr=f"{current_atr:.2f}" if current_atr else "N/A",
        )

        return state

    def _determine_regime(
        self,
        *,
        btc_above_200: bool,
        btc_golden: bool,
        adx_val: Optional[float],
        atr_val: Optional[float],
        atr_thresh: Optional[float],
    ) -> tuple[Regime, str]:
        """
        Decision tree for regime classification.

        Priority:
        1. LOW_VOL if ATR too low
        2. TREND if BTC macro bullish AND ADX >= threshold
        3. RANGE if ADX < threshold
        4. UNKNOWN otherwise
        """
        # 1. Volatility gate
        if atr_val is not None and atr_thresh is not None:
            if atr_val < atr_thresh:
                return Regime.LOW_VOL, f"atr={atr_val:.2f} < {atr_thresh:.2f}"

        # 2. Check BTC macro for trend permission
        if self.config.aggressive_mode:
            # Aggressive: accept EITHER signal as permission
            btc_trend_ok = btc_above_200 or btc_golden
        else:
            # Normal: require BOTH signals
            btc_trend_ok = btc_above_200 and btc_golden

        # 3. Check ADX
        if adx_val is None:
            return Regime.UNKNOWN, "adx_unavailable"

        if adx_val < self.config.adx_range_threshold:
            # Range-bound
            return Regime.RANGE, f"adx={adx_val:.1f} < {self.config.adx_range_threshold}"

        # ADX >= threshold: trending
        if btc_trend_ok:
            return Regime.TREND, f"btc_bullish + adx={adx_val:.1f}"

        # Aggressive override: strong per-symbol trend can bypass macro gate
        if self.config.aggressive_mode and adx_val >= self.config.aggressive_adx_override:
            return Regime.TREND, f"aggressive: adx={adx_val:.1f} >= {self.config.aggressive_adx_override} (macro bypass)"

        # Trending but BTC macro not supportive - safer to skip
        return Regime.UNKNOWN, f"adx={adx_val:.1f} but btc_macro_bearish"
