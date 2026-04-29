"""Tests for core.spatial_filter. Runs without Cinema 4D."""

from __future__ import annotations

import math

import pytest

from core.spatial_filter import (
    FilterResult,
    FilterStats,
    apply_filter,
    c4d_units_to_pc,
    cone_contains,
    filter_for_navigator,
)
from data.schema import CatalogObject, compute_derived_fields


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _obj_at(x_pc: float, y_pc: float, z_pc: float, **overrides) -> CatalogObject:
    """Build an object pre-populated with explicit cartesian coordinates."""
    base = dict(
        uid=f"o-{x_pc}-{y_pc}-{z_pc}",
        catalog_source="unav_sample",
        object_type="star",
        ra_deg=0.0,
        dec_deg=0.0,
    )
    base.update(overrides)
    obj = CatalogObject(**base)
    obj.cartesian_x = x_pc
    obj.cartesian_y = y_pc
    obj.cartesian_z = z_pc
    return obj


# ---------------------------------------------------------------------------
# cone_contains
# ---------------------------------------------------------------------------


def test_cone_contains_object_inside_narrow_cone():
    # Forward = +x. Object straight ahead at 5 pc.
    assert cone_contains(
        origin_pc=(0, 0, 0),
        forward=(1, 0, 0),
        cone_half_angle_deg=10.0,
        point_pc=(5, 0, 0),
    )


def test_cone_contains_object_outside_cone():
    # Forward = +x. Object 90° to the side.
    assert not cone_contains(
        origin_pc=(0, 0, 0),
        forward=(1, 0, 0),
        cone_half_angle_deg=10.0,
        point_pc=(0, 5, 0),
    )


def test_cone_contains_object_behind_camera():
    assert not cone_contains(
        origin_pc=(0, 0, 0),
        forward=(1, 0, 0),
        cone_half_angle_deg=45.0,
        point_pc=(-5, 0, 0),
    )


def test_cone_contains_respects_distance_shell():
    inside = (5, 0, 0)
    assert cone_contains((0, 0, 0), (1, 0, 0), 30.0, inside, near_pc=1.0, far_pc=10.0)
    assert not cone_contains((0, 0, 0), (1, 0, 0), 30.0, inside, near_pc=6.0, far_pc=10.0)
    assert not cone_contains((0, 0, 0), (1, 0, 0), 30.0, inside, near_pc=0.0, far_pc=4.0)


def test_cone_contains_zero_half_angle_is_pure_ray():
    # Strictly axial point passes; off-axis fails.
    assert cone_contains((0, 0, 0), (1, 0, 0), 0.0, (5, 0, 0))
    assert not cone_contains((0, 0, 0), (1, 0, 0), 0.0, (5, 0.001, 0))


def test_cone_contains_full_sphere_disables_test():
    # Half-angle >= 180 means anything in the distance shell passes.
    assert cone_contains((0, 0, 0), (1, 0, 0), 180.0, (-5, 0, 0))


# ---------------------------------------------------------------------------
# apply_filter — distance gate
# ---------------------------------------------------------------------------


def test_apply_filter_far_clip_rejects():
    objs = [_obj_at(100, 0, 0)]
    result = apply_filter(objs, origin_pc=(0, 0, 0), forward=(1, 0, 0), far_clip_pc=50.0)
    assert result.stats.kept == 0
    assert result.stats.rejected_far_clip == 1
    assert result.stats.total == 1


def test_apply_filter_near_clip_rejects():
    objs = [_obj_at(0.05, 0, 0)]
    result = apply_filter(objs, near_clip_pc=1.0, forward=(1, 0, 0))
    assert result.stats.rejected_near_clip == 1


def test_apply_filter_inside_distance_shell_kept():
    objs = [_obj_at(5, 0, 0)]
    result = apply_filter(
        objs, forward=(1, 0, 0), near_clip_pc=1.0, far_clip_pc=10.0,
        cone_half_angle_deg=30.0,
    )
    assert result.stats.kept == 1
    assert result.objects[0] is objs[0]


# ---------------------------------------------------------------------------
# apply_filter — direction gates
# ---------------------------------------------------------------------------


def test_object_inside_cone_kept():
    objs = [_obj_at(10, 0, 0)]
    result = apply_filter(
        objs, forward=(1, 0, 0), cone_half_angle_deg=15.0, far_clip_pc=100.0,
    )
    assert result.stats.kept == 1


