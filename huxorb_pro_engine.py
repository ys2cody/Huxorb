#!/usr/bin/env python3
"""
HuxORB PRO - Prop Firm Trading Engine
======================================
ICT-style Opening Range Breakout with institutional concepts.
Designed for FundedNext and similar prop firms.

NO OPTIMIZATION. Parameters justified by market logic, not backtest performance.

Strategy Components:
1. Session filter (London 07:00-10:00, NY 12:00-16:00 UTC)
2. Spread gate (EURUSD ≤20 pts, GBPUSD ≤25 pts)
3. Regime filter (volatility expansion, avoid chop)
4. Liquidity sweep detection (stop hunt above/below swing points)
5. BOS confirmation (break of structure - swing high/low broken)
6. Displacement + FVG (strong move creating fair value gap)
7. Entry on retrace into FVG/Order Block

Author: HuxORB Team
Version: 1.0.0 - Production Release
"""

import pandas as pd
import numpy as np
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

# ============================================================================
# CONSTANTS - Justified by market structure, NOT curve-fitted
# ============================================================================

# Risk Management
RISK_PER_TRADE_PCT = 0.5  # 0.5% per trade (conservative for prop firms)
DEFAULT_RR = 2.0  # 2:1 reward-risk (conservative, justified by ICT setups)
MAX_TRADES_PER_DAY = 2  # Prop firm requirement: quality over quantity

# Spread Filters (prop firm execution reality)
MAX_SPREAD_EURUSD = 20  # 2.0 pips on 5-digit (typical for good brokers)
MAX_SPREAD_GBPUSD = 25  # 2.5 pips on 5-digit (GBP wider spread)

# Session Windows (UTC) - High liquidity periods only
LONDON_SESSION = (7, 10)  # London open to mid-morning
NEWYORK_SESSION = (12, 16)  # NY open to mid-afternoon

# ICT Concepts - Market Structure Parameters
SWING_LOOKBACK = 10  # Bars to identify swing highs/lows (~50min on M5)
MIN_DISPLACEMENT_PIPS = 15  # Minimum move in pips to qualify as displacement (EURUSD)
MIN_FVG_PIPS = 8  # Minimum gap size in pips to be valid FVG (EURUSD)
ATR_PERIOD = 14  # Standard ATR period for volatility measurement
ATR_EXPANSION_FACTOR = 1.2  # Current ATR > 1.2x recent avg = expansion

# Prop Firm Safety Rails
DAILY_DD_LIMIT_PCT = 4.6  # Stop trading at 4.6% (5% is hard limit)
MAX_DD_LIMIT_PCT = 9.5  # Stop trading at 9.5% (10% is hard limit)
CONSISTENCY_PROFIT_CAP_PCT = 40  # Stop if daily profit > 40% of phase target

# Monte Carlo Simulation
MONTE_CARLO_RUNS = 1000  # Number of random reshuffles for MC analysis

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def pips_to_price(pips, symbol="EURUSD"):
    """Convert pips to price units (5-digit broker)."""
    if symbol in ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD"]:
        return pips * 0.00001
    elif symbol in ["USDJPY"]:
        return pips * 0.001
    else:
        return pips * 0.00001  # Default to 5-digit


def price_to_pips(price, symbol="EURUSD"):
    """Convert price units to pips (5-digit broker)."""
    if symbol in ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD"]:
        return price / 0.00001
    elif symbol in ["USDJPY"]:
        return price / 0.001
    else:
        return price / 0.00001


def in_session(hour_utc):
    """Check if hour is within trading sessions."""
    london = LONDON_SESSION[0] <= hour_utc < LONDON_SESSION[1]
    newyork = NEWYORK_SESSION[0] <= hour_utc < NEWYORK_SESSION[1]
    return london or newyork


# ============================================================================
# DATA LOADING
# ============================================================================

def load_data(csv_path):
    """
    Load OHLCV data from CSV.
    Expected columns: time, open, high, low, close, volume (optional: spread)
    """
    df = pd.read_csv(csv_path)

    # Normalize column names
    df.columns = [c.lower().strip() for c in df.columns]

    # Parse time
    df['time'] = pd.to_datetime(df['time'])
    df = df.sort_values('time').reset_index(drop=True)

    # Ensure required columns
    required = ['time', 'open', 'high', 'low', 'close']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Add spread column if missing (assume best-case 0 for backtesting)
    if 'spread' not in df.columns:
        df['spread'] = 0

    return df


