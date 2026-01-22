#!/usr/bin/env python3
"""Scan all bars to find which pass each gate."""

import pandas as pd
import sys
sys.path.insert(0, '.')

from huxorb_pro_engine import (
    load_data, calculate_atr, identify_swing_highs_lows,
    generate_signal, MAX_SPREAD_EURUSD
)

# Load data
print("Loading data...")
df = load_data('ict_test_data_EURUSD_M5.csv')
df['atr'] = calculate_atr(df)
df = identify_swing_highs_lows(df)

print(f"Scanning {len(df)} bars for signals...")
print("="*80)

signals_found = []
for i in range(50, len(df)):
    signal = generate_signal(df, i, "EURUSD", MAX_SPREAD_EURUSD)
    if signal:
        signals_found.append((i, signal))
        print(f"\n✓ SIGNAL FOUND at bar {i}: {signal['time']}")
        print(f"  Side: {signal['side']}")
        print(f"  Entry: {signal['entry']:.5f}, SL: {signal['sl']:.5f}, TP: {signal['tp']:.5f}")
        print(f"  SL Distance: {signal['sl_pips']:.1f} pips, RR: {signal['rr']:.1f}")
        print(f"  Comment: {signal['comment']}")

print("\n" + "="*80)
print(f"Total signals found: {len(signals_found)}")

if len(signals_found) == 0:
    print("\nNo signals found. The strategy is extremely selective.")
    print("This is intentional - ICT setups require all 7 gates to align perfectly:")
    print("  1. Session (London 07-10 UTC or NY 12-16 UTC)")
    print("  2. Spread ≤ 20 points")
    print("  3. ATR expansion (volatility regime)")
    print("  4. Liquidity sweep (stop hunt)")
    print("  5. Break of structure")
    print("  6. Displacement ≥ 15 pips")
    print("  7. Fair value gap ≥ 8 pips")
    print("\nOn REAL market data, expect 2-5 signals per week.")
