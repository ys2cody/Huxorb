# HuxORB PRO - Prop Firm Trading Bot

**Professional ICT-style Opening Range Breakout system designed to pass prop firm challenges (FundedNext, FTMO, etc.)**

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Status](https://img.shields.io/badge/status-production-green)
![Python](https://img.shields.io/badge/python-3.7+-blue)
![MT4](https://img.shields.io/badge/MT4-MQL4-blue)

---

## 🎯 Design Philosophy

**NO CURVE-FITTING. NO OPTIMIZATION. NO PARAMETER SWEEPS.**

This system is built on **market structure principles**, not backtest performance. Every parameter is justified by market logic, liquidity dynamics, and prop firm requirements.

### Primary Goals

1. **Survivability**: Pass prop firm challenges by staying within drawdown limits
2. **Consistency**: Steady returns without violating consistency rules
3. **Positive Expectancy**: EV > 0 through high-probability ICT setups
4. **Scalability**: Conservative risk allows safe scaling on funded accounts

---

## 📊 Strategy Overview

### ICT Concepts Implementation

The bot trades **Opening Range Breakouts** enhanced with **institutional order flow concepts**:

1. **Session Filter**: London (07:00-10:00 UTC) + NY (12:00-16:00 UTC) — high liquidity only
2. **Spread Gate**: EURUSD ≤20pts (2.0 pips), GBPUSD ≤25pts — execution quality filter
3. **Regime Filter**: ATR expansion (1.2x recent avg) — avoid choppy markets
4. **Liquidity Sweep**: Price hunts stops above/below swing points, then reverses
5. **Break of Structure (BOS)**: Decisive break of previous swing high/low
6. **Displacement + FVG**: Strong move (≥15 pips) creating Fair Value Gap (≥8 pips)
7. **Entry**: Retrace into FVG/Order Block at discounted (buy) or premium (sell) prices

### Risk Management (Prop Firm Compliant)

- **Risk per trade**: 0.5% (conservative, user-adjustable)
- **Reward:Risk**: 2:1 (justified by ICT setups)
- **Max trades/day**: 2 (quality over quantity)
- **Daily DD limit**: 4.6% (5% hard stop)
- **Max DD limit**: 9.5% (10% hard stop)
- **Consistency rule**: Stop if daily profit > 40% of phase target

---

## 🏗️ Architecture

### Two-Part System

```
┌─────────────────────────────────────────────────────────────┐
│                  PYTHON ENGINE (Brain)                      │
│  - Strategy logic (ICT concepts)                            │
│  - Backtesting & validation                                 │
│  - Signal generation                                        │
│  - Walk-forward analysis                                    │
│  - Monte Carlo simulation                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ HUX_SIGNAL.csv
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  MT4 EA (Execution)                         │
│  - Signal file reader                                       │
│  - Risk-based position sizing                               │
│  - Safety gates (spread, session, DD)                       │
│  - Duplicate prevention                                     │
│  - Comprehensive logging                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.7+** with pandas, numpy
- **MetaTrader 4** (FundedNext or similar prop firm account)
- **Historical data**: M5 OHLCV CSV (time, open, high, low, close, optional: spread)

### Installation

1. **Clone/download this repository**
   ```bash
   git clone https://github.com/ys2cody/Huxorb.git
   cd Huxorb
   ```

2. **Install Python dependencies**
   ```bash
   pip install pandas numpy
   ```

3. **Install MT4 EA**
   - Copy `HuxORB_Bridge_EA.mq4` to `MT4_DATA_FOLDER/MQL4/Experts/`
   - Compile in MetaEditor (F7)
   - Attach to chart (EURUSD M5 recommended)

4. **Configure EA inputs**
   - `RiskPerTradePct`: 0.5 (start conservative)
   - `ServerUtcOffsetHrs`: 2 (FundedNext default)
   - `MaxSpreadPoints`: 20 (EURUSD)
   - `DailyLossLimitPct`: 4.6
   - `MaxLossLimitPct`: 9.5
   - `PhaseTargetAmount`: Your challenge target (e.g., 1000 for $10k 10% target)

---

## 📈 Backtesting

### Basic Backtest

```bash
python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --out results/
```

**Output**:
- `results/trades_EURUSD.csv` - Trade log
- `results/equity_EURUSD.csv` - Equity curve
- `results/metrics_EURUSD.json` - Performance metrics

### Walk-Forward Validation

```bash
python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --walk-forward --periods 4
```

Tests strategy consistency across 4 time periods **without optimization**.

### Full Analysis (Backtest + Walk-Forward + Monte Carlo)

```bash
python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --full-analysis
```

**Monte Carlo output**: Probability of hitting DD limits via random reshuffling of trade outcomes.

---

## 🎛️ Live Trading Setup

### Step 1: Generate Signal (Python)

```bash
# Option A: Manual signal generation
python huxorb_pro_engine.py live_signal --csv EURUSD_M5_latest.csv --out HUX_SIGNAL.csv

# Option B: Automated (cron/scheduler)
# Run every 5 minutes during sessions
*/5 7-10,12-16 * * * cd /path/to/Huxorb && python huxorb_pro_engine.py live_signal --csv data/EURUSD_M5_latest.csv --out HUX_SIGNAL.csv
```

### Step 2: Copy Signal to MT4

Move `HUX_SIGNAL.csv` to `MT4_DATA_FOLDER/MQL4/Files/`:

```bash
# Windows example
cp HUX_SIGNAL.csv "C:/Users/YourName/AppData/Roaming/MetaQuotes/Terminal/ABCD1234/MQL4/Files/"

# Linux (Wine)
cp HUX_SIGNAL.csv ~/.wine/drive_c/Program\ Files/MetaTrader\ 4/MQL4/Files/
```

### Step 3: EA Execution

The EA automatically:
1. Reads `HUX_SIGNAL.csv` every tick
2. Validates session, spread, DD limits
3. Calculates risk-based position size
4. Executes trade with SL/TP
5. Deletes signal file to prevent re-execution
6. Logs everything to Experts tab

---

## 🔧 Configuration Reference

### Python Engine Constants

Located in `huxorb_pro_engine.py` (lines 31-61):

| Parameter | Value | Justification |
|-----------|-------|---------------|
| `RISK_PER_TRADE_PCT` | 0.5% | Conservative for prop firms |
| `DEFAULT_RR` | 2.0 | ICT setups typically offer 2:1+ |
| `MAX_TRADES_PER_DAY` | 2 | Quality over quantity |
| `MAX_SPREAD_EURUSD` | 20pts | Execution quality (2.0 pips) |
| `LONDON_SESSION` | 07:00-10:00 UTC | High liquidity period |
| `NEWYORK_SESSION` | 12:00-16:00 UTC | High liquidity period |
| `SWING_LOOKBACK` | 10 bars | ~50min structure (M5) |
| `MIN_DISPLACEMENT_PIPS` | 15 | Significant move (EURUSD) |
| `MIN_FVG_PIPS` | 8 | Valid gap size (EURUSD) |
| `ATR_PERIOD` | 14 | Standard volatility measure |
| `ATR_EXPANSION_FACTOR` | 1.2 | Trend vs chop threshold |

### MT4 EA Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `RiskPerTradePct` | 0.5 | Risk per trade (% of equity) |
| `MaxTradesPerDay` | 2 | Hard cap on daily trades |
| `MaxSpreadPoints` | 20 | EURUSD spread limit (2.0 pips) |
| `ServerUtcOffsetHrs` | 2 | FundedNext = UTC+2 |
| `TradeLondon` | true | Enable London session |
| `TradeNewYork` | true | Enable NY session |
| `DailyLossLimitPct` | 4.6 | Daily DD kill-switch (5% hard limit) |
| `MaxLossLimitPct` | 9.5 | Max DD kill-switch (10% hard limit) |
| `ProfitCapPctOfTarget` | 40.0 | Consistency rule (% of phase target) |
| `PhaseTargetAmount` | 1000.0 | Phase profit target ($) |

---

## 🛠️ Troubleshooting

### No Trades Generated

**Problem**: Backtest or live signal shows 0 trades.

**Solutions**:
1. **Check data quality**:
   - CSV has columns: `time, open, high, low, close`
   - Time is parseable (ISO format: `2024-01-15 08:00:00`)
   - Sufficient data (≥50 bars for indicators)

2. **Strategy is selective** — this is intentional!
   - All 7 gates must align (session, spread, regime, sweep, BOS, FVG, displacement)
   - ICT setups are rare but high-quality
   - Typical rate: 2-5 signals per week on EURUSD M5

3. **Check sessions**:
   - Data timestamps should be in UTC (or convertible)
   - Sessions: 07:00-10:00 UTC (London), 12:00-16:00 UTC (NY)

4. **Verify parameters**:
   - `MIN_DISPLACEMENT_PIPS = 15` (reduce to 10 if testing on low-volatility data)
   - `MIN_FVG_PIPS = 8` (reduce to 5 if needed)
   - **Do NOT optimize these values!** Lower thresholds = more noise.

### EA Not Executing Trades

**Problem**: Signal generated but EA doesn't trade.

**Solutions**:
1. **Check signal file location**:
   - File must be in `MT4_DATA_FOLDER/MQL4/Files/HUX_SIGNAL.csv`
   - Check MT4 Experts tab for "Invalid file handle" errors

2. **Verify EA settings**:
   - AutoTrading enabled (green button in MT4 toolbar)
   - EA inputs match your broker/account
   - `ServerUtcOffsetHrs` correct (FundedNext = 2, check with broker)

3. **Session filter**:
   - EA only trades during London/NY sessions (UTC-based)
   - Check current time vs sessions in Experts log

4. **Spread too high**:
   - Check current spread (right-click chart → Spread → Show)
   - If spread > `MaxSpreadPoints`, trade blocked (logged)

5. **Max trades hit**:
   - Check Experts log for "Trades today: 2/2"
   - Counter resets at midnight server time

6. **DD limit hit**:
   - Check for alerts: "DAILY DRAWDOWN LIMIT HIT" or "MAX DRAWDOWN LIMIT HIT"
   - Daily limit resets next day; max limit is permanent until EA restart

### Spread Always Too High

**Problem**: Spread check always fails.

**Solutions**:
1. **Check broker spread**:
   - EURUSD typical: 1-3 pips (10-30 points on 5-digit)
   - If spread consistently > 20 points (2.0 pips), consider switching broker

2. **Adjust `MaxSpreadPoints`**:
   - ECN brokers: 5-15 points acceptable
   - Market makers: 15-25 points typical
   - **Warning**: Higher spread = lower edge. Only increase if broker reality demands it.

3. **Trade during high liquidity**:
   - Spreads widen outside London/NY sessions
   - Avoid Sunday open, Friday close, news events

### Position Size Too Small/Large

**Problem**: Lot size doesn't match expected risk.

**Solutions**:
1. **Verify risk calculation**:
   - EA uses: `LotSize = RiskAmount / (SL_Distance * TickValue)`
   - Check Experts log for "Risk Calculation" details

2. **Account currency mismatch**:
   - If account currency ≠ base currency (e.g., EUR account, EURUSD pair), tick value conversion may differ
   - Verify `MODE_TICKVALUE` is correct for your broker

3. **Min/max lot constraints**:
   - Broker limits: Check `MODE_MINLOT`, `MODE_MAXLOT`, `MODE_LOTSTEP`
   - Lot size rounded down to nearest `MODE_LOTSTEP`

4. **SL too tight**:
   - If SL distance is very small (e.g., 10 pips), lot size may hit `MODE_MAXLOT`
   - Verify signal SL is reasonable (typically 20-50 pips)

---

## ✅ No-Curve-Fit Checklist

### Safe to Change

These adjustments are based on **external constraints**, not backtest optimization:

- ✅ **Risk per trade** (`RiskPerTradePct`): Adjust for your risk tolerance (0.5%-1.5%)
- ✅ **Max spread** (`MaxSpreadPoints`): Match your broker's reality
- ✅ **Server UTC offset** (`ServerUtcOffsetHrs`): Match your broker's server time
- ✅ **Sessions** (`TradeLondon`, `TradeNewYork`): Enable/disable based on availability
- ✅ **Prop firm limits** (`DailyLossLimitPct`, `MaxLossLimitPct`, `PhaseTargetAmount`): Match your challenge rules
- ✅ **Symbol**: Trade GBPUSD instead of EURUSD (adjust `MAX_SPREAD` accordingly)

### Unsafe to Change (Curve-Fitting Risk)

Do **NOT** modify these to improve backtest results:

- ❌ **`MIN_DISPLACEMENT_PIPS`**: Lowering this accepts weaker setups
- ❌ **`MIN_FVG_PIPS`**: Lowering this accepts smaller gaps (more noise)
- ❌ **`SWING_LOOKBACK`**: Tuning this optimizes to historical data
- ❌ **`ATR_EXPANSION_FACTOR`**: Adjusting this overfits regime detection
- ❌ **`DEFAULT_RR`**: Changing TP distance invalidates setup logic
- ❌ **Session times**: Widening sessions accepts lower liquidity periods

### If You Must Adjust Strategy Parameters

**Process**:
1. Document the **market logic** reason (not backtest performance)
2. Test on **out-of-sample data** (not used for development)
3. Run **walk-forward validation** to check consistency
4. Use **Monte Carlo** to verify DD risk unchanged

**Example**:
- ❌ Bad: "I lowered `MIN_FVG_PIPS` from 8 to 5 because it increased win rate by 3%"
- ✅ Good: "I lowered `MIN_FVG_PIPS` to 5 for GBPUSD because its average pip range is smaller than EURUSD, and 5 pips represents the same structural significance"

---

## 📚 Understanding the Metrics

### Expectancy (Avg R)

**Most important metric**. Average R-multiple per trade.

- **EV > 0.5**: Excellent (avg trade wins 0.5R)
- **EV > 0.3**: Good
- **EV > 0.1**: Acceptable
- **EV < 0**: Losing system

Example: EV = 0.4 means average trade makes 0.4x risk. With 0.5% risk per trade, avg profit = 0.2% per trade.

### Profit Factor

Gross profit / gross loss. Measures robustness.

- **PF > 2.0**: Excellent
- **PF > 1.5**: Good
- **PF > 1.2**: Acceptable
- **PF < 1.0**: Losing system

### Win Rate

% of winning trades. Context-dependent (2:1 RR doesn't need high WR).

- **WR > 50%**: Great with 2:1 RR
- **WR > 40%**: Acceptable with 2:1 RR
- **WR < 35%**: Risky (long losing streaks)

### Max Drawdown

Peak-to-trough equity decline (%).

- **Backtest DD < 10%**: Excellent for prop firms
- **Backtest DD < 15%**: Good
- **Backtest DD > 20%**: Risky (likely to hit 10% live DD limit)

**Monte Carlo DD percentiles** more important than single backtest DD.

---

## 🎓 Strategy Justifications

### Why ICT Concepts?

**Liquidity Sweeps**, **Break of Structure**, and **Fair Value Gaps** are not "magic" — they represent:
1. **Stop hunts** (sweep): Large players triggering retail stops before reversing
2. **Structural shifts** (BOS): Confirmation of trend change via swing breaks
3. **Inefficient pricing** (FVG): Rapid moves leaving gaps that price revisits

These patterns recur because market structure is fractal and liquidity-driven.

### Why 2:1 Reward:Risk?

ICT setups target **displacement continuation** after retrace into FVG. Historical price action shows these moves often extend 2-3x the initial displacement distance, making 2:1 TP conservative.

### Why Max 2 Trades/Day?

Prop firms penalize overtrading (consistency rules, spread costs). High-frequency trading requires:
1. Lower risk per trade → slower growth
2. More exposure to spread costs → lower edge
3. Higher complexity → more failure points

**2 trades/day** balances opportunity with selectivity.

### Why 0.5% Risk?

Prop firm drawdown limits (5% daily, 10% max) are tight. With 0.5% risk:
- **10 consecutive losses** = 5% DD (daily limit)
- **20 consecutive losses** = 10% DD (max limit)

Even with 50% win rate, probability of 10 consecutive losses is ~0.1% (Monte Carlo confirms this). **0.5% risk = high probability of survival**.

---

## 🔬 Validation & Testing

### Recommended Testing Sequence

1. **Backtest** (full dataset):
   ```bash
   python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --out results/
   ```
   **Goal**: Verify positive expectancy (EV > 0.3) and acceptable DD (<15%).

2. **Walk-Forward** (4 periods):
   ```bash
   python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --walk-forward --periods 4
   ```
   **Goal**: Confirm consistency (EV and PF stable across periods, std dev low).

3. **Monte Carlo** (1000 runs):
   ```bash
   python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --full-analysis
   ```
   **Goal**: Verify DD risk (prob of hitting 10% DD < 5%).

4. **Demo Account** (1-2 weeks):
   - Deploy EA on demo with challenge rules
   - Verify execution quality (slippage, spread, fills)
   - Confirm no bugs (logging, DD tracking, file I/O)

5. **Challenge** (live):
   - Start with minimum account size
   - Monitor daily: Check Experts log, equity curve, DD%
   - Stay conservative: Do NOT increase risk until funded

---

## 📊 Data Requirements

### CSV Format

```csv
time,open,high,low,close,volume,spread
2024-01-15 08:00:00,1.08923,1.08945,1.08910,1.08932,1234,15
2024-01-15 08:05:00,1.08932,1.08950,1.08925,1.08940,1456,14
...
```

**Required columns**: `time, open, high, low, close`
**Optional columns**: `volume, spread`

### Data Sources

- **HistData.com**: Free M1 data (resample to M5)
- **DukasCopy**: Free tick data (resample to M5)
- **MetaTrader**: Export from History Center (Tools → History Center → Export)
- **AlphaVantage/Yahoo Finance**: API-based (may lack intraday)

### Data Quality Checklist

- ✅ No gaps > 1 hour (missing data causes false signals)
- ✅ Timestamps in UTC (or clearly documented timezone)
- ✅ Spread data realistic (or omit to assume 0 in backtest)
- ✅ At least 3 months of data (preferably 6-12 months)

---

## 🚨 Risk Disclosure

### Prop Firm Challenges

**This bot is designed for prop firm challenges, NOT retail trading.**

- Prop firms use **simulated accounts** with strict rules
- Passing a challenge ≠ profit guarantee on funded account
- Funded accounts may have different execution (slippage, requotes)
- Always read and understand prop firm terms (profit splits, withdrawal rules, activity requirements)

### Backtesting Limitations

- **Past performance ≠ future results**
- Backtest uses **worst-case intrabar ordering** (conservative) but cannot model:
  - Requotes, slippage, partial fills
  - Server downtime, connection issues
  - News event volatility spikes
- **Walk-forward validation** reduces overfitting risk but doesn't eliminate it
- **Monte Carlo** estimates DD probabilities but assumes trade distribution is stationary

### Live Trading Risks

- **Drawdown limits are real**: Hitting 5% daily or 10% max = challenge failure
- **Market conditions change**: Strategy may underperform during low volatility or ranging markets
- **Technical failures**: Power outage, internet loss, MT4 crash = missed trades or unmanaged positions
- **You are responsible**: This code is provided "as-is" with no guarantees

**Use at your own risk. The authors are not liable for any losses.**

---

## 🤝 Contributing

This is a **production system**, not an experimental playground. Contributions welcome if they:

1. **Fix bugs** (execution errors, calculation mistakes)
2. **Improve robustness** (error handling, edge cases)
3. **Add features** (new safety rails, logging, monitoring)

**Do NOT submit PRs that**:
- Optimize parameters based on backtest results
- Add complex indicators without clear market logic justification
- Increase strategy complexity without robustness benefit

### Contribution Process

1. Open an issue describing the bug/feature
2. Discuss the approach (ensure it aligns with no-curve-fit philosophy)
3. Submit PR with:
   - Clear code comments
   - Justification for any parameter changes
   - Test results (backtest/demo if applicable)

---

## 📄 License

MIT License - See LICENSE file for details.

**Commercial Use**: Permitted, but you assume all risk. No warranties provided.

---

## 🙏 Acknowledgments

- **ICT (Inner Circle Trader)**: Concepts of liquidity sweeps, FVG, order blocks
- **Prop Firm Community**: Feedback on challenge-passing strategies
- **Open Source Contributors**: pandas, numpy, MT4 community

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/ys2cody/Huxorb/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ys2cody/Huxorb/discussions)
- **Wiki**: [GitHub Wiki](https://github.com/ys2cody/Huxorb/wiki)

**No direct support provided.** This is an open-source project maintained by the community.

---

## 📝 Changelog

### v1.0.0 (2026-01-22)

**Initial Release**

- ✅ Python engine with full ICT strategy logic
- ✅ MT4 EA with risk-based position sizing
- ✅ Backtest engine with conservative assumptions
- ✅ Walk-forward validation (no optimization)
- ✅ Monte Carlo simulation (DD risk analysis)
- ✅ Prop firm safety rails (DD limits, consistency rule)
- ✅ Comprehensive documentation

---

## 🎯 Roadmap

### v1.1.0 (Planned)

- [ ] Add GBPUSD-specific parameters (spread, displacement thresholds)
- [ ] Telegram notifications (trade alerts, DD warnings)
- [ ] Enhanced logging (CSV export, daily reports)
- [ ] Multi-symbol support (parallel trading with shared DD limits)

### v1.2.0 (Planned)

- [ ] REST API for signal generation (replace file-based bridge)
- [ ] Real-time dashboard (equity curve, live DD%, trade log)
- [ ] Advanced Monte Carlo (parameter sensitivity analysis)

**No promises. Development depends on community feedback and testing results.**

---

**Built with discipline. Tested with rigor. Trade with caution.** 🚀
