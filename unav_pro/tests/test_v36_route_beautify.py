"""v3.6 route-beautify tests."""

from __future__ import annotations

import pytest

from cinematic import (
    SMOOTHING_MODES,
    BeautificationReport,
    SmoothingMode,
    SmoothingParameters,
    beautify_mission_path,
    beautify_polyline,
    beautify_route_path,
    chaikin_smooth,
    detect_sharp_angles,
    gaussian_smooth,
    interpolate_waypoints,
)


# ---------------------------------------------------------------------------
# SmoothingMode + parameters
# ---------------------------------------------------------------------------


def test_modes_complete():
    assert {SmoothingMode.NONE, SmoothingMode.CHAIKIN,
            SmoothingMode.GAUSSIAN} == set(SMOOTHING_MODES)


def test_parameters_validate_iterations():
    with pytest.raises(ValueError):
        SmoothingParameters(iterations=-1)


def test_parameters_validate_cut_ratio_range():
    with pytest.raises(ValueError):
        SmoothingParameters(cut_ratio=0.0)
    with pytest.raises(ValueError):
        SmoothingParameters(cut_ratio=0.6)


def test_parameters_validate_window():
    with pytest.raises(ValueError):
        SmoothingParameters(window=-1)


def test_parameters_validate_sigma():
    with pytest.raises(ValueError):
        SmoothingParameters(sigma=0.0)


def test_parameters_validate_tension():
    with pytest.raises(ValueError):
        SmoothingParameters(tension=1.5)


# ---------------------------------------------------------------------------
# Chaikin
# ---------------------------------------------------------------------------


def test_chaikin_short_input_returned_verbatim():
    pts = [(0, 0, 0), (1, 0, 0)]
    out = chaikin_smooth(pts, iterations=2)
    assert out == [(0, 0, 0), (1, 0, 0)]


def test_chaikin_zero_iterations_returns_input_copy():
    pts = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    out = chaikin_smooth(pts, iterations=0)
    assert out == pts


def test_chaikin_preserves_endpoints():
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (20, 10, 0)]
    out = chaikin_smooth(pts, iterations=3)
    assert out[0] == (0, 0, 0)
    assert out[-1] == (20, 10, 0)


def test_chaikin_increases_density():
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
    one_iter = chaikin_smooth(pts, iterations=1)
    two_iter = chaikin_smooth(pts, iterations=2)
    assert len(one_iter) > len(pts)
    assert len(two_iter) > len(one_iter)


def test_chaikin_rejects_invalid_cut_ratio():
    pts = [(0, 0, 0), (10, 0, 0), (20, 0, 0)]
    with pytest.raises(ValueError):
        chaikin_smooth(pts, iterations=1, cut_ratio=0.7)


def test_chaikin_deterministic():
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
    a = chaikin_smooth(pts, iterations=2)
    b = chaikin_smooth(pts, iterations=2)
    assert a == b


# ---------------------------------------------------------------------------
# Gaussian
# ---------------------------------------------------------------------------


def test_gaussian_short_input_returned_verbatim():
    pts = [(0, 0, 0), (1, 0, 0)]
    out = gaussian_smooth(pts)
    assert out == [(0, 0, 0), (1, 0, 0)]


def test_gaussian_zero_window_returns_input():
    pts = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    out = gaussian_smooth(pts, window=0)
    assert out == pts


def test_gaussian_preserves_endpoints():
    pts = [(0, 0, 0), (10, 0, 0), (5, 5, 0), (10, 10, 0)]
    out = gaussian_smooth(pts, window=1, sigma=0.7)
    assert out[0] == (0, 0, 0)
    assert out[-1] == (10, 10, 0)


def test_gaussian_smooths_corners():
    """A sharp corner should move toward the average
    of its neighbours."""
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
    out = gaussian_smooth(pts, window=1, sigma=0.7)
    # The corner at (10, 0, 0) gets pulled toward
    # the diagonal of its neighbours.
    assert out[1] != (10, 0, 0)


def test_gaussian_rejects_zero_sigma():
    pts = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    with pytest.raises(ValueError):
        gaussian_smooth(pts, window=1, sigma=0.0)


def test_gaussian_deterministic():
    pts = [(0, 0, 0), (1, 1, 0), (2, 0, 0)]
    a = gaussian_smooth(pts, window=1, sigma=0.7)
    b = gaussian_smooth(pts, window=1, sigma=0.7)
    assert a == b


# ---------------------------------------------------------------------------
# interpolate_waypoints
# ---------------------------------------------------------------------------


def test_interpolate_zero_segments_returns_input():
    pts = [(0, 0, 0), (10, 0, 0)]
    out = interpolate_waypoints(pts, samples_per_segment=0)
    assert out == [(0, 0, 0), (10, 0, 0)]


