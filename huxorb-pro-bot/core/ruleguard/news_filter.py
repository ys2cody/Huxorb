"""
News Filter
===========
Block trading inside event blackout windows.

Ported from MT4 CNewsFilter with crypto-specific adaptations:

- Forex uses "per-currency" filtering (e.g. USD events affect EURUSD/USDJPY).
  Crypto keeps the same model but with a broader "asset" field: a USD event
  affects every *_USDT / *_USD pair, while a "BTC" event (halving, hard fork)
  affects every BTC_* pair.
- All times stored in UTC. No server-offset juggling.
- Two ingest modes:
    * CSV calendar (UTC timestamps, preferred)
    * Programmatic blackouts via `add_blackout()` (useful for maintenance
      windows: exchange downtime, scheduled wallet upgrades, etc.)
- Periodic reload so you can edit the CSV without restarting the bot.

CSV format (with header):
    datetime_utc,asset,impact,title
    2026-01-29 19:00:00,USD,HIGH,FOMC Rate Decision
    2026-04-14 12:00:00,BTC,HIGH,Bitcoin Halving
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from core.utils.logging import get_logger

logger = get_logger(__name__)


IMPACT_LEVELS = {"LOW", "MEDIUM", "HIGH"}

# Quote/base tokens considered "USD-adjacent" so a USD event blacks them out
USD_STABLECOINS = {"USD", "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDE"}


@dataclass
class NewsEvent:
    """A single calendar event and its blackout window."""

    event_time_utc: datetime
    asset: str            # e.g. "USD", "BTC", "ETH"
    impact: str           # "LOW" | "MEDIUM" | "HIGH"
    title: str
    blackout_start: datetime
    blackout_end: datetime

    def __post_init__(self) -> None:
        if self.event_time_utc.tzinfo is None:
            self.event_time_utc = self.event_time_utc.replace(tzinfo=timezone.utc)
        if self.blackout_start.tzinfo is None:
            self.blackout_start = self.blackout_start.replace(tzinfo=timezone.utc)
        if self.blackout_end.tzinfo is None:
            self.blackout_end = self.blackout_end.replace(tzinfo=timezone.utc)
        if self.blackout_end <= self.blackout_start:
            raise ValueError("blackout_end must be after blackout_start")
        self.asset = self.asset.strip().upper()
        self.impact = self.impact.strip().upper()
        if self.impact not in IMPACT_LEVELS:
            raise ValueError(f"impact must be one of {IMPACT_LEVELS}")

    def contains(self, now: datetime) -> bool:
        return self.blackout_start <= now < self.blackout_end

    def affects_symbol(self, symbol: str) -> bool:
        """
        Return True if this event's asset is part of the trading pair.

        symbol: "BTC/USDT" or "BTCUSDT"
        """
        base, quote = _split_symbol(symbol)
        asset = self.asset

        # Direct match on either side
        if asset == base or asset == quote:
            return True

        # USD events cover every stablecoin quote
        if asset == "USD" and quote in USD_STABLECOINS:
            return True

        return False


def _split_symbol(symbol: str) -> Tuple[str, str]:
    """Split 'BTC/USDT' or 'BTCUSDT' into (base, quote). Heuristic fallback."""
    s = symbol.upper()
    if "/" in s:
        base, _, quote = s.partition("/")
        return base, quote
    # No slash: try common quote suffixes
    for quote in ("USDT", "USDC", "BUSD", "USD", "FDUSD", "EUR", "GBP", "BTC", "ETH"):
        if s.endswith(quote) and len(s) > len(quote):
            return s[: -len(quote)], quote
    # Last resort: treat whole symbol as base
    return s, ""


@dataclass
class NewsFilter:
    """
    Loads events from CSV and/or manual adds, exposes `is_blackout()`.
    """

    enabled: bool = True
    minutes_before: int = 30
    minutes_after: int = 15
    high_impact_only: bool = False
    filter_by_symbol: bool = True
    csv_path: Optional[Path] = None
    reload_interval_minutes: int = 10

    _events: List[NewsEvent] = field(default_factory=list)
    _last_reload: Optional[datetime] = field(default=None)

    def __post_init__(self) -> None:
        if self.minutes_before < 0:
            raise ValueError("minutes_before must be >= 0")
        if self.minutes_after < 0:
            raise ValueError("minutes_after must be >= 0")
        if self.csv_path and isinstance(self.csv_path, str):
            self.csv_path = Path(self.csv_path)

        if self.enabled and self.csv_path:
            self.load_csv()

    # ------------------------------------------------------------------ #
    # Ingest
    # ------------------------------------------------------------------ #

    def add_blackout(
        self,
        start: datetime,
        end: datetime,
        asset: str,
        impact: str = "HIGH",
        title: str = "Manual Blackout",
    ) -> NewsEvent:
        """Add a manual blackout window (e.g. exchange maintenance)."""
        event = NewsEvent(
            event_time_utc=start,
            asset=asset,
            impact=impact,
            title=title,
            blackout_start=start,
            blackout_end=end,
        )
        self._events.append(event)
        logger.info(
            "news_blackout_added",
            asset=event.asset,
            impact=event.impact,
            title=event.title,
            start=event.blackout_start.isoformat(),
            end=event.blackout_end.isoformat(),
        )
        return event

    def clear(self) -> None:
        self._events = []

    def load_csv(self, path: Optional[Path] = None) -> int:
        """
        Load (or reload) events from CSV.

        Format: datetime_utc,asset,impact,title

        Past events (older than 1 hour) are discarded. Returns number of
        events loaded.
        """
        csv_path = Path(path) if path else self.csv_path
        if not csv_path or not csv_path.exists():
            logger.warning("news_csv_missing", path=str(csv_path))
            return 0

        self._events = []
        loaded = 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

        with open(csv_path, "r", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    event_time = _parse_csv_datetime(row["datetime_utc"])
                    blackout_start = event_time - timedelta(minutes=self.minutes_before)
                    blackout_end = event_time + timedelta(minutes=self.minutes_after)

                    if blackout_end < cutoff:
                        continue

                    event = NewsEvent(
                        event_time_utc=event_time,
                        asset=row["asset"],
                        impact=row.get("impact", "HIGH"),
                        title=row.get("title", "(no title)"),
                        blackout_start=blackout_start,
                        blackout_end=blackout_end,
                    )
                    self._events.append(event)
                    loaded += 1
                except (KeyError, ValueError) as exc:
                    logger.warning("news_csv_row_skipped", row=row, error=str(exc))

        self._last_reload = datetime.now(timezone.utc)
        logger.info("news_csv_loaded", path=str(csv_path), count=loaded)
        return loaded

    def _reload_if_needed(self) -> None:
        if not self.csv_path:
            return
        if not self._last_reload:
            self.load_csv()
            return
        elapsed = datetime.now(timezone.utc) - self._last_reload
        if elapsed >= timedelta(minutes=self.reload_interval_minutes):
            self.load_csv()

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #

    def is_blackout(
        self,
        symbol: str,
        *,
        now: Optional[datetime] = None,
    ) -> Tuple[bool, str]:
        """
        Return (blackout?, description).

        description examples:
          - "USD:HIGH:FOMC Rate Decision"
          - "no_blackout"
        """
        if not self.enabled:
            return False, "disabled"

        self._reload_if_needed()

        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        for event in self._events:
            if not event.contains(now):
                continue
            if self.filter_by_symbol and not event.affects_symbol(symbol):
                continue
            if self.high_impact_only and event.impact != "HIGH":
                continue

            mins_to_event = int((event.event_time_utc - now).total_seconds() / 60)
            detail = f"{event.asset}:{event.impact}:{event.title} (T{mins_to_event:+d}m)"
            return True, detail

        return False, "no_blackout"

    def next_event(
        self,
        symbol: Optional[str] = None,
        *,
        now: Optional[datetime] = None,
    ) -> Optional[NewsEvent]:
        """Return the next upcoming event (optionally filtered by symbol)."""
        now = now or datetime.now(timezone.utc)
        upcoming = [
            e for e in self._events
            if e.event_time_utc > now
            and (symbol is None or not self.filter_by_symbol or e.affects_symbol(symbol))
        ]
        if not upcoming:
            return None
        return min(upcoming, key=lambda e: e.event_time_utc)

    @property
    def event_count(self) -> int:
        return len(self._events)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #

_ISO_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M",
)


def _parse_csv_datetime(value: str) -> datetime:
    value = value.strip()
    for fmt in _ISO_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Last resort: fromisoformat handles many variants on py3.11+
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
