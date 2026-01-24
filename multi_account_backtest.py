#!/usr/bin/env python3
"""
HuxORB PRO v2.0 - Multi-Account Backtest Simulator
===================================================
Simulates RuleGuard logic and tests 8 different account configurations.

This script demonstrates:
- Multi-account operation with different profiles
- Entry jitter creating different entry times
- RuleGuard validation (session, risk, trade limits)
- Profile-based parameter variation
- Compliance with prop firm rules
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import hashlib
from pathlib import Path

# Import from existing engine
import sys
sys.path.append('.')
from huxorb_pro_engine import (
    load_data, calculate_atr, identify_swing_highs_lows,
    detect_regime, detect_liquidity_sweep, detect_bos,
    detect_displacement_and_fvg, simulate_trade_outcome
)

# ============================================================================
# ACCOUNT PROFILES
# ============================================================================

PROFILES = {
    'DEFAULT': {
        'risk_per_trade': 0.5,
        'max_lot': 10.0,
        'max_open': 2,
        'max_per_day': 2,
        'jitter_sec': 30,
        'base_delay_sec': 0,
        'london': True,
        'newyork': True,
        'asia': False,
    },
    'CONSERVATIVE': {
        'risk_per_trade': 0.5,
        'max_lot': 5.0,
        'max_open': 1,
        'max_per_day': 2,
        'jitter_sec': 60,
        'base_delay_sec': 10,
        'london': True,
        'newyork': True,
        'asia': False,
    },
    'AGGRESSIVE': {
        'risk_per_trade': 1.0,
        'max_lot': 20.0,
        'max_open': 3,
        'max_per_day': 3,
        'jitter_sec': 15,
        'base_delay_sec': 0,
        'london': True,
        'newyork': True,
        'asia': True,
    }
}

# ============================================================================
# ACCOUNT CONFIGURATIONS
# ============================================================================

ACCOUNTS = [
    {'id': 1, 'name': 'Account_1', 'profile': 'CONSERVATIVE', 'account_num': 10001, 'group': 'EURUSD_MAIN'},
    {'id': 2, 'name': 'Account_2', 'profile': 'DEFAULT', 'account_num': 10002, 'group': 'EURUSD_MAIN'},
    {'id': 3, 'name': 'Account_3', 'profile': 'DEFAULT', 'account_num': 10003, 'group': 'EURUSD_MAIN'},
    {'id': 4, 'name': 'Account_4', 'profile': 'CONSERVATIVE', 'account_num': 10004, 'group': 'EURUSD_BACKUP'},
    {'id': 5, 'name': 'Account_5', 'profile': 'AGGRESSIVE', 'account_num': 10005, 'group': 'EURUSD_MAIN'},
    {'id': 6, 'name': 'Account_6', 'profile': 'DEFAULT', 'account_num': 10006, 'group': 'EURUSD_MAIN'},
    {'id': 7, 'name': 'Account_7', 'profile': 'CONSERVATIVE', 'account_num': 10007, 'group': 'EURUSD_BACKUP'},
    {'id': 8, 'name': 'Account_8', 'profile': 'AGGRESSIVE', 'account_num': 10008, 'group': 'EURUSD_MAIN'},
]

# ============================================================================
# RULEGUARD SIMULATION
# ============================================================================

def generate_account_seed(account_num, instance_id, profile_name):
    """Generate stable seed from account info (mimics MQL4 logic)."""
    seed_str = f"{account_num}_{instance_id}_{profile_name}"
    hash_obj = hashlib.md5(seed_str.encode())
    return int(hash_obj.hexdigest()[:8], 16) % 2147483647

def calculate_jitter(account_seed, bar_time, max_jitter_sec):
    """Calculate stable jitter for this account and bar time."""
    if max_jitter_sec == 0:
        return 0

    # Combine account seed with bar time for variation
    time_component = int(bar_time.timestamp()) % 1000
    combined_seed = (account_seed + time_component) % 2147483647

    # Simple LCG (matches MQL4 implementation)
    a = 1103515245
    c = 12345
    m = 2147483647

    random_val = (a * combined_seed + c) % m
    jitter = abs(random_val) % (max_jitter_sec + 1)

    return jitter

def is_in_session(bar_time, london=True, newyork=True, asia=False):
    """Check if time is in trading session (UTC)."""
    hour = bar_time.hour

    # Session times (UTC)
    if london and (7 <= hour < 10):
        return True, "London"
    if newyork and (12 <= hour < 16):
        return True, "NewYork"
    if asia and (0 <= hour < 4):
        return True, "Asia"

    return False, "NONE"

class AccountSimulator:
    """Simulates one account with RuleGuard logic."""

    def __init__(self, account_config):
        self.config = account_config
        self.profile = PROFILES[account_config['profile']]
        self.account_num = account_config['account_num']
        self.instance_id = account_config['id']
        self.name = account_config['name']

        # Generate stable seed
        self.seed = generate_account_seed(
            self.account_num,
            self.instance_id,
            self.config['profile']
        )

        # State tracking
        self.balance = 10000
        self.equity = 10000
        self.starting_balance = 10000
        self.daily_start_equity = 10000
        self.trades_today = 0
        self.open_trades = 0
        self.current_day = None
        self.trades = []
        self.equity_curve = [{'time': None, 'equity': 10000, 'balance': 10000}]
        self.blocked_reasons = []

    def check_new_day(self, current_date):
        """Reset daily counters on new day."""
        if current_date != self.current_day:
            self.current_day = current_date
            self.trades_today = 0
            self.daily_start_equity = self.equity

    def can_open_trade(self, bar_time, reason_out):
        """RuleGuard validation (simplified for backtest)."""

        # Check session
        in_session, session_name = is_in_session(
            bar_time,
            self.profile['london'],
            self.profile['newyork'],
            self.profile['asia']
        )
        if not in_session:
            reason_out.append(f"RG_OUTSIDE_SESSION:{session_name}")
            return False

        # Check max trades per day
        if self.trades_today >= self.profile['max_per_day']:
            reason_out.append(f"RG_MAX_TRADES_TODAY:{self.trades_today}/{self.profile['max_per_day']}")
            return False

        # Check max open trades
        if self.open_trades >= self.profile['max_open']:
            reason_out.append(f"RG_MAX_OPEN_TRADES:{self.open_trades}/{self.profile['max_open']}")
            return False

        # Check daily DD (simplified - just check if < 4.6%)
        daily_dd = ((self.daily_start_equity - self.equity) / self.daily_start_equity) * 100
        if daily_dd >= 4.6:
            reason_out.append(f"RG_DAILY_DD:{daily_dd:.2f}%")
            return False

        # Check max DD
        max_dd = ((self.starting_balance - self.equity) / self.starting_balance) * 100
        if max_dd >= 9.5:
            reason_out.append(f"RG_MAX_DD:{max_dd:.2f}%")
            return False

        return True

    def calculate_entry_time_with_jitter(self, signal_time):
        """Calculate actual entry time with jitter."""
        bar_time = signal_time.replace(second=0, microsecond=0)
        jitter_sec = calculate_jitter(self.seed, bar_time, self.profile['jitter_sec'])
        base_delay = self.profile['base_delay_sec']
        total_delay = jitter_sec + base_delay

        entry_time = signal_time + timedelta(seconds=total_delay)

        return entry_time, jitter_sec

    def execute_signal(self, signal, signal_time, df, signal_idx):
        """Execute signal with RuleGuard validation."""

        # Calculate entry time with jitter
        entry_time, jitter = self.calculate_entry_time_with_jitter(signal_time)

        # Check RuleGuard
        block_reasons = []
        if not self.can_open_trade(entry_time, block_reasons):
            self.blocked_reasons.append({
                'time': signal_time,
                'entry_time': entry_time,
                'jitter': jitter,
                'reasons': block_reasons
            })
            return None

        # Simulate trade outcome
        outcome, exit_price, exit_time, bars_held = simulate_trade_outcome(signal, df, signal_idx)

        # Calculate P&L
        if outcome == 'WIN':
            r_multiple = 2.0
        elif outcome == 'LOSS':
            r_multiple = -1.0
        else:
            r_multiple = 0.0

        risk_amount = self.balance * (self.profile['risk_per_trade'] / 100)
        pnl = risk_amount * r_multiple
        self.balance += pnl
        self.equity = self.balance

        # Record trade
        trade = {
            'account': self.name,
            'trade_num': len(self.trades) + 1,
            'signal_time': signal_time,
            'entry_time': entry_time,
            'jitter_sec': jitter,
            'exit_time': exit_time,
            'side': signal['side'],
            'entry': signal['entry'],
            'sl': signal['sl'],
            'tp': signal['tp'],
            'exit': exit_price,
            'outcome': outcome,
            'r_multiple': r_multiple,
            'risk_amount': risk_amount,
            'pnl': pnl,
            'balance': self.balance,
            'bars_held': bars_held
        }

        self.trades.append(trade)
        self.trades_today += 1
        self.equity_curve.append({'time': exit_time, 'equity': self.equity, 'balance': self.balance})

        return trade

# ============================================================================
# MULTI-ACCOUNT BACKTEST
# ============================================================================

def run_multi_account_backtest(df, symbol="EURUSD"):
    """Run backtest across 8 accounts with different configurations."""

    print("="*80)
    print("HuxORB PRO v2.0 - Multi-Account Backtest Simulator")
    print("="*80)
    print(f"Data: {df['time'].min()} to {df['time'].max()}")
    print(f"Bars: {len(df)}")
    print(f"Accounts: {len(ACCOUNTS)}")
    print("="*80)
    print()

    # Prepare data
    df = df.copy()
    df['atr'] = calculate_atr(df)
    df = identify_swing_highs_lows(df)

    # Create account simulators
    accounts = [AccountSimulator(config) for config in ACCOUNTS]

    # Print account configurations
    print("=== ACCOUNT CONFIGURATIONS ===")
    for acc in accounts:
        print(f"{acc.name}:")
        print(f"  Profile: {acc.config['profile']}")
        print(f"  Account#: {acc.account_num}")
        print(f"  Instance ID: {acc.instance_id}")
        print(f"  Seed: {acc.seed}")
        print(f"  Risk/Trade: {acc.profile['risk_per_trade']}%")
        print(f"  Max Lot: {acc.profile['max_lot']}")
        print(f"  Max Trades/Day: {acc.profile['max_per_day']}")
        print(f"  Jitter: 0-{acc.profile['jitter_sec']} sec")
        print(f"  Sessions: L:{acc.profile['london']} NY:{acc.profile['newyork']} A:{acc.profile['asia']}")
        print()

    print("="*80)
    print("STARTING BACKTEST...")
    print("="*80)
    print()

    # Collect all signals first (same for all accounts)
    signals = []
    for i in range(50, len(df)):
        current_date = df.iloc[i]['time'].date()

        # Generate signal (same logic as original engine)
        signal = generate_signal_simple(df, i, symbol)
        if signal:
            signals.append({'idx': i, 'signal': signal, 'time': df.iloc[i]['time']})

    print(f"Generated {len(signals)} signals from strategy")
    print()

    # Process each signal for each account
    for sig_data in signals:
        signal_idx = sig_data['idx']
        signal = sig_data['signal']
        signal_time = sig_data['time']
        current_date = signal_time.date()

        # Update all accounts for new day
        for acc in accounts:
            acc.check_new_day(current_date)

        # Each account independently evaluates the signal
        for acc in accounts:
            acc.execute_signal(signal, signal_time, df, signal_idx)

    return accounts

def generate_signal_simple(df, i, symbol):
    """Simplified signal generation (uses existing engine logic)."""
    from huxorb_pro_engine import generate_signal, MAX_SPREAD_EURUSD
    return generate_signal(df, i, symbol, MAX_SPREAD_EURUSD)

# ============================================================================
# RESULTS ANALYSIS
# ============================================================================

def analyze_results(accounts):
    """Analyze and print results for all accounts."""

    print("\n" + "="*80)
    print("BACKTEST RESULTS")
    print("="*80)
    print()

    summary = []

    for acc in accounts:
        if len(acc.trades) == 0:
            print(f"### {acc.name} ({acc.config['profile']}) ###")
            print("No trades executed")
            print()
            continue

        trades_df = pd.DataFrame(acc.trades)

        total = len(trades_df)
        wins = len(trades_df[trades_df['outcome'] == 'WIN'])
        losses = len(trades_df[trades_df['outcome'] == 'LOSS'])
        win_rate = (wins / total * 100) if total > 0 else 0

        avg_r = trades_df['r_multiple'].mean()
        net_pnl = trades_df['pnl'].sum()
        roi = (net_pnl / 10000) * 100

        max_equity = acc.equity
        min_equity = min([ec['equity'] for ec in acc.equity_curve])
        max_dd = ((max_equity - min_equity) / max_equity) * 100

        avg_jitter = trades_df['jitter_sec'].mean()

        summary.append({
            'Account': acc.name,
            'Profile': acc.config['profile'],
            'Seed': acc.seed,
            'Trades': total,
            'Wins': wins,
            'Losses': losses,
            'WinRate': win_rate,
            'AvgR': avg_r,
            'NetPnL': net_pnl,
            'ROI': roi,
            'MaxDD': max_dd,
            'AvgJitter': avg_jitter,
            'Blocked': len(acc.blocked_reasons)
        })

        print(f"### {acc.name} ({acc.config['profile']}) ###")
        print(f"Seed: {acc.seed}")
        print(f"Trades: {total} ({wins}W / {losses}L)")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Expectancy: {avg_r:.3f} R")
        print(f"Net P&L: ${net_pnl:.2f}")
        print(f"ROI: {roi:.2f}%")
        print(f"Max DD: {max_dd:.2f}%")
        print(f"Avg Jitter: {avg_jitter:.1f} sec")
        print(f"Blocked Signals: {len(acc.blocked_reasons)}")
        print()

    # Summary table
    print("="*80)
    print("SUMMARY COMPARISON")
    print("="*80)

    summary_df = pd.DataFrame(summary)
    print(summary_df.to_string(index=False))
    print()

    # Entry time analysis
    print("="*80)
    print("ENTRY TIME JITTER ANALYSIS (First 5 Trades)")
    print("="*80)
    print()

    # Show first 5 trades from all accounts to demonstrate jitter
    all_trades = []
    for acc in accounts:
        if len(acc.trades) >= 5:
            all_trades.extend(acc.trades[:5])

    if all_trades:
        trades_df = pd.DataFrame(all_trades)
        trades_df = trades_df.sort_values('signal_time')

        for _, trade in trades_df.head(20).iterrows():
            delay = (trade['entry_time'] - trade['signal_time']).total_seconds()
            print(f"{trade['account']:12} | Signal: {trade['signal_time']} | "
                  f"Entry: {trade['entry_time']} | Jitter: {trade['jitter_sec']:2.0f}s | "
                  f"Total Delay: {delay:.0f}s")

    print()

    return summary_df

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Load data
    print("Loading EURUSD M5 2025 data...")
    df = load_data("EURUSD_M5_2025.csv")

    # Run multi-account backtest
    accounts = run_multi_account_backtest(df, symbol="EURUSD")

    # Analyze results
    summary_df = analyze_results(accounts)

    # Save results
    output_dir = Path("results_multi_account")
    output_dir.mkdir(exist_ok=True)

    # Save summary
    summary_df.to_csv(output_dir / "summary.csv", index=False)
    print(f"Summary saved to {output_dir}/summary.csv")

    # Save individual account trades
    for acc in accounts:
        if len(acc.trades) > 0:
            trades_df = pd.DataFrame(acc.trades)
            trades_df.to_csv(output_dir / f"{acc.name}_trades.csv", index=False)
            print(f"{acc.name} trades saved to {output_dir}/{acc.name}_trades.csv")

    print()
    print("="*80)
    print("MULTI-ACCOUNT BACKTEST COMPLETE")
    print("="*80)
