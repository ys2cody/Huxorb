import sys
sys.path.insert(0, '.')
import huxorb_pro_engine as engine

df = engine.load_data('working_ict_setup.csv')
df['atr'] = engine.calculate_atr(df)
df = engine.identify_swing_highs_lows(df)

print("Detailed check of bars 34-40")
print("="*80)

for i in range(34, 41):
    if i >= len(df):
        continue
    
    current = df.iloc[i]
    print(f"\nBar {i}: {current['time']}")
    
    hour_utc = current['time'].hour
    gate1 = engine.in_session(hour_utc)
    print(f"  Gate 1 - Session: {'✓' if gate1 else '✗'}")
    if not gate1:
        continue
    
    gate2 = current['spread'] <= engine.MAX_SPREAD_EURUSD
    print(f"  Gate 2 - Spread: {'✓' if gate2 else '✗'}")
    if not gate2:
        continue
    
    gate3 = engine.detect_regime(df, i)
    print(f"  Gate 3 - Regime: {'✓' if gate3 else '✗'}")
    if not gate3:
        continue
    
    sweep_type, sweep_level = engine.detect_liquidity_sweep(df, i)
    print(f"  Gate 4 - Sweep: {'✓' if sweep_type else '✗'} {sweep_type}")
    if not sweep_type:
        continue
    
    bos = engine.detect_bos(df, i)
    print(f"  Gate 5 - BOS: {'✓' if bos else '✗'} {bos}")
    if not bos:
        continue
    
    # Alignment check
    if (sweep_type == 'bullish_sweep' and bos == 'bullish_bos') or \
       (sweep_type == 'bearish_sweep' and bos == 'bearish_bos'):
        print(f"  ✓ Alignment OK")
    else:
        print(f"  ✗ Alignment FAILED: {sweep_type} vs {bos}")
        continue
    
    fvg_type, fvg_h, fvg_l, disp = engine.detect_displacement_and_fvg(df, i, "EURUSD")
    print(f"  Gate 6 - FVG: {'✓' if fvg_type else '✗'} {fvg_type}, Disp={disp:.1f}p")
    if not fvg_type:
        continue
    
    # Check FVG alignment
    if (sweep_type == 'bullish_sweep' and fvg_type == 'bullish_fvg') or \
       (sweep_type == 'bearish_sweep' and fvg_type == 'bearish_fvg'):
        print(f"  ✓ FVG Alignment OK")
    else:
        print(f"  ✗ FVG Alignment FAILED: {sweep_type} vs {fvg_type}")
        continue
    
    print(f"\n  🎯 ALL 6 GATES PASSED!")
    
    signal = engine.generate_signal(df, i, "EURUSD", engine.MAX_SPREAD_EURUSD)
    if signal:
        print(f"  ✓✓✓ SIGNAL GENERATED!")
        print(f"      {signal}")
        break
    else:
        print(f"  ✗ No signal (Gate 7 entry logic failed)")
