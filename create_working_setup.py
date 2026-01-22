#!/usr/bin/env python3
"""Create ICT setup WITHIN trading session."""

import pandas as pd
from datetime import datetime, timedelta

base_price = 1.09000
data = []

# Start JUST before London session to have some history
start_time = datetime(2024, 1, 15, 6, 0, 0)  # 06:00 UTC

# Create 24 bars of baseline (06:00-08:00) for indicator history
for i in range(24):
    time = start_time + timedelta(minutes=5*i)
    price = base_price + (i % 5 - 2) * 0.00003  # Small range, low ATR
    data.append({
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'open': round(price, 5),
        'high': round(price + 0.00005, 5),
        'low': round(price - 0.00005, 5),
        'close': round(price, 5),
        'volume': 800,
        'spread': 15
    })

# Now at 08:00 UTC - LONDON SESSION STARTS
# Bars 24-33: Downtrend (increased volatility for ATR expansion)
for i in range(10):
    idx = 24 + i
    time = start_time + timedelta(minutes=5*idx)
    price = base_price - i * 0.00015  # 1.5 pips down per bar
    data.append({
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'open': round(price + 0.00010, 5),
        'high': round(price + 0.00020, 5),  # Higher volatility
        'low': round(price, 5),
        'close': round(price + 0.00005, 5),
        'volume': 1200,
        'spread': 15
    })

swing_low = min([d['low'] for d in data[24:34]])
print(f"Swing low (bars 24-33): {swing_low}")

# Bar 34 (08:50 UTC): LIQUIDITY SWEEP
idx = 34
time = start_time + timedelta(minutes=5*idx)
sweep_low = swing_low - 0.00035  # Sweep 3.5 pips below
sweep_close = base_price - 0.00130 + 0.00020  # Close above sweep
data.append({
    'time': time.strftime('%Y-%m-%d %H:%M:%S'),
    'open': round(base_price - 0.00140, 5),
    'high': round(base_price - 0.00105, 5),
    'low': round(sweep_low, 5),  # SWEEP
    'close': round(sweep_close, 5),
    'volume': 1300,
    'spread': 15
})

print(f"Bar 34 (08:50 UTC): Sweep to {sweep_low}, close at {sweep_close}")

# Bar 35 (08:55 UTC): DISPLACEMENT 1
idx = 35
time = start_time + timedelta(minutes=5*idx)
disp1_open = sweep_close
disp1_close = disp1_open + 0.00022  # 22 pips up
data.append({
    'time': time.strftime('%Y-%m-%d %H:%M:%S'),
    'open': round(disp1_open, 5),
    'high': round(disp1_close + 0.00008, 5),
    'low': round(disp1_open - 0.00005, 5),
    'close': round(disp1_close, 5),
    'volume': 1800,
    'spread': 15
})

print(f"Bar 35: Displacement 1, close at {disp1_close}")

# Bar 36 (09:00 UTC): DISPLACEMENT 2 + FVG
idx = 36
time = start_time + timedelta(minutes=5*idx)
disp2_open = disp1_close
disp2_close = disp2_open + 0.00018  # 18 pips up (total displacement = 40 pips)

# Create FVG: bar 36 low > bar 34 high, with gap >= 8 pips
bar34_high = data[34]['high']
disp2_low = bar34_high + 0.00010  # 10 pips gap

data.append({
    'time': time.strftime('%Y-%m-%d %H:%M:%S'),
    'open': round(disp2_open, 5),
    'high': round(disp2_close + 0.00008, 5),
    'low': round(disp2_low, 5),  # FVG
    'close': round(disp2_close, 5),
    'volume': 1800,
    'spread': 15
})

print(f"Bar 36: Displacement 2, close at {disp2_close}")
fvg_gap = (disp2_low - bar34_high) / 0.00001
print(f"FVG: Bar 34 high={bar34_high}, Bar 36 low={disp2_low}, Gap={fvg_gap:.1f} pips")

# Ensure BOS: close above previous swing high
prev_swing_high = max([d['high'] for d in data[24:35]])
print(f"Previous swing high (bars 24-34): {prev_swing_high}")
print(f"Bar 36 close: {disp2_close}")

if disp2_close <= prev_swing_high:
    # Adjust to break structure
    adjustment = prev_swing_high + 0.00025 - disp2_close
    data[36]['close'] = round(prev_swing_high + 0.00025, 5)
    data[36]['high'] = round(data[36]['close'] + 0.00008, 5)
    print(f"Adjusted bar 36 close to {data[36]['close']} for BOS")

# Bars 37-60: Continuation with high volatility (for ATR expansion)
for i in range(37, 60):
    time = start_time + timedelta(minutes=5*i)
    price = data[i-1]['close'] + (i % 3 - 1) * 0.00018  # High volatility
    data.append({
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'open': round(data[i-1]['close'], 5),
        'high': round(price + 0.00020, 5),
        'low': round(price - 0.00020, 5),
        'close': round(price, 5),
        'volume': 1400,
        'spread': 15
    })

df = pd.DataFrame(data)
df.to_csv('working_ict_setup.csv', index=False)

print(f"\n✓ Created {len(df)} bars")
print(f"✓ ICT setup at bars 34-36 (08:50-09:00 UTC - LONDON SESSION)")
print(f"✓ Saved to: working_ict_setup.csv")
print(f"\nRun: python huxorb_pro_engine.py backtest --csv working_ict_setup.csv --out results/")
