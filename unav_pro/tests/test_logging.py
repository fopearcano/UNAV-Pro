"""Tests for the logging helper. Runs without Cinema 4D."""

from __future__ import annotations

import logging
import os

from core import logging_util


def test_init_logging_is_idempotent(tmp_path):
    log_dir = str(tmp_path / "logs")
    a = logging_util.init_logging(log_dir=log_dir)
    b = logging_util.init_logging(log_dir=log_dir)
    assert a is b
    assert a.name == "unav_pro"


def test_get_logger_returns_child():
    parent = logging_util.get_logger()
    child = logging_util.get_logger("child")
    assert child.name.startswith(parent.name)
    assert child.name.endswith("child")


def test_log_file_created(tmp_path):
    # Reset module state for a clean test.
    logging_util._initialized = False
    logging_util._log_file_path = None
    for h in list(logging.getLogger("unav_pro").handlers):
        logging.getLogger("unav_pro").removeHandler(h)

    log_dir = str(tmp_path / "fresh")
    log = logging_util.init_logging(log_dir=log_dir)
    log.info("hello")
    for h in log.handlers:
        h.flush()

    assert logging_util.log_file_path() is not None
    assert os.path.exists(logging_util.log_file_path())


def test_logging_survives_unwritable_dir(monkeypatch, tmp_path):
    # Reset module state.
    logging_util._initialized = False
    logging_util._log_file_path = None
    for h in list(logging.getLogger("unav_pro").handlers):
        logging.getLogger("unav_pro").removeHandler(h)

    def fail_makedirs(*_a, **_kw):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(logging_util.os, "makedirs", fail_makedirs)
    log = logging_util.init_logging(log_dir=str(tmp_path / "nope"))
    # Should not raise; should still return a logger.
    log.info("still works")
    assert logging_util.log_file_path() is None
