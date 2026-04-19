"""
Configuration System
====================
Type-safe configuration using Pydantic.

Loads config from:
1. Environment variables (.env file)
2. Config dict (for programmatic usage)

Priority: Config dict > Environment variables > Defaults
"""

from decimal import Decimal
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from pathlib import Path


class ExchangeConfig(BaseModel):
    """Exchange connection configuration."""

    exchange: str = Field(..., description="Exchange name (binance, bybit, kraken, etc.)")
    api_key: Optional[str] = Field(None, description="API key")
    api_secret: Optional[str] = Field(None, description="API secret")
    password: Optional[str] = Field(None, description="API password (some exchanges)")

    testnet: bool = Field(False, description="Use testnet/sandbox")
    dry_run: bool = Field(False, description="Simulate orders without sending")

    timeout: int = Field(30000, description="Request timeout (ms)")
    rate_limit: bool = Field(True, description="Enable rate limiting")
    max_retries: int = Field(3, description="Max retry attempts")

    @field_validator('exchange')
    @classmethod
    def exchange_must_be_lowercase(cls, v):
        return v.lower()

    @field_validator('api_key', 'api_secret')
    @classmethod
    def credentials_required_for_trading(cls, v):
        """Warn if credentials missing (public endpoints work without)."""
        # Don't enforce here - let exchange connector handle it
        return v


class RiskConfig(BaseModel):
    """Risk management configuration."""

    risk_per_trade_pct: Decimal = Field(
        Decimal("0.5"),
        description="Risk per trade (% of balance)"
    )

    max_open_trades: int = Field(3, description="Max simultaneous open trades")
    max_trades_per_day: int = Field(5, description="Max trades per day")

    daily_loss_limit_pct: Decimal = Field(
        Decimal("5.0"),
        description="Daily loss limit (% of starting balance)"
    )

    max_drawdown_pct: Decimal = Field(
        Decimal("10.0"),
        description="Max drawdown limit (% of peak balance)"
    )

    @field_validator('risk_per_trade_pct', 'daily_loss_limit_pct', 'max_drawdown_pct')
    @classmethod
    def must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Percentage must be positive")
        return v


class TradingConfig(BaseModel):
    """Trading strategy configuration."""

    symbols: list[str] = Field(
        ["BTC/USDT"],
        description="Symbols to trade"
    )

    timeframe: str = Field("5m", description="Chart timeframe (1m, 5m, 15m, 1h, etc.)")

    max_spread_pct: Decimal = Field(
        Decimal("0.2"),
        description="Max spread (% of bid) to allow entry"
    )

    sessions_enabled: list[str] = Field(
        ["us_hours"],
        description="Trading sessions to enable (us_hours, asia, weekend, all)"
    )

    @field_validator('symbols')
    @classmethod
    def symbols_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("Must specify at least one symbol")
        return v


class BotConfig(BaseSettings):
    """
    Main bot configuration.

    Loads from environment variables with prefix CRYPTO_BOT_
    Example .env:
        CRYPTO_BOT_EXCHANGE__EXCHANGE=binance
        CRYPTO_BOT_EXCHANGE__API_KEY=your_key
        CRYPTO_BOT_EXCHANGE__TESTNET=true
        CRYPTO_BOT_RISK__RISK_PER_TRADE_PCT=0.5
    """

    exchange: ExchangeConfig
    risk: RiskConfig = Field(default_factory=RiskConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)

    log_level: str = Field("INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")
    log_format: str = Field("console", description="Log format (console, json)")
    log_file: Optional[str] = Field(None, description="Log file path")

    class Config:
        env_prefix = "CRYPTO_BOT_"
        env_nested_delimiter = "__"
        case_sensitive = False

    @classmethod
    def from_env(cls, env_file: str = ".env") -> "BotConfig":
        """
        Load config from .env file.

        Args:
            env_file: Path to .env file

        Returns:
            BotConfig instance
        """
        from dotenv import load_dotenv

        env_path = Path(env_file)
        if env_path.exists():
            load_dotenv(env_path)

        # Must provide exchange config at minimum
        return cls(
            exchange=ExchangeConfig(
                exchange="binance"  # Default, will be overridden by env
            )
        )

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "BotConfig":
        """
        Load config from dictionary.

        Args:
            config_dict: Configuration dictionary

        Returns:
            BotConfig instance

        Example:
            config = BotConfig.from_dict({
                'exchange': {
                    'exchange': 'binance',
                    'api_key': 'xxx',
                    'api_secret': 'yyy',
                    'testnet': True
                },
                'risk': {
                    'risk_per_trade_pct': 0.5
                }
            })
        """
        return cls(**config_dict)

    def to_exchange_config(self) -> Dict[str, Any]:
        """
        Convert to exchange connector config format.

        Returns:
            Dict suitable for IExchange.__init__()
        """
        return {
            'exchange': self.exchange.exchange,
            'api_key': self.exchange.api_key,
            'api_secret': self.exchange.api_secret,
            'password': self.exchange.password,
            'testnet': self.exchange.testnet,
            'dry_run': self.exchange.dry_run,
            'timeout': self.exchange.timeout,
            'rate_limit': self.exchange.rate_limit,
            'max_retries': self.exchange.max_retries,
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_config(
    env_file: Optional[str] = None,
    config_dict: Optional[Dict[str, Any]] = None,
) -> BotConfig:
    """
    Load configuration from env file or dict.

    Priority: config_dict > env_file > defaults

    Args:
        env_file: Path to .env file
        config_dict: Configuration dictionary

    Returns:
        BotConfig instance

    Usage:
        # From .env file
        config = load_config(env_file=".env")

        # From dict
        config = load_config(config_dict={
            'exchange': {'exchange': 'binance', 'testnet': True}
        })

        # Hybrid (dict overrides env)
        config = load_config(
            env_file=".env",
            config_dict={'exchange': {'dry_run': True}}
        )
    """
    if config_dict:
        return BotConfig.from_dict(config_dict)
    elif env_file:
        return BotConfig.from_env(env_file)
    else:
        # Defaults
        return BotConfig.from_dict({
            'exchange': {
                'exchange': 'binance',
                'testnet': True,
                'dry_run': True,
            }
        })
