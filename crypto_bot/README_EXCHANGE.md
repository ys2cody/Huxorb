# HuxORB Crypto Bot - Exchange Layer Setup Guide

## 📋 Overview

The exchange layer provides **spot-only, halal-compliant** connectivity to cryptocurrency exchanges via CCXT.

**Key Features:**
- ✅ **Spot trading only** (no margin, no futures, no leverage)
- ✅ **Exchange-agnostic** (works with 100+ exchanges via CCXT)
- ✅ **Testnet support** (Binance, Bybit)
- ✅ **Dry-run mode** (validate orders without sending)
- ✅ **Type-safe** (Pydantic models with validation)
- ✅ **Production-ready** (retry logic, rate limiting, structured logging)

**Supported Exchanges:** Binance, Bybit, Kraken, Coinbase, OKX, KuCoin, and 100+ more via CCXT.

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd crypto_bot
pip install -r requirements.txt
```

### 2. Test with Mock Exchange (No API Needed)

```bash
python scripts/exchange_smoketest.py --exchange mock
```

Expected output:
```
✓ Connection successful
✓ Ticker fetched
✓ Balance fetched
✓ Open orders fetched
✓ Market info fetched
✓ Limit order created
✓ Order canceled
✓ ALL TESTS PASSED!
```

### 3. Test with Binance Testnet

```bash
# Create .env file with your testnet credentials
cat > .env <<EOF
BINANCE_TESTNET_API_KEY=your_testnet_api_key
BINANCE_TESTNET_API_SECRET=your_testnet_api_secret
EOF

# Run smoke test
python scripts/exchange_smoketest.py \
    --exchange binance \
    --testnet \
    --api-key $BINANCE_TESTNET_API_KEY \
    --api-secret $BINANCE_TESTNET_API_SECRET \
    --dry-run
```

---

## 🔑 API Key Setup (Exchange-Specific)

### Binance Testnet

1. Go to https://testnet.binance.vision/
2. Click "Generate HMAC_SHA256 Key"
3. Save API Key and Secret Key
4. **Testnet has fake balance** - you get free test USDT/BTC

**Important:**
- Testnet keys **DO NOT** work on mainnet
- Testnet is safe for testing (no real money)

### Binance Mainnet (Production)

1. Go to https://www.binance.com/en/my/settings/api-management
2. Create new API key with **Spot Trading** enabled
3. **Enable "Spot & Margin Trading"** permission
4. **Restrict to trusted IPs** (your server IP)
5. **DO NOT enable withdrawal permissions** (not needed for trading)

**Security Best Practices:**
- Never share API keys
- Use IP whitelist restrictions
- Store keys in `.env` file (never in code)
- Rotate keys regularly
- Use testnet for all testing

### Bybit Testnet

1. Go to https://testnet.bybit.com/
2. Register account
3. Go to API Management → Create API Key
4. Enable "Spot Trading" permission

### Other Exchanges

See exchange documentation:
- Kraken: https://support.kraken.com/hc/en-us/articles/360000919966
- Coinbase: https://help.coinbase.com/en/exchange/managing-my-account/how-to-create-an-api-key
- OKX: https://www.okx.com/academy/en/how-to-create-an-api-on-okx

---

## 📝 Configuration

### Method 1: Environment Variables (.env file)

```bash
# .env file
CRYPTO_BOT_EXCHANGE__EXCHANGE=binance
CRYPTO_BOT_EXCHANGE__API_KEY=your_api_key
CRYPTO_BOT_EXCHANGE__API_SECRET=your_api_secret
CRYPTO_BOT_EXCHANGE__TESTNET=true
CRYPTO_BOT_EXCHANGE__DRY_RUN=false

CRYPTO_BOT_RISK__RISK_PER_TRADE_PCT=0.5
CRYPTO_BOT_RISK__MAX_OPEN_TRADES=3

CRYPTO_BOT_TRADING__SYMBOLS=["BTC/USDT","ETH/USDT"]
```

Load in Python:
```python
from core.config import load_config

config = load_config(env_file=".env")
```

### Method 2: Dictionary (Programmatic)

```python
from core.config import load_config

