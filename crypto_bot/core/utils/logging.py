"""
Structured Logging Setup
=========================
Uses structlog for structured, JSON-formatted logs.

Benefits:
- Machine-readable logs (JSON)
- Automatic context injection (timestamp, level, module)
- Colorized console output for development
- Easy integration with log aggregation tools (ELK, Datadog)
"""

import logging
import sys
from typing import Optional

import structlog
from structlog.processors import JSONRenderer
from structlog.stdlib import add_log_level, add_logger_name


def setup_logging(
    level: str = "INFO",
    format: str = "console",  # "console" or "json"
    log_file: Optional[str] = None,
) -> None:
    """
    Configure structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Output format:
            - "console": Colored, human-readable (development)
            - "json": JSON format (production)
        log_file: Optional file path to write logs
    """
    # Convert level string to logging constant
    level = getattr(logging, level.upper())

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stdout,
    )

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        logging.root.addHandler(file_handler)

    # Configure structlog processors
    processors = [
        structlog.stdlib.filter_by_level,
        add_log_level,
        add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add format-specific processor
    if format == "json":
        processors.append(JSONRenderer())
    else:  # console
        processors.append(
            structlog.dev.ConsoleRenderer(colors=True)
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Structured logger instance

    Usage:
        logger = get_logger(__name__)
        logger.info("order_created", order_id="12345", symbol="BTC/USDT", amount=0.01)

        # Output (console):
        2026-02-09T10:30:00Z [info     ] order_created order_id=12345 symbol=BTC/USDT amount=0.01

        # Output (json):
        {"event": "order_created", "order_id": "12345", "symbol": "BTC/USDT", "amount": 0.01, "timestamp": "2026-02-09T10:30:00Z", "level": "info"}
    """
    return structlog.get_logger(name)


# Configure default logging (console, INFO level)
setup_logging()
