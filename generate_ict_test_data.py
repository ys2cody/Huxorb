#!/usr/bin/env python3
"""
Generate synthetic data WITH intentional ICT setups for testing.
This ensures the backtest actually finds signals.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

np.random.seed(42)

def create_ict_setup(df, start_idx, direction='bullish'):
    """Create a complete ICT setup at given index."""
    if direction == 'bullish':
        # Create downtrend with swing low
        for i in range(start_idx, start_idx + 10):
            df.loc[i, 'close'] = df.iloc[i]['open'] - 0.00010 - i * 0.00002
            df.loc[i, 'high'] = max(df.iloc[i]['open'], df.iloc[i]['close']) + 0.00005
            df.loc[i, 'low'] = min(df.iloc[i]['open'], df.iloc[i]['close']) - 0.00005

        swing_low = df.iloc[start_idx:start_idx+10]['low'].min()

        # Liquidity sweep: wick below swing low, close above
        sweep_idx = start_idx + 10
        df.loc[sweep_idx, 'low'] = swing_low - 0.00020  # Sweep 2 pips below
        df.loc[sweep_idx, 'close'] = df.iloc[sweep_idx]['open'] + 0.00010
        df.loc[sweep_idx, 'high'] = df.iloc[sweep_idx]['close'] + 0.00005

        # Displacement + FVG: strong move up creating gap
        disp_idx = sweep_idx + 1
        df.loc[disp_idx, 'open'] = df.iloc[sweep_idx]['close']
        df.loc[disp_idx, 'close'] = df.iloc[disp_idx]['open'] + 0.00025  # 25 pips displacement
        df.loc[disp_idx, 'high'] = df.iloc[disp_idx]['close'] + 0.00005
        df.loc[disp_idx, 'low'] = df.iloc[disp_idx]['open'] - 0.00003

        # Second displacement candle (creates FVG)
        disp_idx2 = disp_idx + 1
        df.loc[disp_idx2, 'open'] = df.iloc[disp_idx]['close']
        df.loc[disp_idx2, 'close'] = df.iloc[disp_idx2]['open'] + 0.00020  # Another 20 pips
        df.loc[disp_idx2, 'high'] = df.iloc[disp_idx2]['close'] + 0.00005
        df.loc[disp_idx2, 'low'] = df.iloc[disp_idx2]['open'] - 0.00003

        # FVG is created: gap between candle[sweep].high and candle[disp_idx2].low
        # Make sure gap exists
        if df.iloc[disp_idx2]['low'] <= df.iloc[sweep_idx]['high']:
            # Widen gap
            df.loc[disp_idx2, 'low'] = df.iloc[sweep_idx]['high'] + 0.00010

        # BOS: price closes above previous swing high
        prev_swing_high = df.iloc[start_idx:sweep_idx]['high'].max()
        if df.iloc[disp_idx2]['close'] <= prev_swing_high:
            df.loc[disp_idx2, 'close'] = prev_swing_high + 0.00015
            df.loc[disp_idx2, 'high'] = df.iloc[disp_idx2]['close'] + 0.00005

    else:  # bearish
        # Create uptrend with swing high
        for i in range(start_idx, start_idx + 10):
            df.loc[i, 'close'] = df.iloc[i]['open'] + 0.00010 + i * 0.00002
            df.loc[i, 'high'] = max(df.iloc[i]['open'], df.iloc[i]['close']) + 0.00005
            df.loc[i, 'low'] = min(df.iloc[i]['open'], df.iloc[i]['close']) - 0.00005

        swing_high = df.iloc[start_idx:start_idx+10]['high'].max()

        # Liquidity sweep: wick above swing high, close below
        sweep_idx = start_idx + 10
        df.loc[sweep_idx, 'high'] = swing_high + 0.00020  # Sweep 2 pips above
        df.loc[sweep_idx, 'close'] = df.iloc[sweep_idx]['open'] - 0.00010
        df.loc[sweep_idx, 'low'] = df.iloc[sweep_idx]['close'] - 0.00005

        # Displacement + FVG: strong move down creating gap
        disp_idx = sweep_idx + 1
        df.loc[disp_idx, 'open'] = df.iloc[sweep_idx]['close']
        df.loc[disp_idx, 'close'] = df.iloc[disp_idx]['open'] - 0.00025  # 25 pips displacement
        df.loc[disp_idx, 'high'] = df.iloc[disp_idx]['open'] + 0.00003
        df.loc[disp_idx, 'low'] = df.iloc[disp_idx]['close'] - 0.00005

        # Second displacement candle
        disp_idx2 = disp_idx + 1
        df.loc[disp_idx2, 'open'] = df.iloc[disp_idx]['close']
        df.loc[disp_idx2, 'close'] = df.iloc[disp_idx2]['open'] - 0.00020
        df.loc[disp_idx2, 'high'] = df.iloc[disp_idx2]['open'] + 0.00003
        df.loc[disp_idx2, 'low'] = df.iloc[disp_idx2]['close'] - 0.00005

        # Create FVG
        if df.iloc[disp_idx2]['high'] >= df.iloc[sweep_idx]['low']:
            df.loc[disp_idx2, 'high'] = df.iloc[sweep_idx]['low'] - 0.00010

        # BOS: price closes below previous swing low
        prev_swing_low = df.iloc[start_idx:sweep_idx]['low'].min()
        if df.iloc[disp_idx2]['close'] >= prev_swing_low:
            df.loc[disp_idx2, 'close'] = prev_swing_low - 0.00015
            df.loc[disp_idx2, 'low'] = df.iloc[disp_idx2]['close'] - 0.00005

    # Ensure OHLC consistency for all modified bars
    for i in range(start_idx, start_idx + 13):
        if i >= len(df):
            break
        df.loc[i, 'high'] = max(df.iloc[i]['open'], df.iloc[i]['high'],
                                df.iloc[i]['low'], df.iloc[i]['close'])
        df.loc[i, 'low'] = min(df.iloc[i]['open'], df.iloc[i]['high'],
                               df.iloc[i]['low'], df.iloc[i]['close'])

# Generate base data
n_bars = 24 * 12 * 30  # 1 month of M5 data
start_time = datetime(2024, 1, 1, 0, 0, 0)
times = [start_time + timedelta(minutes=5*i) for i in range(n_bars)]

# Base price around 1.09000
base_price = 1.09000
prices = [base_price + np.random.randn() * 0.00050 for _ in range(n_bars)]

# Create DataFrame
data = []
for i, time in enumerate(times):
    open_price = prices[i] if i == 0 else data[i-1]['close']
    close = prices[i]
    high = max(open_price, close) + abs(np.random.randn() * 0.00005)
    low = min(open_price, close) - abs(np.random.randn() * 0.00005)
    spread = int(abs(np.random.randn() * 3) + 12)  # 12-18 points

    data.append({
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'open': round(open_price, 5),
        'high': round(high, 5),
        'low': round(low, 5),
        'close': round(close, 5),
        'volume': int(np.random.uniform(500, 2000)),
        'spread': max(5, min(25, spread))
    })

df = pd.DataFrame(data)

# Insert ICT setups during trading sessions
setup_count = 0
for day in range(1, 30):
    # London session setup (08:00 UTC)
    london_idx = day * 24 * 12 + 8 * 12 + 30  # 08:30 UTC
    if london_idx + 20 < len(df):
        create_ict_setup(df, london_idx, direction='bullish' if day % 2 == 0 else 'bearish')
        setup_count += 1

    # NY session setup (13:00 UTC)
    ny_idx = day * 24 * 12 + 13 * 12 + 30  # 13:30 UTC
    if ny_idx + 20 < len(df):
        create_ict_setup(df, ny_idx, direction='bearish' if day % 2 == 0 else 'bullish')
        setup_count += 1

# Ensure ATR expansion for regime filter
# Increase volatility around setup times
for i in range(50, len(df)):
    hour = int(df.iloc[i]['time'].split()[1].split(':')[0])
    if hour in [8, 9, 13, 14]:
        # Increase range
        mid = (df.iloc[i]['high'] + df.iloc[i]['low']) / 2
        df.loc[i, 'high'] = mid + 0.00020
        df.loc[i, 'low'] = mid - 0.00020

# Save
output_path = 'ict_test_data_EURUSD_M5.csv'
df.to_csv(output_path, index=False)

print(f"✓ Generated {len(df)} bars with {setup_count} intentional ICT setups")
print(f"✓ Date range: {df['time'].min()} to {df['time'].max()}")
print(f"✓ Saved to: {output_path}")
print(f"\nNote: This data includes artificial ICT patterns for testing.")
