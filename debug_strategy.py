#!/usr/bin/env python3
"""Debug script to see why no signals are generated."""

import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '.')

from huxorb_pro_engine import (
    load_data, calculate_atr, identify_swing_highs_lows,
    in_session, detect_regime, detect_liquidity_sweep,
    detect_bos, detect_displacement_and_fvg
)

# Load data
df = load_data('ict_test_data_EURUSD_M5.csv')
df['atr'] = calculate_atr(df)
df = identify_swing_highs_lows(df)

# Check a few candidate bars
print("Checking bars around intentional setup at index 8*12+30 = 126")
print("="*80)

test_indices = [126, 150, 200, 400, 600, 1000, 1500]

for i in test_indices:
    if i >= len(df):
        continue

    current = df.iloc[i]
    hour_utc = current['time'].hour

    print(f"\nBar {i}: {current['time']}")
    print(f"  Price: O={current['open']:.5f} H={current['high']:.5f} L={current['low']:.5f} C={current['close']:.5f}")
    print(f"  Spread: {current['spread']} points")

    # Gate 1: Session
    session_ok = in_session(hour_utc)
    print(f"  ✓ Session (hour={hour_utc}): {session_ok}" if session_ok else f"  ✗ Session (hour={hour_utc}): {session_ok}")

    # Gate 2: Spread
    spread_ok = current['spread'] <= 20
    print(f"  ✓ Spread: {spread_ok}" if spread_ok else f"  ✗ Spread ({current['spread']} > 20): {spread_ok}")

    # Gate 3: Regime
    if i >= 24:
        regime_ok = detect_regime(df, i)
        print(f"  ✓ Regime (ATR expansion): {regime_ok}" if regime_ok else f"  ✗ Regime: {regime_ok}")
    else:
        print(f"  ✗ Regime: Not enough bars")
        continue

    # Gate 4: Liquidity sweep
    sweep_type, sweep_level = detect_liquidity_sweep(df, i)
    if sweep_type:
        print(f"  ✓ Liquidity Sweep: {sweep_type} at {sweep_level:.5f}")
    else:
        print(f"  ✗ Liquidity Sweep: None detected")
        continue

    # Gate 5: BOS
    bos = detect_bos(df, i)
    if bos:
        print(f"  ✓ BOS: {bos}")
    else:
        print(f"  ✗ BOS: None detected")
        continue

    # Check alignment
    if sweep_type == 'bullish_sweep' and bos != 'bullish_bos':
        print(f"  ✗ Alignment: {sweep_type} != {bos}")
        continue
    if sweep_type == 'bearish_sweep' and bos != 'bearish_bos':
        print(f"  ✗ Alignment: {sweep_type} != {bos}")
        continue

    # Gate 6: Displacement + FVG
    fvg_type, fvg_high, fvg_low, disp_pips = detect_displacement_and_fvg(df, i)
    if fvg_type:
        print(f"  ✓ FVG: {fvg_type} (H={fvg_high:.5f}, L={fvg_low:.5f}, Disp={disp_pips:.1f}p)")
    else:
        print(f"  ✗ FVG/Displacement: disp={disp_pips:.1f}p (need ≥15p + gap ≥8p)")
        continue

    # Check alignment
    if sweep_type == 'bullish_sweep' and fvg_type != 'bullish_fvg':
        print(f"  ✗ Alignment: {sweep_type} != {fvg_type}")
        continue
    if sweep_type == 'bearish_sweep' and fvg_type != 'bearish_fvg':
        print(f"  ✗ Alignment: {sweep_type} != {fvg_type}")
        continue

    print(f"  ✓✓✓ ALL GATES PASSED! This bar should generate a signal! ✓✓✓")

print("\n" + "="*80)
print("Summary: Check which gates are failing most often.")
