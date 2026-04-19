# HuxORB PRO v2.0 - RuleGuard Enhanced EA

## 📋 Overview

HuxORB PRO v2.0 is a **prop-firm compliant** trading EA with comprehensive rule validation and multi-account support. All trades are validated through a modular **RuleGuard** system that prevents rule violations.

### Key Features

✅ **Modular RuleGuard System** - Pre-trade validation layer
✅ **News Blackout Filter** - Blocks trading during high-impact news
✅ **Session Control** - Trade only in configured sessions
✅ **Advanced Risk Management** - DD limits, lot caps, trade limits
✅ **Multi-Account Support** - Safe per-account configuration without code changes
✅ **Entry Jitter** - Optional delay to avoid identical timing across accounts
✅ **Dry-Run Mode** - Test without placing real trades
✅ **Comprehensive Logging** - Detailed logs with reason codes

---

## 🚀 Quick Start

### 1. Installation

1. Copy all files to MT4 directory:
   ```
   <MT4_DATA_FOLDER>/
   ├── Experts/
   │   └── HuxORB_Bridge_EA_v2.mq4
   ├── Include/
   │   ├── RuleGuard.mqh
   │   ├── NewsFilter.mqh
   │   ├── SessionFilter.mqh
   │   ├── RiskManager.mqh
   │   ├── ConfigProfiles.mqh
   │   └── Utils.mqh
   └── Files/
       ├── news_calendar.csv (optional)
       ├── blackout_windows.csv (optional)
       └── HUX_SIGNAL.csv (created by Python engine)
   ```

2. Compile `HuxORB_Bridge_EA_v2.mq4` in MetaEditor (F7)

3. Attach EA to EURUSD M5 chart

---

## ⚙️ Configuration

### Profile-Based Configuration

The EA supports **3 built-in profiles**:

| Profile | Risk/Trade | Max Lot | Max Open | Jitter | News Filter | Best For |
|---------|------------|---------|----------|--------|-------------|----------|
| **DEFAULT** | 0.5% | 10.0 | 2 | 0-30 sec | Yes | Balanced |
| **CONSERVATIVE** | 0.5% | 5.0 | 1 | 0-60 sec | Yes | Prop firm challenges |
| **AGGRESSIVE** | 1.0% | 20.0 | 3 | 0-15 sec | No | Live funded accounts |

**How to use:**
- Set `ProfileName` input to "DEFAULT", "CONSERVATIVE", or "AGGRESSIVE"
- Profile settings can be overridden by individual input parameters

---

## 📰 News Filter Configuration

The EA supports **TWO modes** for news filtering:

### Mode 1: Manual Blackout Windows (Recommended)

**Advantages:**
- Simple to configure
- No dependencies
- Fully deterministic

**Setup:**
1. Set `UseCSVCalendar = false`
2. Create `blackout_windows.csv` in `/Files/` folder
3. Format:
   ```csv
   StartDateTime,EndDateTime,Currency,Impact
   2026-01-24 14:00:00,2026-01-24 15:30:00,USD,HIGH
   2026-01-27 08:00:00,2026-01-27 09:00:00,EUR,MEDIUM
   ```

**Important:**
- All times in **SERVER TIME** (not UTC!)
- FundedNext server is UTC+2, so:
  - UTC 12:30 = 14:30 server time
  - Always add 2 hours to UTC times

**Example:**
```csv
# NFP (First Friday) - UTC 13:30 = Server 15:30
# Block 13:00-14:30 UTC = 15:00-16:30 server time
2026-02-07 15:00:00,2026-02-07 16:30:00,USD,HIGH
```

---

### Mode 2: CSV Calendar (Optional)

**Advantages:**
- Automatic padding (minutes before/after)
- Currency filtering
- Impact filtering

**Setup:**
1. Set `UseCSVCalendar = true`
2. Create `news_calendar.csv` in `/Files/` folder
3. Format:
   ```csv
   DateTime,Currency,Impact,Title
   2026-01-24 14:30:00,USD,HIGH,FOMC Rate Decision
   2026-01-29 08:30:00,EUR,HIGH,ECB Rate Decision
   ```

