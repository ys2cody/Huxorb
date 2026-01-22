#!/usr/bin/env python3
"""
Convert HistData.com M1 data to M5 format for HuxORB PRO
"""

import pandas as pd
import numpy as np

print("Loading M1 data from HistData.com...")
df = pd.read_csv('DAT_MT_EURUSD_M1_2025.csv',
                 names=['date', 'time', 'open', 'high', 'low', 'close', 'volume'],
                 parse_dates=False)

print(f"Loaded {len(df):,} M1 bars")
print(f"Date range: {df['date'].min()} to {df['date'].max()}")

# Combine date and time into datetime
df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%Y.%m.%d %H:%M')

# Set datetime as index
df = df.set_index('datetime')
df = df[['open', 'high', 'low', 'close', 'volume']]

print("\nResampling M1 → M5...")
# Resample to 5-minute bars (use 'min' instead of 'T' for newer pandas)
df_m5 = df.resample('5min').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum'
}).dropna()

print(f"Created {len(df_m5):,} M5 bars")

# Add spread column (typical EURUSD spread = 15 points = 1.5 pips)
df_m5['spread'] = 15

# Reset index to have 'time' column
df_m5 = df_m5.reset_index()
df_m5 = df_m5.rename(columns={'datetime': 'time'})

# Save to CSV
output_file = 'EURUSD_M5_2025.csv'
df_m5.to_csv(output_file, index=False)

print(f"\n✓ Saved to: {output_file}")
print(f"✓ File size: {len(df_m5):,} bars")
print(f"✓ Date range: {df_m5['time'].min()} to {df_m5['time'].max()}")
print(f"\nSample data:")
print(df_m5.head(10))

print("\n" + "="*80)
print("Ready for backtest!")
print("Run: python huxorb_pro_engine.py backtest --csv EURUSD_M5_2025.csv --full-analysis")
print("="*80)
