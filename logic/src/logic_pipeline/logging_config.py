"""Logging configuration for the Godot Logic Pipeline."""

import logging
import os
from pathlib import Path
from typing import Optional


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[Path] = None,
    log_filename: str = "pipeline.log",
) -> logging.Logger:
    """Configures structured console and file logging."""
    logger = logging.getLogger("logic_pipeline")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers to prevent duplicate messages
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(funcName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler (if log_dir provided)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        file_path = log_dir / log_filename
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Returns a namespaced child logger."""
    base_logger = logging.getLogger("logic_pipeline")
    if name:
        return base_logger.getChild(name)
    return base_logger