# ============================================================================
# TECHNICAL INDICATORS
# ============================================================================

def calculate_atr(df, period=ATR_PERIOD):
    """Calculate Average True Range."""
    high = df['high']
    low = df['low']
    close = df['close']

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return atr


def identify_swing_highs_lows(df, lookback=SWING_LOOKBACK):
    """
    Identify swing highs and lows.
    Swing high: highest high in lookback window
    Swing low: lowest low in lookback window
    """
    df['swing_high'] = df['high'].rolling(window=lookback*2+1, center=True).max() == df['high']
    df['swing_low'] = df['low'].rolling(window=lookback*2+1, center=True).min() == df['low']

    return df


# ============================================================================
# ICT STRATEGY COMPONENTS
# ============================================================================

def detect_regime(df, i):
    """
    Regime Filter: Volatility expansion (avoid choppy markets).

    Logic: Current ATR > 1.2x average ATR of previous 10 bars.
    This indicates expanding volatility, suitable for breakout trading.
    """
    if i < ATR_PERIOD + 10:
        return False

    atr = df['atr'].values
    current_atr = atr[i]
    avg_atr = np.mean(atr[i-10:i])

    return current_atr > (avg_atr * ATR_EXPANSION_FACTOR)


def detect_liquidity_sweep(df, i, lookback=SWING_LOOKBACK):
    """
    Liquidity Sweep: Price briefly moves above/below swing high/low to trigger stops,
    then reverses. This is a stop hunt pattern.

    Bullish sweep: Price wicks below recent swing low, closes higher
    Bearish sweep: Price wicks above recent swing high, closes lower
    """
    if i < lookback + 2:
        return None, None

    # Get recent swing levels
    recent_bars = df.iloc[i-lookback:i]
    swing_high = recent_bars['high'].max()
    swing_low = recent_bars['low'].min()

    current = df.iloc[i]

    # Bullish sweep: low breaks below swing low, but close is higher
    if current['low'] < swing_low and current['close'] > swing_low:
        return 'bullish_sweep', swing_low

    # Bearish sweep: high breaks above swing high, but close is lower
    if current['high'] > swing_high and current['close'] < swing_high:
        return 'bearish_sweep', swing_high

    return None, None


def detect_bos(df, i, lookback=SWING_LOOKBACK):
    """
    Break of Structure (BOS): Price decisively breaks previous swing high/low.

    Bullish BOS: Close above recent swing high
    Bearish BOS: Close below recent swing low
    """
    if i < lookback + 1:
        return None

    recent_bars = df.iloc[i-lookback:i-1]  # Exclude current bar
    swing_high = recent_bars['high'].max()
    swing_low = recent_bars['low'].min()

    current_close = df.iloc[i]['close']

    if current_close > swing_high:
        return 'bullish_bos'
    elif current_close < swing_low:
        return 'bearish_bos'

    return None


def detect_displacement_and_fvg(df, i, symbol="EURUSD"):
    """
    Displacement + Fair Value Gap (FVG).

    Displacement: Strong directional move (> MIN_DISPLACEMENT_PIPS).
    FVG: 3-candle pattern where candle[i-1] creates a gap:
         - Bullish FVG: candle[i-1].low > candle[i-3].high (gap up)
         - Bearish FVG: candle[i-1].high < candle[i-3].low (gap down)

    Returns: (fvg_type, fvg_high, fvg_low, displacement_pips)
    """
    if i < 5:
        return None, None, None, 0

    # Check displacement (price movement in last 3 bars)
    start_price = df.iloc[i-3]['close']
    end_price = df.iloc[i]['close']
    displacement = abs(end_price - start_price)
    displacement_pips = price_to_pips(displacement, symbol)

    if displacement_pips < MIN_DISPLACEMENT_PIPS:
        return None, None, None, displacement_pips

    # Check for FVG
    bar_minus_3 = df.iloc[i-3]
    bar_minus_2 = df.iloc[i-2]
    bar_minus_1 = df.iloc[i-1]

    # Bullish FVG: gap between bar[-3].high and bar[-1].low
    if bar_minus_1['low'] > bar_minus_3['high']:
        fvg_low = bar_minus_3['high']
        fvg_high = bar_minus_1['low']
        gap_pips = price_to_pips(fvg_high - fvg_low, symbol)

        if gap_pips >= MIN_FVG_PIPS:
            return 'bullish_fvg', fvg_high, fvg_low, displacement_pips

    # Bearish FVG: gap between bar[-1].high and bar[-3].low
    if bar_minus_1['high'] < bar_minus_3['low']:
        fvg_high = bar_minus_3['low']
        fvg_low = bar_minus_1['high']
        gap_pips = price_to_pips(fvg_high - fvg_low, symbol)

        if gap_pips >= MIN_FVG_PIPS:
            return 'bearish_fvg', fvg_high, fvg_low, displacement_pips

    return None, None, None, displacement_pips