def test_object_outside_cone_rejected():
    # 60° off-axis with a 15° cone.
    objs = [_obj_at(math.cos(math.radians(60)) * 10, math.sin(math.radians(60)) * 10, 0)]
    result = apply_filter(
        objs, forward=(1, 0, 0), cone_half_angle_deg=15.0, far_clip_pc=100.0,
    )
    assert result.stats.kept == 0
    assert result.stats.rejected_outside_cone == 1


def test_object_behind_camera_rejected():
    objs = [_obj_at(-10, 0, 0)]
    result = apply_filter(
        objs, forward=(1, 0, 0), cone_half_angle_deg=30.0, far_clip_pc=100.0,
    )
    assert result.stats.kept == 0
    assert result.stats.rejected_behind == 1


def test_zero_forward_disables_direction_gates():
    # With forward=(0,0,0), only distance applies.
    objs = [_obj_at(-10, 0, 0), _obj_at(10, 0, 0)]
    result = apply_filter(
        objs, forward=(0, 0, 0), cone_half_angle_deg=15.0, far_clip_pc=100.0,
    )
    assert result.stats.kept == 2


# ---------------------------------------------------------------------------
# Source / type filters
# ---------------------------------------------------------------------------


def test_source_filter_excludes_other_sources():
    objs = [
        _obj_at(5, 0, 0, catalog_source="gaia_dr3", uid="a"),
        _obj_at(5, 0, 0, catalog_source="sdss_dr18", uid="b"),
    ]
    result = apply_filter(
        objs, forward=(1, 0, 0), far_clip_pc=100.0,
        selected_sources=("gaia_dr3",),
    )
    assert result.stats.kept == 1
    assert result.objects[0].uid == "a"
    assert result.stats.rejected_source == 1


def test_type_filter_excludes_other_types():
    objs = [
        _obj_at(5, 0, 0, object_type="star", uid="s"),
        _obj_at(5, 0, 0, object_type="galaxy", uid="g"),
    ]
    result = apply_filter(
        objs, forward=(1, 0, 0), far_clip_pc=100.0,
        selected_types=("galaxy",),
    )
    assert result.stats.kept == 1
    assert result.objects[0].uid == "g"
    assert result.stats.rejected_type == 1


# ---------------------------------------------------------------------------
# max_visible_objects cap
# ---------------------------------------------------------------------------


def test_max_visible_cap_keeps_closest_first():
    objs = [
        _obj_at(50, 0, 0, uid="far"),
        _obj_at(5, 0, 0, uid="near"),
        _obj_at(20, 0, 0, uid="mid"),
    ]
    result = apply_filter(
        objs, forward=(1, 0, 0), far_clip_pc=1000.0,
        cone_half_angle_deg=30.0, max_visible_objects=2,
    )
    assert result.stats.kept == 2
    assert result.stats.rejected_over_cap == 1
    kept_uids = [o.uid for o in result.objects]
    assert kept_uids == ["near", "mid"]


def test_max_visible_cap_brightness_mode():
    objs = [
        _obj_at(5, 0, 0, uid="dim", apparent_magnitude=15.0),
        _obj_at(50, 0, 0, uid="bright", apparent_magnitude=1.0),
        _obj_at(20, 0, 0, uid="medium", apparent_magnitude=8.0),
    ]
    result = apply_filter(
        objs, forward=(1, 0, 0), far_clip_pc=1000.0,
        cone_half_angle_deg=30.0, max_visible_objects=2,
        rank_by="brightness",
    )
    assert result.stats.kept == 2
    kept_uids = [o.uid for o in result.objects]
    assert "bright" in kept_uids
    assert "medium" in kept_uids


def test_max_visible_zero_cap_keeps_none():
    objs = [_obj_at(5, 0, 0)]
    result = apply_filter(
        objs, forward=(1, 0, 0), far_clip_pc=1000.0,
        cone_half_angle_deg=30.0, max_visible_objects=0,
    )
    assert result.stats.kept == 0
    assert result.stats.rejected_over_cap == 1


# ---------------------------------------------------------------------------
# No-position handling
# ---------------------------------------------------------------------------


def test_objects_with_no_distance_use_placeholder_and_pass_far_clip_off():
    # Object without distance falls back to PLACEHOLDER_SPHERE_PC which
    # is 1e6 pc — far beyond a 100 pc far-clip.
    obj = CatalogObject(
        uid="noplace",
        catalog_source="unav_sample",
        object_type="star",
        ra_deg=0.0,
        dec_deg=0.0,
    )
    # Don't pre-populate cartesian; let the filter compute it.
    result = apply_filter(
        [obj], forward=(1, 0, 0), far_clip_pc=100.0,
        cone_half_angle_deg=30.0,
    )
    assert result.stats.kept == 0
    assert result.stats.rejected_far_clip == 1


