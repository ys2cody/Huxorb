"""
Strategy Engine Example - KuCoin Spot
======================================
Demonstrates the complete trading flow:
1. Fetch OHLCV from KuCoin
2. Run regime classification
3. Generate trading signals
4. Validate via RuleGuard
5. (Optional) Execute trades

IMPORTANT: This is a demonstration script. Always test thoroughly
with testnet/dry-run before using real funds.
"""

import sys
from pathlib import Path
from decimal import Decimal

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from core.exchange.mock import MockExchange
from core.ruleguard import (
    RiskManager,
    SessionFilter,
    NewsFilter,
    ConfigProfiles,
    RuleGuard,
)
from core.strategy import StrategyEngine, StrategyConfig
from core.utils.logging import get_logger, setup_logging

setup_logging(level="INFO", format="console")
logger = get_logger(__name__)


def main():
    """Run strategy evaluation on mock data."""

    logger.info("=== Strategy Engine Example (KuCoin Spot) ===")

    # --- 1. Setup Exchange (Mock for demo) ---
    # In production, use:
    # from core.exchange import CCXTSpotExchange
    # exchange = CCXTSpotExchange(
    #     exchange="kucoin",
    #     api_key="YOUR_KEY",
    #     api_secret="YOUR_SECRET",
    #     password="YOUR_PASSWORD",
    #     testnet=True,
    # )

    exchange = MockExchange({
        'exchange': 'mock',
        'testnet': True,
    })
    exchange.add_balance("USDT", Decimal("10000"))
    exchange.set_price("BTC/USDT", Decimal("60000"))
    exchange.set_price("ETH/USDT", Decimal("3500"))

    logger.info("exchange_initialized", exchange="MockExchange")

    # --- 2. Setup RuleGuard ---
    risk = RiskManager(
        starting_balance=Decimal("10000"),
        risk_per_trade_pct=Decimal("0.5"),
        max_quantity=Decimal("1"),
        max_open_trades=2,
        max_trades_per_day=3,
        daily_loss_limit_pct=Decimal("5"),
        max_drawdown_pct=Decimal("10"),
    )

    sessions = SessionFilter.all_day()  # 24/7 for crypto
    news = NewsFilter(enabled=False)  # Disable for demo
    config = ConfigProfiles.default()

    guard = RuleGuard(risk, sessions, news, config, dry_run=True)
    logger.info("ruleguard_initialized", dry_run=True)

    # --- 3. Setup Strategy ---
    strategy_config = StrategyConfig(
        symbols=["ETH/USDT"],
        trading_timeframe="4h",
        btc_daily_symbol="BTC/USDT",
    )

    engine = StrategyEngine(strategy_config, exchange, risk, guard)
    logger.info("strategy_engine_initialized")

    # --- 4. Generate Mock OHLCV Data ---
    # In production, fetch from exchange:
    # ohlcv_4h = exchange.fetch_ohlcv("ETH/USDT", "4h", limit=300)
    # btc_1d = exchange.fetch_ohlcv("BTC/USDT", "1d", limit=300)

    eth_ohlcv = generate_mock_ohlcv_trend()
    btc_daily = generate_mock_ohlcv_bullish()

    logger.info(
        "ohlcv_loaded",
        eth_bars=len(eth_ohlcv),
        btc_bars=len(btc_daily),
    )

    # --- 5. Evaluate Trading Decision ---
    decision = engine.evaluate(
        symbol="ETH/USDT",
        ohlcv=eth_ohlcv,
        btc_daily=btc_daily,
    )

    # --- 6. Log Decision ---
    logger.info(
        "decision_made",
        symbol=decision.symbol,
        regime=decision.regime.value,
        regime_reason=decision.regime_reason,
        strategy=decision.strategy_used,
        has_signal=decision.has_signal,
        entry=str(decision.entry_price) if decision.entry_price else None,
        stop=str(decision.stop_loss) if decision.stop_loss else None,
        tp=str(decision.take_profit) if decision.take_profit else None,
        qty=str(decision.quantity) if decision.quantity else None,
        signal_reason=decision.signal_reason,
        blocked=decision.blocked,
        block_reason=decision.block_reason,
    )

    # --- 7. Execute (if valid and dry_run=False) ---
    if decision.has_signal and not decision.blocked:
        logger.info("trade_ready", note="Dry-run mode - no actual execution")
        # order_id = engine.execute_trade(decision)
    else:
        logger.info("no_trade", reason=decision.block_reason or decision.signal_reason)

    logger.info("=== Example Complete ===")


def generate_mock_ohlcv_trend() -> pd.DataFrame:
    """Generate mock OHLCV data simulating an uptrend with pullback."""
    dates = pd.date_range("2026-01-01", periods=250, freq="4h")

    # Simulate uptrend: 3000 → 3500 with pullback to 3400
    base = 3000
    prices = []
    for i in range(250):
        if i < 200:
            # Uptrend
            price = base + (i * 2.5)
        elif i < 220:
            # Pullback
            price = 3500 - ((i - 200) * 5)
        else:
            # Recovery
            price = 3400 + ((i - 220) * 3)

        high = price * 1.01
        low = price * 0.99
        open_ = price * 0.995
        close = price
        volume = 1000000

        prices.append([open_, high, low, close, volume])

    return pd.DataFrame(
        prices,
        columns=["open", "high", "low", "close", "volume"],
        index=dates,
    )


def generate_mock_ohlcv_bullish() -> pd.DataFrame:
    """Generate mock BTC daily OHLCV in bullish regime."""
    dates = pd.date_range("2026-01-01", periods=300, freq="1D")

    # BTC above 200 EMA, 50 EMA > 200 EMA
    base = 50000
    prices = []
    for i in range(300):
        price = base + (i * 50)  # Smooth uptrend
        high = price * 1.02
        low = price * 0.98
        open_ = price * 0.99
        close = price
        volume = 10000000

        prices.append([open_, high, low, close, volume])

    return pd.DataFrame(
        prices,
        columns=["open", "high", "low", "close", "volume"],
        index=dates,
    )


if __name__ == "__main__":
    main()
