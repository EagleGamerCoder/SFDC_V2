"""Centralised console and rotating-file logging setup."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(level_name: str, log_directory: Path) -> None:
    """Configure console logging and a rotating file handler. Safe to call at startup."""
    level = getattr(logging, level_name.upper(), None)
    if not isinstance(level, int):
        raise ValueError(f"Unsupported logging level: {level_name}")

    log_directory.mkdir(parents=True, exist_ok=True)
    log_file = log_directory / "sfd_bot.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    # force=True avoids duplicate handlers if called more than once in a dev process.
    logging.basicConfig(level=level, handlers=[console_handler, file_handler], force=True)

    # Keep noisy library logs at INFO unless the project is explicitly in DEBUG mode.
    library_level = logging.DEBUG if level == logging.DEBUG else logging.INFO
    logging.getLogger("discord").setLevel(library_level)
    logging.getLogger("discord.http").setLevel(library_level)
