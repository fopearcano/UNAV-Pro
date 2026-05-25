"""Home-tab dashboard composition (pure).

The Home tab shows an at-a-glance summary of the session: plugin
version, current workspace, loaded datasets, navigator status, visible-
sector status, the active mission, and the last health-check result.

This module builds that summary as **text** from an injected
:class:`DashboardState`, with no Cinema 4D dependency, so the
composition is unit-tested directly. The dialog gathers the live state,
fills a ``DashboardState``, and drops :func:`build_dashboard_text` into
a read-only widget.

Stdlib-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ui.ui_helpers import Status, compact_separator, format_status_label


@dataclass
class DashboardState:
    """Everything the Home dashboard renders. Every field is optional;
    unknown values render as a ``[MISSING]`` / ``[...]`` line rather
    than blowing up, so the dashboard works even before anything is
    loaded."""

    plugin_version: str = ""
    codename: str = ""
    workspace_path: Optional[str] = None
    dataset_count: int = 0
    enabled_dataset_count: int = 0
    navigator_present: bool = False
    navigator_name: Optional[str] = None
    visible_sector_synced: bool = False
    visible_sector_count: Optional[int] = None
    active_mission: Optional[str] = None
    health_ok: Optional[bool] = None
    health_summary: str = ""


def _version_line(state: DashboardState) -> str:
    if not state.plugin_version:
        return format_status_label(Status.PENDING, "UNAV Pro (version unknown)")
    tail = f" — {state.codename}" if state.codename else ""
    return format_status_label(
        Status.OK, f"UNAV Pro v{state.plugin_version}{tail}",
    )


def _workspace_line(state: DashboardState) -> str:
    if not state.workspace_path:
        return format_status_label(Status.MISSING, "Workspace: none selected")
    return format_status_label(Status.OK, f"Workspace: {state.workspace_path}")


def _datasets_line(state: DashboardState) -> str:
    if state.dataset_count <= 0:
        return format_status_label(Status.MISSING, "Datasets: none registered")
    status = Status.OK if state.enabled_dataset_count > 0 else Status.WARN
    return format_status_label(
        status,
        f"Datasets: {state.enabled_dataset_count} enabled "
        f"of {state.dataset_count} registered",
    )


def _navigator_line(state: DashboardState) -> str:
    if not state.navigator_present:
        return format_status_label(Status.MISSING, "Navigator: not created")
    name = state.navigator_name or "Navigator"
    return format_status_label(Status.OK, f"Navigator: {name}")


def _sector_line(state: DashboardState) -> str:
    if not state.visible_sector_synced:
        return format_status_label(Status.PENDING, "Visible sector: not synced")
    count = (
        f"{state.visible_sector_count} objects"
        if state.visible_sector_count is not None
        else "synced"
    )
    return format_status_label(Status.OK, f"Visible sector: {count}")


def _mission_line(state: DashboardState) -> str:
    if not state.active_mission:
        return format_status_label(Status.INFO, "Mission: none active")
    return format_status_label(Status.OK, f"Mission: {state.active_mission}")


def _health_line(state: DashboardState) -> str:
    if state.health_ok is None:
        return format_status_label(Status.PENDING, "Health check: not run")
    status = Status.OK if state.health_ok else Status.ERROR
    summary = state.health_summary.strip() or (
        "all checks passed" if state.health_ok else "issues found"
    )
    return format_status_label(status, f"Health: {summary}")


def build_dashboard_text(state: DashboardState) -> str:
    """Render the full Home dashboard block."""
    lines: List[str] = [
        _version_line(state),
        compact_separator(),
        _workspace_line(state),
        _datasets_line(state),
        _navigator_line(state),
        _sector_line(state),
        _mission_line(state),
        _health_line(state),
    ]
    return "\n".join(lines)


#: The five primary Home actions, in order. The dialog wires each
#: ``key`` to a button + its existing handler. Kept here so the Home
#: tab and the docs agree on the set.
HOME_ACTIONS = (
    ("create_navigator", "Create Navigator"),
    ("register_dataset", "Load / Register Dataset"),
    ("sync_sector", "Sync Visible Sector"),
    ("open_sample", "Open Sample Demo"),
    ("run_health_check", "Run Health Check"),
)
