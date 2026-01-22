import sys
sys.path.insert(0, '.')
import huxorb_pro_engine as engine

df = engine.load_data('EURUSD_M5_2025.csv')
df['atr'] = engine.calculate_atr(df)

# Check for ANY FVGs (regardless of other gates)
fvg_count = 0
displacements = []

for i in range(100, min(10000, len(df))):
    fvg_type, fvg_h, fvg_l, disp = engine.detect_displacement_and_fvg(df, i, "EURUSD")
    
    displacements.append(disp)
    
    if fvg_type:
        fvg_count += 1
        if fvg_count <= 5:
            print(f"FVG found at bar {i}: {df.iloc[i]['time']}")
            print(f"  Type: {fvg_type}, Displacement: {disp:.1f} pips, Gap: {(fvg_h-fvg_l)/0.00001:.1f} pips")

print(f"\nTotal FVGs found: {fvg_count} / {min(10000, len(df))-100}")
print(f"FVG rate: {fvg_count/(min(10000, len(df))-100)*100:.3f}%")

import numpy as np
displacements = np.array(displacements)
print(f"\nDisplacement statistics (first 10k bars):")
print(f"  Max: {displacements.max():.1f} pips")
print(f"  95th percentile: {np.percentile(displacements, 95):.1f} pips")
print(f"  Median: {np.percentile(displacements, 50):.1f} pips")
print(f"  Bars with disp >= 15 pips: {(displacements >= 15).sum()} ({(displacements >= 15).sum()/len(displacements)*100:.1f}%)")
print(f"  Bars with disp >= 10 pips: {(displacements >= 10).sum()} ({(displacements >= 10).sum()/len(displacements)*100:.1f}%)")

print(f"\nCurrent parameters:")
print(f"  MIN_DISPLACEMENT_PIPS = {engine.MIN_DISPLACEMENT_PIPS}")
print(f"  MIN_FVG_PIPS = {engine.MIN_FVG_PIPS}")