config = load_config(config_dict={
    'exchange': {
        'exchange': 'binance',
        'api_key': 'your_key',
        'api_secret': 'your_secret',
        'testnet': True,
        'dry_run': False,
    },
    'risk': {
        'risk_per_trade_pct': 0.5,
        'max_open_trades': 3,
    },
    'trading': {
        'symbols': ['BTC/USDT', 'ETH/USDT'],
    }
})
```

---

## 🎯 Usage Examples

### Example 1: Fetch Ticker

```python
from core.exchange import CCXTSpotExchange

# Initialize exchange
exchange = CCXTSpotExchange({
    'exchange': 'binance',
    'testnet': True,
})

# Get ticker
ticker = exchange.get_ticker('BTC/USDT')
print(f"BTC/USDT: Bid={ticker.bid}, Ask={ticker.ask}, Spread={ticker.spread:.4f}%")
```

### Example 2: Check Balance

```python
# Get all balances
balances = exchange.get_balance()

for currency, balance in balances.items():
    print(f"{currency}: {balance.free} free, {balance.used} locked, {balance.total} total")
```

### Example 3: Create Market Order (Dry-Run)

```python
from core.exchange import OrderSide, OrderType
from decimal import Decimal

# Create exchange in dry-run mode
exchange = CCXTSpotExchange({
    'exchange': 'binance',
    'testnet': True,
    'dry_run': True,  # Won't send real order
})

# Create market buy order
order = exchange.create_order(
    symbol='BTC/USDT',
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    amount=Decimal('0.001'),  # 0.001 BTC
)

print(f"Order created: {order.id}, Status: {order.status}")
```

### Example 4: Create Limit Order (Real)

```python
from decimal import Decimal

# Create exchange (NOT dry-run)
exchange = CCXTSpotExchange({
    'exchange': 'binance',
    'testnet': True,
    'api_key': 'your_key',
    'api_secret': 'your_secret',
    'dry_run': False,  # REAL ORDER
})

# Get current price
ticker = exchange.get_ticker('BTC/USDT')

# Place limit buy order 5% below current price
limit_price = ticker.bid * Decimal('0.95')

order = exchange.create_order(
    symbol='BTC/USDT',
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    amount=Decimal('0.001'),
    price=limit_price,
)

print(f"Limit order placed: {order.id} @ {limit_price}")
```

### Example 5: Cancel All Open Orders

```python
# Get open orders
open_orders = exchange.get_open_orders('BTC/USDT')
print(f"Open orders: {len(open_orders)}")

# Cancel all
canceled = exchange.cancel_all_orders('BTC/USDT')
print(f"Canceled {len(canceled)} orders")
```

---

## 🛡️ Halal Compliance Enforcement

The exchange layer **enforces halal compliance** at multiple levels:

### 1. Model-Level Validation
```python
# Market model rejects non-spot markets
market = Market(
    symbol='BTC/USDT',
    market_type=MarketType.SPOT,  # Only SPOT allowed
    # market_type=MarketType.FUTURES  # Would raise ValueError
)
```

### 2. Exchange Connector Validation
```python
# CCXTSpotExchange only loads spot markets
markets = exchange.get_markets()
# Returns: {'BTC/USDT': Market(...), 'ETH/USDT': Market(...)}
# Excludes: BTCUSDT-PERP, ETHUSDT-FUTURES, etc.
```

### 3. Order Parameter Validation
```python
# Forbidden parameters raise errors
exchange.create_order(
    symbol='BTC/USDT',
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    amount=Decimal('0.01'),
    params={'leverage': 10}  # ValueError: Parameter 'leverage' not allowed
)
```

**Result:** Impossible to accidentally trade on margin/futures.

---

## 🧪 Testing

### Run Unit Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_exchange_models.py -v

# Specific test
pytest tests/test_exchange_mock.py::TestMockExchangeOrders::test_create_market_buy_order -v
```

### Run Smoke Tests

```bash
# Mock exchange (fast, no API)
python scripts/exchange_smoketest.py --exchange mock

# Binance testnet (real API, fake money)
python scripts/exchange_smoketest.py \
    --exchange binance \
    --testnet \
    --api-key YOUR_KEY \
    --api-secret YOUR_SECRET \
    --dry-run

# With JSON logging
python scripts/exchange_smoketest.py \
    --exchange mock \
    --log-format json
```

---

## 🐛 Troubleshooting

### Error: "Exchange does not support spot trading"

**Cause:** Exchange may not have spot markets or CCXT config issue.

**Solution:**
```python
# Check exchange capabilities
exchange = CCXTSpotExchange({'exchange': 'binance'})
info = exchange.get_exchange_info()
print(f"Has spot: {info.has_spot}")
```

