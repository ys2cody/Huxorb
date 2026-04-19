"""
Strategy Module
===============
Trading strategies for KuCoin Spot (long-only, halal-compliant).

Components:
- indicators: Technical indicators (EMA, ATR, ADX, RSI, Bollinger, etc.)
- regime: Market regime classification (trend / range / low-vol)
- trend_following: Pullback entries in uptrends
- mean_reversion: Oversold bounces in ranges
- engine: Main orchestrator (regime → strategy → signal → validation → execution)

Usage:
    from core.strategy import StrategyEngine, StrategyConfig

    config = StrategyConfig(
        symbols=["BTC/USDT", "ETH/USDT"],
        trading_timeframe="4h",
    )

    engine = StrategyEngine(config, exchange, risk_manager, rule_guard)
    decision = engine.evaluate(symbol, ohlcv_4h, btc_daily)

    if decision.has_signal and not decision.blocked:
        order_id = engine.execute_trade(decision)
"""

from core.strategy.engine import StrategyEngine, StrategyConfig, TradeDecision
from core.strategy.regime import RegimeFilter, Regime, RegimeConfig, RegimeState
from core.strategy.trend_following import (
    TrendFollowingStrategy,
    TrendFollowingConfig,
    TrendSignal,
)
from core.strategy.mean_reversion import (
    MeanReversionStrategy,
    MeanReversionConfig,
    MeanReversionSignal,
)

__all__ = [
    "StrategyEngine",
    "StrategyConfig",
    "TradeDecision",
    "RegimeFilter",
    "Regime",
    "RegimeConfig",
    "RegimeState",
    "TrendFollowingStrategy",
    "TrendFollowingConfig",
    "TrendSignal",
    "MeanReversionStrategy",
    "MeanReversionConfig",
    "MeanReversionSignal",
]
