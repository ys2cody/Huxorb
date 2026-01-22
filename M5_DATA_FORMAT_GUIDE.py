#!/usr/bin/env python3
"""
M5 Data Format Reference
========================

This shows the EXACT format needed for HuxORB PRO backtesting.
"""

print("""
╔══════════════════════════════════════════════════════════════════════════╗
║                  CORRECT M5 DATA FORMAT EXAMPLE                          ║
╚══════════════════════════════════════════════════════════════════════════╝

Your CSV file should look EXACTLY like this:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

time,open,high,low,close,volume,spread
2024-01-15 07:00:00,1.08920,1.08935,1.08915,1.08930,1234,15
2024-01-15 07:05:00,1.08930,1.08945,1.08925,1.08940,1456,14
2024-01-15 07:10:00,1.08940,1.08955,1.08935,1.08950,1567,16
2024-01-15 07:15:00,1.08950,1.08965,1.08945,1.08960,1678,15
2024-01-15 07:20:00,1.08960,1.08975,1.08955,1.08970,1789,17
2024-01-15 07:25:00,1.08970,1.08985,1.08965,1.08980,1890,15
2024-01-15 07:30:00,1.08980,1.08995,1.08975,1.08990,1901,16
...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COLUMN DEFINITIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  time:     Timestamp in format "YYYY-MM-DD HH:MM:SS"
            Must be in UTC timezone
            5-minute intervals (00, 05, 10, 15, 20, etc.)

  open:     Opening price at start of 5-minute bar
            5-digit precision (e.g., 1.08920)

  high:     Highest price during 5-minute bar
            5-digit precision

  low:      Lowest price during 5-minute bar
            5-digit precision

  close:    Closing price at end of 5-minute bar
            5-digit precision

  volume:   Tick volume (number of price changes)
            Integer (optional, can use 1000 if not available)

  spread:   Spread in points (5-digit broker)
            15 points = 1.5 pips (typical for EURUSD)
            Optional: can use 15 if not available

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KEY REQUIREMENTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✓ Must be M5 (5-minute) bars - NOT D1, H1, M1
  ✓ Must be sorted by time (oldest first)
  ✓ Must have header row (column names)
  ✓ Time must be in UTC (NOT broker time)
  ✓ Minimum 3 months of data (6-12 months recommended)
  ✓ No gaps > 1 hour (missing data causes issues)
  ✓ Prices in 5-digit format (e.g., 1.08920, NOT 1.0892)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHAT YOU HAVE vs WHAT YOU NEED:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Your File (EURUSD1440.csv):
  ────────────────────────────────────────────────────────────────
  2010-01-11 00:00  1.45149  1.45539  1.44769  1.45063  68096
  2010-01-12 00:00  1.45064  1.45479  1.44507  1.44750  79503
  2010-01-13 00:00  1.44751  1.45797  1.44550  1.45215  80530
  ...

  ❌ Format: Tab-separated (should be comma-separated)
  ❌ Timeframe: D1 daily (need M5 = 5-minute)
  ❌ Frequency: 1 bar per day (need 288 bars per day)
  ❌ Missing: spread column


  What You Need (EURUSD_M5.csv):
  ────────────────────────────────────────────────────────────────
  time,open,high,low,close,volume,spread
  2024-01-15 07:00:00,1.08920,1.08935,1.08915,1.08930,1234,15
  2024-01-15 07:05:00,1.08930,1.08945,1.08925,1.08940,1456,14
  2024-01-15 07:10:00,1.08940,1.08955,1.08935,1.08950,1567,16
  ...

  ✓ Format: Comma-separated CSV
  ✓ Timeframe: M5 (5-minute bars)
  ✓ Frequency: 288 bars per day
  ✓ Has: spread column (or add default 15)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HOW TO GET M5 DATA (Step-by-Step):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPTION 1: HistData.com (Easiest)
─────────────────────────────────

  Step 1: Go to https://www.histdata.com/download-free-forex-data/

  Step 2: Download EURUSD M1 (1-minute) data
          - Select: EURUSD
          - Format: ASCII
          - Download: Last 6-12 months (multiple zip files)

  Step 3: Extract all zip files to a folder

  Step 4: Combine and resample to M5 using this script:

          import pandas as pd
          import glob

          # Load all M1 files
          files = glob.glob('EURUSD_*.csv')
          dfs = []
          for f in files:
              df = pd.read_csv(f, names=['time','open','high','low','close','volume'])
              dfs.append(df)

          # Combine
          df = pd.concat(dfs, ignore_index=True)
          df['time'] = pd.to_datetime(df['time'], format='%Y%m%d %H%M%S')
          df = df.sort_values('time').set_index('time')

          # Resample M1 → M5
          df_m5 = df.resample('5T').agg({
              'open': 'first',
              'high': 'max',
              'low': 'min',
              'close': 'last',
              'volume': 'sum'
          }).dropna()

          # Add spread
          df_m5['spread'] = 15

          # Save
          df_m5.reset_index().to_csv('EURUSD_M5.csv', index=False)
          print(f"Created EURUSD_M5.csv with {len(df_m5)} bars")

  Step 5: Run backtest:
          python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --full-analysis


OPTION 2: DukasCopy (Best Quality)
───────────────────────────────────

  Step 1: Go to https://www.dukascopy.com/swiss/english/marketwatch/historical/

  Step 2: Select:
          - Instrument: EUR/USD
          - Timeframe: M5
          - Date Range: Last 6 months
          - Format: CSV

  Step 3: Click "Get Data" and download

  Step 4: Format the CSV if needed (add header, adjust columns)

  Step 5: Run backtest:
          python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --full-analysis


OPTION 3: MT4 Export (If You Have MT4)
───────────────────────────────────────

  Step 1: Open MetaTrader 4

  Step 2: Tools → History Center

  Step 3: Select: EURUSD → 5 Minutes (M5)

  Step 4: Double-click to download history

  Step 5: Export:
          - Right-click on EURUSD M5
          - Export → Choose location
          - Save as EURUSD_M5.csv

  Step 6: Format the CSV (MT4 exports may need column adjustment)

  Step 7: Run backtest:
          python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --full-analysis

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILE SIZE EXPECTATIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  3 months M5:    ~18,000 bars   →   ~3-5 MB
  6 months M5:    ~37,000 bars   →   ~7-10 MB
  12 months M5:   ~75,000 bars   →   ~15-20 MB

  If your file is < 1 MB for 6 months, it's probably NOT M5 data!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ONCE YOU HAVE M5 DATA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run this to validate the format:

  python -c "
  import pandas as pd
  df = pd.read_csv('EURUSD_M5.csv')
  print('Bars:', len(df))
  print('Columns:', list(df.columns))
  print('Date range:', df['time'].min(), 'to', df['time'].max())
  print('Sample:')
  print(df.head())
  "

Expected output:
  Bars: 75000
  Columns: ['time', 'open', 'high', 'low', 'close', 'volume', 'spread']
  Date range: 2024-01-01 00:00:00 to 2024-12-31 23:55:00
  Sample:
                     time     open     high      low    close  volume  spread
  0  2024-01-01 00:00:00  1.10450  1.10465  1.10445  1.10460    1234      15
  1  2024-01-01 00:05:00  1.10460  1.10475  1.10455  1.10470    1456      14
  ...

Then run backtest:
  python huxorb_pro_engine.py backtest --csv EURUSD_M5.csv --full-analysis

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUMMARY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Your D1 data:  ❌ Won't work (too coarse for ICT patterns)
  Need M5 data:  ✓ 5-minute bars showing intraday price action
  Best source:   HistData.com (free) or DukasCopy (quality)
  File size:     ~10-20 MB for 6-12 months
  Format:        CSV with time,open,high,low,close,volume,spread

Once you have proper M5 data, the backtest will show 50-120 trades and
give you real validation of the strategy!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
