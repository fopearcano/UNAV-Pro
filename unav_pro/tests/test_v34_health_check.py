"""v3.4 health-check tests.

Cover the new beta probes added to
``core/health_check.py``: Python runtime, C4D host,
workspace, active mission, visible sector, presentation
module.
"""

from __future__ import annotations

import pytest

from core.health_check import (
    STATUS_ERROR,
    STATUS_INFO,
    STATUS_OK,
    STATUS_WARNING,
    HealthCheckEntry,
    HealthReport,
    _probe_active_mission_state,
    _probe_c4d_host,
    _probe_presentation_module,
    _probe_python_runtime,
    _probe_visible_sector_state,
    _probe_workspace_state,
    list_probe_names,
    run_health_check,
)
from core.state_manager import (
    set_current_mission,
    set_current_workspace,
)


# ---------------------------------------------------------------------------
# Probe inventory
# ---------------------------------------------------------------------------


def test_v34_probes_listed_in_inventory():
    names = list_probe_names()
    expected = {
        "probe_version", "probe_python_runtime", "probe_c4d_host",
        "probe_config_dir", "probe_cache_dir", "probe_dataset_registry",
        "probe_sample_catalog", "probe_db_module", "probe_voyage_module",
        "probe_export_module", "probe_workspace_state",
        "probe_active_mission_state", "probe_visible_sector_state",
        "probe_presentation_module",
    }
    assert expected.issubset(set(names))


def test_v34_probes_count_is_at_least_fourteen():
    assert len(list_probe_names()) >= 14


# ---------------------------------------------------------------------------
# Python runtime probe
# ---------------------------------------------------------------------------


def test_python_runtime_probe_returns_ok_on_modern_python():
    entry = _probe_python_runtime()
    assert isinstance(entry, HealthCheckEntry)
    assert entry.name == "python_runtime"
    # On 3.10+, status is OK.
    import sys
    if sys.version_info >= (3, 10):
        assert entry.status == STATUS_OK
        assert "Python" in entry.detail


# ---------------------------------------------------------------------------
# C4D host probe
# ---------------------------------------------------------------------------


def test_c4d_host_probe_outside_c4d_returns_info():
    """Outside Cinema 4D, probe reports INFO not ERROR."""
    entry = _probe_c4d_host()
    assert entry.name == "c4d_host"
    # Test suite runs outside C4D.
    assert entry.status == STATUS_INFO


# ---------------------------------------------------------------------------
# Workspace probe
# ---------------------------------------------------------------------------


def test_workspace_probe_idle_returns_info():
    set_current_workspace(None)
    entry = _probe_workspace_state()
    assert entry.name == "workspace"
    assert entry.status == STATUS_INFO


def test_workspace_probe_with_intact_workspace_returns_ok(tmp_path):
    from project import create_workspace
    ws = create_workspace(str(tmp_path / "ws"))
    set_current_workspace(ws)
    try:
        entry = _probe_workspace_state()
    finally:
        set_current_workspace(None)
    assert entry.status == STATUS_OK
    assert "intact" in entry.detail


def test_workspace_probe_with_damaged_workspace_warns(tmp_path):
    """Removing a subdir flips intact → False; the probe
    should warn rather than error."""
    import os
    from project import create_workspace
    ws = create_workspace(str(tmp_path / "ws"))
    os.rmdir(ws.cache_dir())
    set_current_workspace(ws)
    try:
        entry = _probe_workspace_state()
    finally:
        set_current_workspace(None)
    assert entry.status == STATUS_WARNING


# ---------------------------------------------------------------------------
# Active-mission probe
# ---------------------------------------------------------------------------


def test_active_mission_probe_idle_returns_info():
    set_current_mission(None)
    entry = _probe_active_mission_state()
    assert entry.name == "active_mission"
    assert entry.status == STATUS_INFO


def test_active_mission_probe_with_mission_returns_ok():
    from voyage import Mission, MissionWaypoint
    mission = Mission(title="Demo")
    mission.waypoints.append(MissionWaypoint(
        kind="coordinate", label="origin",
        x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
    ))
    set_current_mission(mission)
    try:
        entry = _probe_active_mission_state()
    finally:
        set_current_mission(None)
    assert entry.status == STATUS_OK
    assert "Demo" in entry.detail


# ---------------------------------------------------------------------------
# Visible-sector probe
# ---------------------------------------------------------------------------


def test_visible_sector_probe_returns_info_outside_c4d():
    """Outside C4D, the visible-sector probe falls back
    to the state-manager's stub summary."""
    entry = _probe_visible_sector_state()
    assert entry.name == "visible_sector"
    # Either OK with a summary string or INFO with the
    # outside-C4D fallback. Either is acceptable.
    assert entry.status in (STATUS_OK, STATUS_INFO)


# ---------------------------------------------------------------------------
# Presentation probe
# ---------------------------------------------------------------------------


def test_presentation_probe_returns_ok_when_importable():
    entry = _probe_presentation_module()
    assert entry.name == "presentation"
    assert entry.status == STATUS_OK


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------


def test_run_health_check_includes_all_v34_probes():
    report = run_health_check()
    names = [e.name for e in report.entries]
    for required in (
        "version", "python_runtime", "c4d_host",
        "workspace", "active_mission",
        "visible_sector", "presentation",
    ):
        assert required in names


def test_run_health_check_overall_passes_in_test_env():
    """The full health check must pass (no errors) when
    run from the test suite."""
    set_current_workspace(None)
    set_current_mission(None)
    report = run_health_check()
    assert report.is_healthy()


def test_render_includes_v34_probes():
    set_current_workspace(None)
    set_current_mission(None)
    report = run_health_check()
    text = report.render()
    assert "python_runtime" in text
    assert "c4d_host" in text
    assert "presentation" in text
