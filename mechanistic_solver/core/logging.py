"""Logging framework for the independent mechanistic solver.

Provides a unified logger configured for console outputs and formatting.
"""
from __future__ import annotations

import logging
import sys


def get_logger(name: str = "mechanistic_solver") -> logging.Logger:
    """Retrieve or configure a logger with specific formatting.

    Args:
        name (str): Logger name. Defaults to "mechanistic_solver".

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Formatter: timestamp | level | logger name | message
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger
