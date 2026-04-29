"""Tests for core.logger — ring buffer, environment snapshot, and the
diagnostics formatter. Pure CPython, no Cinema 4D."""

from __future__ import annotations

import logging

import pytest

from core import logger as logger_mod
from core.config import UnavConfig
from core.dataset_registry import DatasetEntry, DatasetRegistry, DatasetStats
from core.logger import (
    LEVELS,
    RING_BUFFER_DEFAULT,
    RingBufferHandler,
    clear_recent_logs,
    debug,
    error,
    format_diagnostics,
    gather_environment,
    info,
    install_ring_buffer,
    log_folder,
    plugin_root,
    recent_logs,
    reset_ring_buffer_for_tests,
    warning,
)
from core.logging_util import get_logger
from core.metadata_lookup import MetadataLookup
from data.schema import CatalogObject


@pytest.fixture(autouse=True)
def _clean_ring():
    """Every test starts with a fresh ring buffer."""
    reset_ring_buffer_for_tests()
    yield
    reset_ring_buffer_for_tests()


def _emit(level: str, message: str) -> None:
    log = get_logger("test")
    getattr(log, level.lower())(message)


# ---------------------------------------------------------------------------
# Ring-buffer handler
# ---------------------------------------------------------------------------


def test_install_ring_buffer_returns_singleton():
    a = install_ring_buffer()
    b = install_ring_buffer()
    assert a is b
    assert isinstance(a, RingBufferHandler)


def test_ring_buffer_captures_records():
    install_ring_buffer()
    _emit("info", "hello world")
    out = recent_logs()
    assert any("hello world" in r["message"] for r in out)


def test_ring_buffer_captures_each_level():
    install_ring_buffer()
    for level in ("debug", "info", "warning", "error"):
        _emit(level, f"{level} payload")
    out = recent_logs()
    levels_seen = {r["level"] for r in out}
    assert levels_seen.issuperset(set(LEVELS))


def test_ring_buffer_respects_maxlen():
    install_ring_buffer(maxlen=3)
    for i in range(10):
        _emit("info", f"msg {i}")
    out = recent_logs()
    # Only the most recent 3 records survive.
    msgs = [r["message"] for r in out]
    assert len(msgs) == 3
    assert msgs[-1] == "msg 9"
    assert msgs[0] == "msg 7"


def test_recent_logs_filters_by_level():
    install_ring_buffer()
    _emit("info", "informational")
    _emit("warning", "be careful")
    _emit("error", "boom")
    only_warn = recent_logs(level="WARNING")
    assert all(r["level"] == "WARNING" for r in only_warn)
    assert any("careful" in r["message"] for r in only_warn)


def test_recent_logs_filter_unknown_level_returns_all():
    install_ring_buffer()
    _emit("info", "hi")
    _emit("error", "bye")
    out = recent_logs(level="NOTALEVEL")
    levels = {r["level"] for r in out}
    assert "INFO" in levels and "ERROR" in levels


def test_recent_logs_respects_limit():
    install_ring_buffer()
    for i in range(5):
        _emit("info", f"m{i}")
    out = recent_logs(limit=2)
    assert len(out) == 2
    assert [r["message"] for r in out] == ["m3", "m4"]


def test_recent_logs_returns_empty_when_buffer_not_installed():
    assert recent_logs() == []


def test_clear_recent_logs_empties_buffer():
    install_ring_buffer()
    _emit("info", "first")
    clear_recent_logs()
    assert recent_logs() == []


def test_ring_buffer_emit_never_raises_for_bad_record():
    handler = install_ring_buffer()
    bad = logging.LogRecord(
        name="x", level=logging.INFO, pathname="?", lineno=0,
        msg="%s", args=("only one — but format expects another %s",),
        exc_info=None,
    )
    # Should not raise even when getMessage() would fail.
    try:
        handler.emit(bad)
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"ring buffer raised: {exc!r}")


# ---------------------------------------------------------------------------
# Convenience shortcuts
# ---------------------------------------------------------------------------


def test_shortcuts_route_through_package_logger():
    install_ring_buffer()
    info("info shortcut")
    warning("warn shortcut")
    error("err shortcut")
    debug("dbg shortcut")
    msgs = [r["message"] for r in recent_logs()]
    assert any("info shortcut" in m for m in msgs)
    assert any("warn shortcut" in m for m in msgs)
    assert any("err shortcut" in m for m in msgs)


def test_shortcut_with_explicit_name_lands_under_subpath():
    install_ring_buffer()
    info("named", name="diagnostics_test")
    out = recent_logs()
    assert any(r["name"].endswith("diagnostics_test") for r in out)


# ---------------------------------------------------------------------------
# Environment snapshot
# ---------------------------------------------------------------------------


def test_plugin_root_resolves_to_unav_pro_dir():
    p = plugin_root()
    assert p.endswith("unav_pro") or p.endswith("unav_pro" + "/")  # tolerate trailing sep


def test_gather_environment_minimal_keys_present():
    env = gather_environment()
    for key in ("c4d_version", "python_version", "platform",
                "plugin_root", "log_file", "log_folder"):
        assert key in env


def test_gather_environment_without_c4d_reports_placeholder():
    env = gather_environment()
    assert "not running inside C4D" in env["c4d_version"]


def test_gather_environment_with_config_includes_cache_root(tmp_path):
    config = UnavConfig(cache_root=str(tmp_path))
    env = gather_environment(config=config)
    assert env["cache_root"] == str(tmp_path)