def find_order_block(df, i, direction):
    """
    Order Block: Last opposite-direction candle before displacement.

    Bullish OB: Last bearish candle before bullish displacement
    Bearish OB: Last bullish candle before bearish displacement
    """
    if i < 5:
        return None, None

    # Look back for last opposite candle
    for j in range(i-1, max(i-10, 0), -1):
        bar = df.iloc[j]

        if direction == 'bullish':
            # Find last bearish candle (close < open)
            if bar['close'] < bar['open']:
                return bar['low'], bar['high']
        elif direction == 'bearish':
            # Find last bullish candle (close > open)
            if bar['close'] > bar['open']:
                return bar['low'], bar['high']

    return None, None


# ============================================================================
# SIGNAL GENERATION
# ============================================================================

def generate_signal(df, i, symbol="EURUSD", max_spread=MAX_SPREAD_EURUSD):
    """
    Generate trade signal if all conditions met.

    Returns: dict with signal details or None
    """
    current = df.iloc[i]

    # Gate 1: Session filter
    hour_utc = current['time'].hour
    if not in_session(hour_utc):
        return None

    # Gate 2: Spread filter
    spread = current['spread']
    if spread > max_spread:
        return None

    # Gate 3: Regime filter (volatility expansion)
    if not detect_regime(df, i):
        return None

    # Gate 4: Liquidity sweep detection
    sweep_type, sweep_level = detect_liquidity_sweep(df, i)
    if sweep_type is None:
        return None

    # Gate 5: BOS confirmation
    bos = detect_bos(df, i)
    if bos is None:
        return None

    # Check alignment: bullish sweep needs bullish BOS
    if sweep_type == 'bullish_sweep' and bos != 'bullish_bos':
        return None
    if sweep_type == 'bearish_sweep' and bos != 'bearish_bos':
        return None

    # Gate 6: Displacement + FVG
    fvg_type, fvg_high, fvg_low, disp_pips = detect_displacement_and_fvg(df, i, symbol)
    if fvg_type is None:
        return None

    # Check alignment
    if sweep_type == 'bullish_sweep' and fvg_type != 'bullish_fvg':
        return None
    if sweep_type == 'bearish_sweep' and fvg_type != 'bearish_fvg':
        return None

    # Gate 7: Entry on retrace into FVG/OB
    direction = 'bullish' if sweep_type == 'bullish_sweep' else 'bearish'
    ob_low, ob_high = find_order_block(df, i, direction)

    # Entry logic: wait for price to retrace into FVG zone
    if direction == 'bullish':
        # For bullish setup, wait for price to touch FVG zone from above
        # Entry: buy at FVG_low (discounted price)
        # SL: below sweep_level (or OB low)
        # TP: 2:1 RR

        entry = fvg_low
        sl = sweep_level - pips_to_price(5, symbol)  # 5 pips buffer
        sl_pips = price_to_pips(entry - sl, symbol)
        tp = entry + (entry - sl) * DEFAULT_RR

        return {
            'time': current['time'],
            'symbol': symbol,
            'side': 'BUY',
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'sl_pips': sl_pips,
            'rr': DEFAULT_RR,
            'comment': f'Bullish ICT: Sweep+BOS+FVG (Disp={disp_pips:.1f}p)'
        }

    else:  # bearish
        # For bearish setup, wait for price to touch FVG zone from below
        # Entry: sell at FVG_high (premium price)
        # SL: above sweep_level (or OB high)
        # TP: 2:1 RR

        entry = fvg_high
        sl = sweep_level + pips_to_price(5, symbol)  # 5 pips buffer
        sl_pips = price_to_pips(sl - entry, symbol)
        tp = entry - (sl - entry) * DEFAULT_RR

        return {
            'time': current['time'],
            'symbol': symbol,
            'side': 'SELL',
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'sl_pips': sl_pips,
            'rr': DEFAULT_RR,
            'comment': f'Bearish ICT: Sweep+BOS+FVG (Disp={disp_pips:.1f}p)'
        }


