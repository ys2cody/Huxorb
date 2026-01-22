#!/usr/bin/env python3
"""Diagnose why no trades on 2025 M5 data"""

import sys
sys.path.insert(0, '.')
import huxorb_pro_engine as engine
import pandas as pd

# Load data
df = engine.load_data('EURUSD_M5_2025.csv')
df['atr'] = engine.calculate_atr(df)
df = engine.identify_swing_highs_lows(df)

print(f"Total bars: {len(df):,}")
print(f"Date range: {df['time'].min()} to {df['time'].max()}")
print()

# Count how many bars pass each gate
gates_passed = {
    'total_bars': len(df),
    'gate1_session': 0,
    'gate2_spread': 0,
    'gate3_regime': 0,
    'gate4_sweep': 0,
    'gate5_bos': 0,
    'gate6_fvg': 0,
    'all_gates': 0
}

# Sample random 1000 bars for speed
import numpy as np
np.random.seed(42)
sample_indices = np.random.choice(range(50, len(df)), min(5000, len(df)-50), replace=False)
sample_indices = sorted(sample_indices)

print(f"Sampling {len(sample_indices):,} bars for diagnosis...")
print()

for idx, i in enumerate(sample_indices):
    if idx % 1000 == 0:
        print(f"Progress: {idx}/{len(sample_indices)}")

    current = df.iloc[i]

    # Gate 1: Session
    hour_utc = current['time'].hour
    gate1 = engine.in_session(hour_utc)
    if gate1:
        gates_passed['gate1_session'] += 1
    else:
        continue

    # Gate 2: Spread
    gate2 = current['spread'] <= engine.MAX_SPREAD_EURUSD
    if gate2:
        gates_passed['gate2_spread'] += 1
    else:
        continue

    # Gate 3: Regime
    if i < 24:
        continue
    gate3 = engine.detect_regime(df, i)
    if gate3:
        gates_passed['gate3_regime'] += 1
    else:
        continue

    # Gate 4: Sweep
    sweep_type, sweep_level = engine.detect_liquidity_sweep(df, i)
    if sweep_type:
        gates_passed['gate4_sweep'] += 1
    else:
        continue

    # Gate 5: BOS
    bos = engine.detect_bos(df, i)
    if bos:
        gates_passed['gate5_bos'] += 1
    else:
        continue

    # Check alignment
    if (sweep_type == 'bullish_sweep' and bos != 'bullish_bos') or \
       (sweep_type == 'bearish_sweep' and bos != 'bearish_bos'):
        continue

    # Gate 6: FVG
    fvg_type, fvg_h, fvg_l, disp = engine.detect_displacement_and_fvg(df, i, "EURUSD")
    if fvg_type:
        gates_passed['gate6_fvg'] += 1
    else:
        continue

    # Check FVG alignment
    if (sweep_type == 'bullish_sweep' and fvg_type == 'bullish_fvg') or \
       (sweep_type == 'bearish_sweep' and fvg_type == 'bearish_fvg'):
        gates_passed['all_gates'] += 1
        if gates_passed['all_gates'] <= 5:
            print(f"\n✓ ALL GATES PASSED at bar {i}: {current['time']}")
            print(f"  Sweep: {sweep_type}, BOS: {bos}, FVG: {fvg_type}, Disp: {disp:.1f}p")

print("\n" + "="*80)
print("GATE PASS RATES (on sample)")
print("="*80)
print(f"Total sampled bars:         {len(sample_indices):,}")
print(f"Gate 1 - Session:           {gates_passed['gate1_session']:,} ({gates_passed['gate1_session']/len(sample_indices)*100:.1f}%)")
print(f"Gate 2 - Spread:            {gates_passed['gate2_spread']:,} ({gates_passed['gate2_spread']/len(sample_indices)*100:.1f}%)")
print(f"Gate 3 - Regime:            {gates_passed['gate3_regime']:,} ({gates_passed['gate3_regime']/len(sample_indices)*100:.1f}%)")
print(f"Gate 4 - Liquidity Sweep:   {gates_passed['gate4_sweep']:,} ({gates_passed['gate4_sweep']/len(sample_indices)*100:.1f}%)")
print(f"Gate 5 - BOS:               {gates_passed['gate5_bos']:,} ({gates_passed['gate5_bos']/len(sample_indices)*100:.1f}%)")
print(f"Gate 6 - FVG:               {gates_passed['gate6_fvg']:,} ({gates_passed['gate6_fvg']/len(sample_indices)*100:.1f}%)")
print(f"ALL GATES:                  {gates_passed['all_gates']:,} ({gates_passed['all_gates']/len(sample_indices)*100:.3f}%)")
print("="*80)

# Extrapolate to full dataset
total_bars = len(df) - 50
expected_trades = (gates_passed['all_gates'] / len(sample_indices)) * total_bars
print(f"\nExpected trades on full dataset: ~{expected_trades:.0f}")

# Check session distribution
session_hours = df['time'].dt.hour.value_counts().sort_index()
london_bars = session_hours.loc[7:9].sum() if any(h in session_hours.index for h in range(7, 10)) else 0
ny_bars = session_hours.loc[12:15].sum() if any(h in session_hours.index for h in range(12, 16)) else 0

print(f"\nSession Distribution:")
print(f"  London (07-09 UTC): {london_bars:,} bars ({london_bars/len(df)*100:.1f}%)")
print(f"  NY (12-15 UTC):     {ny_bars:,} bars ({ny_bars/len(df)*100:.1f}%)")
print(f"  Total session bars: {london_bars + ny_bars:,} ({(london_bars+ny_bars)/len(df)*100:.1f}%)")

if london_bars + ny_bars == 0:
    print("\n⚠️  WARNING: NO BARS DURING TRADING SESSIONS!")
    print("   Data may not be in UTC timezone!")
    print("   HistData times might be in broker timezone (e.g., GMT+2/+3)")
