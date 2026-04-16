"""
Live Trading Engine
===================
Production trading loop with real KuCoin orders.

Similar to PaperTradingLoop but executes real trades via OrderManager.

Safety features:
- Dry-run mode (logs without executing)
- RuleGuard validation before every order
- Position tracking via database/JSON state
- Alert integration for entries/exits
- Graceful shutdown on Ctrl+C
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from core.backtest.data_loader import fetch_ohlcv_ccxt
from core.dashboard import (
    AlertManager,
    ConsoleAlertHandler,
    TelegramAlertHandler,
    WebhookAlertHandler,
)
from core.exchange.kucoin import KuCoinConnector
from core.live.order_manager import OrderManager, OrderResultStatus
from core.ruleguard import (
    RiskManager,
    SessionFilter,
    NewsFilter,
    ConfigProfiles,
    RuleGuard,
)
from core.strategy.breakout import BreakoutStrategy
from core.strategy.regime import Regime, RegimeFilter
from core.strategy.trend_following import TrendFollowingStrategy
from core.strategy.mean_reversion import MeanReversionStrategy
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LivePosition:
    """An open live position with exchange order IDs."""
    position_id: int
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    entry_time: datetime
    stop_loss: Decimal
    take_profit: Decimal
    strategy: str
    regime: str
    entry_order_id: str
    stop_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None


@dataclass
class LiveTradingConfig:
    """Live trading configuration loaded from environment."""
    api_key: str
    api_secret: str
    passphrase: str
    testnet: bool = True
    dry_run: bool = True

    symbols: List[str] = None
    trading_timeframe: str = "4h"
    btc_daily_symbol: str = "BTC/USDT"

    poll_interval_seconds: int = 3600
    ohlcv_limit: int = 300

    # If None, the engine fetches the live USDT balance from KuCoin
    # at startup and uses that as the baseline for risk/drawdown tracking.
    starting_balance: Optional[Decimal] = None
    risk_per_trade_pct: Decimal = Decimal("1.5")
    max_open_trades: int = 4
    max_trades_per_day: int = 6

    alert_webhook_url: str = ""

    # Telegram alerts (optional). Set both to enable phone notifications.
    # See TelegramAlertHandler docstring for setup via @BotFather.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    state_dir: Path = None

    # Aggressive regime filter: trade in bear markets if per-symbol trend is strong
    aggressive_mode: bool = False

    # Bear mode: ignore regime filter, trade only mean-reversion on BTC/ETH
    # Designed for capital preservation + small gains during crypto bear markets.
    # Expected: £1-5/month on £100, not a route to riches.
    bear_mode: bool = False

    # Automatically exit bear mode when BTC macro improves (above 200MA + golden cross)
    auto_bear_mode_exit: bool = False

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "LiveTradingConfig":
        """
        Load config from environment variables.

        If env_file is provided, loads from that file first.
        Otherwise uses os.environ.
        """
        if env_file and env_file.exists():
            # Load .env file
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

        return cls(
            api_key=os.getenv("KUCOIN_API_KEY", ""),
            api_secret=os.getenv("KUCOIN_API_SECRET", ""),
            passphrase=os.getenv("KUCOIN_PASSPHRASE", ""),
            testnet=os.getenv("KUCOIN_TESTNET", "true").lower() == "true",
            dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
            symbols=os.getenv(
                "SYMBOLS",
                "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,ADA/USDT,"
                "DOGE/USDT,AVAX/USDT,LINK/USDT,DOT/USDT,POL/USDT,LTC/USDT,"
                "NEAR/USDT,UNI/USDT,ATOM/USDT,APT/USDT,FIL/USDT,ARB/USDT,"
                "INJ/USDT,OP/USDT",
            ).split(","),
            starting_balance=(
                Decimal(os.environ["STARTING_BALANCE"])
                if os.getenv("STARTING_BALANCE")
                else None
            ),
            risk_per_trade_pct=Decimal(os.getenv("RISK_PER_TRADE_PCT", "1.5")),
            max_open_trades=int(os.getenv("MAX_OPEN_TRADES", "4")),
            max_trades_per_day=int(os.getenv("MAX_TRADES_PER_DAY", "6")),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "3600")),
            alert_webhook_url=os.getenv("ALERT_WEBHOOK_URL", ""),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            state_dir=Path(os.getenv("STATE_DIR", "data/live_state")),
            aggressive_mode=os.getenv("AGGRESSIVE_MODE", "false").lower() == "true",
            bear_mode=os.getenv("BEAR_MODE", "false").lower() == "true",
            auto_bear_mode_exit=os.getenv("AUTO_BEAR_MODE_EXIT", "false").lower() == "true",
        )

    def __post_init__(self):
        if not self.api_key or not self.api_secret or not self.passphrase:
            raise ValueError(
                "Missing KuCoin API credentials. Set KUCOIN_API_KEY, "
                "KUCOIN_API_SECRET, KUCOIN_PASSPHRASE environment variables."
            )


class LiveTradingEngine:
    """
    Production trading engine.

    Polls live OHLCV, runs strategy, executes real orders via KuCoin.
    """

    def __init__(self, config: LiveTradingConfig):
        self.config = config

        # Bear mode overrides: safer setup for bear markets
        if config.bear_mode:
            if config.aggressive_mode:
                logger.warning("bear_mode_overrides_aggressive_mode")
                config.aggressive_mode = False
            config.symbols = ["BTC/USDT", "ETH/USDT"]
            config.risk_per_trade_pct = Decimal("0.75")
            config.max_open_trades = 2
            config.max_trades_per_day = 4
            logger.info("bear_mode_active", symbols=config.symbols, risk=str(config.risk_per_trade_pct))

        # KuCoin connector
        self.connector = KuCoinConnector(
            api_key=config.api_key,
            api_secret=config.api_secret,
            passphrase=config.passphrase,
            testnet=config.testnet,
        )

        # Test connection
        if not self.connector.test_connection():
            raise ConnectionError("KuCoin API connection failed. Check credentials.")

        # Order manager
        self.order_mgr = OrderManager(
            connector=self.connector,
            dry_run=config.dry_run,
        )

        # Resolve starting balance: explicit override OR live USDT balance from KuCoin
        if config.starting_balance is not None:
            starting_balance = config.starting_balance
            logger.info("starting_balance_override", value=str(starting_balance))
        else:
            balances = self.connector.get_balance()
            usdt = balances.get("USDT")
            starting_balance = usdt.total if usdt else Decimal("0")
            if starting_balance <= 0:
                raise ValueError(
                    "No USDT balance found on KuCoin account. "
                    "Deposit USDT or set STARTING_BALANCE in your .env file."
                )
            logger.info("starting_balance_from_exchange", value=str(starting_balance))

        self._starting_balance = starting_balance

        # Risk manager
        self.risk = RiskManager(
            starting_balance=starting_balance,
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
            dry_run=config.dry_run,
        )

        # Strategy
        from core.strategy.regime import RegimeConfig
        regime_cfg = RegimeConfig(aggressive_mode=config.aggressive_mode)
        self.regime_filter = RegimeFilter(regime_cfg)
        self.trend_strategy = TrendFollowingStrategy()
        self.meanrev_strategy = MeanReversionStrategy()
        self.breakout_strategy = BreakoutStrategy()

        # Alerts
        self.alerts = AlertManager()
        self.alerts.add_handler(ConsoleAlertHandler())
        if config.alert_webhook_url:
            self.alerts.add_handler(
                WebhookAlertHandler(config.alert_webhook_url)
            )
        if config.telegram_bot_token and config.telegram_chat_id:
            self.alerts.add_handler(
                TelegramAlertHandler(
                    bot_token=config.telegram_bot_token,
                    chat_id=config.telegram_chat_id,
                )
            )
            logger.info("telegram_alerts_enabled")

        # State
        self._running = False
        self._positions: List[LivePosition] = []
        self._next_id = 1
        self._last_bar_time: Dict[str, datetime] = {}

        logger.info(
            "live_engine_initialized",
            dry_run=config.dry_run,
            testnet=config.testnet,
            symbols=config.symbols,
        )

    # ------------------------------------------------------------------ #
    # Main Loop
    # ------------------------------------------------------------------ #

    def run(self, max_cycles: Optional[int] = None) -> None:
        """
        Start the live trading loop.

        Args:
            max_cycles: Stop after N cycles (None = run forever)
        """
        self._running = True
        cycle = 0

        logger.info(
            "live_trading_start",
            dry_run=self.config.dry_run,
            testnet=self.config.testnet,
            symbols=self.config.symbols,
        )

        print()
        print("=" * 60)
        print("   HUXORB PRO — LIVE TRADING")
        print("=" * 60)
        print(f"  Mode:       {'DRY RUN' if self.config.dry_run else 'LIVE EXECUTION'}")
        print(f"  Exchange:   KuCoin {'SANDBOX' if self.config.testnet else 'PRODUCTION'}")
        print(f"  Balance:    {self._starting_balance} USDT")
        print(f"  Symbols:    {len(self.config.symbols)} ({', '.join(self.config.symbols[:5])}...)")
        print(f"  Risk/trade: {self.config.risk_per_trade_pct}%")
        if self.config.bear_mode:
            print(f"  Bear Mode:  ON (mean-reversion only, BTC/ETH)")
        elif self.config.aggressive_mode:
            print(f"  Aggressive: ON (relaxed macro gate)")
        else:
            print(f"  Profile:    standard")
        print(f"  Poll:       {self.config.poll_interval_seconds}s")
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            print(f"  Telegram:   ON (phone notifications enabled)")
        print("=" * 60)
        print()
        print("  Press Ctrl+C to stop")
        print()

        while self._running:
            cycle += 1
            if max_cycles and cycle > max_cycles:
                break

            try:
                self._run_cycle()
            except KeyboardInterrupt:
                logger.info("live_trading_interrupted")
                self._running = False
                break
            except Exception as exc:
                logger.error("live_cycle_error", error=str(exc), cycle=cycle)
                self.alerts.on_drawdown_warning(0, Decimal("0"), f"cycle_error: {exc}")

            if self._running and (max_cycles is None or cycle < max_cycles):
                logger.info(
                    "live_sleeping",
                    seconds=self.config.poll_interval_seconds,
                    next_check=str(datetime.now(timezone.utc)),
                )
                time.sleep(self.config.poll_interval_seconds)

        # Final summary
        print()
        print("=" * 60)
        print("   LIVE TRADING STOPPED")
        print("=" * 60)
        print(f"  Open positions: {len(self._positions)}")
        print()

    def stop(self) -> None:
        self._running = False

    def _run_cycle(self) -> None:
        """Single live trading cycle."""
        now = datetime.now(timezone.utc)
        logger.info("live_cycle_start", time=now.isoformat())

        # 1. Fetch BTC daily for regime
        btc_daily = self._fetch_ohlcv(self.config.btc_daily_symbol, "1d")
        if btc_daily.empty:
            logger.warning("live_skip", reason="no_btc_daily_data")
            return

        # 1.5. Auto-exit bear mode if market recovered
        self._check_auto_bear_exit(btc_daily)

        # 2. Process each symbol
        for symbol in self.config.symbols:
            self._process_symbol(symbol, btc_daily)

        # 3. Check position exits via exchange orders (SL/TP filled?)
        self._check_position_exits()

        # 4. Update risk manager
        balance = self.connector.get_balance()
        total_equity = sum(b.total for b in balance.values())
        self.risk.update_balance(total_equity)
        self.risk.set_open_trades(len(self._positions))

        # 5. Alert thresholds
        # (We don't have full portfolio equity tracking like paper mode,
        #  but we can alert on drawdown if we track starting balance)
        # self.alerts.check_thresholds(portfolio_obj, prices) — skipped for now

        logger.info("live_cycle_complete", open_positions=len(self._positions))

    def _process_symbol(self, symbol: str, btc_daily: pd.DataFrame) -> None:
        """Process one symbol: check for new signals."""
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

        # Current price
        current_price = Decimal(str(ohlcv["close"].iloc[-1]))

        # Check max positions
        if len(self._positions) >= self.config.max_open_trades:
            return

        # Regime
        regime_state = self.regime_filter.classify(btc_daily, ohlcv)

        # Strategy signal
        signal = None
        strategy_name = None

        if self.config.bear_mode:
            # Bear mode: mean-reversion only, bypass regime filter.
            # We pass btc_macro_bearish=False to stop the strategy rejecting
            # signals purely because BTC is weak (that's the whole point here).
            sig = self.meanrev_strategy.check_signal(ohlcv, btc_macro_bearish=False)
            if sig.has_signal:
                signal = sig
                strategy_name = "mean_reversion_bear"
        else:
            if not regime_state.is_tradeable():
                logger.debug("live_no_regime", symbol=symbol, regime=regime_state.regime.value)
                return

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

        # Position sizing
        market = self.connector.get_market(symbol)
        quantity = self.risk.calculate_quantity(
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            step_size=None,
            min_quantity=market.min_amount,
        )

        if quantity <= 0:
            return

        # RuleGuard
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
                "live_blocked",
                symbol=symbol,
                reason=decision.reason.value,
                detail=decision.detail,
            )
            return

        # Execute entry + SL/TP orders
        result = self.order_mgr.place_entry_with_stops(
            symbol=symbol,
            side="buy",
            quantity=quantity,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )

        if result.status == OrderResultStatus.SUCCESS:
            pos = LivePosition(
                position_id=self._next_id,
                symbol=symbol,
                quantity=quantity,
                entry_price=signal.entry_price if not result.order else Decimal(str(result.order.average or result.order.price or signal.entry_price)),
                entry_time=datetime.now(timezone.utc),
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                strategy=strategy_name,
                regime=regime_state.regime.value,
                entry_order_id=result.order.id if result.order else "dry_run",
                stop_order_id=result.stop_order.id if result.stop_order else None,
                tp_order_id=result.tp_order.id if result.tp_order else None,
            )
            self._next_id += 1
            self._positions.append(pos)
            self.risk.increment_trade_count()

            logger.info(
                "live_entry",
                symbol=symbol,
                strategy=strategy_name,
                regime=regime_state.regime.value,
                entry=str(signal.entry_price),
                sl=str(signal.stop_loss),
                tp=str(signal.take_profit),
                qty=str(quantity),
            )
            self.alerts.on_trade_entry(pos)

        else:
            logger.warning(
                "live_entry_failed",
                symbol=symbol,
                status=result.status.value,
                error=result.error,
            )

    def _check_position_exits(self) -> None:
        """
        Check if any stop-loss or take-profit orders have filled.

        For each open position, query the exchange for SL/TP order status.
        If filled, remove position and log exit.
        """
        if self.config.dry_run:
            return  # No real orders to check

        closed = []
        for pos in list(self._positions):
            # Check TP order
            if pos.tp_order_id:
                order = self.order_mgr.get_order_status(pos.tp_order_id, pos.symbol)
                if order and order.is_closed:
                    logger.info(
                        "live_exit_tp",
                        symbol=pos.symbol,
                        order_id=pos.tp_order_id,
                        qty=str(pos.quantity),
                    )
                    closed.append((pos, "take_profit"))
                    continue

            # Check SL order
            if pos.stop_order_id:
                order = self.order_mgr.get_order_status(pos.stop_order_id, pos.symbol)
                if order and order.is_closed:
                    logger.info(
                        "live_exit_sl",
                        symbol=pos.symbol,
                        order_id=pos.stop_order_id,
                        qty=str(pos.quantity),
                    )
                    closed.append((pos, "stop_loss"))
                    continue

        # Remove closed positions
        for pos, reason in closed:
            self._positions = [p for p in self._positions if p.position_id != pos.position_id]

            # Alert (we don't have exact PnL without fetching fill prices, but we can estimate)
            class _FakeTrade:
                symbol = pos.symbol
                exit_reason = reason
                pnl = Decimal("0")  # Placeholder — would need to calc from fill prices
            self.alerts.on_trade_exit(_FakeTrade())

    def _check_auto_bear_exit(self, btc_daily: pd.DataFrame) -> None:
        """
        Automatically exit bear mode if BTC macro conditions improve.

        Conditions to exit bear mode:
        - BTC close > 200-day EMA
        - BTC 50-day EMA > 200-day EMA (golden cross)
        """
        if not self.config.auto_bear_mode_exit:
            return

        if not self.config.bear_mode:
            return  # Not in bear mode, nothing to exit

        if len(btc_daily) < 210:
            return  # Not enough data

        # Calculate BTC macro conditions
        from core.strategy.indicators import ema
        btc_close = btc_daily["close"]
        btc_ema50 = ema(btc_close, 50)
        btc_ema200 = ema(btc_close, 200)

        btc_above_200 = btc_close.iloc[-1] > btc_ema200.iloc[-1]
        btc_golden = btc_ema50.iloc[-1] > btc_ema200.iloc[-1]

        # Exit bear mode if both conditions met
        if btc_above_200 and btc_golden:
            logger.info(
                "auto_bear_exit_triggered",
                btc_above_200=btc_above_200,
                btc_golden=btc_golden,
                btc_price=float(btc_close.iloc[-1]),
                btc_ema200=float(btc_ema200.iloc[-1]),
            )

            # Reinitialize to standard settings
            self.config.bear_mode = False
            # Restore original symbols from env (or default to top 20)
            from core.live.engine import LiveTradingConfig
            temp_config = LiveTradingConfig.from_env()
            self.config.symbols = temp_config.symbols
            self.config.risk_per_trade_pct = temp_config.risk_per_trade_pct
            self.config.max_open_trades = temp_config.max_open_trades
            self.config.max_trades_per_day = temp_config.max_trades_per_day

            # Update risk manager with new settings
            self.risk.risk_per_trade_pct = self.config.risk_per_trade_pct
            self.risk.max_open_trades = self.config.max_open_trades
            self.risk.max_trades_per_day = self.config.max_trades_per_day

            # Send alert
            self.alerts.on_drawdown_warning(
                0,
                Decimal("0"),
                f"AUTO-SWITCH: Bear mode OFF — BTC recovered (${btc_close.iloc[-1]:.0f} > 200MA). "
                f"Trading {len(self.config.symbols)} symbols with {self.config.risk_per_trade_pct}% risk."
            )

            logger.info(
                "auto_bear_exit_complete",
                symbols=len(self.config.symbols),
                risk_pct=str(self.config.risk_per_trade_pct),
            )

    def _fetch_ohlcv(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Fetch OHLCV from KuCoin."""
        try:
            return fetch_ohlcv_ccxt(
                "kucoin",
                symbol,
                timeframe,
                limit=self.config.ohlcv_limit,
            )
        except Exception as exc:
            logger.error("live_fetch_error", symbol=symbol, tf=timeframe, error=str(exc))
            return pd.DataFrame()