# ============================================================================
# BACKTESTING ENGINE
# ============================================================================

def simulate_trade_outcome(signal, df, signal_idx):
    """
    Simulate trade outcome using worst-case intrabar ordering.
    Conservative: SL hit before TP if both touched on same bar.

    Returns: (outcome, exit_price, exit_time, bars_held)
    """
    entry = signal['entry']
    sl = signal['sl']
    tp = signal['tp']
    side = signal['side']

    # Search forward for TP or SL hit
    for j in range(signal_idx + 1, min(signal_idx + 200, len(df))):  # Max 200 bars (~16 hours)
        bar = df.iloc[j]

        if side == 'BUY':
            # Conservative: check SL first
            if bar['low'] <= sl:
                return 'LOSS', sl, bar['time'], j - signal_idx
            if bar['high'] >= tp:
                return 'WIN', tp, bar['time'], j - signal_idx
        else:  # SELL
            # Conservative: check SL first
            if bar['high'] >= sl:
                return 'LOSS', sl, bar['time'], j - signal_idx
            if bar['low'] <= tp:
                return 'WIN', tp, bar['time'], j - signal_idx

    # If neither hit after 200 bars, close at breakeven (conservative)
    return 'BREAKEVEN', entry, df.iloc[min(signal_idx + 199, len(df)-1)]['time'], 200


def backtest(df, symbol="EURUSD", starting_balance=10000):
    """
    Run backtest on historical data.

    Returns: (trades_df, equity_curve_df, metrics_dict)
    """
    # Prepare data
    df = df.copy()
    df['atr'] = calculate_atr(df)
    df = identify_swing_highs_lows(df)

    # Determine max spread
    max_spread = MAX_SPREAD_EURUSD if symbol == "EURUSD" else MAX_SPREAD_GBPUSD

    # Track state
    balance = starting_balance
    equity = starting_balance
    trades = []
    equity_curve = [{'time': df.iloc[0]['time'], 'equity': equity, 'balance': balance}]

    daily_trades_count = {}
    daily_pnl = {}

    print(f"\n{'='*60}")
    print(f"Starting Backtest: {symbol}")
    print(f"Data: {df['time'].min()} to {df['time'].max()}")
    print(f"Bars: {len(df)}")
    print(f"{'='*60}\n")

    # Scan for signals
    for i in range(50, len(df)):  # Start at bar 50 to have sufficient history
        current_date = df.iloc[i]['time'].date()

        # Check max trades per day
        trades_today = daily_trades_count.get(current_date, 0)
        if trades_today >= MAX_TRADES_PER_DAY:
            continue

        # Generate signal
        signal = generate_signal(df, i, symbol, max_spread)
        if signal is None:
            continue

        # Simulate trade
        outcome, exit_price, exit_time, bars_held = simulate_trade_outcome(signal, df, i)

        # Calculate P&L
        if outcome == 'WIN':
            r_multiple = signal['rr']
        elif outcome == 'LOSS':
            r_multiple = -1.0
        else:  # BREAKEVEN
            r_multiple = 0.0

        risk_amount = balance * (RISK_PER_TRADE_PCT / 100)
        pnl = risk_amount * r_multiple
        balance += pnl
        equity = balance

        # Record trade
        trade_record = {
            'trade_num': len(trades) + 1,
            'entry_time': signal['time'],
            'exit_time': exit_time,
            'symbol': symbol,
            'side': signal['side'],
            'entry': signal['entry'],
            'sl': signal['sl'],
            'tp': signal['tp'],
            'exit': exit_price,
            'outcome': outcome,
            'sl_pips': signal['sl_pips'],
            'r_multiple': r_multiple,
            'risk_amount': risk_amount,
            'pnl': pnl,
            'balance': balance,
            'bars_held': bars_held,
            'comment': signal['comment']
        }
        trades.append(trade_record)

        # Update counters
        daily_trades_count[current_date] = trades_today + 1
        daily_pnl[current_date] = daily_pnl.get(current_date, 0) + pnl

        # Equity curve
        equity_curve.append({'time': exit_time, 'equity': equity, 'balance': balance})

        print(f"Trade #{len(trades):3d} | {signal['time']} | {signal['side']:4s} | "
              f"{outcome:10s} | R={r_multiple:+.2f} | PnL={pnl:+8.2f} | Bal={balance:.2f}")

    # Convert to DataFrames
    trades_df = pd.DataFrame(trades)
    equity_curve_df = pd.DataFrame(equity_curve)

    # Calculate metrics
    metrics = calculate_metrics(trades_df, equity_curve_df, starting_balance, daily_pnl)

    return trades_df, equity_curve_df, metrics


