#!/usr/bin/env python3
"""
DEMO BACKTEST - Relaxed parameters for testing ONLY.

This demonstrates the system works technically.
DO NOT use these parameters for real trading!
"""

import pandas as pd
import numpy as np
import sys
import json
from pathlib import Path

# Import with modified constants for demo
import huxorb_pro_engine as engine

# TEMPORARILY relax parameters for demo (TESTING ONLY!)
print("="*80)
print("DEMO MODE - Using relaxed parameters for testing")
print("="*80)
print("PRODUCTION values → DEMO values:")
print(f"  MIN_DISPLACEMENT_PIPS: {engine.MIN_DISPLACEMENT_PIPS} → 10")
print(f"  MIN_FVG_PIPS: {engine.MIN_FVG_PIPS} → 5")
print(f"  ATR_EXPANSION_FACTOR: {engine.ATR_EXPANSION_FACTOR} → 1.1")
print("="*80)
print("⚠️  WARNING: These relaxed parameters are for DEMONSTRATION ONLY!")
print("⚠️  DO NOT use for real trading - they accept lower-quality setups.")
print("="*80 + "\n")

# Temporarily modify constants (demo only)
engine.MIN_DISPLACEMENT_PIPS = 10  # Relaxed from 15
engine.MIN_FVG_PIPS = 5           # Relaxed from 8
engine.ATR_EXPANSION_FACTOR = 1.1  # Relaxed from 1.2

# Load data
df = engine.load_data('ict_test_data_EURUSD_M5.csv')

# Run backtest
trades_df, equity_df, metrics = engine.backtest(df, "EURUSD", 10000)
engine.print_metrics(metrics)

# Save results
if len(trades_df) > 0:
    output_dir = Path('demo_results')
    output_dir.mkdir(exist_ok=True)

    trades_df.to_csv(output_dir / 'trades_DEMO.csv', index=False)
    equity_df.to_csv(output_dir / 'equity_DEMO.csv', index=False)

    with open(output_dir / 'metrics_DEMO.json', 'w') as f:
        json.dump(metrics, f, indent=2, default=str)

    print(f"Demo results saved to {output_dir}/")
    print("\nSample trades:")
    print(trades_df[['trade_num', 'entry_time', 'side', 'outcome', 'r_multiple', 'pnl', 'balance']].head(10))

print("\n" + "="*80)
print("REMINDER: This was a DEMO with relaxed parameters.")
print("For real trading, use the PRODUCTION parameters in the original code.")
print("="*80)
