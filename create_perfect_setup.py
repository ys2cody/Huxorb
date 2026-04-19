#!/usr/bin/env python3
"""Create a perfect ICT setup that WILL trigger all gates."""

import pandas as pd
from datetime import datetime, timedelta

# Create base data
base_price = 1.09000
data = []

# Start at London session open
start_time = datetime(2024, 1, 15, 8, 0, 0)  # 08:00 UTC (London)

# Create 100 bars of baseline data
for i in range(100):
    time = start_time + timedelta(minutes=5*i)
    # Gentle sideways with small ATR
    price = base_price + (i % 10 - 5) * 0.00005
    data.append({
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'open': round(price, 5),
        'high': round(price + 0.00005, 5),
        'low': round(price - 0.00005, 5),
        'close': round(price, 5),
        'volume': 1000,
        'spread': 15
    })

# Now create perfect ICT setup starting at bar 100 (08:20 UTC - still in London session)
# Phase 1: Create downtrend with swing low (bars 100-109)
for i in range(10):
    idx = 100 + i
    time = start_time + timedelta(minutes=5*idx)
    price = base_price - i * 0.00010  # Trending down, 1 pip per bar
    data.append({
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'open': round(price + 0.00005, 5),
        'high': round(price + 0.00010, 5),
        'low': round(price, 5),
        'close': round(price + 0.00002, 5),
        'volume': 1000,
        'spread': 15
    })

swing_low = data[109]['low']
print(f"Swing low at bar 109: {swing_low}")

# Phase 2: Liquidity sweep (bar 110) - wick below swing low, close higher
idx = 110
time = start_time + timedelta(minutes=5*idx)
sweep_low = swing_low - 0.00030  # Sweep 3 pips below
sweep_close = base_price - 0.00080 + 0.00015  # Close above sweep level
data.append({
    'time': time.strftime('%Y-%m-%d %H:%M:%S'),
    'open': round(base_price - 0.00095, 5),
    'high': round(base_price - 0.00070, 5),
    'low': round(sweep_low, 5),  # LIQUIDITY SWEEP
    'close': round(sweep_close, 5),
    'volume': 1000,
    'spread': 15
})

print(f"Bar 110: Liquidity sweep to {sweep_low}, close at {sweep_close}")

# Phase 3: Strong displacement UP (bars 111-112) - Creates FVG
# Bar 111: Big bullish candle (20 pips)
idx = 111
time = start_time + timedelta(minutes=5*idx)
disp1_open = sweep_close
disp1_close = disp1_open + 0.00020  # 20 pips up
data.append({
    'time': time.strftime('%Y-%m-%d %H:%M:%S'),
    'open': round(disp1_open, 5),
    'high': round(disp1_close + 0.00005, 5),
    'low': round(disp1_open - 0.00003, 5),
    'close': round(disp1_close, 5),
    'volume': 1500,
    'spread': 15
})

print(f"Bar 111: Displacement candle 1, close at {disp1_close}")

# Bar 112: Another bullish candle (15 pips) - Creates FVG gap
idx = 112
time = start_time + timedelta(minutes=5*idx)
disp2_open = disp1_close
disp2_close = disp2_open + 0.00015  # 15 pips up
# Make FVG: bar 112 low > bar 110 high
disp2_low = data[110]['high'] + 0.00012  # Gap of 12 pips (> 8 pips required)
data.append({
    'time': time.strftime('%Y-%m-%d %H:%M:%S'),
    'open': round(disp2_open, 5),
    'high': round(disp2_close + 0.00005, 5),
    'low': round(disp2_low, 5),  # FVG created
    'close': round(disp2_close, 5),
    'volume': 1500,
    'spread': 15
})

print(f"Bar 112: Displacement candle 2, close at {disp2_close}")
print(f"FVG: Bar 110 high={data[110]['high']}, Bar 112 low={disp2_low}, Gap={(disp2_low - data[110]['high']) / 0.00001:.1f} pips")

# Check BOS: price should break above swing high from bars 100-109
prev_swing_high = max([d['high'] for d in data[100:110]])
print(f"Previous swing high (bars 100-109): {prev_swing_high}")
print(f"Current close (bar 112): {disp2_close}")
print(f"BOS: {disp2_close > prev_swing_high}")

# Ensure bar 112 breaks above previous swing high (BOS)
if disp2_close <= prev_swing_high:
    data[112]['close'] = prev_swing_high + 0.00020
    data[112]['high'] = data[112]['close'] + 0.00005
    print(f"Adjusted bar 112 close to {data[112]['close']} for BOS")

# Phase 4: Add more bars for ATR expansion detection
# Need higher volatility in recent bars
for i in range(113, 130):
    time = start_time + timedelta(minutes=5*i)
    price = data[i-1]['close'] + (i % 2 - 0.5) * 0.00015  # Higher volatility
    data.append({
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'open': round(data[i-1]['close'], 5),
        'high': round(price + 0.00015, 5),
        'low': round(price - 0.00015, 5),
        'close': round(price, 5),
        'volume': 1200,
        'spread': 15
    })

# Save
df = pd.DataFrame(data)
df.to_csv('perfect_ict_setup.csv', index=False)

print(f"\n✓ Created {len(df)} bars with PERFECT ICT setup")
print(f"✓ Setup location: Bars 110-112 (08:20-08:30 UTC - London session)")
print(f"✓ All gates should pass at bar 112 or shortly after")
print(f"✓ Saved to: perfect_ict_setup.csv")
