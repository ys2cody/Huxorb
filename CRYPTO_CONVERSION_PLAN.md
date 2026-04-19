# HuxORB FOREX → CRYPTO CONVERSION PLAN
## STEP 1: Architecture Analysis & Conversion Checklist

---

## 📊 CURRENT ARCHITECTURE (MT4 Forex EA)

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: STRATEGY ENGINE (Python)                          │
│  ─────────────────────────────────────────────────────────  │
│  File: huxorb_pro_engine.py                                 │
│  • ICT strategy logic (sweep, BOS, FVG, displacement)       │
│  • Session filtering (London/NY)                            │
│  • Technical indicators (ATR, swing highs/lows)             │
│  • Signal generation → CSV file                             │
│  • FOREX-SPECIFIC: pips, spreads, 5-digit pricing           │
└─────────────────────────────────────────────────────────────┘
                          ↓ (writes signals to CSV)
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: EXECUTION ENGINE (MT4 EA - MQL4)                  │
│  ─────────────────────────────────────────────────────────  │
│  File: HuxORB_Bridge_EA_v2.mq4                              │
│  • Reads CSV signals every tick                             │
│  • Routes through RuleGuard validation                      │
│  • Places orders via OrderSend()                            │
│  • FOREX-SPECIFIC: lot sizing, MT4 broker API               │
└─────────────────────────────────────────────────────────────┘
                          ↓ (uses)
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: RULEGUARD SYSTEM (MQL4 Modules)                   │
│  ─────────────────────────────────────────────────────────  │
│  Include/*.mqh files:                                       │
│                                                              │
│  1. RuleGuard.mqh (orchestrator)                            │
│     • 7-step validation before every trade                  │
│     • Reason code system (RG_NEWS_BLACKOUT, etc.)           │
│                                                              │
│  2. NewsFilter.mqh                                          │
│     • CSV-based news calendar                               │
│     • FOREX-SPECIFIC: currency pair filtering (EUR/USD)     │
│                                                              │
│  3. SessionFilter.mqh                                       │
│     • London/NY/Asia presets                                │
│     • UTC offset handling                                   │
│     • MOSTLY COMPATIBLE: crypto trades 24/7                 │
│                                                              │
│  4. RiskManager.mqh                                         │
│     • DD tracking (daily/max)                               │
│     • FOREX-SPECIFIC: lot sizing, AccountBalance()          │
│                                                              │
│  5. ConfigProfiles.mqh                                      │
│     • Multi-account support                                 │
│     • Entry jitter (anti-mirroring)                         │
│     • COMPATIBLE: crypto needs same desync                  │
│                                                              │
│  6. Utils.mqh                                               │
│     • Helper functions                                      │
│     • FOREX-SPECIFIC: SymbolContainsCurrency()              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔴 FOREX-SPECIFIC COMPONENTS THAT MUST CHANGE

### 1. **Order Execution** (Critical)
**Current (Forex):**
- `OrderSend(Symbol(), OP_BUY, lotSize, Ask, slippage, SL, TP, comment, magic)`
- Uses MT4 broker API
- Lot sizing based on AccountBalance()

**Crypto Replacement:**
- REST API calls to exchange: `POST /api/v3/order` (Binance)
- Quote/base currency sizing (e.g., 0.001 BTC, $100 USDT)
- Spot: Buy with USDT → Own BTC → Sell for USDT
- NO leverage, NO margin, NO borrowing (halal-compliant)

---

### 2. **Symbol & Asset Formatting** (Critical)
**Current (Forex):**
- Symbols: `EURUSD`, `GBPUSD` (6-char format)
- Pricing: 5-digit (1.08451)
- Spread in points (20 = 2.0 pips)

**Crypto Replacement:**
- Symbols: `BTCUSDT`, `ETHUSDT` (exchange format)
- Pricing: Variable decimals (BTC: 2, ETH: 2, altcoins: 4-8)
- Spread: `(ask - bid) / bid * 100` (percentage, not pips)

---

### 3. **Lot Sizing → Quantity Calculation** (Critical)
**Current (Forex):**
```mql4
// Risk 0.5% of $10,000 = $50
// SL = 30 pips = $30/lot on EURUSD
// Lot size = $50 / $30 = 1.67 lots
double lotSize = (AccountBalance() * RiskPct) / (SL_pips * tickValue);
```

**Crypto Replacement:**
```python
# Risk 0.5% of $10,000 = $50
# Entry: BTC @ $50,000, SL @ $49,000 (2% drop)
# Quantity = $50 / ($50,000 - $49,000) = $50 / $1000 = 0.05 BTC
quantity = (account_balance * risk_pct) / abs(entry_price - sl_price)

# Then convert to exchange format:
# - Min notional (Binance BTCUSDT = $10 min)
# - Step size (BTC = 0.00001)
# - Quote precision (USDT = 2 decimals)
```

---

### 4. **Sessions** (Minor)
**Current (Forex):**
- London: 07:00-10:00 UTC
- New York: 12:00-16:00 UTC
- Asia: 00:00-04:00 UTC

**Crypto Replacement:**
- Crypto trades 24/7/365
- Sessions still useful for volatility filtering:
  - US Market Hours: 13:00-20:00 UTC (NYSE open)
  - Asia Hours: 00:00-08:00 UTC (lower volume)
  - Weekend: Different behavior (lower liquidity)
- **Keep SessionFilter.mqh logic, adjust presets**

---

### 5. **News Filter** (Moderate)
**Current (Forex):**
- CSV calendar with currency filtering (USD, EUR, GBP)
- Blocks trades if `SymbolContainsCurrency(symbol, eventCurrency)`

**Crypto Replacement:**
- Crypto affected by macro events (FOMC, CPI, etc.)
- NO currency-pair filtering needed
- Filter by event type instead:
  - FOMC Rate Decision → Block all crypto
  - BTC ETF Approval → Block BTC pairs
  - SEC Lawsuit → Block affected tokens
- **Redesign NewsFilter: event type → asset mapping**

---

### 6. **Risk Management** (Moderate)
**Current (Forex):**
- `AccountBalance()`, `AccountEquity()` from MT4
- DD tracking in account currency

**Crypto Replacement:**
- REST API: `GET /api/v3/account` → parse balances
- Track USDT balance (or USD equivalent)
- DD calculation same logic, different data source

---

### 7. **Spread Filtering** (Minor)
**Current (Forex):**
```mql4
int spread = (int)((Ask - Bid) / Point);  // Points
if(spread > MaxSpreadPoints) return false;
```

**Crypto Replacement:**
```python
bid = ticker['bidPrice']
ask = ticker['askPrice']
spread_pct = (ask - bid) / bid * 100
if spread_pct > MAX_SPREAD_PCT:  # e.g., 0.1%
    return False
```

---

## ✅ CONVERSION CHECKLIST

### Phase 1: Core Infrastructure
- [ ] **Exchange Connector Module**
  - [ ] Binance REST API wrapper
  - [ ] Bybit REST API wrapper (optional)
  - [ ] Abstract base class for exchange-agnostic logic
  - [ ] Error handling (rate limits, network errors)
  - [ ] Testnet/mainnet switching

- [ ] **Symbol Manager**
  - [ ] Load exchange info (min notional, step size, precision)
  - [ ] Normalize symbol format (BTCUSDT vs BTC-USDT)
  - [ ] Price formatting per exchange rules

- [ ] **Account Manager**
  - [ ] Fetch balance (USDT, BTC, etc.)
  - [ ] Calculate equity (spot balances only, no margin)
  - [ ] Track realized PnL
  - [ ] DD calculation

### Phase 2: Strategy Layer
- [ ] **Port huxorb_pro_engine.py → crypto_huxorb_engine.py**
  - [ ] Replace `pips_to_price()` → `percent_to_price()`
  - [ ] Remove spread column (fetch live via API)
  - [ ] Adjust ATR thresholds (crypto more volatile)
  - [ ] Keep ICT logic (sweep, BOS, FVG) unchanged
  - [ ] Output: JSON signal file instead of CSV

### Phase 3: RuleGuard System
- [ ] **Port RiskManager.mqh → risk_manager.py**
  - [ ] Quote/base quantity calculation
  - [ ] Min notional validation
  - [ ] Step size rounding
  - [ ] DD tracking (same logic, API data source)

- [ ] **Port SessionFilter.mqh → session_filter.py**
  - [ ] Crypto session presets (US hours, Asia, Weekend)
  - [ ] Keep validation logic

- [ ] **Port NewsFilter.mqh → news_filter.py**
  - [ ] Event type → asset mapping
  - [ ] CSV format: `DateTime,EventType,AffectedAssets,Impact`
  - [ ] Example: `2026-02-10 14:00,FOMC,ALL,HIGH`

- [ ] **Port ConfigProfiles.mqh → config_profiles.py**
  - [ ] Keep jitter logic (important for multi-account)
  - [ ] Profile-based settings

- [ ] **Port RuleGuard.mqh → rule_guard.py**
  - [ ] Same 7-step validation
  - [ ] Same reason codes
  - [ ] Pre-trade checks before API calls

### Phase 4: Execution Layer
- [ ] **Unified Trading Engine**
  - [ ] Read signals from JSON
  - [ ] RuleGuard validation
  - [ ] Calculate quantity (not lot size)
  - [ ] Place spot order via exchange API
  - [ ] Error handling & retries
  - [ ] Order status tracking
  - [ ] Dry-run mode (testnet or paper trading)

### Phase 5: Testing & Deployment
- [ ] **Backtesting**
  - [ ] Load crypto OHLCV data (Binance historical)
  - [ ] Simulate order fills
  - [ ] Commission simulation (0.1% maker/taker)
  - [ ] Multi-account backtest

- [ ] **Testnet Validation**
  - [ ] Run on Binance Testnet
  - [ ] Verify order placement
  - [ ] Verify RuleGuard blocks

- [ ] **Production Deployment**
  - [ ] Start with 1 account, small capital
  - [ ] Monitor for 1 week
  - [ ] Scale to 2-3 accounts

---

## 🏗️ NEW CRYPTO BOT ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: STRATEGY ENGINE (Python)                          │
│  ─────────────────────────────────────────────────────────  │
│  File: crypto_huxorb_engine.py                              │
│  • ICT strategy (same logic, crypto pricing)                │
│  • Load OHLCV from Binance API or CSV                       │
│  • Generate signals → JSON file                             │
│  • Output: {"symbol": "BTCUSDT", "side": "BUY", ...}        │
└─────────────────────────────────────────────────────────────┘
                          ↓ (writes JSON signals)
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: EXECUTION ENGINE (Python)                         │
│  ─────────────────────────────────────────────────────────  │
│  File: crypto_trading_bot.py                                │
│  • Reads JSON signals                                       │
│  • Routes through RuleGuard                                 │
│  • Calculates quantity (quote/base)                         │
│  • Places order: exchange.create_order()                    │
│  • Monitors fills & exits                                   │
└─────────────────────────────────────────────────────────────┘
                          ↓ (uses)
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: RULEGUARD SYSTEM (Python Modules)                 │
│  ─────────────────────────────────────────────────────────  │
│  crypto_ruleguard/*.py files:                               │
│                                                              │
│  1. rule_guard.py (orchestrator)                            │
│     • Same 7-step validation                                │
│     • Same reason codes                                     │
│                                                              │
│  2. news_filter.py                                          │
│     • Event type → asset mapping                            │
│     • FOMC → block all, SEC → block ETH, etc.               │
│                                                              │
│  3. session_filter.py                                       │
│     • Crypto sessions (US hours, weekend filter)            │
│                                                              │
│  4. risk_manager.py                                         │
│     • Quantity calculation (not lot sizing)                 │
│     • DD tracking via API balances                          │
│                                                              │
│  5. config_profiles.py                                      │
│     • Multi-account jitter                                  │
│     • Profile system (CONSERVATIVE, AGGRESSIVE)             │
│                                                              │
│  6. utils.py                                                │
│     • Price formatting, rounding                            │
│     • Time conversions                                      │
└─────────────────────────────────────────────────────────────┘
                          ↓ (uses)
┌─────────────────────────────────────────────────────────────┐
│  LAYER 4: EXCHANGE CONNECTORS (Python)                      │
│  ─────────────────────────────────────────────────────────  │
│  exchanges/*.py files:                                      │
│                                                              │
│  1. base_exchange.py (abstract interface)                   │
│     • create_order(), get_balance(), get_ticker()           │
│                                                              │
│  2. binance_exchange.py                                     │
│     • Binance REST API implementation                       │
│     • Testnet support                                       │
│                                                              │
│  3. bybit_exchange.py (optional)                            │
│     • Bybit implementation                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 NEW FILE STRUCTURE

```
Huxorb/
├── crypto_huxorb_engine.py         # Strategy (ported from huxorb_pro_engine.py)
├── crypto_trading_bot.py           # Main execution loop
├── crypto_backtest.py              # Backtesting engine
├── config.yaml                     # Bot configuration
├── crypto_ruleguard/               # RuleGuard system
│   ├── __init__.py
│   ├── rule_guard.py               # Main orchestrator
│   ├── news_filter.py              # Event-based filtering
│   ├── session_filter.py           # 24/7 with session hints
│   ├── risk_manager.py             # Quantity calc + DD tracking
│   ├── config_profiles.py          # Multi-account profiles
│   └── utils.py                    # Helpers
├── exchanges/                      # Exchange connectors
│   ├── __init__.py
│   ├── base_exchange.py            # Abstract base class
│   ├── binance_exchange.py         # Binance implementation
│   └── bybit_exchange.py           # Bybit (optional)
├── data/
│   ├── signals/                    # JSON signal files
│   ├── news_calendar.csv           # Event calendar
│   └── crypto_ohlcv/               # Historical data for backtesting
├── logs/                           # Trading logs
└── tests/                          # Unit tests
```

---

## 🎯 IMPLEMENTATION ORDER (Next Steps)

**STEP 2 (After Approval):**
1. Create file structure
2. Implement `exchanges/base_exchange.py` (abstract interface)
3. Implement `exchanges/binance_exchange.py` (testnet mode)
4. Test connection + basic order placement on testnet

**STEP 3:**
1. Port `crypto_ruleguard/utils.py`
2. Port `crypto_ruleguard/risk_manager.py` (quantity calc)
3. Unit tests for quantity calculation

**STEP 4:**
1. Port `crypto_ruleguard/session_filter.py`
2. Port `crypto_ruleguard/news_filter.py`
3. Port `crypto_ruleguard/config_profiles.py`

**STEP 5:**
1. Port `crypto_ruleguard/rule_guard.py` (orchestrator)
2. Integration tests (all validations)

**STEP 6:**
1. Port `crypto_huxorb_engine.py` (strategy)
2. Backtest on historical crypto data

**STEP 7:**
1. Implement `crypto_trading_bot.py` (main loop)
2. Test on Binance Testnet
3. Deploy with $500-1000 on mainnet

---

## ⚠️ CRITICAL DECISIONS NEEDED BEFORE STEP 2

1. **Exchange Choice:**
   - Binance (largest, best API)
   - Bybit (good for derivatives, but we're spot-only)
   - Multiple exchanges? (diversification)

2. **Asset Selection:**
   - Start with BTC/USDT only? (safest, most liquid)
   - Add ETH/USDT?
   - Trade multiple pairs? (5-10 altcoins)

3. **Capital Allocation:**
   - How much starting capital per account?
   - Risk per trade? (keep 0.5% or increase to 1%?)

4. **Halal Compliance:**
   - Spot only: ✅ Confirmed
   - Stablecoins (USDT): Acceptable?
   - Staking rewards: Allowed or avoid?

---

## ✅ READY FOR STEP 2?

**What I've delivered (STEP 1):**
- ✅ Complete architecture analysis
- ✅ Forex-specific component identification
- ✅ Conversion checklist
- ✅ New crypto bot architecture diagram
- ✅ File structure plan
- ✅ Implementation order

**Waiting for your confirmation to proceed to STEP 2:**
- Create exchange connector skeleton
- Test Binance testnet connection
- Implement basic order placement

**Type "PROCEED" or ask questions if anything needs clarification!**
