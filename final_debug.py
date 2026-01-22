import sys
sys.path.insert(0, '.')
import huxorb_pro_engine as engine

# Load data
df = engine.load_data('working_ict_setup.csv')
df['atr'] = engine.calculate_atr(df)
df = engine.identify_swing_highs_lows(df)

print("Checking bars 34-40 (the ICT setup area)")
print("="*80)

for i in range(34, 41):
    if i >= len(df):
        continue
    
    current = df.iloc[i]
    print(f"\nBar {i}: {current['time']}")
    
    # Gate 1: Session
    hour_utc = current['time'].hour
    gate1 = engine.in_session(hour_utc)
    print(f"  Gate 1 - Session (hour={hour_utc}): {'✓' if gate1 else '✗'} {gate1}")
    if not gate1:
        continue
    
    # Gate 2: Spread
    gate2 = current['spread'] <= engine.MAX_SPREAD_EURUSD
    print(f"  Gate 2 - Spread ({current['spread']}): {'✓' if gate2 else '✗'} {gate2}")
    if not gate2:
        continue
    
    # Gate 3: Regime
    gate3 = engine.detect_regime(df, i)
    atr_current = df['atr'].iloc[i]
    atr_avg = df['atr'].iloc[i-10:i].mean() if i >= 10 else 0
    print(f"  Gate 3 - Regime: {'✓' if gate3 else '✗'} {gate3}")
    print(f"           ATR={atr_current:.5f}, Avg={atr_avg:.5f}, Ratio={atr_current/atr_avg:.2f if atr_avg > 0 else 0}")
    if not gate3:
        continue
    
    # Gate 4: Liquidity sweep
    sweep_type, sweep_level = engine.detect_liquidity_sweep(df, i)
    gate4 = sweep_type is not None
    print(f"  Gate 4 - Liquidity Sweep: {'✓' if gate4 else '✗'} {sweep_type} at {sweep_level if sweep_level else 'N/A'}")
    if not gate4:
        continue
    
    # Gate 5: BOS
    bos = engine.detect_bos(df, i)
    gate5 = bos is not None
    print(f"  Gate 5 - BOS: {'✓' if gate5 else '✗'} {bos}")
    if not gate5:
        continue
    
    # Check alignment
    if sweep_type == 'bullish_sweep' and bos != 'bullish_bos':
        print(f"  ✗ Alignment failed: {sweep_type} vs {bos}")
        continue
    if sweep_type == 'bearish_sweep' and bos != 'bearish_bos':
        print(f"  ✗ Alignment failed: {sweep_type} vs {bos}")
        continue
    print(f"  ✓ Alignment: {sweep_type} matches {bos}")
    
    # Gate 6: Displacement + FVG
    fvg_type, fvg_high, fvg_low, disp_pips = engine.detect_displacement_and_fvg(df, i, "EURUSD")
    gate6 = fvg_type is not None
    print(f"  Gate 6 - Displacement: {disp_pips:.1f} pips (need ≥{engine.MIN_DISPLACEMENT_PIPS})")
    print(f"           FVG: {'✓' if gate6 else '✗'} {fvg_type}")
    if gate6 and fvg_high and fvg_low:
        gap_pips = (fvg_high - fvg_low) / 0.00001
        print(f"           Gap: {gap_pips:.1f} pips (need ≥{engine.MIN_FVG_PIPS})")
    if not gate6:
        continue
    
    # Check alignment
    if sweep_type == 'bullish_sweep' and fvg_type != 'bullish_fvg':
        print(f"  ✗ Alignment failed: {sweep_type} vs {fvg_type}")
        continue
    if sweep_type == 'bearish_sweep' and fvg_type != 'bearish_fvg':
        print(f"  ✗ Alignment failed: {sweep_type} vs {fvg_type}")
        continue
    print(f"  ✓ Alignment: {sweep_type} matches {fvg_type}")
    
    print(f"\n  🎯 ALL GATES PASSED! Signal should be generated!")
    
    # Try to generate signal
    signal = engine.generate_signal(df, i, "EURUSD", engine.MAX_SPREAD_EURUSD)
    if signal:
        print(f"  ✓✓✓ SIGNAL CONFIRMED: {signal['side']} at {signal['entry']}")
    else:
        print(f"  ✗✗✗ generate_signal() returned None - check Gate 7 (entry logic)")

print("\n" + "="*80)
