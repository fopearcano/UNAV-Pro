"""v2.0 procedural overlays tests."""

from __future__ import annotations

import math

import pytest

from procedural import (
    DEFAULT_OVERLAY_RADIUS_PC,
    KIND_DISTANCE_RINGS,
    KIND_ECLIPTIC_PLANE,
    KIND_GALACTIC_PLANE,
    KIND_GRID,
    KIND_ROUTE_CORRIDOR,
    KIND_SECTOR_CONE,
    KIND_WAYPOINT_LABELS,
    MAX_RING_COUNT,
    MAX_SEGMENT_COUNT,
    OVERLAY_KINDS,
    OverlayBundle,
    OverlayPolyline,
    OverlaySettings,
    build_distance_rings,
    build_ecliptic_plane,
    build_galactic_plane,
    build_grid,
    build_overlay_bundle,
    build_route_corridor,
    build_sector_cone,
    build_waypoint_labels,
)


# ---------------------------------------------------------------------------
# OverlaySettings — defaults + validation
# ---------------------------------------------------------------------------


def test_defaults_are_all_invisible():
    s = OverlaySettings()
    assert s.any_visible() is False
    for k in OVERLAY_KINDS:
        assert s.is_visible(k) is False


def test_zero_radius_rejected():
    with pytest.raises(ValueError):
        OverlaySettings(radius_pc=0)


def test_opacity_out_of_range_rejected():
    with pytest.raises(ValueError):
        OverlaySettings(opacity=1.5)
    with pytest.raises(ValueError):
        OverlaySettings(opacity=-0.1)


def test_segment_count_clamped_high():
    s = OverlaySettings(segment_count=100_000)
    assert s.segment_count == MAX_SEGMENT_COUNT


def test_segment_count_clamped_low():
    s = OverlaySettings(segment_count=2)
    assert s.segment_count == 4


def test_distance_ring_radii_dedup_and_sort():
    s = OverlaySettings(distance_ring_radii_pc=[50.0, 10.0, 50.0, -1.0, 25.0])
    assert s.distance_ring_radii_pc == [10.0, 25.0, 50.0]


def test_distance_ring_radii_default_when_empty():
    s = OverlaySettings(distance_ring_radii_pc=[])
    assert s.distance_ring_radii_pc == [DEFAULT_OVERLAY_RADIUS_PC]


def test_distance_ring_radii_capped():
    s = OverlaySettings(
        distance_ring_radii_pc=[float(i) for i in range(MAX_RING_COUNT * 2)],
    )
    assert len(s.distance_ring_radii_pc) <= MAX_RING_COUNT


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


def test_overlay_settings_round_trip():
    s = OverlaySettings(
        show_grid=True, show_galactic_plane=True,
        show_distance_rings=True, show_route_corridor=True,
        radius_pc=250.0, segment_count=128,
        grid_step_pc=10.0, grid_extent_pc=200.0,
        distance_ring_radii_pc=[10.0, 50.0, 100.0],
        corridor_width_pc=2.0, label_height_pc=3.0,
        opacity=0.5,
    )
    rt = OverlaySettings.from_dict(s.to_dict())
    assert rt.show_grid is True
    assert rt.show_galactic_plane is True
    assert rt.show_distance_rings is True
    assert rt.show_route_corridor is True
    assert rt.radius_pc == 250.0
    assert rt.segment_count == 128
    assert rt.distance_ring_radii_pc == [10.0, 50.0, 100.0]
    assert rt.corridor_width_pc == 2.0
    assert rt.opacity == 0.5


def test_corrupt_dict_falls_through_to_defaults():
    """Bad payload → ``OverlaySettings.from_dict`` returns
    defaults rather than raising. Mirrors the v1.7 fail-closed
    persistence contract."""
    s = OverlaySettings.from_dict({"radius_pc": -5.0})  # invalid
    assert s.radius_pc == DEFAULT_OVERLAY_RADIUS_PC


def test_from_dict_ignores_unknown_keys():
    s = OverlaySettings.from_dict({
        "show_grid": True, "bogus": 99, "radius_pc": 50.0,
    })
    assert s.show_grid is True
    assert s.radius_pc == 50.0


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------


def test_grid_emits_one_polyline_per_line():
    s = OverlaySettings(show_grid=True, grid_extent_pc=10.0, grid_step_pc=5.0)
    polys = build_grid(s)
    # extent=10, step=5 → coords [-10, -5, 0, 5, 10] = 5 values
    # → 5 X-lines + 5 Y-lines = 10 polylines.
    assert len(polys) == 10
    assert all(p.kind == KIND_GRID for p in polys)
    assert all(len(p.points) == 2 for p in polys)


