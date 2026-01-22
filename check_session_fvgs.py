import sys
sys.path.insert(0, '.')
import huxorb_pro_engine as engine

df = engine.load_data('EURUSD_M5_2025.csv')
df['atr'] = engine.calculate_atr(df)
df = engine.identify_swing_highs_lows(df)

# Count FVGs during sessions with other gates
fvgs_in_session = 0
fvgs_with_sweep = 0
fvgs_with_bos = 0
full_setups = 0

for i in range(100, min(20000, len(df))):
    current = df.iloc[i]
    hour_utc = current['time'].hour
    
    # Must be in session
    if not engine.in_session(hour_utc):
        continue
    
    # Check regime
    if not engine.detect_regime(df, i):
        continue
    
    # Check FVG
    fvg_type, fvg_h, fvg_l, disp = engine.detect_displacement_and_fvg(df, i, "EURUSD")
    if not fvg_type:
        continue
    
    fvgs_in_session += 1
    
    # Check sweep
    sweep_type, _ = engine.detect_liquidity_sweep(df, i)
    if sweep_type:
        fvgs_with_sweep += 1
        
        # Check BOS
        bos = engine.detect_bos(df, i)
        if bos:
            fvgs_with_bos += 1
            
            # Check alignment
            if (sweep_type == 'bullish_sweep' and bos == 'bullish_bos' and fvg_type == 'bullish_fvg') or \
               (sweep_type == 'bearish_sweep' and bos == 'bearish_bos' and fvg_type == 'bearish_fvg'):
                full_setups += 1
                if full_setups <= 10:
                    print(f"\n✓ COMPLETE SETUP at bar {i}: {current['time']}")
                    print(f"  {sweep_type} → {bos} → {fvg_type}")
                    print(f"  Disp: {disp:.1f} pips, Gap: {(fvg_h-fvg_l)/0.00001:.1f} pips")

print(f"\n" + "="*80)
print("SETUP FUNNEL ANALYSIS (first 20k bars)")
print("="*80)
print(f"FVGs in session with regime:         {fvgs_in_session}")
print(f"+ Liquidity Sweep:                   {fvgs_with_sweep}")
print(f"+ BOS:                               {fvgs_with_bos}")
print(f"+ Correct Alignment (FULL SETUP):    {full_setups}")
print("="*80)

if full_setups > 0:
    print(f"\n✅ Found {full_setups} complete setups in first 20k bars!")
    print(f"   Extrapolated to full year: ~{full_setups * (len(df)/20000):.0f} trades")
else:
    print("\n⚠️  No complete setups found in first 20k bars.")
    print("   Strategy requirements are EXTREMELY selective.")
    print("   This is intentional (no curve-fitting) but may need adjustment.")
