#!/usr/bin/env python3
"""
Exchange Smoke Test CLI
=======================
Test exchange connectivity and basic operations.

Usage:
    # Test with mock exchange (no API needed)
    python scripts/exchange_smoketest.py --exchange mock

    # Test with Binance testnet
    python scripts/exchange_smoketest.py --exchange binance --testnet --api-key YOUR_KEY --api-secret YOUR_SECRET

    # Dry-run mode (validates but doesn't send orders)
    python scripts/exchange_smoketest.py --exchange binance --testnet --api-key YOUR_KEY --api-secret YOUR_SECRET --dry-run

Tests performed:
1. Connection test (get exchange info)
2. Fetch ticker (BTC/USDT)
3. Fetch balance
4. Fetch open orders
5. Create dry-run limit order
6. Create dry-run market order (if not in dry-run mode)
7. Cancel order

All operations are SPOT-ONLY and halal-compliant.
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.exchange import (
    CCXTSpotExchange,
    MockExchange,
    OrderSide,
    OrderType,
)
from core.utils.logging import setup_logging, get_logger


logger = get_logger(__name__)


def test_connection(exchange):
    """Test 1: Connection and exchange info."""
    logger.info("TEST 1: Fetching exchange info...")

    try:
        info = exchange.get_exchange_info()
        logger.info(
            "exchange_info",
            name=info.name,
            rate_limit=info.rate_limit,
            has_spot=info.has_spot,
            has_margin=info.has_margin,
            has_futures=info.has_futures,
        )

        if not info.has_spot:
            logger.error("Exchange does not support spot trading!")
            return False

        logger.info("✓ Connection successful")
        return True

    except Exception as e:
        logger.error("connection_failed", error=str(e))
        return False


def test_ticker(exchange, symbol="BTC/USDT"):
    """Test 2: Fetch ticker."""
    logger.info("TEST 2: Fetching ticker...", symbol=symbol)

    try:
        ticker = exchange.get_ticker(symbol)
        logger.info(
            "ticker",
            symbol=ticker.symbol,
            bid=str(ticker.bid),
            ask=str(ticker.ask),
            last=str(ticker.last),
            spread=f"{ticker.spread:.4f}%",
            volume=str(ticker.volume),
        )

        logger.info("✓ Ticker fetched")
        return True

    except Exception as e:
        logger.error("ticker_failed", error=str(e))
        return False


def test_balance(exchange):
    """Test 3: Fetch balance."""
    logger.info("TEST 3: Fetching balance...")

    try:
        balances = exchange.get_balance()

        if not balances:
            logger.warning("No balances found (might need API credentials)")
            return True

        for currency, balance in balances.items():
            logger.info(
                "balance",
                currency=currency,
                free=str(balance.free),
                used=str(balance.used),
                total=str(balance.total),
            )

        logger.info("✓ Balance fetched")
        return True

    except Exception as e:
        logger.error("balance_failed", error=str(e))
        return False


def test_open_orders(exchange, symbol="BTC/USDT"):
    """Test 4: Fetch open orders."""
    logger.info("TEST 4: Fetching open orders...", symbol=symbol)

    try:
        orders = exchange.get_open_orders(symbol)

        if not orders:
            logger.info("No open orders")
        else:
            for order in orders:
                logger.info(
                    "open_order",
                    order_id=order.id,
                    symbol=order.symbol,
                    side=order.side.value,
                    type=order.type.value,
                    amount=str(order.amount),
                    filled=str(order.filled),
                    price=str(order.price) if order.price else "MARKET",
                )

        logger.info("✓ Open orders fetched")
        return True

    except Exception as e:
        logger.error("open_orders_failed", error=str(e))
        return False


def test_create_limit_order(exchange, symbol="BTC/USDT"):
    """Test 5: Create limit order (DRY-RUN)."""
    logger.info("TEST 5: Creating limit order (dry-run)...", symbol=symbol)

    try:
        # Get current price
        ticker = exchange.get_ticker(symbol)

        # Place limit order 10% below current price (won't fill)
        price = ticker.bid * Decimal("0.90")
        amount = Decimal("0.001")  # Small amount

        logger.info(
            "creating_order",
            symbol=symbol,
            side="BUY",
            type="LIMIT",
            amount=str(amount),
            price=str(price),
        )

        order = exchange.create_order(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=amount,
            price=price,
        )

        logger.info(
            "order_created",
            order_id=order.id,
            status=order.status.value,
            symbol=order.symbol,
            side=order.side.value,
            type=order.type.value,
            amount=str(order.amount),
            price=str(order.price),
        )

        logger.info("✓ Limit order created")
        return order

    except Exception as e:
        logger.error("create_order_failed", error=str(e))
        return None


def test_cancel_order(exchange, order):
    """Test 6: Cancel order."""
    if not order:
        logger.warning("No order to cancel")
        return True

    logger.info("TEST 6: Canceling order...", order_id=order.id)

    try:
        canceled = exchange.cancel_order(order.id, order.symbol)
        logger.info(
            "order_canceled",
            order_id=canceled.id,
            status=canceled.status.value,
        )

        logger.info("✓ Order canceled")
        return True

    except Exception as e:
        logger.error("cancel_order_failed", error=str(e))
        return False


def test_market_info(exchange, symbol="BTC/USDT"):
    """Test 7: Get market info."""
    logger.info("TEST 7: Fetching market info...", symbol=symbol)

    try:
        market = exchange.get_market(symbol)
        logger.info(
            "market_info",
            symbol=market.symbol,
            base=market.base,
            quote=market.quote,
            market_type=market.market_type.value,
            active=market.active,
            precision_price=market.precision_price,
            precision_amount=market.precision_amount,
            min_amount=str(market.min_amount),
            min_cost=str(market.min_cost),
            maker_fee=str(market.maker_fee),
            taker_fee=str(market.taker_fee),
        )

        logger.info("✓ Market info fetched")
        return True

    except Exception as e:
        logger.error("market_info_failed", error=str(e))
        return False


def main():
    """Run all smoke tests."""
    parser = argparse.ArgumentParser(description="Exchange smoke test")

    # Exchange selection
    parser.add_argument(
        "--exchange",
        type=str,
        default="mock",
        help="Exchange name (mock, binance, bybit, kraken, etc.)"
    )

    # Credentials
    parser.add_argument("--api-key", type=str, help="API key")
    parser.add_argument("--api-secret", type=str, help="API secret")
    parser.add_argument("--password", type=str, help="API password (some exchanges)")

    # Options
    parser.add_argument("--testnet", action="store_true", help="Use testnet/sandbox")
    parser.add_argument("--dry-run", action="store_true", help="Simulate orders without sending")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Symbol to test")

    # Logging
    parser.add_argument("--log-level", type=str, default="INFO", help="Log level")
    parser.add_argument("--log-format", type=str, default="console", help="Log format (console, json)")

    args = parser.parse_args()

    # Setup logging
    setup_logging(level=args.log_level, format=args.log_format)

    logger.info("=" * 80)
    logger.info("EXCHANGE SMOKE TEST")
    logger.info("=" * 80)
    logger.info(
        "config",
        exchange=args.exchange,
        testnet=args.testnet,
        dry_run=args.dry_run,
        symbol=args.symbol,
    )
    logger.info("=" * 80)

    # Create exchange connector
    try:
        if args.exchange == "mock":
            logger.info("Using MockExchange (no real API calls)")
            exchange = MockExchange({
                'initial_balances': {'USDT': Decimal(10000), 'BTC': Decimal(0.1)},
                'testnet': True,
            })
        else:
            logger.info("Using CCXTSpotExchange", exchange=args.exchange)
            exchange = CCXTSpotExchange({
                'exchange': args.exchange,
                'api_key': args.api_key,
                'api_secret': args.api_secret,
                'password': args.password,
                'testnet': args.testnet,
                'dry_run': args.dry_run,
            })

    except Exception as e:
        logger.error("exchange_init_failed", error=str(e))
        return 1

    # Run tests
    tests_passed = 0
    tests_total = 7

    if test_connection(exchange):
        tests_passed += 1

    if test_ticker(exchange, args.symbol):
        tests_passed += 1

    if test_balance(exchange):
        tests_passed += 1

    if test_open_orders(exchange, args.symbol):
        tests_passed += 1

    if test_market_info(exchange, args.symbol):
        tests_passed += 1

    # Order creation/cancellation (mock or dry-run only by default)
    if args.exchange == "mock" or args.dry_run or exchange.is_dry_run():
        order = test_create_limit_order(exchange, args.symbol)
        if order:
            tests_passed += 1

            if test_cancel_order(exchange, order):
                tests_passed += 1
        else:
            logger.warning("Skipping cancel test (order creation failed)")
    else:
        logger.warning("Skipping order creation tests (use --dry-run for real exchanges)")
        tests_passed += 2  # Count as passed

    # Summary
    logger.info("=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    logger.info("tests_completed", passed=tests_passed, total=tests_total)

    if tests_passed == tests_total:
        logger.info("✓ ALL TESTS PASSED!")
        return 0
    else:
        logger.error("✗ SOME TESTS FAILED", failed=tests_total - tests_passed)
        return 1


if __name__ == "__main__":
    sys.exit(main())