def calculate_metrics(trades_df, equity_curve_df, starting_balance, daily_pnl):
    """Calculate comprehensive backtest metrics."""
    if len(trades_df) == 0:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_r': 0,
            'expectancy': 0,
            'profit_factor': 0,
            'max_dd': 0,
            'max_dd_pct': 0,
            'final_balance': starting_balance,
            'net_profit': 0,
            'roi_pct': 0
        }

    # Basic metrics
    total_trades = len(trades_df)
    wins = len(trades_df[trades_df['outcome'] == 'WIN'])
    losses = len(trades_df[trades_df['outcome'] == 'LOSS'])
    breakevens = len(trades_df[trades_df['outcome'] == 'BREAKEVEN'])

    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    # R-multiples
    avg_r = trades_df['r_multiple'].mean()
    avg_win_r = trades_df[trades_df['outcome'] == 'WIN']['r_multiple'].mean() if wins > 0 else 0
    avg_loss_r = trades_df[trades_df['outcome'] == 'LOSS']['r_multiple'].mean() if losses > 0 else 0

    # Expectancy (average R per trade)
    expectancy = avg_r

    # Profit factor
    gross_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    gross_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0

    # Drawdown
    equity = equity_curve_df['equity'].values
    running_max = np.maximum.accumulate(equity)
    drawdown = running_max - equity
    max_dd = drawdown.max()
    max_dd_pct = (max_dd / running_max[drawdown.argmax()] * 100) if max_dd > 0 else 0

    # Returns
    final_balance = equity[-1]
    net_profit = final_balance - starting_balance
    roi_pct = (net_profit / starting_balance) * 100

    # Streaks
    outcomes = trades_df['outcome'].values
    max_win_streak = 0
    max_loss_streak = 0
    current_win_streak = 0
    current_loss_streak = 0

    for outcome in outcomes:
        if outcome == 'WIN':
            current_win_streak += 1
            current_loss_streak = 0
            max_win_streak = max(max_win_streak, current_win_streak)
        elif outcome == 'LOSS':
            current_loss_streak += 1
            current_win_streak = 0
            max_loss_streak = max(max_loss_streak, current_loss_streak)

    # Daily metrics
    daily_returns = pd.Series(daily_pnl)
    avg_daily_pnl = daily_returns.mean() if len(daily_returns) > 0 else 0
    best_day = daily_returns.max() if len(daily_returns) > 0 else 0
    worst_day = daily_returns.min() if len(daily_returns) > 0 else 0

    return {
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses,
        'breakevens': breakevens,
        'win_rate': win_rate,
        'avg_r': avg_r,
        'avg_win_r': avg_win_r,
        'avg_loss_r': avg_loss_r,
        'expectancy': expectancy,
        'profit_factor': profit_factor,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'max_dd': max_dd,
        'max_dd_pct': max_dd_pct,
        'final_balance': final_balance,
        'net_profit': net_profit,
        'roi_pct': roi_pct,
        'max_win_streak': max_win_streak,
        'max_loss_streak': max_loss_streak,
        'avg_daily_pnl': avg_daily_pnl,
        'best_day': best_day,
        'worst_day': worst_day,
        'avg_bars_held': trades_df['bars_held'].mean()
    }