**Important:**
- All times in **UTC** (will be converted to server time)
- Currency filtering: EURUSD blocked by EUR or USD events
- Impact filtering: HIGH, MEDIUM, LOW

**Configuration:**
- `NewsMinutesBefore` - Block N minutes before event (default: 30)
- `NewsMinutesAfter` - Block N minutes after event (default: 10)
- `NewsFilterBySymbol` - Only block if event affects symbol (default: true)
- `NewsHighImpactOnly` - Only block HIGH impact events (default: false)

**Calendar Updates:**
- Calendar is reloaded every 10 minutes automatically
- Past events (> 1 hour ago) are automatically filtered out
- Update the CSV file anytime - no need to restart EA

---

## 🕐 Session Configuration

### Built-in Session Presets

**London Session:**
- Time: 07:00-10:00 UTC
- Best for: European currency pairs
- Enable: `TradeLondon = true`

**New York Session:**
- Time: 12:00-16:00 UTC
- Best for: USD currency pairs
- Enable: `TradeNewYork = true`

**Asia Session:**
- Time: 00:00-04:00 UTC
- Best for: JPY, AUD, NZD pairs
- Enable: `TradeAsia = true`

**Server Offset:**
- Set `ServerUtcOffsetHrs` to your broker's UTC offset
- FundedNext: +2
- Most EU brokers: +2 or +3
- US brokers: -5 to -8

**Example Configuration:**
```
TradeLondon = true      // 07:00-10:00 UTC = 09:00-12:00 FundedNext server time
TradeNewYork = true     // 12:00-16:00 UTC = 14:00-18:00 FundedNext server time
TradeAsia = false       // Disabled
ServerUtcOffsetHrs = 2  // FundedNext
```

---

## 🛡️ Risk Management

### Drawdown Limits

**Daily Loss Limit:**
- Default: 4.6% (prop firm safe zone for 5% limit)
- Includes realized + unrealized P&L
- Resets at start of each day
- Action: Blocks new trades for the day

**Max Overall Drawdown:**
- Default: 9.5% (prop firm safe zone for 10% limit)
- Measured from starting balance
- Includes floating losses
- Action: Blocks all trading permanently

**Auto-Close on DD Limit:**
- Set `CloseTradesOnDDLimit = true` to auto-close all trades when limit hit
- **WARNING:** Only use if you understand the implications
- Generally recommended to leave as `false` and manually intervene

---

### Trade Limits

**Max Trades Per Day:**
- Default: 2
- Hard cap enforced by RuleGuard
- Prevents overtrading
- Resets at start of each day

**Max Open Trades:**
- Default: 2
- Prevents excessive exposure
- Counted across all symbols (if using multiple)

**Max Lot Size:**
- Default: 10.0
- Cap on calculated lot size
- Prevents position size errors

---

### Consistency Rule (Prop Firm)

**Profit Cap:**
- Default: 40% of phase target
- Example: If target is $1,000, blocks trading after $400 daily profit
- Prevents "one-day hero" violations
- Set `PhaseTargetAmount` to your challenge target

**How it works:**
1. Calculate daily profit: `CurrentEquity - DailyStartEquity`
2. Calculate cap: `40% × PhaseTarget`
3. If `DailyProfit >= Cap`: Block trading for the day

---

## 👥 Multi-Account Configuration

### Running Multiple Accounts Safely

**Key Principles:**
1. Each account runs on separate MT4 terminal
2. Each account has unique `InstanceID`
3. Each account can use different `ProfileName`
4. Entry jitter prevents identical timing
5. **NO TRADE MIRRORING** - Each account independently validates trades

---

### Configuration Per Account

**Account 1:**
```
ProfileName = "CONSERVATIVE"
InstanceID = 1
AccountGroup = "EURUSD_ACCOUNT1"
EntryDelayJitterSec = 45
```

