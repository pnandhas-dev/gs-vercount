"""Logging utilities."""

import logging
import sys
from typing import TextIO

from rich.console import Console
from rich.logging import RichHandler


def setup_logging(
    level: str = "INFO",
    format_string: str | None = None,
    stream: TextIO = sys.stderr
) -> logging.Logger:
    """Setup logging with Rich handler."""
    logger = logging.getLogger("qadmcli")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers
    logger.handlers = []
    
    # Create Rich handler
    console = Console(file=stream, force_terminal=True)
    handler = RichHandler(
        console=console,
        show_time=True,
        show_path=True,
        rich_tracebacks=True
    )
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Set formatter if provided
    if format_string:
        formatter = logging.Formatter(format_string)
        handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger


def get_logger(name: str = "qadmcli") -> logging.Logger:
    """Get logger instance."""
    return logging.getLogger(name)
