```markdown
# Strategy Layer

**STEP 4 COMPLETE**: Regime-aware, long-only spot trading strategies for KuCoin.

## Architecture

```
┌──────────────────┐
│  Market Data     │  (OHLCV from KuCoin via CCXT)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Regime Filter   │  → TREND / RANGE / LOW_VOL
└────────┬─────────┘
         │
         ▼
    ┌────────┴────────┐
    ▼                 ▼
┌─────────┐      ┌─────────────┐
│ Trend   │      │ Mean-Rev    │
│ Follow  │      │ Strategy    │
└────┬────┘      └──────┬──────┘
     │                  │
     └────────┬─────────┘
              ▼
       ┌──────────────┐
       │ TradeDecision │ (entry/stop/tp)
       └──────┬───────┘
              ▼
       ┌──────────────┐
       │  RuleGuard   │  → validation
       └──────┬───────┘
              ▼
       ┌──────────────┐
       │   Exchange   │  → order execution
       └──────────────┘
```

## Components

### 1. Regime Filter (`regime.py`)

Classifies market conditions using BTC macro + symbol micro:

**Inputs:**
- BTC daily OHLCV (macro trend)
- Symbol 4H OHLCV (micro conditions)

**Regimes:**
- **TREND**: BTC above 200D EMA, 50D > 200D, ADX >= 20 → use trend-following
- **RANGE**: ADX < 20 → use mean-reversion
- **LOW_VOL**: ATR below 25th percentile → skip (too quiet)

**Configuration:**
```python
from core.strategy import RegimeConfig

config = RegimeConfig(
    btc_daily_ema_fast=50,
    btc_daily_ema_slow=200,
    adx_range_threshold=20.0,
    atr_period=14,
    atr_low_vol_percentile=25.0,
)
```

### 2. Trend-Following Strategy (`trend_following.py`)

Long-only pullback entries in uptrends.

**Conditions:**
1. Price above 200 EMA
2. 50 EMA > 200 EMA (momentum alignment)
3. Price pulls back to 20 EMA or 50 EMA (within 1%)
4. Confirmation pattern:
   - Bullish engulfing candle, OR
   - Strong rejection wick (lower shadow >= 2x body), OR
   - Break above prior candle high

**Entry:** Market order after confirmation candle closes

**Stop Loss:** max(recent swing low, ATR(14) * 1.5 below entry)

**Take Profit:** 2R (risk-reward ratio)

**Configuration:**
```python
from core.strategy import TrendFollowingConfig

config = TrendFollowingConfig(
    ema_fast=50,
    ema_slow=200,
    ema_entry=20,
    atr_stop_multiplier=1.5,
    risk_reward_ratio=2.0,
    require_confirmation=True,
)
```

### 3. Mean-Reversion Strategy (`mean_reversion.py`)

Long-only oversold bounces in range markets.

**Conditions:**
1. ADX < 20 (range regime, enforced by RegimeFilter)
2. Price touches or goes below lower Bollinger Band
3. RSI(14) < 30 (oversold)
4. Price closes back inside Bollinger Band (bounce confirmation)
5. BTC macro not strongly bearish

**Entry:** Market order after bounce confirmation

**Stop Loss:** max(recent swing low, ATR(14) * 1.5 below entry)

**Take Profit:** min(middle Bollinger Band, 1.5R)

**Configuration:**
```python
from core.strategy import MeanReversionConfig

config = MeanReversionConfig(
    bb_period=20,
    bb_std_dev=2.0,
    rsi_period=14,
    rsi_oversold=30.0,
    atr_stop_multiplier=1.5,
    risk_reward_ratio=1.5,
)
```

### 4. Strategy Engine (`engine.py`)

Orchestrates the complete decision flow per symbol per tick.

**Flow:**
1. Classify regime
2. Select strategy (trend / mean-rev)
3. Generate signal (entry/stop/tp)
4. Calculate position size via RiskManager
5. Validate via RuleGuard
6. Execute trade

**Usage:**
```python
from core.strategy import StrategyEngine, StrategyConfig
from core.ruleguard import RuleGuard, RiskManager
from core.exchange import CCXTSpotExchange

# Setup
exchange = CCXTSpotExchange(exchange="kucoin", testnet=True)
risk = RiskManager(starting_balance=Decimal("10000"))
guard = RuleGuard(risk, sessions, news, config, dry_run=False)

config = StrategyConfig(
    symbols=["BTC/USDT", "ETH/USDT"],
    trading_timeframe="4h",
)

engine = StrategyEngine(config, exchange, risk, guard)