**Account 2:**
```
ProfileName = "DEFAULT"
InstanceID = 2
AccountGroup = "EURUSD_ACCOUNT2"
EntryDelayJitterSec = 30
```

**Account 3:**
```
ProfileName = "AGGRESSIVE"
InstanceID = 3
AccountGroup = "EURUSD_ACCOUNT3"
EntryDelayJitterSec = 60
```

---

### Entry Jitter Explained

**Purpose:**
- Avoid identical entry times across multiple accounts
- Prop firms may flag simultaneous entries as "trade copying"
- Creates natural variation in entry timing

**How it works:**
1. Signal received at time `T`
2. Jitter calculated: Random(0, EntryDelayJitterSec) based on stable seed
3. Entry delayed until `T + Jitter + BaseDelay`
4. Jitter is **deterministic** per account (same seed = same jitter for same 5-min bar)

**Stable Seed Formula:**
```
Seed = Hash(AccountNumber + InstanceID + ProfileName + CurrentM5BarTime)
```

**Important:**
- Jitter **NEVER increases risk**
- Jitter **NEVER overrides RuleGuard checks**
- If jitter would cause entry during news blackout, trade is blocked
- Each account has different seed → different jitter values

**Recommended Settings:**
- 2-4 accounts: 30-60 seconds jitter
- 5-8 accounts: 45-90 seconds jitter
- More accounts: 60-120 seconds jitter

---

### Signal File Management

Each account needs **separate signal file**:

**Account 1:**
```
SignalFileName = "ACCOUNT1_SIGNAL.csv"
```

**Account 2:**
```
SignalFileName = "ACCOUNT2_SIGNAL.csv"
```

**Python signal generation:**
```bash
python huxorb_pro_engine.py live_signal --csv EURUSD_M5.csv --out ACCOUNT1_SIGNAL.csv
python huxorb_pro_engine.py live_signal --csv EURUSD_M5.csv --out ACCOUNT2_SIGNAL.csv
```

---

## 🧪 Dry-Run Mode

### Testing Without Real Trades

**Purpose:**
- Test EA configuration safely
- Validate RuleGuard blocking logic
- Debug issues before going live

**How to enable:**
```
DryRunMode = true
```

**What happens:**
- EA processes signals normally
- All RuleGuard validations are performed
- **NO real orders are sent**
- Logs show what WOULD have happened
- Alerts show simulated trades

**Example Log Output:**
```
[RULEGUARD][BLOCKED:NEWS_BLACKOUT] NEWS:USD:HIGH (in 15 min)
[MAIN] ✗ Trade BLOCKED: NEWS_BLACKOUT:USD:HIGH (in 15 min)

[RULEGUARD] ✓ All checks passed
[MAIN] [DRY-RUN] Would place order: BUY 0.50 lots @ 1.08500 (SL:1.08350 TP:1.08800)
```

**Testing Checklist:**
1. Enable `DryRunMode = true`
2. Set `PrintStatusOnTick = true` (optional, very verbose)
3. Run for 1 hour during news time
4. Verify news blackout blocks trades
5. Run during non-session time
6. Verify session filter blocks trades
7. Check logs for any unexpected blocks
8. Disable dry-run when satisfied

---

## 📊 Diagnostics & Monitoring

### Status Monitoring

**Print Status Command:**
Add to EA (in OnTick or custom function):
```mql4
if(PrintStatusOnTick)
{
   g_ruleGuard.PrintStatus();
}
```

**Output:**
```
=== RULE GUARD STATUS ===
Mode: LIVE
Trading enabled: YES
In session: YES (London)
News blackout: NO
Current spread: 12 points
Trades today: 1/2
Open trades: 1/2
Daily P&L: $145.50
Daily DD: 0.75%
Max DD: 1.20%
Next news event: 2026-01-24 14:30:00 (in 45 min)
=========================
```

---

### Reason Codes

When a trade is blocked, RuleGuard logs a **reason code**:

