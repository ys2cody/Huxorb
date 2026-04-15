"""
Technical Indicators
====================
Clean implementations of common indicators for crypto strategies.

All functions accept pandas Series/DataFrame and return the same shape.
No magical defaults - every parameter is explicit.
"""

from typing import Tuple
import pandas as pd
import numpy as np


def ema(series: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average.

    Args:
        series: Price series (typically close)
        period: EMA period

    Returns:
        EMA series (same index as input)
    """
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Average True Range.

    Args:
        high, low, close: OHLC series
        period: ATR smoothing period

    Returns:
        ATR series
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Average Directional Index.

    Measures trend strength (0-100). Below 20 = weak/range, above 25 = trending.

    Args:
        high, low, close: OHLC series
        period: Smoothing period

    Returns:
        ADX series
    """
    # Calculate +DM and -DM
    high_diff = high.diff()
    low_diff = -low.diff()

    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)

    # ATR for normalization
    atr_val = atr(high, low, close, period)

    # Smooth DMs
    plus_dm_smooth = plus_dm.ewm(span=period, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(span=period, adjust=False).mean()

    # Directional Indicators
    plus_di = 100 * (plus_dm_smooth / atr_val)
    minus_di = 100 * (minus_dm_smooth / atr_val)

    # DX and ADX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx_val = dx.ewm(span=period, adjust=False).mean()

    return adx_val


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index.

    Momentum oscillator (0-100). Below 30 = oversold, above 70 = overbought.

    Args:
        series: Price series (typically close)
        period: RSI period

    Returns:
        RSI series
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))

    return rsi_val


def bollinger_bands(
    series: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands.

    Args:
        series: Price series (typically close)
        period: Moving average period
        std_dev: Standard deviation multiplier

    Returns:
        (upper_band, middle_band, lower_band)
    """
    middle = sma(series, period)
    std = series.rolling(window=period).std()

    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)

    return upper, middle, lower


def swing_low(low: pd.Series, lookback: int = 5) -> pd.Series:
    """
    Detect swing lows (local minima).

    A swing low at bar i is when low[i] < all lows in [i-lookback, i+lookback].

    Args:
        low: Low price series
        lookback: Bars to check on each side

    Returns:
        Series with swing low prices (NaN where no swing)
    """
    swings = pd.Series(index=low.index, dtype=float)

    for i in range(lookback, len(low) - lookback):
        current = low.iloc[i]
        left_window = low.iloc[i - lookback:i]
        right_window = low.iloc[i + 1:i + lookback + 1]

        if (current < left_window).all() and (current < right_window).all():
            swings.iloc[i] = current

    return swings


def swing_high(high: pd.Series, lookback: int = 5) -> pd.Series:
    """
    Detect swing highs (local maxima).

    Args:
        high: High price series
        lookback: Bars to check on each side

    Returns:
        Series with swing high prices (NaN where no swing)
    """
    swings = pd.Series(index=high.index, dtype=float)

    for i in range(lookback, len(high) - lookback):
        current = high.iloc[i]
        left_window = high.iloc[i - lookback:i]
        right_window = high.iloc[i + 1:i + lookback + 1]

        if (current > left_window).all() and (current > right_window).all():
            swings.iloc[i] = current

    return swings


def is_bullish_engulfing(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> pd.Series:
    """
    Detect bullish engulfing candlestick pattern.

    Pattern: previous candle is bearish, current candle is bullish and
    completely engulfs the previous candle's body.

    Returns:
        Boolean series (True where pattern occurs)
    """
    prev_open = open_.shift(1)
    prev_close = close.shift(1)

    prev_bearish = prev_close < prev_open
    current_bullish = close > open_

    engulfs_body = (open_ < prev_close) & (close > prev_open)

    return prev_bearish & current_bullish & engulfs_body


def has_rejection_wick(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    min_wick_ratio: float = 2.0,
) -> pd.Series:
    """
    Detect strong rejection wicks (long lower shadow).

    A rejection wick is when the lower shadow is at least `min_wick_ratio`
    times the candle body, indicating buyers rejected lower prices.

    Args:
        min_wick_ratio: Lower wick must be this many times the body size

    Returns:
        Boolean series
    """
    body = (close - open_).abs()
    lower_wick = pd.concat([open_, close], axis=1).min(axis=1) - low

    # Avoid division by zero for doji candles
    body_nonzero = body.where(body > 0, 0.0001)

    return (lower_wick / body_nonzero) >= min_wick_ratio


def higher_high(close: pd.Series, lookback: int = 1) -> pd.Series:
    """Check if current high is higher than N bars ago."""
    return close > close.shift(lookback)