def test_interpolate_doubles_density_at_two_per_segment():
    pts = [(0, 0, 0), (10, 0, 0)]
    out = interpolate_waypoints(pts, samples_per_segment=2)
    assert len(out) == 3  # endpoints + 1 midpoint


def test_interpolate_preserves_endpoints_and_originals():
    pts = [(0, 0, 0), (10, 0, 0), (20, 0, 0)]
    out = interpolate_waypoints(pts, samples_per_segment=4)
    assert out[0] == (0, 0, 0)
    assert (10, 0, 0) in out
    assert out[-1] == (20, 0, 0)


# ---------------------------------------------------------------------------
# beautify_polyline
# ---------------------------------------------------------------------------


def test_beautify_polyline_returns_report():
    out = beautify_polyline(
        [(0, 0, 0), (10, 0, 0), (10, 10, 0)],
        mode=SmoothingMode.CHAIKIN,
    )
    assert isinstance(out, BeautificationReport)
    assert out.input_point_count == 3
    assert out.output_point_count > 3


def test_beautify_polyline_none_mode_passes_through():
    pts = [(0, 0, 0), (10, 0, 0)]
    out = beautify_polyline(pts, mode=SmoothingMode.NONE)
    assert out.points == pts


def test_beautify_polyline_with_densify():
    pts = [(0, 0, 0), (10, 0, 0)]
    out = beautify_polyline(
        pts, mode=SmoothingMode.CHAIKIN, densify_segments=4,
    )
    assert any("densified" in n for n in out.notes)


def test_beautify_polyline_short_summary():
    out = beautify_polyline(
        [(0, 0, 0), (1, 0, 0), (2, 0, 0)],
        mode=SmoothingMode.GAUSSIAN,
    )
    assert "gaussian" in out.short_summary().lower()
    assert "point" in out.short_summary().lower()


# ---------------------------------------------------------------------------
# Mission / Route facades
# ---------------------------------------------------------------------------


def test_beautify_mission_does_not_mutate_input():
    """The smoother must return a new polyline; the
    mission's waypoints are untouched."""
    from voyage import Mission, MissionWaypoint
    mission = Mission(title="X")
    mission.waypoints.append(MissionWaypoint(
        kind="coordinate", label="a",
        x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
    ))
    mission.waypoints.append(MissionWaypoint(
        kind="coordinate", label="b",
        x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
    ))
    mission.waypoints.append(MissionWaypoint(
        kind="coordinate", label="c",
        x_c4d=10.0, y_c4d=10.0, z_c4d=0.0,
    ))
    snapshot = [(w.x_c4d, w.y_c4d, w.z_c4d) for w in mission.waypoints]
    rep = beautify_mission_path(mission, mode=SmoothingMode.CHAIKIN)
    assert rep.input_point_count == 3
    after = [(w.x_c4d, w.y_c4d, w.z_c4d) for w in mission.waypoints]
    assert snapshot == after


def test_beautify_route_returns_report():
    from core.route import Route, Waypoint
    route = Route(name="r")
    route.waypoints.append(
        Waypoint(kind="coordinate", label="a", x_c4d=0, y_c4d=0, z_c4d=0),
    )
    route.waypoints.append(
        Waypoint(kind="coordinate", label="b", x_c4d=10, y_c4d=0, z_c4d=0),
    )
    route.waypoints.append(
        Waypoint(kind="coordinate", label="c", x_c4d=10, y_c4d=10, z_c4d=0),
    )
    rep = beautify_route_path(route, mode=SmoothingMode.GAUSSIAN)
    assert rep.input_point_count == 3


# ---------------------------------------------------------------------------
# detect_sharp_angles
# ---------------------------------------------------------------------------


def test_detect_sharp_angles_short_input_returns_empty():
    assert detect_sharp_angles([(0, 0, 0), (1, 0, 0)]) == []


def test_detect_sharp_angles_finds_right_angle():
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
    sharp = detect_sharp_angles(pts, angle_threshold_deg=80.0)
    assert sharp == [1]


def test_detect_sharp_angles_ignores_straight_line():
    pts = [(0, 0, 0), (10, 0, 0), (20, 0, 0)]
    sharp = detect_sharp_angles(pts, angle_threshold_deg=60.0)
    assert sharp == []


def test_detect_sharp_angles_handles_degenerate_neighbours():
    """Two coincident points produce a zero-length
    edge — the helper skips, doesn't crash."""
    pts = [(0, 0, 0), (0, 0, 0), (10, 0, 0)]
    sharp = detect_sharp_angles(pts)
    assert sharp == []