| Code | Meaning | Action |
|------|---------|--------|
| `RG_OK` | Trade allowed | Execute |
| `RG_NEWS_BLACKOUT` | News event active | Wait for news to pass |
| `RG_OUTSIDE_SESSION` | Outside trading hours | Wait for session |
| `RG_SPREAD_TOO_HIGH` | Spread exceeds limit | Wait for spread to tighten |
| `RG_DAILY_LOSS_LIMIT` | Daily DD limit hit | Stop trading for the day |
| `RG_MAX_DD` | Max DD limit hit | Stop trading permanently |
| `RG_MAX_TRADES_TODAY` | Trade limit reached | Wait for new day |
| `RG_MAX_OPEN_TRADES` | Too many open trades | Close some trades |
| `RG_LOT_CAP` | Lot size too large | Reduce risk |
| `RG_ENTRY_DELAY_JITTER` | Waiting for jitter delay | Wait a few seconds |
| `RG_DRY_RUN_MODE` | Dry-run mode active | Trade simulated |

---

### Log Interpretation

**Example Log Sequence:**

```
[2026-01-24 14:25:00][MAIN] === PROCESSING SIGNAL ===
[2026-01-24 14:25:00][MAIN] Side: BUY | Entry: 1.08500 | SL: 1.08350 | TP: 1.08800
[2026-01-24 14:25:00][MAIN] Calculated lot size: 0.50
[2026-01-24 14:25:00][RULEGUARD][BLOCKED:NEWS_BLACKOUT] NEWS:USD:HIGH (in 5 min)
[2026-01-24 14:25:00][MAIN] ✗ Trade BLOCKED: NEWS_BLACKOUT:USD:HIGH (in 5 min)

[2026-01-24 14:45:00][MAIN] === PROCESSING SIGNAL ===
[2026-01-24 14:45:00][MAIN] Side: BUY | Entry: 1.08500 | SL: 1.08350 | TP: 1.08800
[2026-01-24 14:45:00][MAIN] Calculated lot size: 0.50
[2026-01-24 14:45:00][MAIN] ✓ All RuleGuard checks passed
[2026-01-24 14:45:00][MAIN] ✓ Trade executed successfully. Ticket: 12345 | Lots: 0.50 | Trades today: 1/2
```

**Interpretation:**
1. First attempt blocked due to news (5 minutes before USD HIGH event)
2. After news passed, signal processed again
3. All checks passed, trade executed

---

## 🔧 Advanced Configuration

### Custom Session Times

Modify `SessionFilter.mqh` to add custom sessions:

```mql4
// Add Frankfurt session (06:00-08:00 UTC)
g_sessionFilter.AddSession("Frankfurt", 6, 0, 8, 0,
                           true, true, true, true, true, true);
```

---

### Custom Risk Profiles

Create custom profile in `ConfigProfiles.mqh`:

```mql4
void LoadCustomProfile()
{
   m_currentProfile.profileName = "CUSTOM";
   m_currentProfile.riskPerTradePct = 0.75;  // Custom risk
   m_currentProfile.maxLotSize = 8.0;
   m_currentProfile.maxOpenTrades = 2;
   // ... more settings
}
```

---

### Per-Symbol Configuration

To run EA on multiple symbols with different settings:

**EURUSD Instance:**
```
ProfileName = "EURUSD_CONSERVATIVE"
MaxSpreadPoints = 15
TradeLondon = true
TradeNewYork = true
```

**GBPUSD Instance:**
```
ProfileName = "GBPUSD_AGGRESSIVE"
MaxSpreadPoints = 25
TradeLondon = true
TradeNewYork = false
```

---

## ⚠️ Important Warnings

### Compliance

✅ **DO:**
- Use different InstanceID for each account
- Use appropriate jitter (30-90 seconds)
- Keep logs for audit purposes
- Test in dry-run mode first

❌ **DON'T:**
- Use same InstanceID across accounts
- Set jitter to 0 on all accounts (looks like copying)
- Disable RuleGuard validations
- Try to "game" the system