def test_gather_environment_with_registry_lists_datasets():
    reg = DatasetRegistry()
    e = DatasetEntry(name="a", path="/p", enabled=True)
    e.stats = DatasetStats(object_count=42, sources=["unav_sample"])
    reg.entries.append(e)
    reg.entries.append(DatasetEntry(name="b", path="/q", enabled=False))
    env = gather_environment(registry=reg)
    assert env["datasets_total"] == 2
    assert env["datasets_enabled"] == 1
    names = {d["name"] for d in env["datasets"]}
    assert names == {"a", "b"}
    a = next(d for d in env["datasets"] if d["name"] == "a")
    assert a["object_count"] == 42
    assert a["sources"] == ["unav_sample"]


def test_gather_environment_with_lookup_reports_counts():
    lookup = MetadataLookup([
        CatalogObject(uid="a", catalog_source="x", object_type="star",
                      ra_deg=10.0, dec_deg=20.0),
        CatalogObject(uid="b", catalog_source="y", object_type="galaxy",
                      ra_deg=11.0, dec_deg=21.0),
    ])
    env = gather_environment(lookup=lookup)
    assert env["lookup_object_count"] == 2
    assert sorted(env["lookup_sources"]) == ["x", "y"]


def test_gather_environment_generated_count_is_none_outside_c4d():
    env = gather_environment()
    # Outside Cinema 4D the helper cannot count visible-sector
    # children — the dialog renders this as "(no active document)".
    assert env["generated_count"] is None


# ---------------------------------------------------------------------------
# Diagnostics formatter
# ---------------------------------------------------------------------------


def test_format_diagnostics_includes_environment_keys():
    env = gather_environment(config=UnavConfig(cache_root="/tmp"))
    text = format_diagnostics(env)
    assert "UNAV Pro Diagnostics" in text
    assert "Cinema 4D" in text
    assert "Python" in text
    assert "Plugin root" in text
    assert "Cache root      : /tmp" in text


def test_format_diagnostics_renders_dataset_table():
    reg = DatasetRegistry()
    e = DatasetEntry(name="A", path="/a", enabled=True)
    e.stats = DatasetStats(object_count=10, sources=["gaia_dr3"])
    reg.entries.append(e)
    reg.entries.append(DatasetEntry(name="B", path="/b", enabled=False))
    text = format_diagnostics(gather_environment(registry=reg))
    assert "[ON ]" in text
    assert "[off]" in text
    assert "A" in text and "B" in text
    assert "gaia_dr3" in text


def test_format_diagnostics_no_registry_says_so():
    text = format_diagnostics(gather_environment())
    assert "no registry attached" in text


def test_format_diagnostics_includes_recent_records():
    install_ring_buffer()
    _emit("info", "a marker line")
    text = format_diagnostics(
        gather_environment(),
        recent_logs(),
    )
    assert "Recent log entries" in text
    assert "a marker line" in text


def test_format_diagnostics_empty_records_omits_section():
    text = format_diagnostics(gather_environment(), [])
    assert "Recent log entries" not in text


def test_format_diagnostics_renders_lookup_section():
    lookup = MetadataLookup([
        CatalogObject(uid="x", catalog_source="src", object_type="star",
                      ra_deg=0.0, dec_deg=0.0),
    ])
    text = format_diagnostics(gather_environment(lookup=lookup))
    assert "Lookup objects  : 1" in text
    assert "src" in text


def test_format_diagnostics_generated_count_when_none():
    env = gather_environment()
    text = format_diagnostics(env)
    assert "no active document" in text


# ---------------------------------------------------------------------------
# DiagnosticsController (non-c4d code)
# ---------------------------------------------------------------------------


def test_diagnostics_controller_snapshot_composes_text(tmp_path):
    from ui.diagnostics_panel import DiagnosticsController

    install_ring_buffer()
    _emit("warning", "ctrl warn")

    reg = DatasetRegistry()
    reg.entries.append(DatasetEntry(name="a", path="/a"))
    config = UnavConfig(cache_root=str(tmp_path / "cache"))
    lookup = MetadataLookup([
        CatalogObject(uid="x", catalog_source="src", object_type="star",
                      ra_deg=0.0, dec_deg=0.0),
    ])

    ctrl = DiagnosticsController(registry=reg, lookup=lookup, config=config)
    text = ctrl.snapshot()
    assert "UNAV Pro Diagnostics" in text
    assert "ctrl warn" in text
    assert str(tmp_path / "cache") in text
    assert "[ON ]" in text or "[off]" in text


def test_diagnostics_controller_level_filter():
    from ui.diagnostics_panel import DiagnosticsController

    install_ring_buffer()
    _emit("info", "info-line")
    _emit("error", "error-line")

    ctrl = DiagnosticsController()
    error_only = ctrl.snapshot(level="ERROR")
    assert "error-line" in error_only
    assert "info-line" not in error_only.split("Recent log entries")[1]


def test_diagnostics_controller_resolves_lazily(tmp_path, monkeypatch):
    """If no registry/lookup/config is passed, the controller must
    fall back to the default lookups and never raise."""
    from ui.diagnostics_panel import DiagnosticsController

    # Point the registry path at an empty location so load() yields
    # an empty registry.
    monkeypatch.setattr(
        "core.dataset_registry.default_registry_path",
        lambda: str(tmp_path / "no.json"),
    )
    ctrl = DiagnosticsController()
    text = ctrl.snapshot()
    assert "UNAV Pro Diagnostics" in text


# ---------------------------------------------------------------------------
# log_folder
# ---------------------------------------------------------------------------


def test_log_folder_returns_directory_or_none():
    folder = log_folder()
    # Can be None on read-only filesystems, otherwise a real
    # directory string.
    if folder is not None:
        import os
        assert os.path.basename(folder) == "unav_pro"
