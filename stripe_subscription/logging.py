"""
Structured logging configuration for SOC2 compliance.
Uses structlog for JSON-formatted, machine-readable logs.
"""

import logging
import sys
from contextvars import ContextVar

import structlog

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def setup_logging(json_logs: bool | None = None) -> None:
    """
    Configure structured logging with structlog.

    Args:
        json_logs: Force JSON output. If None, auto-detect based on TTY.
    """
    if json_logs is None:
        json_logs = not sys.stdout.isatty()

    timestamper = structlog.processors.TimeStamper(fmt="iso")

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    handlers = []
    if json_logs:
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer()
        )
    else:
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=True)
        )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handlers.append(handler)

    # Apply to root logger
    root_logger = logging.getLogger()
    root_logger.handlers = handlers
    root_logger.setLevel(logging.INFO)

    # Silence noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str = "pocket_tts"):
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Auto-setup on import
setup_logging()
logger = get_logger()


class RequestIdFilter(logging.Filter):
    """Filter that adds request_id to log records."""

    def filter(self, record):
        record.request_id = request_id_var.get() or "no-id"
        return True
