"""
Live Trading Module
===================
Real-money trading engine with KuCoin integration.

Components:
- engine: Main live trading loop (like paper trading but with real orders)
- order_manager: Safe order execution with retries and validation

Usage:
    from core.live import LiveTradingEngine, LiveTradingConfig

    config = LiveTradingConfig.from_env()
    engine = LiveTradingEngine(config)
    engine.run()
"""

from core.live.engine import LiveTradingEngine, LiveTradingConfig
from core.live.order_manager import OrderManager, OrderResult, OrderResultStatus

__all__ = [
    "LiveTradingEngine",
    "LiveTradingConfig",
    "OrderManager",
    "OrderResult",
    "OrderResultStatus",
]
