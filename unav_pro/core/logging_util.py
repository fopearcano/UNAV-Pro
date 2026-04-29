"""Logging helper for UNAV Pro.

The plugin must remain quiet by default but produce a useful, persistent
log when the user reports an issue. We log to:

  1. Python ``logging`` (so the C4D Python console captures messages).
  2. A rotating log file at ``<temp>/unav_pro/unav_pro.log``.

The directory is created lazily; if the filesystem is read-only or the
path cannot be created the file handler is silently skipped — logging
must never crash the plugin.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import tempfile
from typing import Optional

_LOGGER_NAME = "unav_pro"
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False
_log_file_path: Optional[str] = None


def _default_log_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "unav_pro")


def _ensure_dir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except OSError:
        return False


def init_logging(level: int = logging.INFO, log_dir: Optional[str] = None) -> logging.Logger:
    """Initialize the UNAV Pro logger. Idempotent.

    Returns the root UNAV Pro logger. If a file handler cannot be
    attached (e.g. read-only filesystem) only the stream handler is used.
    """
    global _initialized, _log_file_path

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)

    if _initialized:
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    target_dir = log_dir or _default_log_dir()
    if _ensure_dir(target_dir):
        log_path = os.path.join(target_dir, "unav_pro.log")
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            _log_file_path = log_path
        except OSError:
            # Filesystem refused; carry on with stream-only logging.
            logger.warning("Could not open log file at %s; stream logging only.", log_path)

    logger.propagate = False
    _initialized = True
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a child of the UNAV Pro logger.

    Calling this before ``init_logging`` returns a logger with default
    settings — it will work, just without our formatting.
    """
    if not _initialized:
        init_logging()
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)


def log_file_path() -> Optional[str]:
    """Path to the active rotating log file, or None if file logging is off."""
    return _log_file_path
