import pandas as pd

# Read the tab-separated data
df = pd.read_csv('EURUSD1440.csv', sep='\t', header=None, 
                 names=['time', 'open', 'high', 'low', 'close', 'volume'])

# Add spread column (assume 15 points for daily data)
df['spread'] = 15

# Save in correct format
df.to_csv('EURUSD_D1.csv', index=False)

print(f"✓ Converted {len(df)} daily bars")
print(f"✓ Date range: {df['time'].min()} to {df['time'].max()}")
print(f"✓ Saved to: EURUSD_D1.csv")