def test_grid_lines_are_in_xy_plane():
    s = OverlaySettings(show_grid=True, grid_extent_pc=10.0, grid_step_pc=5.0)
    for poly in build_grid(s):
        for (x, y, z) in poly.points:
            assert z == 0.0


def test_grid_empty_when_step_or_extent_zero():
    """Construction validates step/extent positive, so we
    test the function directly with a hand-crafted stub."""
    s = OverlaySettings(show_grid=True)
    s.grid_step_pc = -1.0
    assert build_grid(s) == []


# ---------------------------------------------------------------------------
# Planes
# ---------------------------------------------------------------------------


def test_galactic_plane_radius_matches_settings():
    s = OverlaySettings(radius_pc=50.0, segment_count=32)
    poly = build_galactic_plane(s)
    assert poly.kind == KIND_GALACTIC_PLANE
    assert poly.closed is True
    assert len(poly.points) == 32
    # Every point on the circle should be at radius ~ settings.radius_pc.
    for (x, y, z) in poly.points:
        r = math.sqrt(x * x + y * y + z * z)
        assert abs(r - 50.0) < 1e-3


def test_ecliptic_plane_radius_matches_settings():
    s = OverlaySettings(radius_pc=10.0)
    poly = build_ecliptic_plane(s)
    assert poly.kind == KIND_ECLIPTIC_PLANE
    assert poly.closed is True
    for (x, y, z) in poly.points:
        r = math.sqrt(x * x + y * y + z * z)
        assert abs(r - 10.0) < 1e-3


def test_galactic_and_ecliptic_planes_are_distinct():
    """The two planes are tilted ~63° to each other; their
    point clouds shouldn't be element-wise identical."""
    s = OverlaySettings(segment_count=32)
    g = build_galactic_plane(s).points
    e = build_ecliptic_plane(s).points
    assert g != e


# ---------------------------------------------------------------------------
# Distance rings
# ---------------------------------------------------------------------------


def test_distance_rings_one_per_radius():
    s = OverlaySettings(distance_ring_radii_pc=[10.0, 25.0, 100.0])
    rings = build_distance_rings(s)
    assert len(rings) == 3
    assert all(r.kind == KIND_DISTANCE_RINGS for r in rings)
    assert all(r.closed for r in rings)


def test_distance_rings_radii_match_settings():
    s = OverlaySettings(distance_ring_radii_pc=[10.0, 50.0])
    for ring, expected_r in zip(build_distance_rings(s), [10.0, 50.0]):
        for (x, y, z) in ring.points:
            r = math.sqrt(x * x + y * y + z * z)
            assert abs(r - expected_r) < 1e-3


# ---------------------------------------------------------------------------
# Sector cone
# ---------------------------------------------------------------------------


def test_sector_cone_emits_far_disc_plus_edges():
    s = OverlaySettings()
    polys = build_sector_cone(
        s, origin_pc=(0, 0, 0), forward=(1, 0, 0),
        cone_half_angle_deg=30.0, far_pc=10.0,
    )
    # Far disc + four cardinal edge lines = 5 polylines
    # (no near disc when near_pc=0).
    assert len(polys) == 5
    assert all(p.kind == KIND_SECTOR_CONE for p in polys)


def test_sector_cone_with_near_emits_two_discs():
    s = OverlaySettings()
    polys = build_sector_cone(
        s, origin_pc=(0, 0, 0), forward=(1, 0, 0),
        cone_half_angle_deg=30.0, near_pc=2.0, far_pc=10.0,
    )
    # Far + near + four edges = 6.
    assert len(polys) == 6


def test_sector_cone_zero_far_returns_empty():
    s = OverlaySettings()
    assert build_sector_cone(
        s, origin_pc=(0, 0, 0), forward=(1, 0, 0),
        cone_half_angle_deg=30.0, far_pc=0.0,
    ) == []


def test_sector_cone_invalid_half_angle_returns_empty():
    s = OverlaySettings()
    assert build_sector_cone(
        s, origin_pc=(0, 0, 0), forward=(1, 0, 0),
        cone_half_angle_deg=181.0, far_pc=10.0,
    ) == []


# ---------------------------------------------------------------------------
# Route corridor
# ---------------------------------------------------------------------------