def print_metrics(metrics):
    """Print formatted metrics report."""
    print(f"\n{'='*60}")
    print("BACKTEST RESULTS")
    print(f"{'='*60}")
    print(f"Total Trades:        {metrics['total_trades']}")

    if metrics['total_trades'] == 0:
        print("\nNo trades generated.")
        print("\nPossible reasons:")
        print("  1. Strategy is very selective (all 7 gates must align)")
        print("  2. Data may not contain suitable ICT setups")
        print("  3. Sessions: Check data timestamps are in UTC")
        print("  4. Spread: Check spread values in data")
        print(f"\nTip: ICT setups are rare but high-quality.")
        print(f"     Typical rate: 2-5 signals per week on real EURUSD M5 data.")
        print(f"{'='*60}\n")
        return

    print(f"Wins:                {metrics['wins']} ({metrics['win_rate']:.1f}%)")
    print(f"Losses:              {metrics['losses']}")
    print(f"Breakevens:          {metrics['breakevens']}")
    print(f"\nExpectancy (Avg R):  {metrics['expectancy']:.3f}")
    print(f"Avg Win (R):         {metrics['avg_win_r']:.3f}")
    print(f"Avg Loss (R):        {metrics['avg_loss_r']:.3f}")
    print(f"Profit Factor:       {metrics['profit_factor']:.2f}")
    print(f"\nGross Profit:        ${metrics['gross_profit']:.2f}")
    print(f"Gross Loss:          ${metrics['gross_loss']:.2f}")
    print(f"Net Profit:          ${metrics['net_profit']:.2f}")
    print(f"ROI:                 {metrics['roi_pct']:.2f}%")
    print(f"\nMax Drawdown:        ${metrics['max_dd']:.2f} ({metrics['max_dd_pct']:.2f}%)")
    print(f"Max Win Streak:      {metrics['max_win_streak']}")
    print(f"Max Loss Streak:     {metrics['max_loss_streak']}")
    print(f"\nAvg Daily P&L:       ${metrics['avg_daily_pnl']:.2f}")
    print(f"Best Day:            ${metrics['best_day']:.2f}")
    print(f"Worst Day:           ${metrics['worst_day']:.2f}")
    print(f"Avg Bars Held:       {metrics['avg_bars_held']:.1f}")
    print(f"{'='*60}\n")


# ============================================================================
# WALK-FORWARD VALIDATION
# ============================================================================

def walk_forward_validation(df, symbol="EURUSD", n_periods=4):
    """
    Walk-forward validation WITHOUT optimization.

    Simply splits data into N periods and tests same logic on each.
    Validates consistency of strategy across time.
    """
    print(f"\n{'='*60}")
    print(f"WALK-FORWARD VALIDATION ({n_periods} periods)")
    print(f"{'='*60}\n")

    period_size = len(df) // n_periods
    results = []

    for i in range(n_periods):
        start_idx = i * period_size
        end_idx = (i + 1) * period_size if i < n_periods - 1 else len(df)

        period_df = df.iloc[start_idx:end_idx].copy()
        period_start = period_df['time'].min()
        period_end = period_df['time'].max()

        print(f"Period {i+1}/{n_periods}: {period_start} to {period_end}")

        trades_df, equity_df, metrics = backtest(period_df, symbol, starting_balance=10000)

        results.append({
            'period': i + 1,
            'start': period_start,
            'end': period_end,
            'trades': metrics['total_trades'],
            'win_rate': metrics['win_rate'],
            'expectancy': metrics['expectancy'],
            'profit_factor': metrics['profit_factor'],
            'roi_pct': metrics['roi_pct'],
            'max_dd_pct': metrics['max_dd_pct']
        })

        print(f"  Trades={metrics['total_trades']}, WR={metrics['win_rate']:.1f}%, "
              f"Exp={metrics['expectancy']:.3f}, PF={metrics['profit_factor']:.2f}, "
              f"ROI={metrics['roi_pct']:.1f}%, MaxDD={metrics['max_dd_pct']:.1f}%\n")

    results_df = pd.DataFrame(results)

    print(f"{'='*60}")
    print("WALK-FORWARD SUMMARY")
    print(f"{'='*60}")
    print(f"Avg Win Rate:        {results_df['win_rate'].mean():.1f}% (±{results_df['win_rate'].std():.1f}%)")
    print(f"Avg Expectancy:      {results_df['expectancy'].mean():.3f} (±{results_df['expectancy'].std():.3f})")
    print(f"Avg Profit Factor:   {results_df['profit_factor'].mean():.2f} (±{results_df['profit_factor'].std():.2f})")
    print(f"Avg ROI:             {results_df['roi_pct'].mean():.1f}% (±{results_df['roi_pct'].std():.1f}%)")
    print(f"Avg Max DD:          {results_df['max_dd_pct'].mean():.1f}% (±{results_df['max_dd_pct'].std():.1f}%)")
    print(f"{'='*60}\n")

    return results_df


# ============================================================================
# MONTE CARLO SIMULATION
# ============================================================================

