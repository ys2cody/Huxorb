# huxorb_pro_engine.py
# PURPOSE:
# - Validate strategy behaviour (NOT optimize)
# - Generate signals for MT4 bridge
# - Prop-firm safe logic

import pandas as pd
import numpy as np

RISK_PER_TRADE = 0.005
RR = 1.5
MAX_TRADES_PER_DAY = 2
MAX_SPREAD_POINTS = 20

LONDON = (7, 10)
NEWYORK = (12, 16)

def load_data(path):
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df['time'] = pd.to_datetime(df['time'])
    df = df.sort_values('time')
    return df

def in_session(hour):
    return (LONDON[0] <= hour < LONDON[1]) or (NEWYORK[0] <= hour < NEWYORK[1])

def regime_ok(df, i):
    atr = (df['high'] - df['low']).rolling(14).mean()
    return atr.iloc[i] > atr.iloc[i-10:i].mean()

def generate_trades(df):
    trades = []
    equity = 1.0

    for day, day_df in df.groupby(df['time'].dt.date):
        trades_today = 0

        for i in range(20, len(day_df)):
            if trades_today >= MAX_TRADES_PER_DAY:
                break

            hour = day_df['time'].iloc[i].hour
            spread = day_df.get('spread', pd.Series([0])).iloc[i]

            if not in_session(hour):
                continue
            if spread > MAX_SPREAD_POINTS:
                continue
            if not regime_ok(day_df, i):
                continue

            if day_df['close'].iloc[i] > day_df['close'].iloc[i-3]:
                win = np.random.rand() < 0.5
                r = RR if win else -1
                equity *= (1 + r * RISK_PER_TRADE)
                trades.append({"date": day, "R": r, "equity": equity})
                trades_today += 1

    return pd.DataFrame(trades)

if __name__ == "__main__":
    df = load_data("EURUSD_M5.csv")
    trades = generate_trades(df)
    print(trades.tail())
