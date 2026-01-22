#!/usr/bin/env python3
"""
Generate synthetic EURUSD M5 data for testing HuxORB PRO.
This creates realistic-looking price action with potential ICT setups.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Set seed for reproducibility
np.random.seed(42)

# Generate 2 months of M5 data (24 hours * 12 bars/hour * 60 days)
n_bars = 24 * 12 * 60

# Start date: January 1, 2024
start_time = datetime(2024, 1, 1, 0, 0, 0)
times = [start_time + timedelta(minutes=5*i) for i in range(n_bars)]

# Base price
base_price = 1.09000

# Generate price with trend, noise, and occasional strong moves (for displacement/FVG)
prices = []
current_price = base_price
trend = 0.0

for i in range(n_bars):
    # Session-based volatility (higher during London/NY)
    hour = times[i].hour
    if 7 <= hour < 10 or 12 <= hour < 16:  # London/NY sessions
        volatility = 0.00015  # ~1.5 pips per bar
        displacement_prob = 0.02  # 2% chance of strong move
    else:
        volatility = 0.00005  # ~0.5 pips per bar
        displacement_prob = 0.005  # 0.5% chance

    # Occasional displacement moves (for FVG setups)
    if np.random.random() < displacement_prob:
        displacement = np.random.choice([-1, 1]) * np.random.uniform(0.00020, 0.00040)  # 20-40 pips
        trend = displacement * 0.3  # Trend continuation
    else:
        displacement = 0

    # Random walk with trend
    change = np.random.randn() * volatility + trend * 0.1 + displacement
    current_price += change

    # Mean reversion (keep price in reasonable range)
    if current_price > base_price + 0.02:
        current_price -= 0.001
        trend = -0.0001
    elif current_price < base_price - 0.02:
        current_price += 0.001
        trend = 0.0001

    # Decay trend
    trend *= 0.98

    prices.append(current_price)

# Generate OHLC from prices with realistic intrabar movement
data = []
for i, close in enumerate(prices):
    # High/low around close with some randomness
    spread_high = abs(np.random.randn() * 0.00005)  # ~0.5 pips
    spread_low = abs(np.random.randn() * 0.00005)

    high = close + spread_high
    low = close - spread_low

    # Open is close from previous bar (with small gap sometimes)
    if i > 0:
        open_price = prices[i-1] + np.random.randn() * 0.00002  # Small gap
    else:
        open_price = close

    # Ensure OHLC consistency
    high = max(high, open_price, close)
    low = min(low, open_price, close)

    # Spread in points (5-digit broker)
    spread = int(abs(np.random.randn() * 5) + 10)  # 10-20 points typical
    spread = max(5, min(30, spread))  # Clamp to 5-30 points

    # Volume (irrelevant for this strategy, but include for completeness)
    volume = int(np.random.uniform(500, 2000))

    data.append({
        'time': times[i].strftime('%Y-%m-%d %H:%M:%S'),
        'open': round(open_price, 5),
        'high': round(high, 5),
        'low': round(low, 5),
        'close': round(close, 5),
        'volume': volume,
        'spread': spread
    })

# Create DataFrame
df = pd.DataFrame(data)

# Add some liquidity sweeps (wick below recent low, close above)
# This increases chance of ICT setups being triggered
for i in range(100, len(df), 500):
    if df.iloc[i]['time'].split()[1].split(':')[0] in ['08', '09', '13', '14']:  # During sessions
        # Bullish sweep
        recent_low = df.iloc[i-20:i]['low'].min()
        df.loc[i, 'low'] = recent_low - 0.00015  # Sweep 1.5 pips below
        df.loc[i, 'close'] = df.iloc[i]['open'] + 0.00025  # Close higher (displacement)
        df.loc[i, 'high'] = max(df.iloc[i]['high'], df.iloc[i]['close'])

# Save to CSV
output_path = 'test_data_EURUSD_M5.csv'
df.to_csv(output_path, index=False)

print(f"✓ Generated {len(df)} bars of synthetic EURUSD M5 data")
print(f"✓ Date range: {df['time'].min()} to {df['time'].max()}")
print(f"✓ Price range: {df['close'].min():.5f} to {df['close'].max():.5f}")
print(f"✓ Saved to: {output_path}")
print(f"\nNote: This is SYNTHETIC data for testing only.")
print(f"For real backtesting, use actual historical data from HistData.com or DukasCopy.")