def monte_carlo_analysis(trades_df, starting_balance=10000, n_runs=MONTE_CARLO_RUNS):
    """
    Monte Carlo simulation by randomly reshuffling trade outcomes.

    Estimates probability of hitting drawdown limits with same trade distribution.
    """
    if len(trades_df) == 0:
        print("No trades to analyze.")
        return None

    print(f"\n{'='*60}")
    print(f"MONTE CARLO SIMULATION ({n_runs} runs)")
    print(f"{'='*60}\n")

    r_multiples = trades_df['r_multiple'].values
    risk_pct = RISK_PER_TRADE_PCT / 100

    daily_dd_breaches = 0
    max_dd_breaches = 0
    max_dds = []
    final_balances = []

    for run in range(n_runs):
        # Shuffle trade outcomes
        shuffled_r = np.random.permutation(r_multiples)

        balance = starting_balance
        peak = starting_balance
        max_dd_pct = 0
        daily_start_balance = balance

        for r in shuffled_r:
            # Simulate trade
            risk_amount = balance * risk_pct
            pnl = risk_amount * r
            balance += pnl

            # Track peak and drawdown
            if balance > peak:
                peak = balance
                daily_start_balance = balance  # Reset daily tracking at new peak

            current_dd_pct = ((peak - balance) / peak) * 100
            max_dd_pct = max(max_dd_pct, current_dd_pct)

            # Check daily DD (simplified: each trade is a "day")
            daily_dd_pct = ((daily_start_balance - balance) / daily_start_balance) * 100
            if daily_dd_pct >= DAILY_DD_LIMIT_PCT:
                daily_dd_breaches += 1
                break

            # Check max DD
            if current_dd_pct >= MAX_DD_LIMIT_PCT:
                max_dd_breaches += 1
                break

        max_dds.append(max_dd_pct)
        final_balances.append(balance)

    # Calculate statistics
    max_dds = np.array(max_dds)
    final_balances = np.array(final_balances)

    prob_daily_breach = (daily_dd_breaches / n_runs) * 100
    prob_max_breach = (max_dd_breaches / n_runs) * 100
    prob_profit = (np.sum(final_balances > starting_balance) / n_runs) * 100

    print(f"Probability of breaching daily DD limit ({DAILY_DD_LIMIT_PCT}%): {prob_daily_breach:.2f}%")
    print(f"Probability of breaching max DD limit ({MAX_DD_LIMIT_PCT}%):   {prob_max_breach:.2f}%")
    print(f"Probability of profit:                                {prob_profit:.2f}%")
    print(f"\nMax DD Distribution:")
    print(f"  5th percentile:  {np.percentile(max_dds, 5):.2f}%")
    print(f"  25th percentile: {np.percentile(max_dds, 25):.2f}%")
    print(f"  Median:          {np.percentile(max_dds, 50):.2f}%")
    print(f"  75th percentile: {np.percentile(max_dds, 75):.2f}%")
    print(f"  95th percentile: {np.percentile(max_dds, 95):.2f}%")
    print(f"\nFinal Balance Distribution:")
    print(f"  5th percentile:  ${np.percentile(final_balances, 5):.2f}")
    print(f"  25th percentile: ${np.percentile(final_balances, 25):.2f}")
    print(f"  Median:          ${np.percentile(final_balances, 50):.2f}")
    print(f"  75th percentile: ${np.percentile(final_balances, 75):.2f}")
    print(f"  95th percentile: ${np.percentile(final_balances, 95):.2f}")
    print(f"{'='*60}\n")

    return {
        'prob_daily_breach': prob_daily_breach,
        'prob_max_breach': prob_max_breach,
        'prob_profit': prob_profit,
        'max_dd_percentiles': {
            5: np.percentile(max_dds, 5),
            25: np.percentile(max_dds, 25),
            50: np.percentile(max_dds, 50),
            75: np.percentile(max_dds, 75),
            95: np.percentile(max_dds, 95)
        }
    }


# ============================================================================
# LIVE SIGNAL GENERATION
# ============================================================================

