"""v3.0 partial-rebuild planner tests.

Covers the pure helpers in ``core/scene_sync.py``:

* ``SyncDiff.is_unchanged`` — short-circuit when nothing
  changed.
* ``plan_overlay_rebuild`` — visibility vs geometry diff.
* ``plan_science_rebuild`` — same shape for science layers.
* ``plan_mission_update`` — waypoint-level diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from core.scene_sync import (
    MissionUpdatePlan,
    OverlayRebuildPlan,
    ScienceRebuildPlan,
    SyncDiff,
    compute_diff,
    plan_mission_update,
    plan_overlay_rebuild,
    plan_science_rebuild,
)


# ---------------------------------------------------------------------------
# SyncDiff.is_unchanged
# ---------------------------------------------------------------------------


def test_sync_diff_is_unchanged_for_empty_diff():
    diff = SyncDiff()
    assert diff.is_unchanged is True


def test_sync_diff_is_unchanged_with_only_kept():
    diff = SyncDiff(kept_uids=["a", "b", "c"])
    assert diff.is_unchanged is True


def test_sync_diff_not_unchanged_with_added():
    diff = SyncDiff(added_uids=["x"])
    assert diff.is_unchanged is False


def test_sync_diff_not_unchanged_with_removed():
    diff = SyncDiff(removed_uids=["x"])
    assert diff.is_unchanged is False


def test_sync_diff_not_unchanged_when_capped():
    diff = SyncDiff(kept_uids=["a"], capped_uids=5)
    assert diff.is_unchanged is False


def test_sync_diff_short_summary_says_unchanged():
    diff = SyncDiff(kept_uids=["a", "b"])
    assert "unchanged" in diff.short_summary()


def test_compute_diff_unchanged_when_uids_match():
    diff = compute_diff(["a", "b"], ["a", "b"])
    assert diff.is_unchanged is True


# ---------------------------------------------------------------------------
# plan_overlay_rebuild
# ---------------------------------------------------------------------------


@dataclass
class FakeOverlaySettings:
    show_grid: bool = False
    show_galactic_plane: bool = False
    show_ecliptic_plane: bool = False
    show_distance_rings: bool = False
    show_sector_cone: bool = False
    show_route_corridor: bool = False
    show_waypoint_labels: bool = False
    radius_pc: float = 100.0
    segment_count: int = 64
    grid_step_pc: float = 25.0
    grid_extent_pc: float = 100.0
    distance_ring_radii_pc: List[float] = field(
        default_factory=lambda: [10.0, 25.0],
    )
    corridor_width_pc: float = 1.0
    label_height_pc: float = 1.5
    opacity: float = 1.0


def test_plan_overlay_rebuild_unchanged_when_identical():
    a = FakeOverlaySettings()
    b = FakeOverlaySettings()
    plan = plan_overlay_rebuild(a, b)
    assert plan.rebuild_required is False
    assert "unchanged" in plan.reason


def test_plan_overlay_rebuild_visibility_only_change():
    a = FakeOverlaySettings(show_grid=False)
    b = FakeOverlaySettings(show_grid=True)
    plan = plan_overlay_rebuild(a, b)
    assert plan.rebuild_required is True
    assert plan.visibility_only is True
    assert "grid" in plan.changed_kinds
    assert plan.geometry_dirty is False


def test_plan_overlay_rebuild_geometry_change():
    a = FakeOverlaySettings(radius_pc=100.0)
    b = FakeOverlaySettings(radius_pc=200.0)
    plan = plan_overlay_rebuild(a, b)
    assert plan.rebuild_required is True
    assert plan.geometry_dirty is True
    assert plan.visibility_only is False


def test_plan_overlay_rebuild_ring_radii_change():
    a = FakeOverlaySettings(distance_ring_radii_pc=[10.0, 25.0])
    b = FakeOverlaySettings(distance_ring_radii_pc=[10.0, 25.0, 100.0])
    plan = plan_overlay_rebuild(a, b)
    assert plan.rebuild_required is True
    assert plan.geometry_dirty is True


def test_plan_overlay_rebuild_handles_none_to_settings():
    plan = plan_overlay_rebuild(None, FakeOverlaySettings())
    assert plan.rebuild_required is True
    assert "appeared" in plan.reason or "disappeared" in plan.reason


def test_plan_overlay_rebuild_both_none():
    plan = plan_overlay_rebuild(None, None)
    assert plan.rebuild_required is False


# ---------------------------------------------------------------------------
# plan_science_rebuild
# ---------------------------------------------------------------------------


@dataclass
class FakeScienceSettings:
    show_distance_shells: bool = False
    show_redshift_shells: bool = False
    show_magnitude_shells: bool = False
    show_motion_vectors: bool = False
    show_catalog_source_regions: bool = False
    show_solar_system_orbits: bool = False
    show_constellation_boundaries: bool = False
    show_object_density_volume: bool = False
    shell_radii_pc: tuple = (10.0, 50.0)
    vector_scale: float = 1.0


def test_plan_science_unchanged():
    a = FakeScienceSettings()
    b = FakeScienceSettings()
    plan = plan_science_rebuild(a, b)
    assert plan.rebuild_required is False


def test_plan_science_visibility_change():
    a = FakeScienceSettings(show_distance_shells=False)
    b = FakeScienceSettings(show_distance_shells=True)
    plan = plan_science_rebuild(a, b)
    assert plan.rebuild_required is True
    assert "distance_shells" in plan.changed_kinds


def test_plan_science_parameter_change():
    a = FakeScienceSettings(vector_scale=1.0)
    b = FakeScienceSettings(vector_scale=2.0)
    plan = plan_science_rebuild(a, b)
    assert plan.rebuild_required is True
    assert "parameter" in plan.reason


def test_plan_science_both_none():
    plan = plan_science_rebuild(None, None)
    assert plan.rebuild_required is False


# ---------------------------------------------------------------------------
# plan_mission_update
# ---------------------------------------------------------------------------


@dataclass
class FakeWaypoint:
    kind: str = "object"
    uid: str = "u1"
    label: str = "L"
    x_c4d: float = 0.0
    y_c4d: float = 0.0
    z_c4d: float = 0.0
    duration_seconds: float = 4.0
    epoch_jd: float = 2461041.5


@dataclass
class FakeMission:
    title: str = "Demo"
    description: str = ""
    waypoints: List[FakeWaypoint] = field(default_factory=list)


def test_plan_mission_unchanged():
    a = FakeMission(waypoints=[FakeWaypoint(uid="u1"), FakeWaypoint(uid="u2")])
    b = FakeMission(waypoints=[FakeWaypoint(uid="u1"), FakeWaypoint(uid="u2")])
    plan = plan_mission_update(a, b)
    assert plan.rebuild_required is False


def test_plan_mission_waypoint_added():
    a = FakeMission(waypoints=[FakeWaypoint(uid="u1")])
    b = FakeMission(waypoints=[FakeWaypoint(uid="u1"), FakeWaypoint(uid="u2")])
    plan = plan_mission_update(a, b)
    assert plan.rebuild_required is True
    assert (1, "added") in plan.waypoint_changes


def test_plan_mission_waypoint_removed():
    a = FakeMission(waypoints=[FakeWaypoint(uid="u1"), FakeWaypoint(uid="u2")])
    b = FakeMission(waypoints=[FakeWaypoint(uid="u1")])
    plan = plan_mission_update(a, b)
    assert plan.rebuild_required is True
    assert (1, "removed") in plan.waypoint_changes


def test_plan_mission_waypoint_position_change():
    a = FakeMission(waypoints=[FakeWaypoint(uid="u1", x_c4d=0.0)])
    b = FakeMission(waypoints=[FakeWaypoint(uid="u1", x_c4d=10.0)])
    plan = plan_mission_update(a, b)
    assert plan.rebuild_required is True
    assert (0, "changed") in plan.waypoint_changes


def test_plan_mission_title_only_change_skips_rebuild():
    a = FakeMission(title="A", waypoints=[FakeWaypoint(uid="u1")])
    b = FakeMission(title="B", waypoints=[FakeWaypoint(uid="u1")])
    plan = plan_mission_update(a, b)
    assert plan.rebuild_required is False
    assert plan.title_changed is True


def test_plan_mission_both_none():
    plan = plan_mission_update(None, None)
    assert plan.rebuild_required is False
