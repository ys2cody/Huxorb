# HuxORB Crypto Trading Bot

**Professional Spot Trading System for Cryptocurrency Markets**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## 🎯 Overview

HuxORB Crypto Bot is a **production-ready, halal-compliant spot trading system** for cryptocurrency exchanges. Built with institutional-grade architecture, it provides a clean abstraction layer for automated trading strategies.

### ✨ Key Features

- **🕌 Halal-Compliant**: Spot trading only, no leverage/margin/futures
- **🔌 Multi-Exchange Support**: Unified interface for Binance, Coinbase, Kraken, etc.
- **🧪 Built-in Testing**: MockExchange for development and unit tests
- **📊 Production-Ready**: Structured logging, type safety, comprehensive error handling
- **🚀 Fast & Reliable**: Async-ready architecture with rate limiting

## 📦 Installation

### Requirements

- Python 3.9+
- pip or Poetry

### Quick Start

```bash
# Clone the repository
git clone https://github.com/ys2cody/huxorb-crypto-bot.git
cd huxorb-crypto-bot

# Install dependencies
pip install -r requirements.txt

# Run smoke tests
python scripts/exchange_smoketest.py --exchange mock
```

## 🚀 Usage

### Basic Example

```python
from crypto_bot.core.exchange import create_exchange
from decimal import Decimal

# Create exchange instance (testnet mode)
exchange = create_exchange('binance', {
    'api_key': 'your_api_key',
    'api_secret': 'your_secret',
    'testnet': True,
})

# Get current price
ticker = exchange.get_ticker('BTC/USDT')
print(f"BTC Price: ${ticker.last}")

# Place market buy order
order = exchange.create_order(
    symbol='BTC/USDT',
    side='buy',
    order_type='market',
    amount=Decimal('0.001'),
)
print(f"Order placed: {order.id}")

# Check balance
balances = exchange.get_balance()
print(f"USDT Balance: {balances['USDT'].free}")
```

### Mock Exchange (Testing)

```python
from crypto_bot.core.exchange import create_exchange
from decimal import Decimal

# Create mock exchange for testing
exchange = create_exchange('mock', {
    'initial_balances': {'USDT': 10000, 'BTC': 0.5},
    'base_prices': {'BTC/USDT': 50000},
})

# Test your strategy without real money
order = exchange.create_order('BTC/USDT', 'buy', 'market', Decimal('0.01'))
print(f"Test order: {order.status}")  # CLOSED (instant fill in mock)
```

## 📁 Project Structure

```
huxorb-crypto-bot/
├── core/
│   ├── exchange/          # Exchange abstraction layer
│   │   ├── base.py        # IExchange interface
│   │   ├── ccxt_spot.py   # CCXT implementation (real exchanges)
│   │   ├── mock.py        # MockExchange (testing)
│   │   └── models.py      # Data models (Order, Balance, etc.)
│   ├── utils/             # Utilities
│   │   └── logging.py     # Structured logging
│   └── config.py          # Configuration management
├── scripts/
│   └── exchange_smoketest.py  # CLI testing tool
├── tests/                 # Unit tests
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## 🧪 Testing

### Run All Tests

```bash
# Unit tests
pytest tests/ -v

# Smoke tests (quick validation)
python scripts/exchange_smoketest.py --exchange mock

# Test with real exchange (testnet)
python scripts/exchange_smoketest.py --exchange binance --testnet
```

### Expected Output

```
🔬 Exchange Smoke Test: mock
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Exchange info
✓ Market data (BTC/USDT)
✓ Initial balance
✓ Create market buy order
✓ Order filled
✓ Balance updated
✓ Get open orders

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ ALL TESTS PASSED! (7/7)
```

## 🏗️ Architecture

### Exchange Layer (STEP 2 - Complete)

The exchange connector provides a clean, unified interface to cryptocurrency exchanges:

**Key Components:**

1. **IExchange Interface** (`base.py`)
   - Abstract base class defining the contract
   - Type-safe, Pythonic API
   - Validation and error handling

2. **CCXTSpotExchange** (`ccxt_spot.py`)
   - Real exchange implementation using CCXT
   - Supports 100+ exchanges
   - Rate limiting, retry logic

3. **MockExchange** (`mock.py`)
   - In-memory simulation for testing
   - Deterministic, fast, no API calls
   - Perfect for unit tests and development

4. **Data Models** (`models.py`)
   - Immutable dataclasses (Order, Balance, Ticker)
   - Type hints for IDE support
   - Validation built-in

### Design Principles

- **Separation of Concerns**: Exchange logic isolated from strategy logic
- **Dependency Inversion**: Code depends on interfaces, not implementations
- **Type Safety**: Full type hints for catch errors early
- **Testability**: MockExchange enables fast, reliable testing
- **Production-Ready**: Logging, error handling, rate limiting included

## 🔐 Security & Compliance

### Halal Trading Compliance

This bot is designed for **spot trading only**:

✅ **Allowed:**
- Spot market purchases (own the asset)
- Market and limit orders
- Portfolio rebalancing

❌ **Not Supported:**
- Margin/leverage trading
- Futures/derivatives
- Short selling
- Lending/borrowing

### API Security

**Best Practices:**

1. **Use API Keys with Minimal Permissions**
   - Binance: Enable "Spot Trading" only, disable margin/futures
   - Coinbase: "Trade" permission only

2. **Never Commit Credentials**
   - Use environment variables
   - Add `.env` to `.gitignore`
   - Use secrets management in production

3. **Enable IP Whitelisting**
   - Restrict API access to your server's IP
   - Reduces risk if keys are compromised

4. **Use Testnet First**
   - Always test on testnet before live trading
   - Binance testnet: `testnet=True` in config

## 📊 Supported Exchanges

Via CCXT library (100+ exchanges):

- **Binance** (recommended)
- Coinbase
- Kraken
- Bybit
- OKX
- KuCoin
- Gate.io
- And many more...

## 🛣️ Roadmap

### ✅ Phase 1: Foundation (COMPLETE)
- Exchange connector layer
- MockExchange for testing
- Comprehensive unit tests
- Documentation

### 🚧 Phase 2: Strategy Engine (In Progress)
- Strategy base classes
- Position management
- Risk management
- Portfolio tracking

### 📋 Phase 3: Advanced Features (Planned)
- Backtesting engine
- Performance analytics
- Web dashboard
- Alert system (Telegram, email)

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Install dev dependencies
pip install -r requirements.txt
pip install pytest black mypy

# Format code
black core/ tests/

# Type check
mypy core/

# Run tests
pytest tests/ -v
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

**IMPORTANT:** This software is for educational and research purposes only.

- Cryptocurrency trading carries significant risk
- You can lose all your capital
- Past performance does not guarantee future results
- Always test thoroughly on testnet before live trading
- The authors are not responsible for any financial losses

**Trade responsibly. Never invest more than you can afford to lose.**

## 📞 Support

- **Documentation**: See [README_EXCHANGE.md](README_EXCHANGE.md) for detailed exchange layer docs
- **Issues**: [GitHub Issues](https://github.com/ys2cody/huxorb-crypto-bot/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ys2cody/huxorb-crypto-bot/discussions)

## 🙏 Acknowledgments

- [CCXT](https://github.com/ccxt/ccxt) - Cryptocurrency exchange library
- [structlog](https://www.structlog.org/) - Structured logging
- The open-source trading community

---

**Built with ❤️ for halal-compliant algorithmic trading**