def test_filter_handles_object_with_uncomputable_position(monkeypatch):
    obj = _obj_at(5, 0, 0)
    obj.cartesian_x = None
    obj.cartesian_y = None
    obj.cartesian_z = None

    # Force compute_derived_fields to raise.
    from core import spatial_filter as sf

    def boom(*_a, **_kw):
        raise ValueError("synthetic")

    monkeypatch.setattr(sf, "compute_derived_fields", boom)

    result = apply_filter([obj], forward=(1, 0, 0), far_clip_pc=100.0)
    assert result.stats.rejected_no_position == 1
    assert result.stats.kept == 0


# ---------------------------------------------------------------------------
# Stats summary
# ---------------------------------------------------------------------------


def test_stats_short_summary_lists_nonzero_only():
    s = FilterStats(total=10, kept=3, rejected_far_clip=5, rejected_outside_cone=2)
    text = s.short_summary()
    assert "kept 3/10" in text
    assert "5 far" in text
    assert "2 outside cone" in text
    assert "behind" not in text  # zero counters omitted


def test_stats_total_equals_kept_plus_rejections():
    objs = [
        _obj_at(5, 0, 0),
        _obj_at(-5, 0, 0),
        _obj_at(0, 5, 0),
        _obj_at(1000, 0, 0),
    ]
    result = apply_filter(
        objs, forward=(1, 0, 0), cone_half_angle_deg=15.0, far_clip_pc=100.0,
        max_visible_objects=1,
    )
    s = result.stats
    accounted = (
        s.kept + s.rejected_source + s.rejected_type + s.rejected_no_position
        + s.rejected_near_clip + s.rejected_far_clip
        + s.rejected_behind + s.rejected_outside_cone + s.rejected_over_cap
    )
    assert accounted == s.total


# ---------------------------------------------------------------------------
# C4D-units conversion
# ---------------------------------------------------------------------------


def test_c4d_units_to_pc_pc_mode_identity():
    assert c4d_units_to_pc((1.0, 2.0, 3.0), "pc") == (1.0, 2.0, 3.0)


def test_c4d_units_to_pc_kpc_inverse():
    assert c4d_units_to_pc((1.0, 0.0, 0.0), "kpc") == (1000.0, 0.0, 0.0)


def test_c4d_units_to_pc_rejects_unknown_scale():
    with pytest.raises(ValueError):
        c4d_units_to_pc((1, 2, 3), "warp")


# ---------------------------------------------------------------------------
# filter_for_navigator wrapper
# ---------------------------------------------------------------------------


def test_filter_for_navigator_uses_params():
    from core.navigation_state import NavigationParams

    objs = [_obj_at(5, 0, 0, uid="forward"), _obj_at(-5, 0, 0, uid="behind")]
    params = NavigationParams(
        cone_angle_deg=30.0,
        far_clip_parsec=100.0,
        max_visible_objects=10,
        c4d_scale="pc",
    )
    # Origin already in pc since c4d_scale == "pc".
    result = filter_for_navigator(
        objs, origin_c4d=(0.0, 0.0, 0.0), forward=(1, 0, 0), params=params,
    )
    kept = [o.uid for o in result.objects]
    assert kept == ["forward"]


def test_filter_for_navigator_translates_origin_for_kpc_scale():
    from core.navigation_state import NavigationParams

    # Object at 5 pc on +x; origin at 5000 C4D-units in kpc mode == 5 pc.
    # So the displacement is (5-5, 0, 0) = (0, 0, 0): the cone test is
    # bypassed at zero-distance, but the near-clip rejects.
    objs = [_obj_at(5, 0, 0)]
    params = NavigationParams(
        c4d_scale="kpc",
        near_clip_parsec=0.5,
        far_clip_parsec=100.0,
    )
    result = filter_for_navigator(
        objs, origin_c4d=(5000.0 * 0.001, 0.0, 0.0),
        # NOTE: 5000 C4D units in kpc mode is 5000 / 0.001 pc — too far!
        # Use 0.005 C4D units = 0.005 / 0.001 = 5 pc.
        forward=(1, 0, 0), params=params,
    )
    # Origin is 0.005/0.001 = 5 pc, exactly at the object. Distance 0
    # falls below near_clip = 0.5 pc.
    assert result.stats.kept == 0
