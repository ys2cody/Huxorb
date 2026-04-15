"""
Strategy Engine
===============
Orchestrates the complete trading decision flow:

1. Regime classification (trend / range / low-vol)
2. Strategy selection based on regime
3. Signal generation (entry / stop / tp)
4. Position sizing via RiskManager
5. RuleGuard validation
6. Order creation via Exchange

This is the main loop that runs per symbol per tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict

import pandas as pd

from core.exchange.base import IExchange
from core.exchange.models import OrderSide, OrderType
from core.ruleguard import RuleGuard, RiskManager
from core.strategy.regime import RegimeFilter, Regime, RegimeConfig
from core.strategy.trend_following import TrendFollowingStrategy, TrendFollowingConfig
from core.strategy.mean_reversion import MeanReversionStrategy, MeanReversionConfig
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StrategyConfig:
    """Combined strategy configuration."""

    symbols: list[str]
    trading_timeframe: str = "4h"
    btc_daily_symbol: str = "BTC/USDT"

    regime: RegimeConfig = None
    trend: TrendFollowingConfig = None
    meanrev: MeanReversionConfig = None

    def __post_init__(self):
        self.regime = self.regime or RegimeConfig()
        self.trend = self.trend or TrendFollowingConfig()
        self.meanrev = self.meanrev or MeanReversionConfig()


@dataclass
class TradeDecision:
    """Result of strategy decision cycle."""

    symbol: str
    timestamp: pd.Timestamp
    regime: Regime
    regime_reason: str
    strategy_used: Optional[str]
    has_signal: bool
    entry_price: Optional[Decimal]
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    quantity: Optional[Decimal]
    signal_reason: str
    blocked: bool
    block_reason: str


class StrategyEngine:
    """
    Main trading logic orchestrator.

    Usage:
        engine = StrategyEngine(config, exchange, risk_manager, rule_guard)
        decision = engine.evaluate(symbol, ohlcv_4h, btc_ohlcv_1d)

        if decision.has_signal and not decision.blocked:
            order = engine.execute_trade(decision)
    """

    def __init__(
        self,
        config: StrategyConfig,
        exchange: IExchange,
        risk_manager: RiskManager,
        rule_guard: RuleGuard,
    ):
        self.config = config
        self.exchange = exchange
        self.risk = risk_manager
        self.guard = rule_guard

        # Strategy components
        self.regime_filter = RegimeFilter(config.regime)
        self.trend_strategy = TrendFollowingStrategy(config.trend)
        self.meanrev_strategy = MeanReversionStrategy(config.meanrev)

        logger.info(
            "strategy_engine_init",
            symbols=config.symbols,
            timeframe=config.trading_timeframe,
        )

    def evaluate(
        self,
        symbol: str,
        ohlcv: pd.DataFrame,
        btc_daily: pd.DataFrame,
    ) -> TradeDecision:
        """
        Evaluate trading decision for one symbol at current bar close.

        Args:
            symbol: Trading symbol (e.g. "ETH/USDT")
            ohlcv: Symbol's OHLCV on trading timeframe (4H)
            btc_daily: BTC/USDT daily OHLCV for macro regime

        Returns:
            TradeDecision with full reasoning chain
        """
        timestamp = ohlcv.index[-1]

        # --- STEP 1: Classify regime ---
        regime_state = self.regime_filter.classify(btc_daily, ohlcv)

        if not regime_state.is_tradeable():
            return TradeDecision(
                symbol=symbol,
                timestamp=timestamp,
                regime=regime_state.regime,
                regime_reason=regime_state.reason,
                strategy_used=None,
                has_signal=False,
                entry_price=None,
                stop_loss=None,
                take_profit=None,
                quantity=None,
                signal_reason="regime_not_tradeable",
                blocked=False,
                block_reason="",
            )

        # --- STEP 2: Select strategy based on regime ---
        if regime_state.regime == Regime.TREND:
            signal = self.trend_strategy.check_signal(ohlcv)
            strategy_name = "trend_following"
        elif regime_state.regime == Regime.RANGE:
            btc_bearish = not regime_state.btc_ema_golden
            signal = self.meanrev_strategy.check_signal(ohlcv, btc_macro_bearish=btc_bearish)
            strategy_name = "mean_reversion"
        else:
            # Shouldn't reach here if is_tradeable() passed
            return self._no_trade_decision(symbol, timestamp, regime_state, "unknown_regime")

        # --- STEP 3: Check if signal exists ---
        if not signal.has_signal:
            return self._no_trade_decision(
                symbol, timestamp, regime_state, signal.reason, strategy_name
            )

        # --- STEP 4: Calculate position size ---
        market = self.exchange.get_market(symbol)
        quantity = self.risk.calculate_quantity(
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            step_size=None,  # TODO: Add step_size to Market model
            min_quantity=market.min_amount,
        )

        if quantity <= 0:
            return self._no_trade_decision(
                symbol,
                timestamp,
                regime_state,
                "quantity_zero",
                strategy_name,
                entry=signal.entry_price,
                stop=signal.stop_loss,
                tp=signal.take_profit,
            )

        # --- STEP 5: RuleGuard validation ---
        ticker = self.exchange.get_ticker(symbol)
        guard_decision = self.guard.can_open_trade(
            symbol=symbol,
            side="buy",  # long-only
            quantity=quantity,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            bid=ticker.bid,
            ask=ticker.ask,
        )

        blocked = not guard_decision.allowed
        block_reason = guard_decision.detail if blocked else ""

        return TradeDecision(
            symbol=symbol,
            timestamp=timestamp,
            regime=regime_state.regime,
            regime_reason=regime_state.reason,
            strategy_used=strategy_name,
            has_signal=True,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            quantity=quantity,
            signal_reason=signal.reason,
            blocked=blocked,
            block_reason=block_reason,
        )

    def execute_trade(self, decision: TradeDecision) -> Optional[str]:
        """
        Execute the trade if decision is valid.

        Args:
            decision: TradeDecision from evaluate()

        Returns:
            Order ID if successful, None otherwise
        """
        if not decision.has_signal or decision.blocked:
            logger.warning(
                "execute_skipped",
                symbol=decision.symbol,
                has_signal=decision.has_signal,
                blocked=decision.blocked,
                reason=decision.block_reason or decision.signal_reason,
            )
            return None

        logger.info(
            "executing_trade",
            symbol=decision.symbol,
            entry=str(decision.entry_price),
            stop=str(decision.stop_loss),
            tp=str(decision.take_profit),
            qty=str(decision.quantity),
            regime=decision.regime.value,
            strategy=decision.strategy_used,
        )

        try:
            order = self.exchange.create_order(
                symbol=decision.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=decision.quantity,
            )

            # TODO: Place stop-loss and take-profit orders as well
            # (Requires exchange support for stop orders)

            self.risk.increment_trade_count()
            self.guard.clear_signal()

            logger.info(
                "trade_executed",
                symbol=decision.symbol,
                order_id=order.id,
                filled=str(order.filled),
                price=str(order.average_price or decision.entry_price),
            )

            return order.id

        except Exception as exc:
            logger.error(
                "trade_execution_failed",
                symbol=decision.symbol,
                error=str(exc),
            )
            return None

    def _no_trade_decision(
        self,
        symbol: str,
        timestamp: pd.Timestamp,
        regime_state,
        reason: str,
        strategy: Optional[str] = None,
        entry: Optional[Decimal] = None,
        stop: Optional[Decimal] = None,
        tp: Optional[Decimal] = None,
    ) -> TradeDecision:
        return TradeDecision(
            symbol=symbol,
            timestamp=timestamp,
            regime=regime_state.regime,
            regime_reason=regime_state.reason,
            strategy_used=strategy,
            has_signal=False,
            entry_price=entry,
            stop_loss=stop,
            take_profit=tp,
            quantity=None,
            signal_reason=reason,
            blocked=False,
            block_reason="",
        )
