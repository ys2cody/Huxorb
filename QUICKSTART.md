# HuxORB PRO - Quick Start Guide

## 5-Minute Setup

### 1. Install Dependencies
```bash
pip install pandas numpy
```

### 2. Prepare Data
Your CSV must have these columns: `time,open,high,low,close`

Example format:
```csv
time,open,high,low,close,spread
2024-01-15 08:00:00,1.08923,1.08945,1.08910,1.08932,15
2024-01-15 08:05:00,1.08932,1.08950,1.08925,1.08940,14
```

### 3. Run Backtest
```bash
python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --out results/
```

### 4. Install EA in MT4
1. Copy `HuxORB_Bridge_EA.mq4` to `MT4/MQL4/Experts/`
2. Open MetaEditor (F4 in MT4)
3. Compile EA (F7)
4. Attach to EURUSD M5 chart

### 5. Configure EA
**Critical settings**:
- `RiskPerTradePct`: 0.5 (conservative)
- `ServerUtcOffsetHrs`: 2 (FundedNext) or check your broker
- `MaxSpreadPoints`: 20 (EURUSD)
- `PhaseTargetAmount`: Your challenge profit target (e.g., 1000 for $10k 10% target)

---

## Parameter Quick Reference

### Python Engine (huxorb_pro_engine.py)

| What | Where | Default | Change if... |
|------|-------|---------|--------------|
| Risk % | Line 36 | 0.5% | You want more/less aggressive |
| RR ratio | Line 37 | 2.0 | Never (invalidates setup logic) |
| Max trades/day | Line 38 | 2 | Prop firm allows more |
| EURUSD spread | Line 41 | 20pts | Your broker has wider spread |
| Displacement pips | Line 50 | 15 | Trading different symbol (adjust proportionally) |
| FVG min pips | Line 51 | 8 | Trading different symbol (adjust proportionally) |

### MT4 EA (HuxORB_Bridge_EA.mq4)

| Input | Default | When to change |
|-------|---------|----------------|
| RiskPerTradePct | 0.5 | Want 1% risk instead |
| MaxTradesPerDay | 2 | Prop firm allows 3+ |
| MaxSpreadPoints | 20 | Broker spread > 2 pips |
| ServerUtcOffsetHrs | 2 | Different broker (check server time) |
| DailyLossLimitPct | 4.6 | Prop firm has different limit |
| MaxLossLimitPct | 9.5 | Prop firm has different limit |
| PhaseTargetAmount | 1000 | Your challenge target differs |

---

## Expected Performance (EURUSD M5)

**Realistic expectations**:
- **Trades per week**: 2-5 (strategy is selective!)
- **Win rate**: 40-55% (2:1 RR doesn't need high WR)
- **Expectancy**: 0.2-0.5 R (positive edge)
- **Profit factor**: 1.3-2.0 (conservative)
- **Max DD**: 5-15% (backtest, Monte Carlo important)

**This is NOT a get-rich-quick system**. It's designed to pass prop challenges reliably, not to 2x your account in a week.

---

## Common Mistakes

### ❌ Increasing risk to 2-5%
**Why bad**: 5 losses = 10-25% DD (challenge failed)

### ❌ Lowering MIN_DISPLACEMENT_PIPS to get more trades
**Why bad**: Curve-fitting! Weaker setups = lower edge

### ❌ Running on M1 or H1 timeframe
**Why bad**: Strategy designed for M5 structure

### ❌ Trading outside London/NY sessions
**Why bad**: Lower liquidity = wider spreads, more slippage

### ❌ Skipping backtesting
**Why bad**: You won't know if data quality is good or parameters match your broker

---

## Troubleshooting in 30 Seconds

| Problem | Solution |
|---------|----------|
| No trades in backtest | Data might be bad quality OR strategy is correctly selective (check sessions in data) |
| EA not trading | Check AutoTrading enabled, signal file in MQL4/Files/, spread < limit |
| Lot size wrong | Verify account currency matches pair base currency, check MODE_TICKVALUE |
| Spread always too high | Trade during London/NY only, or adjust MaxSpreadPoints to broker reality |

---

## Next Steps

1. ✅ Run backtest on 3+ months of data
2. ✅ Check expectancy > 0.3 and DD < 15%
3. ✅ Run walk-forward validation to verify consistency
4. ✅ Run Monte Carlo to check DD risk
5. ✅ Deploy on demo for 1-2 weeks
6. ✅ Start prop firm challenge

**Do NOT skip steps 4-5!** Going live without testing is gambling, not trading.

---

## Support

Read the full README.md for detailed explanations.

For issues: https://github.com/ys2cody/Huxorb/issues

**Remember**: This is a tool, not a magic money printer. Your discipline and risk management determine success.
