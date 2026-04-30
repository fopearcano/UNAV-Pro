"""Mission panel — dialog-side glue for the v1.4 voyage system.

Pure-Python helpers: building summary text for the dialog,
adding the user's current selection / target lock / bookmark
as a waypoint, validating a freshly-edited title, and
formatting playback status lines. Cinema 4D bindings are
isolated in the dialog command dispatcher (``main_dialog.py``);
this module is unit-testable without c4d.

Functions in this module never raise on bad inputs — failure
modes return a status string the dialog appends to its log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from core.logging_util import get_logger
from voyage.camera_path import CameraPathConfig, build_camera_path
from voyage.mission import (
    MAX_WAYPOINTS_PER_MISSION,
    Mission,
    MissionWaypoint,
)
from voyage.mission_manager import (
    MissionManager,
    waypoint_from_object,
)
from voyage.playback import Playback, PlaybackTick

_log = get_logger("ui.mission_panel")


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def render_mission_list(manager: MissionManager) -> str:
    """Multi-line plain-text rendering of the artist's
    missions. The dialog renders this verbatim in the panel's
    list area."""
    if len(manager) == 0:
        return (
            "No missions yet. Click 'New Mission' to start one, "
            "or 'Import…' to load a JSON."
        )
    lines: List[str] = []
    lines.append(f"=== Missions ({len(manager)}) ===")
    for i, mission in enumerate(manager.list_all()):
        line = (
            f"  [{i}] {mission.title}  "
            f"({len(mission.waypoints)} wp, "
            f"{mission.total_duration_seconds():.1f}s)"
        )
        if mission.tags:
            line += f"  [{', '.join(mission.tags)}]"
        lines.append(line)
        if mission.description:
            lines.append(f"      {mission.description}")
    return "\n".join(lines)


def render_mission_detail(mission: Mission) -> str:
    """Full per-mission summary used when the artist selects a
    mission in the list."""
    lines: List[str] = []
    lines.append(f"=== {mission.title} ===")
    if mission.description:
        lines.append(mission.description)
    if mission.tags:
        lines.append("Tags: " + ", ".join(mission.tags))
    lines.append(
        f"Total: {len(mission.waypoints)} waypoint(s), "
        f"{mission.total_duration_seconds():.1f}s runtime"
    )
    epoch_range = mission.epoch_range()
    if epoch_range is not None:
        lines.append(f"Epoch range: JD {epoch_range[0]:.3f} → {epoch_range[1]:.3f}")
    lines.append(f"Created : {mission.created_iso}")
    lines.append(f"Modified: {mission.modified_iso}")
    lines.append("")
    lines.append("--- Waypoints ---")
    for i, wp in enumerate(mission.waypoints):
        line = f"  [{i}] {wp.display_label()}  ({wp.kind})"
        if wp.has_epoch():
            line += f"  @ JD {wp.epoch_jd:.3f}"
        line += f"  ({wp.duration_seconds:.1f}s)"
        lines.append(line)
        if wp.notes:
            lines.append(f"      note: {wp.notes}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Add / edit
# ---------------------------------------------------------------------------


def validate_title(title: str) -> Tuple[bool, str]:
    """Validate a freshly-typed mission title."""
    title = (title or "").strip()
    if not title:
        return False, "Mission: title can't be empty."
    if len(title) > 200:
        return False, "Mission: title is too long (200 char max)."
    return True, ""


def add_object_waypoint(
    mission: Mission, *,
    uid: str,
    label: str = "",
    catalog_source: Optional[str] = None,
    object_type: Optional[str] = None,
    epoch_jd: Optional[float] = None,
    duration_seconds: float = 4.0,
    notes: str = "",
) -> Tuple[bool, str]:
    """Add an ``object``-kind waypoint. The caller already
    knows the uid (from a search result, a selected scene
    object, or a bookmark). The cached position is left
    unresolved; the resolver fills it at playback build time.

    Returns ``(was_added, status_line)``."""
    if not uid:
        return False, "Mission: cannot add waypoint without a uid."
    if len(mission.waypoints) >= MAX_WAYPOINTS_PER_MISSION:
        return False, (
            f"Mission: already at max {MAX_WAYPOINTS_PER_MISSION} "
            "waypoints; split into two missions."
        )
    wp = waypoint_from_object(
        uid=uid, label=label,
        catalog_source=catalog_source,
        object_type=object_type,
        epoch_jd=epoch_jd,
        duration_seconds=duration_seconds,
        notes=notes,
    )
    mission.add(wp)
    return True, f"Mission: added waypoint {wp.display_label()}."


def add_bookmark_waypoint(
    mission: Mission, *,
    bookmark_id: str,
    label: str = "",
    epoch_jd: Optional[float] = None,
    duration_seconds: float = 4.0,
    notes: str = "",
) -> Tuple[bool, str]:
    """Add a ``bookmark``-kind waypoint."""
    if not bookmark_id:
        return False, "Mission: cannot add waypoint without bookmark_id."
    if len(mission.waypoints) >= MAX_WAYPOINTS_PER_MISSION:
        return False, (
            f"Mission: already at max {MAX_WAYPOINTS_PER_MISSION} "
            "waypoints; split into two missions."
        )
    wp = MissionWaypoint(
        kind="bookmark",
        bookmark_id=bookmark_id,
        label=label,
        epoch_jd=epoch_jd,
        duration_seconds=duration_seconds,
        notes=notes,
    )
    mission.add(wp)
    return True, f"Mission: added bookmark waypoint {wp.display_label()}."


def add_coordinate_waypoint(
    mission: Mission, *,
    x_c4d: float, y_c4d: float, z_c4d: float,
    label: str = "",
    epoch_jd: Optional[float] = None,
    duration_seconds: float = 4.0,
    notes: str = "",
) -> Tuple[bool, str]:
    """Add a ``coordinate``-kind waypoint at a free 3D point."""
    if len(mission.waypoints) >= MAX_WAYPOINTS_PER_MISSION:
        return False, (
            f"Mission: already at max {MAX_WAYPOINTS_PER_MISSION} "
            "waypoints; split into two missions."
        )
    wp = MissionWaypoint(
        kind="coordinate",
        label=label or "(coord)",
        x_c4d=float(x_c4d), y_c4d=float(y_c4d), z_c4d=float(z_c4d),
        epoch_jd=epoch_jd,
        duration_seconds=duration_seconds,
        notes=notes,
    )
    mission.add(wp)
    return True, f"Mission: added coordinate waypoint {wp.display_label()}."


def reorder_waypoint(mission: Mission, src: int, dst: int) -> Tuple[bool, str]:
    """Move waypoint ``src`` to position ``dst``."""
    if not mission.move(src, dst):
        return False, f"Mission: index {src} out of range."
    return True, f"Mission: moved waypoint {src} → {dst}."


def remove_waypoint(mission: Mission, index: int) -> Tuple[bool, str]:
    """Drop one waypoint by index."""
    removed = mission.remove_at(index)
    if removed is None:
        return False, f"Mission: index {index} out of range."
    return True, f"Mission: removed waypoint '{removed.display_label()}'."


# ---------------------------------------------------------------------------
# Playback status
# ---------------------------------------------------------------------------


def render_playback_status(playback: Optional[Playback]) -> str:
    """One-line playback status the dialog appends to the
    voyage panel header."""
    if playback is None:
        return "Playback: idle (no mission loaded)."
    if playback.total_steps == 0:
        return "Playback: empty mission (need ≥ 2 resolved waypoints)."
    state = "PLAYING" if playback.is_playing else (
        "FINISHED" if playback.is_finished else "PAUSED"
    )
    return (
        f"Playback: {state}  step {playback.step}/{playback.total_steps}  "
        f"interval {playback.effective_step_interval_seconds * 1000.0:.1f} ms"
    )


def render_tick(tick: PlaybackTick) -> str:
    """One-line description of a ``PlaybackTick``. Used for
    the dialog log."""
    sample = tick.sample
    line = (
        f"tick step={tick.step}/{tick.total_steps} "
        f"wp={sample.waypoint_index} "
        f"pos=({sample.x:+.3g},{sample.y:+.3g},{sample.z:+.3g})"
    )
    if sample.epoch_jd is not None:
        line += f" epoch_jd={sample.epoch_jd:.3f}"
    if tick.trigger_sync:
        line += "  [sync]"
    if tick.is_finished:
        line += "  [finished]"
    return line


# ---------------------------------------------------------------------------
# Build helpers exposed for the dialog
# ---------------------------------------------------------------------------


@dataclass
class MissionBuildReport:
    """Output of the build-mission step. Surfaces unresolved
    waypoint counts so the dialog can warn the artist."""

    resolved_count: int = 0
    unresolved_count: int = 0
    unresolved_indices: List[int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.unresolved_indices is None:
            self.unresolved_indices = []


def build_camera_path_with_report(
    mission: Mission,
    config: Optional[CameraPathConfig] = None,
) -> Tuple[object, MissionBuildReport]:
    """Build a camera path and a per-mission resolution report
    in one call. The dialog uses the report to show "X
    waypoints could not be resolved" before the artist hits
    Play."""
    report = MissionBuildReport()

    def _on_unresolved(idx: int, _wp) -> None:
        report.unresolved_count += 1
        report.unresolved_indices.append(idx)

    path = build_camera_path(mission, config, on_unresolved=_on_unresolved)
    report.resolved_count = path.waypoint_count()
    return path, report
