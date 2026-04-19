"""
Config Profiles
===============
Pre-baked risk/timing profiles + per-account jitter.

Ported from MT4 CConfigProfiles.

Why jitter exists
-----------------
If you run the same strategy on multiple exchange accounts, you do NOT want
every account firing a market order at the exact same millisecond. That
would:

1. Move the market against yourself (self-front-running)
2. Look suspicious to exchanges that flag coordinated trading
3. Concentrate slippage risk

Solution: each account inserts a small random delay before entry.

The jitter is DETERMINISTIC per-account-per-5min-bucket so the same account
doesn't flap around, but different accounts get different delays. It is
ONLY additive (adds a few seconds of wait); it never skips RuleGuard checks
and never increases trade size.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AccountProfile:
    """All per-account tunables."""

    profile_name: str = "DEFAULT"
    instance_id: int = 1
    account_group: str = "DEFAULT"

    # Risk knobs (copied into RiskManager at init time)
    risk_per_trade_pct: Decimal = Decimal("0.5")
    max_quantity: Decimal = Decimal("1000")
    max_open_trades: int = 2
    max_trades_per_day: int = 3

    # Timing
    entry_delay_jitter_sec: int = 0     # max jitter
    entry_delay_base_sec: int = 0       # always-applied base delay

    # Sessions (flags consumed by orchestrator when building SessionFilter)
    use_us_hours: bool = False
    use_weekends: bool = True
    use_asia: bool = True

    # News
    news_filter_enabled: bool = False
    news_minutes_before: int = 30
    news_minutes_after: int = 15

    # Spread (percent of bid)
    max_spread_pct: Decimal = Decimal("0.2")


@dataclass
class ConfigProfiles:
    """
    Holds the currently-active AccountProfile and calculates jitter.

    Seed is derived from `profile_name + instance_id + account_group` so
    different accounts get different (but stable) jitter values.
    """

    profile: AccountProfile = field(default_factory=AccountProfile)
    _last_jitter_calc: Optional[datetime] = field(default=None)
    _current_jitter_sec: int = field(default=0)
    _account_seed: int = field(default=0)

    def __post_init__(self) -> None:
        self._account_seed = self._derive_seed()
        logger.info(
            "profile_init",
            profile=self.profile.profile_name,
            instance=self.profile.instance_id,
            account_group=self.profile.account_group,
            seed=self._account_seed,
        )

    # ------------------------------------------------------------------ #
    # Jitter
    # ------------------------------------------------------------------ #

    def calculate_entry_delay_sec(self, *, now: Optional[datetime] = None) -> int:
        """
        Return total delay = base_delay + current_jitter.

        Jitter is recalculated every 5 minutes so multiple signals in the
        same bucket share the same delay (predictable for debugging).
        """
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if self.profile.entry_delay_jitter_sec <= 0:
            self._current_jitter_sec = 0
        else:
            needs_recalc = (
                self._last_jitter_calc is None
                or (now - self._last_jitter_calc).total_seconds() >= 300
            )
            if needs_recalc:
                bucket = int(now.timestamp() // 300)
                self._current_jitter_sec = self._stable_random(
                    seed=self._account_seed + bucket,
                    lo=0,
                    hi=self.profile.entry_delay_jitter_sec,
                )
                self._last_jitter_calc = now
                logger.debug(
                    "profile_jitter_recalc",
                    jitter_sec=self._current_jitter_sec,
                    max_jitter=self.profile.entry_delay_jitter_sec,
                )

        return self.profile.entry_delay_base_sec + self._current_jitter_sec

    def should_delay_entry(
        self,
        signal_time: datetime,
        *,
        now: Optional[datetime] = None,
    ) -> int:
        """
        Return remaining seconds to wait before entry is allowed.
        0 means "go now", positive means "wait".
        """
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if signal_time.tzinfo is None:
            signal_time = signal_time.replace(tzinfo=timezone.utc)

        total_delay = self.calculate_entry_delay_sec(now=now)
        if total_delay <= 0:
            return 0

        elapsed = (now - signal_time).total_seconds()
        remaining = total_delay - int(elapsed)
        return max(remaining, 0)

    def reset_jitter(self) -> None:
        self._last_jitter_calc = None
        self._current_jitter_sec = 0

    # ------------------------------------------------------------------ #
    # Seed / RNG
    # ------------------------------------------------------------------ #

    def _derive_seed(self) -> int:
        """Hash profile identity to a stable 31-bit int."""
        key = f"{self.profile.profile_name}|{self.profile.instance_id}|{self.profile.account_group}"
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF

    @staticmethod
    def _stable_random(*, seed: int, lo: int, hi: int) -> int:
        """
        Deterministic pseudo-random int in [lo, hi]. Linear congruential
        generator - same as the MT4 version for behavioural parity.
        """
        if hi <= lo:
            return lo
        a = 1103515245
        c = 12345
        m = 2147483647
        r = (a * (seed & 0xFFFFFFFF) + c) % m
        return lo + (abs(r) % (hi - lo + 1))

    # ------------------------------------------------------------------ #
    # Presets
    # ------------------------------------------------------------------ #

    @classmethod
    def default(cls, *, instance_id: int = 1, account_group: str = "DEFAULT") -> "ConfigProfiles":
        return cls(profile=AccountProfile(
            profile_name="DEFAULT",
            instance_id=instance_id,
            account_group=account_group,
            risk_per_trade_pct=Decimal("0.5"),
            max_quantity=Decimal("1000"),
            max_open_trades=2,
            max_trades_per_day=3,
            entry_delay_jitter_sec=30,
            entry_delay_base_sec=0,
            use_us_hours=False,
            use_weekends=True,
            use_asia=True,
            news_filter_enabled=True,
            news_minutes_before=30,
            news_minutes_after=15,
            max_spread_pct=Decimal("0.2"),
        ))

    @classmethod
    def conservative(cls, *, instance_id: int = 1, account_group: str = "DEFAULT") -> "ConfigProfiles":
        return cls(profile=AccountProfile(
            profile_name="CONSERVATIVE",
            instance_id=instance_id,
            account_group=account_group,
            risk_per_trade_pct=Decimal("0.25"),
            max_quantity=Decimal("500"),
            max_open_trades=1,
            max_trades_per_day=2,
            entry_delay_jitter_sec=60,
            entry_delay_base_sec=10,
            use_us_hours=True,         # prefer higher-liquidity hours
            use_weekends=False,        # skip weekend chop
            use_asia=False,
            news_filter_enabled=True,
            news_minutes_before=60,
            news_minutes_after=30,
            max_spread_pct=Decimal("0.15"),
        ))

    @classmethod
    def aggressive(cls, *, instance_id: int = 1, account_group: str = "DEFAULT") -> "ConfigProfiles":
        return cls(profile=AccountProfile(
            profile_name="AGGRESSIVE",
            instance_id=instance_id,
            account_group=account_group,
            risk_per_trade_pct=Decimal("1.0"),
            max_quantity=Decimal("2000"),
            max_open_trades=3,
            max_trades_per_day=5,
            entry_delay_jitter_sec=15,
            entry_delay_base_sec=0,
            use_us_hours=False,
            use_weekends=True,
            use_asia=True,
            news_filter_enabled=False,
            news_minutes_before=15,
            news_minutes_after=5,
            max_spread_pct=Decimal("0.35"),
        ))

    # ------------------------------------------------------------------ #
    # Snapshot
    # ------------------------------------------------------------------ #

    def snapshot(self) -> dict:
        p = self.profile
        return {
            "profile_name": p.profile_name,
            "instance_id": p.instance_id,
            "account_group": p.account_group,
            "account_seed": self._account_seed,
            "risk_per_trade_pct": str(p.risk_per_trade_pct),
            "max_quantity": str(p.max_quantity),
            "max_open_trades": p.max_open_trades,
            "max_trades_per_day": p.max_trades_per_day,
            "entry_delay_base_sec": p.entry_delay_base_sec,
            "entry_delay_jitter_sec": p.entry_delay_jitter_sec,
            "current_jitter_sec": self._current_jitter_sec,
            "news_filter_enabled": p.news_filter_enabled,
            "max_spread_pct": str(p.max_spread_pct),
        }
