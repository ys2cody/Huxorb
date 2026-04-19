"""
Paper Trading Module
====================
Live market data + virtual portfolio = risk-free strategy validation.

Components:
- portfolio: Virtual portfolio with position tracking and JSON persistence
- live_loop: Polling loop that fetches live OHLCV and runs strategy decisions

Usage:
    from core.paper import PaperTradingLoop, PaperTradingConfig

    config = PaperTradingConfig(
        exchange_id="kucoin",
        symbols=["BTC/USDT", "ETH/USDT"],
        starting_balance=Decimal("10000"),
        poll_interval_seconds=3600,
    )

    loop = PaperTradingLoop(config)
    loop.run()  # Ctrl+C to stop
"""

from core.paper.portfolio import PaperPortfolio, PaperPosition, PaperTrade
from core.paper.live_loop import PaperTradingLoop, PaperTradingConfig

__all__ = [
    "PaperPortfolio",
    "PaperPosition",
    "PaperTrade",
    "PaperTradingLoop",
    "PaperTradingConfig",
]
