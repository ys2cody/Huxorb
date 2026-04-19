"""
Session Filter
==============
Optional trading-hour enforcement.

Crypto markets run 24/7, unlike forex. This filter is therefore:

- OFF by default (SessionFilter.all_day() allows every moment)
- OPT-IN via explicit sessions when you want to avoid low-liquidity hours
  (e.g. weekend chop) or enforce your own trading schedule

A "session" is a weekday + time window in UTC. Multiple sessions are OR'd:
if ANY enabled session matches the current UTC time, we are "in session".

Examples:
    # 24/7 (crypto default)
    SessionFilter.all_day()

    # Avoid weekend: Mon-Fri only
    SessionFilter.weekdays_only()

    # US-market overlap only (13:30-20:00 UTC Mon-Fri)
    filt = SessionFilter()
    filt.add_session(TradingSession(
        name="US", start_hour=13, start_minute=30, end_hour=20, end_minute=0,
        days={1,2,3,4,5}, enabled=True,
    ))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, time
from typing import List, Optional, Set, Tuple

from core.utils.logging import get_logger

logger = get_logger(__name__)


# ISO weekday: Monday=1 ... Sunday=7
_ALL_DAYS: Set[int] = {1, 2, 3, 4, 5, 6, 7}
_WEEKDAYS: Set[int] = {1, 2, 3, 4, 5}


@dataclass
class TradingSession:
    """
    A single UTC time window + day-of-week mask.

    Sessions may cross midnight (end <= start). In that case a match
    means current_minutes >= start OR current_minutes < end.
    """

    name: str
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    days: Set[int] = field(default_factory=lambda: set(_ALL_DAYS))
    enabled: bool = True

    def __post_init__(self) -> None:
        if not (0 <= self.start_hour <= 23):
            raise ValueError("start_hour must be 0-23")
        if not (0 <= self.end_hour <= 24):  # 24 allowed to express "end of day"
            raise ValueError("end_hour must be 0-24")
        if not (0 <= self.start_minute <= 59):
            raise ValueError("start_minute must be 0-59")
        if not (0 <= self.end_minute <= 59):
            raise ValueError("end_minute must be 0-59")
        if not self.days:
            raise ValueError("days set cannot be empty")
        for d in self.days:
            if d not in _ALL_DAYS:
                raise ValueError(f"day {d} not in 1..7 (ISO weekday)")

    @property
    def start_minutes(self) -> int:
        return self.start_hour * 60 + self.start_minute

    @property
    def end_minutes(self) -> int:
        return self.end_hour * 60 + self.end_minute

    @property
    def crosses_midnight(self) -> bool:
        return self.end_minutes <= self.start_minutes

    def contains(self, now_utc: datetime) -> bool:
        """True if `now_utc` falls inside this session (and it is enabled)."""
        if not self.enabled:
            return False

        iso_weekday = now_utc.isoweekday()
        if iso_weekday not in self.days:
            return False

        current_minutes = now_utc.hour * 60 + now_utc.minute

        if self.crosses_midnight:
            return (
                current_minutes >= self.start_minutes
                or current_minutes < self.end_minutes
            )
        return self.start_minutes <= current_minutes < self.end_minutes

    def describe(self) -> str:
        day_labels = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
        days_str = ",".join(day_labels[d] for d in sorted(self.days))
        state = "on" if self.enabled else "off"
        return (
            f"{self.name}({days_str} "
            f"{self.start_hour:02d}:{self.start_minute:02d}-"
            f"{self.end_hour:02d}:{self.end_minute:02d} UTC) [{state}]"
        )


@dataclass
class SessionFilter:
    """
    Collection of TradingSessions. In-session if ANY enabled session matches.

    If no sessions are configured, behaviour depends on `allow_when_empty`:
    - True  (default for `all_day`)  -> always in-session
    - False (default for custom)     -> never in-session
    """

    sessions: List[TradingSession] = field(default_factory=list)
    allow_when_empty: bool = False

    def add_session(self, session: TradingSession) -> None:
        self.sessions.append(session)
        logger.info("session_added", **{"session": session.describe()})

    def clear(self) -> None:
        self.sessions = []

    def is_in_session(self, *, now: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Returns (in_session, name_or_reason).

        name_or_reason is the matching session name when in-session, or a
        short human-readable reason ("24/7", "outside", "no_sessions") when not.
        """
        if not self.sessions:
            if self.allow_when_empty:
                return True, "24/7"
            return False, "no_sessions"

        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        for session in self.sessions:
            if session.contains(now):
                return True, session.name

        return False, "outside"

    def describe(self) -> str:
        if not self.sessions:
            return "24/7 (open)" if self.allow_when_empty else "no sessions configured"
        return "; ".join(s.describe() for s in self.sessions)

    # ---- Convenience constructors ------------------------------------ #

    @classmethod
    def all_day(cls) -> "SessionFilter":
        """Crypto default: always allowed."""
        return cls(sessions=[], allow_when_empty=True)

    @classmethod
    def weekdays_only(cls) -> "SessionFilter":
        """Monday-Friday, all hours UTC. Skip weekends for lower-liquidity avoidance."""
        return cls(sessions=[
            TradingSession(
                name="weekdays",
                start_hour=0, start_minute=0,
                end_hour=24, end_minute=0,
                days=set(_WEEKDAYS),
                enabled=True,
            ),
        ])

    @classmethod
    def us_hours(cls) -> "SessionFilter":
        """US cash-market overlap (13:30-20:00 UTC) Mon-Fri."""
        return cls(sessions=[
            TradingSession(
                name="us_hours",
                start_hour=13, start_minute=30,
                end_hour=20, end_minute=0,
                days=set(_WEEKDAYS),
                enabled=True,
            ),
        ])

    @classmethod
    def avoid_low_liquidity(cls) -> "SessionFilter":
        """
        Opinionated preset: skip the Friday 22:00 - Sunday 22:00 UTC window
        where crypto volume is typically lowest.
        """
        return cls(sessions=[
            # Mon 00:00 - Fri 22:00
            TradingSession(
                name="weekdays_main",
                start_hour=0, start_minute=0,
                end_hour=22, end_minute=0,
                days={1, 2, 3, 4, 5},
                enabled=True,
            ),
            # Sun 22:00 - end of day (pre-market catch)
            TradingSession(
                name="sunday_late",
                start_hour=22, start_minute=0,
                end_hour=24, end_minute=0,
                days={7},
                enabled=True,
            ),
        ])
