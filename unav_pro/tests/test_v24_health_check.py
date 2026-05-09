"""v2.4 health-check tests."""

from __future__ import annotations

import pytest

from core.health_check import (
    STATUS_ERROR,
    STATUS_INFO,
    STATUS_OK,
    STATUS_WARNING,
    HealthCheckEntry,
    HealthReport,
    list_probe_names,
    run_health_check,
)


# ---------------------------------------------------------------------------
# Severity constants
# ---------------------------------------------------------------------------


def test_severity_constants():
    assert STATUS_OK == "ok"
    assert STATUS_WARNING == "warning"
    assert STATUS_ERROR == "error"
    assert STATUS_INFO == "info"


# ---------------------------------------------------------------------------
# Entry shape
# ---------------------------------------------------------------------------


def test_entry_predicates():
    ok = HealthCheckEntry(name="x", status=STATUS_OK)
    warn = HealthCheckEntry(name="x", status=STATUS_WARNING)
    err = HealthCheckEntry(name="x", status=STATUS_ERROR)
    assert ok.is_ok() and not ok.is_error() and not ok.is_warning()
    assert warn.is_warning() and not warn.is_error()
    assert err.is_error() and not err.is_ok()


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------


def test_empty_report_summary_says_ok():
    rpt = HealthReport()
    assert rpt.is_healthy()
    assert "OK" in rpt.summary_line()


def test_report_with_only_warnings_is_healthy():
    rpt = HealthReport(entries=[
        HealthCheckEntry(name="x", status=STATUS_WARNING, detail="meh"),
    ])
    assert rpt.is_healthy()
    assert rpt.has_warnings()
    assert "warning" in rpt.summary_line() or "OK" in rpt.summary_line()


def test_report_with_error_is_unhealthy():
    rpt = HealthReport(entries=[
        HealthCheckEntry(name="x", status=STATUS_ERROR, detail="bad"),
    ])
    assert not rpt.is_healthy()
    assert "FAIL" in rpt.summary_line()


def test_report_render_includes_each_entry():
    rpt = HealthReport(entries=[
        HealthCheckEntry(name="alpha", status=STATUS_OK, detail="present"),
        HealthCheckEntry(name="beta",  status=STATUS_WARNING, detail="check"),
    ])
    text = rpt.render()
    assert "alpha" in text
    assert "beta" in text
    assert "[OK]" in text
    assert "[!!]" in text


# ---------------------------------------------------------------------------
# Probe registry
# ---------------------------------------------------------------------------


def test_list_probe_names_includes_required_set():
    names = set(list_probe_names())
    expected = {
        "probe_version", "probe_config_dir", "probe_cache_dir",
        "probe_dataset_registry", "probe_sample_catalog",
        "probe_db_module", "probe_voyage_module", "probe_export_module",
    }
    assert expected.issubset(names)


# ---------------------------------------------------------------------------
# run_health_check end-to-end
# ---------------------------------------------------------------------------


def test_run_health_check_returns_one_entry_per_probe():
    rpt = run_health_check()
    assert len(rpt.entries) == len(list_probe_names())


def test_run_health_check_does_not_raise():
    """Defensive contract: every probe is wrapped in a
    boundary handler. The top-level function must never
    raise even on a hostile environment."""
    rpt = run_health_check()
    assert isinstance(rpt, HealthReport)


def test_run_health_check_clean_install_is_healthy():
    """In the source-repo working tree, every probe should
    be OK or info (no errors). Warnings are acceptable
    (e.g. sqlite3 absent on rare Python builds)."""
    rpt = run_health_check()
    errors = rpt.errors()
    if errors:
        # Print the entries so a CI failure shows what
        # broke without the test itself losing context.
        details = "; ".join(f"{e.name}={e.detail}" for e in errors)
        pytest.fail(f"unexpected errors: {details}")


def test_version_probe_reports_canonical_version():
    rpt = run_health_check()
    version_entry = next(
        (e for e in rpt.entries if e.name == "version"), None,
    )
    assert version_entry is not None
    assert version_entry.is_ok()
    from version import PLUGIN_VERSION
    assert PLUGIN_VERSION in version_entry.detail


def test_voyage_probe_present():
    rpt = run_health_check()
    voyage_entry = next(
        (e for e in rpt.entries if e.name == "voyage"), None,
    )
    assert voyage_entry is not None
    assert voyage_entry.is_ok()


def test_export_probe_present():
    rpt = run_health_check()
    export_entry = next(
        (e for e in rpt.entries if e.name == "export"), None,
    )
    assert export_entry is not None
    assert export_entry.is_ok()


def test_health_check_is_deterministic():
    """Same environment + same call → same probe results."""
    a = run_health_check()
    b = run_health_check()
    assert len(a.entries) == len(b.entries)
    for ea, eb in zip(a.entries, b.entries):
        assert ea.name == eb.name
        # Status may shift if the environment changes between
        # calls (rare); for v2.4 we assert the names line up.
