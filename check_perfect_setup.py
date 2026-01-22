import sys
sys.path.insert(0, '.')
from huxorb_pro_engine import *

df = load_data('perfect_ict_setup.csv')
df['atr'] = calculate_atr(df)
df = identify_swing_highs_lows(df)

# Check bars 110-120
for i in range(110, 120):
    if i >= len(df):
        continue
    
    print(f"\n{'='*60}")
    print(f"Bar {i}: {df.iloc[i]['time']}")
    c = df.iloc[i]
    print(f"OHLC: {c['open']:.5f} / {c['high']:.5f} / {c['low']:.5f} / {c['close']:.5f}")
    
    # Check each gate
    hour = c['time'].hour
    print(f"1. Session (hour {hour}): {in_session(hour)}")
    print(f"2. Spread ({c['spread']}): {c['spread'] <= 20}")
    
    if i >= 24:
        regime = detect_regime(df, i)
        print(f"3. Regime: {regime}")
        if regime:
            print(f"   ATR[{i}]={df['atr'].iloc[i]:.5f}, Avg ATR[-10:]={df['atr'].iloc[i-10:i].mean():.5f}")
    
    sweep_type, sweep_level = detect_liquidity_sweep(df, i)
    print(f"4. Liquidity Sweep: {sweep_type} at {sweep_level:.5f if sweep_level else 'None'}")
    
    bos = detect_bos(df, i)
    print(f"5. BOS: {bos}")
    
    fvg_type, fvg_h, fvg_l, disp = detect_displacement_and_fvg(df, i)
    print(f"6. FVG: {fvg_type}, Disp={disp:.1f}p")
    if fvg_type:
        print(f"   FVG zone: {fvg_l:.5f} to {fvg_h:.5f}")
    
    # Try generating signal
    signal = generate_signal(df, i, "EURUSD", 20)
    if signal:
        print(f"\n✓✓✓ SIGNAL GENERATED! ✓✓✓")
        print(f"   {signal}")
        break
    else:
        print(f"\n✗ No signal")
