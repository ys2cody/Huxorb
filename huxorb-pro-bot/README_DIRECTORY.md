# 🚀 Huxorb PRO Trading Bot

This directory contains the **PRO version** of the Huxorb trading bot with cryptocurrency exchange support.

## 📁 What's Different from the Original?

- **Multi-Exchange Support**: Binance, Coinbase, Kraken, OKX
- **Advanced Order Types**: Market, Limit, Stop-Loss, Take-Profit
- **Real-time WebSocket**: Live price feeds and order updates
- **Professional Risk Management**: Position sizing, drawdown limits
- **Backtesting Engine**: Test strategies on historical data

## 🗂️ Structure

```
huxorb-pro-bot/
├── core/                    # Core trading engine
│   ├── strategy/           # Trading strategies
│   ├── risk/               # Risk management
│   ├── exchange/           # Exchange connectors
│   └── backtest/           # Backtesting engine
├── scripts/                # Utility scripts
├── tests/                  # Unit tests
└── requirements.txt        # Python dependencies
```

## 🔧 Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure exchange:**
   ```bash
   cd scripts
   python setup_exchange.py
   ```

3. **Run the bot:**
   ```bash
   python main.py
   ```

## 📖 Documentation

- See [README.md](./README.md) for full documentation
- See [README_EXCHANGE.md](./README_EXCHANGE.md) for exchange setup

## ⚠️ Note

This is the **PRO version** - separate from the original Huxorb Forex bot in the root directory.

---

**Built:** March 2026
**Version:** 1.0.0
