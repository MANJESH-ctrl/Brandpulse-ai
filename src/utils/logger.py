import logging
import structlog
from src.utils.config import settings


def setup_logging() -> None:
    """Configure structlog for the entire application. Call once on startup."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.debug:
        # Human-readable output for development
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]
    else:
        # Machine-readable JSON for production
        processors = shared_processors + [structlog.processors.JSONRenderer()]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a named logger. Usage: logger = get_logger(__name__)"""
    return structlog.get_logger(name)