### Error: "Insufficient balance"

**Cause:** Not enough USDT/BTC for order.

**Solution:**
```python
# Check balance before order
balances = exchange.get_balance()
print(f"USDT: {balances.get('USDT', 'None')}")
print(f"BTC: {balances.get('BTC', 'None')}")

# On testnet, fund your account at https://testnet.binance.vision/
```

### Error: "Authentication failed"

**Cause:** Invalid API key/secret or wrong testnet/mainnet.

**Solution:**
1. Verify API key is correct (no spaces)
2. Check testnet=True matches your API key source
3. Binance: Testnet keys start with `vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A`
4. Mainnet keys are different - don't mix them up

### Error: "Symbol not found"

**Cause:** Symbol format or symbol doesn't exist on exchange.

**Solution:**
```python
# List available markets
markets = exchange.get_markets()
print(f"Available symbols: {list(markets.keys())[:10]}")

# Use correct format (BTC/USDT not BTCUSDT)
ticker = exchange.get_ticker('BTC/USDT')  # ✓ Correct
# ticker = exchange.get_ticker('BTCUSDT')  # ✗ Wrong (will auto-convert but better to use /)
```

### Error: "Rate limit exceeded"

**Cause:** Too many API requests.

**Solution:**
```python
# CCXT has built-in rate limiting
exchange = CCXTSpotExchange({
    'exchange': 'binance',
    'rate_limit': True,  # Enable (default)
})

# If still hitting limits, increase retry count
exchange = CCXTSpotExchange({
    'exchange': 'binance',
    'max_retries': 5,  # Will wait longer between retries
})
```

---

## 📊 Exchange Comparison

| Exchange | Spot | Testnet | Fees (Maker/Taker) | Min Order | Notes |
|----------|------|---------|-------------------|-----------|-------|
| **Binance** | ✅ | ✅ | 0.10% / 0.10% | $10 | Best liquidity |
| **Bybit** | ✅ | ✅ | 0.10% / 0.10% | $10 | Good for derivatives (we use spot only) |
| **Kraken** | ✅ | ❌ | 0.16% / 0.26% | $10 | High fees |
| **Coinbase** | ✅ | ❌ | 0.40% / 0.60% | $10 | US-regulated, high fees |
| **OKX** | ✅ | ✅ | 0.08% / 0.10% | $10 | Low fees |

**Recommendation:** Start with **Binance testnet**, then move to **Binance mainnet** when ready.

---

## 🔒 Security Checklist

Before going live with real money:

- [ ] ✅ Test on **testnet** first (at least 1 week)
- [ ] ✅ Use **IP whitelist** on API keys
- [ ] ✅ Enable **only Spot Trading** permission (no withdrawal)
- [ ] ✅ Store API keys in `.env` file (not in code)
- [ ] ✅ Add `.env` to `.gitignore` (never commit keys)
- [ ] ✅ Start with **small capital** ($100-500)
- [ ] ✅ Enable **dry-run mode** for initial production test
- [ ] ✅ Monitor logs for **authentication errors**
- [ ] ✅ Set up **alerts** for failed orders
- [ ] ✅ Have **emergency stop** plan (cancel all orders script)

---

## 📚 Next Steps

After completing STEP 2 (Exchange Layer):

- **STEP 3:** RuleGuard system (risk manager, session filter, etc.)
- **STEP 4:** Strategy engine (port ICT concepts to crypto)
- **STEP 5:** Main trading bot loop
- **STEP 6:** Backtesting on historical crypto data
- **STEP 7:** Deploy to production

---

## 🆘 Support

If you encounter issues:

1. Check this README first
2. Run smoke test: `python scripts/exchange_smoketest.py --exchange mock`
3. Check logs (set `--log-level DEBUG` for verbose output)
4. Review test files in `tests/` for usage examples
5. Check CCXT documentation: https://docs.ccxt.com/

---

## ✅ STEP 2 COMPLETE!

You now have a production-grade, halal-compliant exchange connectivity layer.

**What you can do:**
- ✅ Connect to 100+ exchanges via CCXT
- ✅ Fetch tickers, balances, orders
- ✅ Place spot-only orders (market/limit)
- ✅ Test on testnet or mock exchange
- ✅ Use dry-run mode for safety

**Next:** STEP 3 - RuleGuard System (risk management, session filters, news filters)