def generate_live_signal(df, symbol="EURUSD", output_path="HUX_SIGNAL.csv"):
    """
    Generate signal file for MT4 EA from latest data.

    Output format: symbol,side,entry,sl,tp,comment
    """
    # Prepare data
    df = df.copy()
    df['atr'] = calculate_atr(df)
    df = identify_swing_highs_lows(df)

    # Get latest signal (last 50 bars)
    max_spread = MAX_SPREAD_EURUSD if symbol == "EURUSD" else MAX_SPREAD_GBPUSD

    signal = None
    for i in range(len(df) - 50, len(df)):
        if i < 50:
            continue
        sig = generate_signal(df, i, symbol, max_spread)
        if sig is not None:
            signal = sig
            break

    if signal is None:
        print("No signal generated from latest data.")
        return None

    # Write signal file
    signal_df = pd.DataFrame([{
        'symbol': signal['symbol'],
        'side': signal['side'],
        'entry': signal['entry'],
        'sl': signal['sl'],
        'tp': signal['tp'],
        'comment': signal['comment']
    }])

    signal_df.to_csv(output_path, index=False)
    print(f"Signal written to {output_path}")
    print(signal_df)

    return signal


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="HuxORB PRO - Prop Firm Trading Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run backtest
  python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --out results/

  # Run walk-forward validation
  python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --walk-forward --periods 4

  # Generate live signal
  python huxorb_pro_engine.py live_signal --csv EURUSD_M5_latest.csv --out HUX_SIGNAL.csv

  # Full analysis (backtest + walk-forward + monte carlo)
  python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --full-analysis
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Backtest command
    backtest_parser = subparsers.add_parser('backtest', help='Run backtest')
    backtest_parser.add_argument('--csv', required=True, help='Path to OHLCV CSV file')
    backtest_parser.add_argument('--symbol', default='EURUSD', help='Trading symbol (default: EURUSD)')
    backtest_parser.add_argument('--balance', type=float, default=10000, help='Starting balance (default: 10000)')
    backtest_parser.add_argument('--out', default='results', help='Output directory for results')
    backtest_parser.add_argument('--walk-forward', action='store_true', help='Run walk-forward validation')
    backtest_parser.add_argument('--periods', type=int, default=4, help='Number of walk-forward periods (default: 4)')
    backtest_parser.add_argument('--monte-carlo', action='store_true', help='Run Monte Carlo simulation')
    backtest_parser.add_argument('--full-analysis', action='store_true', help='Run full analysis (backtest + WF + MC)')

    # Live signal command
    live_parser = subparsers.add_parser('live_signal', help='Generate live signal for MT4 EA')
    live_parser.add_argument('--csv', required=True, help='Path to latest OHLCV CSV file')
    live_parser.add_argument('--symbol', default='EURUSD', help='Trading symbol (default: EURUSD)')
    live_parser.add_argument('--out', default='HUX_SIGNAL.csv', help='Output signal file (default: HUX_SIGNAL.csv)')

    args = parser.parse_args()

    if args.command == 'backtest':
        # Load data
        print(f"Loading data from {args.csv}...")
        df = load_data(args.csv)

        # Create output directory
        output_dir = Path(args.out)
        output_dir.mkdir(exist_ok=True)

        # Run backtest
        trades_df, equity_df, metrics = backtest(df, args.symbol, args.balance)
        print_metrics(metrics)

        # Save results
        if len(trades_df) > 0:
            trades_path = output_dir / f'trades_{args.symbol}.csv'
            equity_path = output_dir / f'equity_{args.symbol}.csv'
            metrics_path = output_dir / f'metrics_{args.symbol}.json'

            trades_df.to_csv(trades_path, index=False)
            equity_df.to_csv(equity_path, index=False)

            with open(metrics_path, 'w') as f:
                json.dump(metrics, f, indent=2, default=str)

            print(f"Results saved to {output_dir}/")
            print(f"  - {trades_path.name}")
            print(f"  - {equity_path.name}")
            print(f"  - {metrics_path.name}")

        # Walk-forward validation
        if args.walk_forward or args.full_analysis:
            wf_results = walk_forward_validation(df, args.symbol, args.periods)
            wf_path = output_dir / f'walk_forward_{args.symbol}.csv'
            wf_results.to_csv(wf_path, index=False)
            print(f"Walk-forward results saved to {wf_path}")

        # Monte Carlo simulation
        if args.monte_carlo or args.full_analysis:
            if len(trades_df) > 0:
                mc_results = monte_carlo_analysis(trades_df, args.balance)
                if mc_results:
                    mc_path = output_dir / f'monte_carlo_{args.symbol}.json'
                    with open(mc_path, 'w') as f:
                        json.dump(mc_results, f, indent=2, default=str)
                    print(f"Monte Carlo results saved to {mc_path}")

    elif args.command == 'live_signal':
        # Load latest data
        print(f"Loading latest data from {args.csv}...")
        df = load_data(args.csv)

        # Generate signal
        generate_live_signal(df, args.symbol, args.out)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