# Evaluate
ohlcv_4h = exchange.fetch_ohlcv("ETH/USDT", timeframe="4h", limit=300)
btc_1d = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=300)

decision = engine.evaluate("ETH/USDT", ohlcv_4h, btc_1d)

# Execute if signal is valid and not blocked
if decision.has_signal and not decision.blocked:
    order_id = engine.execute_trade(decision)
```

## Indicators (`indicators.py`)

Clean pandas-based implementations:

- `ema(series, period)` - Exponential Moving Average
- `sma(series, period)` - Simple Moving Average
- `atr(high, low, close, period)` - Average True Range
- `adx(high, low, close, period)` - Average Directional Index
- `rsi(series, period)` - Relative Strength Index
- `bollinger_bands(series, period, std_dev)` - Bollinger Bands
- `swing_low(low, lookback)` - Local minima detection
- `swing_high(high, lookback)` - Local maxima detection
- `is_bullish_engulfing(open, high, low, close)` - Candlestick pattern
- `has_rejection_wick(open, high, low, close, min_wick_ratio)` - Wick detection
- `higher_high(close, lookback)` - Momentum check

All accept pandas Series/DataFrame, return same shape.

## KuCoin Integration

### Symbol Format

KuCoin uses slash format via CCXT:
```python
symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
```

### Market Metadata

Respect KuCoin's constraints:
```python
market = exchange.get_market("BTC/USDT")
print(market.limits.amount.min)   # Min order size
print(market.limits.amount.step)  # Quantity step
print(market.precision.amount)    # Decimal places
```

Position sizing automatically rounds to `step`:
```python
qty = risk.calculate_quantity(
    entry_price=Decimal("60000"),
    stop_loss=Decimal("59400"),
    step_size=market.limits.amount.step,
    min_quantity=market.limits.amount.min,
)
```

### Testnet

KuCoin testnet support:
```python
exchange = CCXTSpotExchange(
    exchange="kucoin",
    api_key="your_key",
    api_secret="your_secret",
    password="your_password",  # KuCoin requires API password
    testnet=True,  # Use sandbox
)
```

## Halal Compliance

**Spot-only enforcement:**
- No leverage, margin, futures, perpetuals
- RuleGuard rejects any order params with forbidden keys (leverage, margin, etc.)
- CCXTSpotExchange filters out non-spot markets
- Position sizing based on owned capital only

**Long-only:**
- No shorting (sell-side trades disabled)
- All entries are BUY orders
- Own the asset before selling

## Logging

Every decision cycle logs:
```json
{
  "timestamp": "2026-04-15T12:00:00Z",
  "symbol": "ETH/USDT",
  "regime": "trend",
  "regime_reason": "btc_bullish + adx=32.1",
  "strategy": "trend_following",
  "has_signal": true,
  "entry_price": "3500.00",
  "stop_loss": "3450.00",
  "take_profit": "3600.00",
  "quantity": "0.285",
  "signal_reason": "pullback_confirmed:bullish_engulfing",
  "blocked": false
}
```

## Configuration

Strategy settings can be customized per deployment:

```python
from core.strategy import (
    StrategyConfig,
    RegimeConfig,
    TrendFollowingConfig,
    MeanReversionConfig,
)

config = StrategyConfig(
    symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
    trading_timeframe="4h",
    btc_daily_symbol="BTC/USDT",
    regime=RegimeConfig(
        adx_range_threshold=20.0,
        atr_low_vol_percentile=25.0,
    ),
    trend=TrendFollowingConfig(
        risk_reward_ratio=2.0,
        require_confirmation=True,
    ),
    meanrev=MeanReversionConfig(
        rsi_oversold=30.0,
        risk_reward_ratio=1.5,
    ),
)
```

## Testing

Smoke test the strategy layer:
```bash
python3 -c "
from core.strategy import StrategyEngine, StrategyConfig
from core.strategy.indicators import ema, atr, rsi
import pandas as pd

# Test indicators
closes = pd.Series([100, 101, 102, 103, 104])
print('EMA:', ema(closes, 3).iloc[-1])

# Test regime filter
from core.strategy import RegimeFilter
regime = RegimeFilter()
print('Regime filter initialized')

print('✓ Strategy layer operational')
"
```

## Next Steps

- **STEP 5**: Backtesting engine (test strategies on historical data)
- **STEP 6**: Paper trading mode (live data, simulated orders)
- **STEP 7**: Live deployment on KuCoin Spot

---

**Built**: April 2026  
**Status**: STEP 4 Complete  
**Exchange**: KuCoin Spot  
**Mode**: Long-only, halal-compliant
```
