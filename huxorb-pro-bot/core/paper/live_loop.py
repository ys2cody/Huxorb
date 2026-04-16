"""
Paper Trading Live Loop
========================
Polls live OHLCV from KuCoin (or any CCXT exchange), runs the strategy,
and manages virtual positions.

Loop flow (every cycle):
1. Fetch latest OHLCV candles
2. Get live ticker prices
3. Check open positions for stop/tp hits
4. Run regime + strategy for new signals
5. Open new positions if signal + RuleGuard passes
6. Log everything
7. Sleep until next cycle

The loop is designed to run on the 4H timeframe:
- Checks once per hour (catches new 4H candle close)
- Avoids hammering the API
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from core.backtest.data_loader import fetch_ohlcv_ccxt
from core.paper.portfolio import PaperPortfolio
from core.ruleguard import (
    RiskManager,
    SessionFilter,
    NewsFilter,
    ConfigProfiles,
    RuleGuard,
)
from core.strategy import StrategyEngine, StrategyConfig
from core.strategy.regime import Regime
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PaperTradingConfig:
    """Paper trading loop configuration."""

    exchange_id: str = "kucoin"
    symbols: list = None
    trading_timeframe: str = "4h"
    btc_daily_symbol: str = "BTC/USDT"

    # Polling
    poll_interval_seconds: int = 3600  # 1 hour
    ohlcv_limit: int = 300  # Bars to fetch

    # Capital (Aggressive growth defaults)
    starting_balance: Decimal = Decimal("500")
    risk_per_trade_pct: Decimal = Decimal("1.5")
    max_open_trades: int = 4
    max_trades_per_day: int = 6

    # State persistence
    state_dir: Path = None

    def __post_init__(self):
        if self.symbols is None:
            # Aggressive default: top 20 altcoins by market cap
            self.symbols = [
                "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
                "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT",
                "POL/USDT", "LTC/USDT", "NEAR/USDT", "UNI/USDT", "ATOM/USDT",
                "APT/USDT", "FIL/USDT", "ARB/USDT", "INJ/USDT", "OP/USDT",
            ]
        if self.state_dir is None:
            self.state_dir = Path(__file__).parent.parent.parent / "data" / "paper_state"


class PaperTradingLoop:
    """
    Main paper trading loop.

    Fetches live data from KuCoin, runs the strategy engine, and manages
    a virtual portfolio. No real orders are placed.
    """

    def __init__(self, config: PaperTradingConfig):
        self.config = config

        # State file for persistence
        state_file = config.state_dir / "portfolio.json"

        # Paper portfolio
        self.portfolio = PaperPortfolio(
            starting_balance=config.starting_balance,
            state_file=state_file,
        )

        # Risk manager (tracks balance/DD)
        self.risk = RiskManager(
            starting_balance=config.starting_balance,
            risk_per_trade_pct=config.risk_per_trade_pct,
            max_quantity=Decimal("10"),
            max_open_trades=config.max_open_trades,
            max_trades_per_day=config.max_trades_per_day,
        )

        # RuleGuard
        sessions = SessionFilter.all_day()
        news = NewsFilter(enabled=False)
        profiles = ConfigProfiles.default()

        self.guard = RuleGuard(
            risk_manager=self.risk,
            session_filter=sessions,
            news_filter=news,
            config=profiles,
            dry_run=False,  # Not dry-run; paper portfolio simulates
        )

        # Strategy
        strategy_config = StrategyConfig(
            symbols=config.symbols,
            trading_timeframe=config.trading_timeframe,
        )

        # We pass None for exchange since we fetch data directly
        self.strategy_config = strategy_config
        self.regime_filter = __import__(
            "core.strategy.regime", fromlist=["RegimeFilter"]
        ).RegimeFilter()
        self.trend_strategy = __import__(
            "core.strategy.trend_following", fromlist=["TrendFollowingStrategy"]
        ).TrendFollowingStrategy()
        self.meanrev_strategy = __import__(
            "core.strategy.mean_reversion", fromlist=["MeanReversionStrategy"]
        ).MeanReversionStrategy()
        self.breakout_strategy = __import__(
            "core.strategy.breakout", fromlist=["BreakoutStrategy"]
        ).BreakoutStrategy()

        self._running = False
        self._last_bar_time: Dict[str, datetime] = {}

    def run(self, max_cycles: Optional[int] = None) -> None:
        """
        Start the paper trading loop.

        Args:
            max_cycles: Stop after N cycles (None = run forever)
        """
        self._running = True
        cycle = 0

        logger.info(
            "paper_trading_start",
            exchange=self.config.exchange_id,
            symbols=self.config.symbols,
            balance=str(self.config.starting_balance),
            poll_interval=self.config.poll_interval_seconds,
        )

        while self._running:
            cycle += 1
            if max_cycles and cycle > max_cycles:
                break

            try:
                self._run_cycle()
            except KeyboardInterrupt:
                logger.info("paper_trading_interrupted")
                self._running = False
                break
            except Exception as exc:
                logger.error("paper_cycle_error", error=str(exc), cycle=cycle)

            if self._running and (max_cycles is None or cycle < max_cycles):
                logger.info(
                    "paper_sleeping",
                    seconds=self.config.poll_interval_seconds,
                    next_check=str(datetime.now(timezone.utc)),
                )
                time.sleep(self.config.poll_interval_seconds)

        # Final summary
        self._print_summary()

    def stop(self) -> None:
        self._running = False

    def _run_cycle(self) -> None:
        """Single paper trading cycle."""
        now = datetime.now(timezone.utc)
        logger.info("paper_cycle_start", time=now.isoformat())

        # --- 1. Fetch BTC daily for regime ---
        btc_daily = self._fetch_ohlcv(self.config.btc_daily_symbol, "1d")
        if btc_daily.empty:
            logger.warning("paper_skip", reason="no_btc_daily_data")
            return

        # --- 2. Process each symbol ---
        for symbol in self.config.symbols:
            self._process_symbol(symbol, btc_daily)

        # --- 3. Update risk manager ---
        prices = self._get_latest_prices()
        equity = self.portfolio.equity(prices)
        self.risk.update_balance(equity)
        self.risk.set_open_trades(len(self.portfolio.open_positions))

        # --- 4. Log status ---
        summary = self.portfolio.summary(prices)
        logger.info("paper_cycle_status", **summary)

    def _process_symbol(self, symbol: str, btc_daily: pd.DataFrame) -> None:
        """Process one symbol: check exits, check for new signals."""

        # Fetch OHLCV
        ohlcv = self._fetch_ohlcv(symbol, self.config.trading_timeframe)
        if ohlcv.empty or len(ohlcv) < 220:
            return

        # Check if we have a new bar
        latest_bar = ohlcv.index[-1]
        last_seen = self._last_bar_time.get(symbol)
        if last_seen is not None and latest_bar <= last_seen:
            return  # Same bar, skip
        self._last_bar_time[symbol] = latest_bar

        # Get current price
        current_price = Decimal(str(ohlcv["close"].iloc[-1]))

        # --- Check exits on open positions ---
        prices = {symbol: current_price}
        closed = self.portfolio.check_exits(prices)
        for trade in closed:
            logger.info(
                "paper_exit",
                symbol=trade.symbol,
                reason=trade.exit_reason,
                pnl=str(trade.pnl),
            )

        # --- Check for new entry ---
        if len(self.portfolio.open_positions) >= self.config.max_open_trades:
            return

        # Regime
        regime_state = self.regime_filter.classify(btc_daily, ohlcv)

        if not regime_state.is_tradeable():
            logger.debug("paper_no_regime", symbol=symbol, regime=regime_state.regime.value)
            return

        # Strategy signal
        signal = None
        strategy_name = None

        if regime_state.regime == Regime.TREND:
            sig = self.trend_strategy.check_signal(ohlcv)
            if sig.has_signal:
                signal = sig
                strategy_name = "trend_following"
            else:
                sig = self.breakout_strategy.check_signal(ohlcv)
                if sig.has_signal:
                    signal = sig
                    strategy_name = "breakout"

        elif regime_state.regime == Regime.RANGE:
            btc_bearish = not regime_state.btc_ema_golden
            sig = self.meanrev_strategy.check_signal(ohlcv, btc_macro_bearish=btc_bearish)
            if sig.has_signal:
                signal = sig
                strategy_name = "mean_reversion"

        if signal is None:
            return

        # --- Position sizing ---
        quantity = self.risk.calculate_quantity(
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
        )

        if quantity <= 0:
            return

        # --- RuleGuard ---
        decision = self.guard.can_open_trade(
            symbol=symbol,
            side="buy",
            quantity=quantity,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )

        if not decision.allowed:
            logger.info(
                "paper_blocked",
                symbol=symbol,
                reason=decision.reason.value,
                detail=decision.detail,
            )
            return

        # --- Open paper position ---
        try:
            self.portfolio.open_position(
                symbol=symbol,
                quantity=quantity,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                strategy=strategy_name,
                regime=regime_state.regime.value,
            )
            self.risk.increment_trade_count()

            logger.info(
                "paper_entry",
                symbol=symbol,
                strategy=strategy_name,
                regime=regime_state.regime.value,
                entry=str(signal.entry_price),
                sl=str(signal.stop_loss),
                tp=str(signal.take_profit),
                qty=str(quantity),
                reason=signal.reason,
            )
        except ValueError as exc:
            logger.warning("paper_entry_failed", symbol=symbol, error=str(exc))

    def _fetch_ohlcv(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Fetch OHLCV from exchange."""
        try:
            return fetch_ohlcv_ccxt(
                self.config.exchange_id,
                symbol,
                timeframe,
                limit=self.config.ohlcv_limit,
            )
        except Exception as exc:
            logger.error("paper_fetch_error", symbol=symbol, tf=timeframe, error=str(exc))
            return pd.DataFrame()

    def _get_latest_prices(self) -> Dict[str, Decimal]:
        """Get latest close price for each symbol."""
        prices = {}
        for symbol in self.config.symbols:
            ohlcv = self._fetch_ohlcv(symbol, self.config.trading_timeframe)
            if not ohlcv.empty:
                prices[symbol] = Decimal(str(ohlcv["close"].iloc[-1]))
        return prices

    def _print_summary(self) -> None:
        """Print final paper trading summary."""
        logger.info("=" * 50)
        logger.info("   PAPER TRADING SESSION COMPLETE")
        logger.info("=" * 50)

        summary = self.portfolio.summary()
        for key, val in summary.items():
            logger.info(f"  {key}: {val}")

        if self.portfolio.closed_trades:
            logger.info("")
            logger.info("  RECENT TRADES:")
            for trade in self.portfolio.closed_trades[-5:]:
                pnl_sign = "+" if trade.pnl > 0 else ""
                logger.info(
                    f"  #{trade.trade_id} {trade.symbol} "
                    f"{trade.strategy} {trade.exit_reason} "
                    f"{pnl_sign}{trade.pnl:.2f} USDT"
                )