---

### Risk Disclosure

**This EA is a tool, not a guarantee:**
- Past performance ≠ future results
- RuleGuard prevents violations but doesn't guarantee profits
- News filters reduce risk but can't eliminate it
- Always monitor your accounts
- Prop firms can change rules - stay updated

**Test everything:**
- Run in dry-run mode first
- Test news blocking during actual news
- Test session filters outside sessions
- Verify DD limits trigger correctly
- Monitor for at least 1 week before trusting fully

---

## 📞 Troubleshooting

### Common Issues

**Issue: Trades not executing**
- Check: `DryRunMode = false`
- Check: In trading session (use PrintStatus)
- Check: Not in news blackout
- Check: DD limits not hit
- Check: Spread not too high

**Issue: News filter not blocking**
- Check: `NewsFilterEnabled = true`
- Check: CSV file exists in `/Files/` folder
- Check: Times are correct (UTC vs Server time!)
- Check: Currency matches symbol

**Issue: Session filter blocking when it shouldn't**
- Check: `ServerUtcOffsetHrs` is correct
- Check: Session enabled (`TradeLondon = true`, etc.)
- Check: Current time is actually in session (use PrintStatus)

**Issue: All accounts entering at same time**
- Check: `EntryDelayJitterSec > 0`
- Check: Different `InstanceID` per account
- Check: Logs show different jitter values

---

## 📁 File Structure

```
MT4_DATA_FOLDER/
├── Experts/
│   └── HuxORB_Bridge_EA_v2.mq4          # Main EA
├── Include/
│   ├── RuleGuard.mqh                     # Core validation
│   ├── NewsFilter.mqh                    # News blackout
│   ├── SessionFilter.mqh                 # Session control
│   ├── RiskManager.mqh                   # Risk management
│   ├── ConfigProfiles.mqh                # Multi-account profiles
│   └── Utils.mqh                         # Helper functions
└── Files/
    ├── news_calendar.csv                 # CSV calendar (optional)
    ├── blackout_windows.csv              # Manual blackout (optional)
    ├── HUX_SIGNAL.csv                    # Signal from Python engine
    ├── ACCOUNT1_SIGNAL.csv               # Signal for account 1
    ├── ACCOUNT2_SIGNAL.csv               # Signal for account 2
    └── ...
```

---

## 🚀 Deployment Checklist

**Before Going Live:**

- [ ] Test in dry-run mode for 1 week
- [ ] Verify news filter blocks during actual news
- [ ] Verify session filter works correctly
- [ ] Test DD limits (manually adjust equity in demo)
- [ ] Confirm jitter creates different entry times across accounts
- [ ] Review all logs for unexpected blocks
- [ ] Verify spread filter catches high spreads
- [ ] Test signal file processing
- [ ] Configure correct broker offset
- [ ] Set appropriate risk per trade
- [ ] Set correct phase target amount
- [ ] Update news calendar (if using CSV mode)
- [ ] Backup all configuration files

**After Going Live:**

- [ ] Monitor logs daily
- [ ] Check for any RuleGuard blocks
- [ ] Verify trades are within prop firm rules
- [ ] Update news calendar weekly (if using CSV)
- [ ] Review DD levels daily
- [ ] Check consistency rule hasn't triggered unexpectedly

---

## 📄 License & Support

**Copyright:** HuxORB Team
**License:** Proprietary - For use with HuxORB PRO system only
**Support:** https://github.com/ys2cody/Huxorb/issues

---

## 📚 Version History

**v2.0.0 (Current)**
- Added RuleGuard validation layer
- Added NewsFilter (manual + CSV modes)
- Added enhanced SessionFilter
- Added multi-account support with jitter
- Added dry-run mode
- Added comprehensive diagnostics

**v1.0.0**
- Initial release
- Basic session and DD limits
- Signal file execution

---

**Built for compliance. Designed for success. Trade safely.** 🚀