def test_route_corridor_centre_plus_two_edges():
    s = OverlaySettings(corridor_width_pc=1.0)
    polys = build_route_corridor(
        s, waypoints=[(0, 0, 0), (10, 0, 0), (10, 10, 0)],
    )
    assert len(polys) == 3  # centre + left + right
    assert polys[0].label == "centre"
    # Centre line passes through every waypoint.
    assert polys[0].points[0] == (0, 0, 0)
    assert polys[0].points[-1] == (10, 10, 0)


def test_route_corridor_zero_width_omits_edges():
    s = OverlaySettings(corridor_width_pc=0.0)
    polys = build_route_corridor(
        s, waypoints=[(0, 0, 0), (10, 0, 0)],
    )
    assert len(polys) == 1  # centre only


def test_route_corridor_short_input_empty():
    s = OverlaySettings()
    assert build_route_corridor(s, waypoints=[(0, 0, 0)]) == []
    assert build_route_corridor(s, waypoints=[]) == []


def test_route_corridor_edges_are_offset_perpendicularly():
    """For a horizontal segment along +X, the perpendicular
    (with world +Z as up reference) lies along ±Y. Each edge
    sits at (x, ±width, 0); the two edges are mirrors of each
    other across the centre line."""
    s = OverlaySettings(corridor_width_pc=2.0)
    polys = build_route_corridor(
        s, waypoints=[(0, 0, 0), (10, 0, 0)],
    )
    left, right = polys[1], polys[2]
    # The two edges are mirrors of each other in y; the
    # specific sign of "left" is implementation-defined and
    # doesn't matter for the corridor's visual function.
    assert abs(left.points[0][1]) == pytest.approx(2.0, abs=1e-6)
    assert abs(right.points[0][1]) == pytest.approx(2.0, abs=1e-6)
    assert left.points[0][1] == pytest.approx(-right.points[0][1])
    # X- and Z-components are unchanged at the offset.
    assert left.points[0][0] == 0.0
    assert left.points[0][2] == 0.0


# ---------------------------------------------------------------------------
# Waypoint labels
# ---------------------------------------------------------------------------


def test_waypoint_labels_offset_above_position():
    s = OverlaySettings(label_height_pc=5.0)
    labels = build_waypoint_labels(
        s, waypoints=[("A", (1.0, 2.0, 3.0))],
    )
    assert len(labels) == 1
    assert labels[0].text == "A"
    # +Z offset by label_height_pc.
    assert labels[0].position[2] == pytest.approx(8.0)


def test_waypoint_labels_skip_blank():
    s = OverlaySettings()
    labels = build_waypoint_labels(
        s, waypoints=[("", (0, 0, 0)), ("B", (1, 1, 1))],
    )
    assert len(labels) == 1
    assert labels[0].text == "B"


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------


def test_bundle_empty_when_no_flag_on():
    s = OverlaySettings()
    b = build_overlay_bundle(s)
    assert b.empty()


def test_bundle_groups_polylines_by_kind():
    s = OverlaySettings(
        show_grid=True, show_galactic_plane=True, show_distance_rings=True,
        grid_extent_pc=5.0, grid_step_pc=5.0,
        distance_ring_radii_pc=[10.0],
    )
    b = build_overlay_bundle(s)
    kinds = {p.kind for p in b.polylines}
    assert KIND_GRID in kinds
    assert KIND_GALACTIC_PLANE in kinds
    assert KIND_DISTANCE_RINGS in kinds


def test_bundle_includes_route_only_when_waypoints_passed():
    s = OverlaySettings(show_route_corridor=True)
    b = build_overlay_bundle(s)
    # No waypoints supplied → no corridor.
    assert all(p.kind != KIND_ROUTE_CORRIDOR for p in b.polylines)
    b2 = build_overlay_bundle(
        s, route_waypoints=[(0, 0, 0), (1, 1, 1)],
    )
    assert any(p.kind == KIND_ROUTE_CORRIDOR for p in b2.polylines)


def test_bundle_includes_labels_only_when_supplied():
    s = OverlaySettings(show_waypoint_labels=True)
    b = build_overlay_bundle(s)
    assert b.labels == []
    b2 = build_overlay_bundle(
        s, waypoint_labels=[("A", (0, 0, 0))],
    )
    assert len(b2.labels) == 1


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_overlay_bundle_is_deterministic():
    s = OverlaySettings(
        show_galactic_plane=True, show_distance_rings=True,
        radius_pc=42.0, segment_count=32,
    )
    a = build_overlay_bundle(s)
    b = build_overlay_bundle(s)
    assert len(a.polylines) == len(b.polylines)
    for pa, pb in zip(a.polylines, b.polylines):
        assert pa.kind == pb.kind
        assert pa.points == pb.points
