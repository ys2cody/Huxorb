"""
OHLCV Data Loader
=================
Fetch and cache historical OHLCV data from exchanges via CCXT.

Supports:
- Fetching from any CCXT exchange (KuCoin, Binance, etc.)
- CSV cache (avoid re-downloading)
- Multiple timeframes
- Pandas DataFrame output ready for strategy consumption
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd

from core.utils.logging import get_logger

logger = get_logger(__name__)


def load_ohlcv_csv(path: Path) -> pd.DataFrame:
    """
    Load OHLCV from CSV file.

    Expected columns: timestamp, open, high, low, close, volume
    Timestamp can be ISO string or unix ms.
    """
    df = pd.read_csv(path)

    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    # Parse timestamp
    if df["timestamp"].dtype == "int64" or df["timestamp"].dtype == "float64":
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    df = df.set_index("timestamp").sort_index()

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    return df


def save_ohlcv_csv(df: pd.DataFrame, path: Path) -> None:
    """Save OHLCV to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out.index.name = "timestamp"
    out.to_csv(path)
    logger.info("ohlcv_saved", path=str(path), rows=len(out))


def fetch_ohlcv_ccxt(
    exchange_id: str,
    symbol: str,
    timeframe: str,
    since: Optional[datetime] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    """
    Fetch OHLCV from a CCXT exchange (public endpoint, no API key needed).

    Args:
        exchange_id: CCXT exchange name ("kucoin", "binance", etc.)
        symbol: Trading pair ("BTC/USDT")
        timeframe: Candle size ("1h", "4h", "1d")
        since: Start datetime (UTC). None = exchange default.
        limit: Max candles per request

    Returns:
        OHLCV DataFrame with datetime index
    """
    import ccxt

    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})

    since_ms = int(since.timestamp() * 1000) if since else None

    all_candles = []
    current_since = since_ms

    # Paginate to get all data
    while True:
        candles = exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            since=current_since,
            limit=limit,
        )

        if not candles:
            break

        all_candles.extend(candles)

        # Move cursor forward
        last_ts = candles[-1][0]
        if current_since and last_ts <= current_since:
            break
        current_since = last_ts + 1

        # Stop if we got fewer than limit (no more data)
        if len(candles) < limit:
            break

        logger.debug("ohlcv_page_fetched", count=len(candles), total=len(all_candles))

    if not all_candles:
        logger.warning("ohlcv_empty", exchange=exchange_id, symbol=symbol, timeframe=timeframe)
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(
        all_candles,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()

    # Remove duplicates
    df = df[~df.index.duplicated(keep="last")]

    logger.info(
        "ohlcv_fetched",
        exchange=exchange_id,
        symbol=symbol,
        timeframe=timeframe,
        rows=len(df),
        start=str(df.index[0]),
        end=str(df.index[-1]),
    )

    return df


def load_or_fetch(
    exchange_id: str,
    symbol: str,
    timeframe: str,
    cache_dir: Path,
    since: Optional[datetime] = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Load from cache or fetch from exchange.

    Cache filename: {exchange}_{symbol}_{timeframe}.csv
    """
    safe_symbol = symbol.replace("/", "_")
    cache_path = cache_dir / f"{exchange_id}_{safe_symbol}_{timeframe}.csv"

    if cache_path.exists() and not force_refresh:
        logger.info("ohlcv_cache_hit", path=str(cache_path))
        return load_ohlcv_csv(cache_path)

    logger.info("ohlcv_cache_miss", path=str(cache_path), fetching=True)
    df = fetch_ohlcv_ccxt(exchange_id, symbol, timeframe, since=since)

    if not df.empty:
        save_ohlcv_csv(df, cache_path)

    return df
