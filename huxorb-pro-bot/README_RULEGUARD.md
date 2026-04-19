# RuleGuard

The **RuleGuard** is a validation layer that sits between your trading
strategy and the exchange connector. It is the ONLY path through which
orders should be placed.

```
┌──────────────┐        ┌─────────────┐        ┌──────────────┐
│  Strategy    │ ─────▶ │  RuleGuard  │ ─────▶ │  Exchange    │
│  (signals)   │        │  (checks)   │        │  (orders)    │
└──────────────┘        └─────────────┘        └──────────────┘
                              │
                              ├── RiskManager
                              ├── SessionFilter
                              ├── NewsFilter
                              └── ConfigProfiles
```

## Why

Protect capital and enforce discipline:

- Cap risk per trade (fixed % of balance)
- Halt trading on daily/max drawdown
- Limit trades per day and simultaneous open positions
- Optionally skip low-liquidity sessions (weekends, off-hours)
- Block trading around scheduled news events (FOMC, CPI, halvings, etc.)
- Enforce halal compliance: reject any order carrying leverage/margin params
- Multi-account jitter so parallel instances don't front-run each other

## Components

### RiskManager — position sizing, drawdown, trade counts

```python
from decimal import Decimal
from core.ruleguard import RiskManager

risk = RiskManager(
    starting_balance=Decimal("10000"),
    risk_per_trade_pct=Decimal("0.5"),    # 0.5% per trade
    max_quantity=Decimal("1"),            # max 1 BTC
    max_open_trades=2,
    max_trades_per_day=3,
    daily_loss_limit_pct=Decimal("5"),    # stop for the day at -5%
    max_drawdown_pct=Decimal("10"),       # stop forever at -10% from peak
)

# Size a position so exactly 0.5% is at risk
qty = risk.calculate_quantity(
    entry_price=Decimal("60000"),
    stop_loss=Decimal("59400"),
    step_size=Decimal("0.00001"),         # exchange lot step
    min_quantity=Decimal("0.0001"),
)

# Keep fresh on every tick
risk.update_balance(Decimal("10150"))
risk.set_open_trades(1)
```

### SessionFilter — optional trading hours

Crypto is 24/7 by default, but you may prefer to skip weekends or
restrict to high-liquidity hours.

```python
from core.ruleguard import SessionFilter, TradingSession

# Always on (crypto default)
sessions = SessionFilter.all_day()

# Weekdays only
sessions = SessionFilter.weekdays_only()

# US market overlap only (13:30-20:00 UTC Mon-Fri)
sessions = SessionFilter.us_hours()

# Custom
sessions = SessionFilter()
sessions.add_session(TradingSession(
    name="london_ny_overlap",
    start_hour=12, start_minute=0,
    end_hour=16, end_minute=0,
    days={1, 2, 3, 4, 5},     # Mon-Fri (ISO weekday)
))
```

### NewsFilter — event blackouts

Block trading inside `minutes_before..minutes_after` a scheduled event.

```python
from core.ruleguard import NewsFilter

# From CSV (preferred)
news = NewsFilter(
    enabled=True,
    csv_path="data/news_calendar.csv",
    minutes_before=30,
    minutes_after=15,
    high_impact_only=False,
)

# Or manually (useful for exchange maintenance windows)
from datetime import datetime, timezone, timedelta
start = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
news.add_blackout(
    start=start,
    end=start + timedelta(hours=2),
    asset="BTC",
    impact="HIGH",
    title="Exchange Wallet Upgrade",
)
```

**CSV format** (`data/news_calendar.csv`):

```
datetime_utc,asset,impact,title
2026-04-30 18:00:00,USD,HIGH,FOMC Rate Decision
2026-05-01 12:30:00,USD,HIGH,Non-Farm Payrolls
```

The filter matches by asset:
- `USD` covers every stablecoin quote (USDT, USDC, BUSD, …)
- Crypto tickers (BTC, ETH, …) match the base or quote side of the pair

### ConfigProfiles — presets + multi-account jitter

Three presets: `default`, `conservative`, `aggressive`. Each account
gets a deterministic jitter delay so parallel bots don't fire at the
exact same moment.

```python
from core.ruleguard import ConfigProfiles

# Use a preset
config = ConfigProfiles.conservative(instance_id=1, account_group="PRIMARY")

# Or fully custom
from core.ruleguard import AccountProfile
config = ConfigProfiles(profile=AccountProfile(
    profile_name="CUSTOM",
    instance_id=42,
    risk_per_trade_pct=Decimal("0.75"),
    entry_delay_jitter_sec=45,
))
```

### RuleGuard — orchestrator

```python
from core.ruleguard import RuleGuard

guard = RuleGuard(
    risk_manager=risk,
    session_filter=sessions,
    news_filter=news,
    config=config,
    dry_run=False,      # True blocks everything for paper testing
)

# Every order must go through this gate
decision = guard.can_open_trade(
    symbol="BTC/USDT",
    side="buy",
    quantity=Decimal("0.01"),
    entry_price=Decimal("60000"),
    stop_loss=Decimal("59400"),
    take_profit=Decimal("61500"),
    bid=Decimal("59999"),
    ask=Decimal("60001"),
)

if decision.allowed:
    order = exchange.create_order(...)
    risk.increment_trade_count()
else:
    logger.warning("blocked", reason=decision.reason, detail=decision.detail)
```

## Validation order

`can_open_trade()` runs these checks in order and fails fast on the first
failure:

1. **DRY_RUN_MODE** — if `dry_run=True`
2. **FORBIDDEN_PARAM** — rejects leverage/margin/reduceOnly params
3. Parameter sanity — side, prices, SL on correct side, SL not too close
4. **SPREAD_TOO_HIGH** — current bid/ask spread > profile cap
5. **OUTSIDE_SESSION** — not inside any enabled session
6. **NEWS_BLACKOUT** — inside an event blackout window
7. Risk limits:
    - **QUANTITY_CAP**, **INVALID_QUANTITY**
    - **MAX_TRADES_TODAY**
    - **MAX_OPEN_TRADES**
    - **DAILY_LOSS_LIMIT**, **MAX_DRAWDOWN**
8. **ENTRY_DELAY_JITTER** — awaiting per-account delay

Every block returns a `RuleGuardDecision` with a machine-readable
`reason` (see `core/ruleguard/reasons.py`) and a human `detail` string.

## Halal compliance

Three layers prevent any non-spot behaviour:

1. `Market` Pydantic model rejects any `market_type != SPOT`
2. `CCXTSpotExchange` connector filters out non-spot markets
3. `RuleGuard` rejects any order `params` containing `leverage`,
   `margin`, `reduceOnly`, `isolated`, `cross`, or `positionSide`

## Tests

```bash
pytest tests/test_risk_manager.py \
       tests/test_session_filter.py \
       tests/test_news_filter.py \
       tests/test_config_profiles.py \
       tests/test_rule_guard.py -v
```

All 87 tests should pass.
