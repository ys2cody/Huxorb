"""
Backtesting Engine
==================
Walks through historical OHLCV bars and simulates strategy execution.

Bar-by-bar simulation:
1. Check open trades for stop/tp hits
2. Classify regime
3. Run strategy for new signals
4. Size position, validate, open trade
5. Record results

No look-ahead bias: at bar i, the engine only sees bars [0..i].
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

import pandas as pd

from core.backtest.trade_tracker import TradeTracker, BacktestTrade
from core.strategy.regime import RegimeFilter, Regime, RegimeConfig
from core.strategy.trend_following import TrendFollowingStrategy, TrendFollowingConfig
from core.strategy.mean_reversion import MeanReversionStrategy, MeanReversionConfig
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestConfig:
    """Backtest parameters."""

    # Universe
    symbols: List[str]
    btc_daily_symbol: str = "BTC/USDT"

    # Capital
    starting_balance: Decimal = Decimal("10000")
    risk_per_trade_pct: Decimal = Decimal("0.5")

    # Risk limits
    max_open_trades: int = 2
    max_trades_per_day: int = 3
    max_daily_loss_pct: Decimal = Decimal("2.0")
    max_consecutive_losses: int = 3
    max_total_risk_pct: Decimal = Decimal("1.5")

    # Strategy configs
    regime: RegimeConfig = None
    trend: TrendFollowingConfig = None
    meanrev: MeanReversionConfig = None

    # Execution
    commission_pct: Decimal = Decimal("0.1")  # 0.1% per side (KuCoin maker)
    slippage_pct: Decimal = Decimal("0.05")   # 0.05% simulated slippage

    # Bars needed for warmup (longest indicator: 200 EMA)
    warmup_bars: int = 210

    def __post_init__(self):
        self.regime = self.regime or RegimeConfig()
        self.trend = self.trend or TrendFollowingConfig()
        self.meanrev = self.meanrev or MeanReversionConfig()


class BacktestEngine:
    """
    Walk-forward backtester.

    Simulates the strategy on historical data bar-by-bar without look-ahead.
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.regime_filter = RegimeFilter(config.regime)
        self.trend_strategy = TrendFollowingStrategy(config.trend)
        self.meanrev_strategy = MeanReversionStrategy(config.meanrev)

    def run(
        self,
        symbol_data: Dict[str, pd.DataFrame],
        btc_daily: pd.DataFrame,
    ) -> TradeTracker:
        """
        Run backtest across all symbols.

        Args:
            symbol_data: Dict of {symbol: OHLCV DataFrame} on trading timeframe
            btc_daily: BTC/USDT daily OHLCV

        Returns:
            TradeTracker with all recorded trades and metrics
        """
        tracker = TradeTracker(starting_balance=self.config.starting_balance)

        # Track daily state
        daily_losses = 0
        consecutive_losses = 0
        last_trade_date = None
        trades_today = 0

        for symbol, ohlcv in symbol_data.items():
            logger.info("backtest_start", symbol=symbol, bars=len(ohlcv))

            if len(ohlcv) < self.config.warmup_bars:
                logger.warning("backtest_skip", symbol=symbol, reason="insufficient_bars")
                continue

            for i in range(self.config.warmup_bars, len(ohlcv)):
                bar_time = ohlcv.index[i]
                bar_high = ohlcv["high"].iloc[i]
                bar_low = ohlcv["low"].iloc[i]
                bar_close = ohlcv["close"].iloc[i]

                # --- Day rollover ---
                current_date = bar_time.date() if hasattr(bar_time, 'date') else bar_time
                if last_trade_date != current_date:
                    last_trade_date = current_date
                    trades_today = 0
                    daily_losses = 0

                # --- 1. Check open trades for stop/tp hits ---
                self._check_exits(tracker, bar_time, bar_high, bar_low)

                # --- 2. Risk gates ---
                if len(tracker.open_trades) >= self.config.max_open_trades:
                    continue
                if trades_today >= self.config.max_trades_per_day:
                    continue
                if consecutive_losses >= self.config.max_consecutive_losses:
                    continue

                # Check daily loss limit
                daily_pnl = self._daily_pnl(tracker, current_date)
                daily_loss_limit = tracker.current_equity * self.config.max_daily_loss_pct / Decimal("100")
                if daily_pnl < -daily_loss_limit:
                    continue

                # Check total active risk
                active_risk = sum(t.risk_amount for t in tracker.open_trades)
                max_risk = tracker.current_equity * self.config.max_total_risk_pct / Decimal("100")
                if active_risk >= max_risk:
                    continue

                # --- 3. Slice data up to current bar (no look-ahead) ---
                ohlcv_slice = ohlcv.iloc[:i + 1]

                # BTC daily slice: find matching date range
                btc_slice = btc_daily[btc_daily.index <= bar_time]
                if len(btc_slice) < 210:
                    continue

                # --- 4. Classify regime ---
                regime_state = self.regime_filter.classify(btc_slice, ohlcv_slice)

                if not regime_state.is_tradeable():
                    continue

                # --- 5. Run strategy ---
                signal = None
                strategy_name = None

                if regime_state.regime == Regime.TREND:
                    sig = self.trend_strategy.check_signal(ohlcv_slice)
                    if sig.has_signal:
                        signal = sig
                        strategy_name = "trend_following"

                elif regime_state.regime == Regime.RANGE:
                    btc_bearish = not regime_state.btc_ema_golden
                    sig = self.meanrev_strategy.check_signal(ohlcv_slice, btc_macro_bearish=btc_bearish)
                    if sig.has_signal:
                        signal = sig
                        strategy_name = "mean_reversion"

                if signal is None:
                    continue

                # --- 6. Position sizing ---
                entry_price = signal.entry_price
                stop_loss = signal.stop_loss
                take_profit = signal.take_profit

                # Apply slippage to entry
                slippage = entry_price * self.config.slippage_pct / Decimal("100")
                entry_price = entry_price + slippage  # Buying higher (worse fill)

                sl_distance = entry_price - stop_loss
                if sl_distance <= 0:
                    continue

                risk_amount = tracker.current_equity * self.config.risk_per_trade_pct / Decimal("100")
                quantity = risk_amount / sl_distance

                if quantity <= 0:
                    continue

                # Check we can afford it
                cost = entry_price * quantity
                commission = cost * self.config.commission_pct / Decimal("100")
                total_cost = cost + commission

                if total_cost > tracker.current_equity:
                    continue

                # --- 7. Open trade ---
                trade = tracker.open_trade(
                    symbol=symbol,
                    strategy=strategy_name,
                    regime=regime_state.regime.value,
                    entry_time=bar_time,
                    entry_price=entry_price,
                    quantity=quantity,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )

                trades_today += 1

                logger.debug(
                    "backtest_entry",
                    id=trade.trade_id,
                    symbol=symbol,
                    entry=str(entry_price),
                    sl=str(stop_loss),
                    tp=str(take_profit),
                    qty=str(quantity),
                    regime=regime_state.regime.value,
                    strategy=strategy_name,
                )

            # Close any remaining open trades at last bar close
            last_close = Decimal(str(ohlcv["close"].iloc[-1]))
            last_time = ohlcv.index[-1]
            for trade in list(tracker.open_trades):
                if trade.symbol == symbol:
                    tracker.close_trade(trade, last_time, last_close, "end_of_data")

        # Update consecutive losses
        for trade in tracker.closed_trades:
            if trade.is_winner:
                consecutive_losses = 0
            else:
                consecutive_losses += 1

        logger.info(
            "backtest_complete",
            total_trades=len(tracker.closed_trades),
            final_equity=str(tracker.current_equity),
        )

        return tracker

    def _check_exits(
        self,
        tracker: TradeTracker,
        bar_time: datetime,
        bar_high: float,
        bar_low: float,
    ) -> None:
        """Check if any open trades hit stop loss or take profit."""
        for trade in list(tracker.open_trades):
            # Stop loss hit (low touches or goes below SL)
            if bar_low <= float(trade.stop_loss):
                exit_price = trade.stop_loss
                # Apply slippage on exit
                slippage = exit_price * self.config.slippage_pct / Decimal("100")
                exit_price = exit_price - slippage  # Selling lower (worse fill)

                # Subtract commission
                commission = exit_price * trade.quantity * self.config.commission_pct / Decimal("100")
                exit_price = exit_price - commission / trade.quantity

                tracker.close_trade(trade, bar_time, exit_price, "stop_loss")
                continue

            # Take profit hit (high touches or goes above TP)
            if bar_high >= float(trade.take_profit):
                exit_price = trade.take_profit
                # Apply slippage
                slippage = exit_price * self.config.slippage_pct / Decimal("100")
                exit_price = exit_price - slippage

                # Subtract commission
                commission = exit_price * trade.quantity * self.config.commission_pct / Decimal("100")
                exit_price = exit_price - commission / trade.quantity

                tracker.close_trade(trade, bar_time, exit_price, "take_profit")
                continue

    def _daily_pnl(self, tracker: TradeTracker, current_date) -> Decimal:
        """Sum PnL of trades closed today."""
        pnl = Decimal("0")
        for trade in tracker.closed_trades:
            if trade.exit_time is not None:
                trade_date = trade.exit_time.date() if hasattr(trade.exit_time, 'date') else trade.exit_time
                if trade_date == current_date:
                    pnl += trade.pnl
        return pnl
