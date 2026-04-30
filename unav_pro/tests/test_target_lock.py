"""Tests for core.target_lock (v0.6 target lock system)."""

from __future__ import annotations

import math

import pytest

from core.metadata_lookup import MetadataLookup
from core.target_lock import (
    INSTANT_SNAP_T,
    TargetLock,
    acquire_target,
    compute_focus_pose,
    evaluate_target_against_clip,
    forward_vector,
    interpolate_position,
)
from data.schema import CatalogObject, compute_derived_fields


def _build_obj_with_position(uid: str, x_pc: float, y_pc: float, z_pc: float):
    """Helper: a CatalogObject with cartesian + c4d already populated."""
    o = CatalogObject(
        uid=uid, catalog_source="Test", object_type="star",
        ra_deg=0.0, dec_deg=0.0, distance_parsec=None,
    )
    o.cartesian_x, o.cartesian_y, o.cartesian_z = x_pc, y_pc, z_pc
    o.c4d_x, o.c4d_y, o.c4d_z = x_pc, y_pc, z_pc  # default scale_mode=pc
    return o


# ---------------------------------------------------------------------------
# acquire_target
# ---------------------------------------------------------------------------


def test_acquire_returns_none_for_empty_uid():
    lookup = MetadataLookup([])
    assert acquire_target("", lookup) is None


def test_acquire_returns_none_when_uid_missing_from_lookup():
    lookup = MetadataLookup([])
    assert acquire_target("gaia:404", lookup) is None


def test_acquire_returns_lock_with_position_for_known_object():
    obj = _build_obj_with_position("gaia:1", 10.0, 0.0, 0.0)
    obj.name = "TestStar"
    lookup = MetadataLookup([obj])
    lock = acquire_target("gaia:1", lookup)
    assert lock is not None
    assert lock.uid == "gaia:1"
    assert lock.label == "TestStar"
    assert lock.position_c4d == (10.0, 0.0, 0.0)
    assert lock.position_pc == (10.0, 0.0, 0.0)
    assert lock.is_resolved


def test_acquire_records_distance_when_navigator_position_supplied():
    obj = _build_obj_with_position("gaia:1", 3.0, 4.0, 0.0)
    lookup = MetadataLookup([obj])
    lock = acquire_target(
        "gaia:1", lookup, navigator_position_c4d=(0.0, 0.0, 0.0),
    )
    assert lock is not None
    assert lock.distance_c4d == pytest.approx(5.0)
    assert lock.distance_pc == pytest.approx(5.0)  # default scale "pc"


def test_acquire_falls_back_to_compute_derived_when_fields_missing():
    o = CatalogObject(
        uid="g:1", catalog_source="Gaia DR3", object_type="star",
        ra_deg=0.0, dec_deg=0.0, distance_parsec=10.0,
    )
    # cartesian_* and c4d_* not pre-populated; lookup forces derive.
    lookup = MetadataLookup([o])
    lock = acquire_target("g:1", lookup)
    assert lock is not None
    assert lock.position_c4d is not None
    # 10 pc at (ra=0, dec=0) → x=10, y=0, z=0 in pc.
    assert lock.position_c4d[0] == pytest.approx(10.0, abs=1e-9)


# ---------------------------------------------------------------------------
# interpolate_position
# ---------------------------------------------------------------------------


def test_interp_t_zero_returns_current():
    assert interpolate_position((1.0, 2.0, 3.0), (10.0, 20.0, 30.0), 0.0) == (1.0, 2.0, 3.0)


def test_interp_t_one_returns_target():
    assert interpolate_position((1.0, 2.0, 3.0), (10.0, 20.0, 30.0), 1.0) == (10.0, 20.0, 30.0)


def test_interp_midpoint():
    assert interpolate_position((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), 0.5) == (5.0, 0.0, 0.0)


def test_interp_clamps_negative_t():
    assert interpolate_position((1.0, 2.0, 3.0), (10.0, 20.0, 30.0), -2.0) == (1.0, 2.0, 3.0)


def test_interp_clamps_t_above_one():
    assert interpolate_position((1.0, 2.0, 3.0), (10.0, 20.0, 30.0), 5.0) == (10.0, 20.0, 30.0)


# ---------------------------------------------------------------------------
# compute_focus_pose
# ---------------------------------------------------------------------------


def _lock_at(x, y, z):
    return TargetLock(
        uid="g:1", catalog_source="Gaia DR3", label="t",
        position_c4d=(x, y, z),
    )


def test_focus_default_keeps_navigator_in_place_when_t_is_zero_or_one():
    lock = _lock_at(10.0, 0.0, 0.0)
    new_pos, target = compute_focus_pose(lock, (0.0, 0.0, 0.0), t=INSTANT_SNAP_T)
    # Default mode (no place_at_target, no standoff): nav stays put.
    assert new_pos == (0.0, 0.0, 0.0)
    assert target == (10.0, 0.0, 0.0)


def test_focus_place_at_target_snaps_navigator_to_object():
    lock = _lock_at(10.0, 0.0, 0.0)
    new_pos, _ = compute_focus_pose(
        lock, (0.0, 0.0, 0.0), t=INSTANT_SNAP_T, place_at_target=True,
    )
    assert new_pos == (10.0, 0.0, 0.0)


def test_focus_place_at_target_with_t_half_moves_halfway():
    lock = _lock_at(10.0, 0.0, 0.0)
    new_pos, _ = compute_focus_pose(
        lock, (0.0, 0.0, 0.0), t=0.5, place_at_target=True,
    )
    assert new_pos == (5.0, 0.0, 0.0)


def test_focus_with_standoff_stops_short_of_target():
    lock = _lock_at(10.0, 0.0, 0.0)
    new_pos, _ = compute_focus_pose(
        lock, (0.0, 0.0, 0.0), t=INSTANT_SNAP_T, standoff_c4d=2.0,
    )
    # Travelled 8 of the 10 distance, stopping 2 short.
    assert new_pos[0] == pytest.approx(8.0)


def test_focus_intermediate_t_drifts_navigator_toward_target():
    lock = _lock_at(10.0, 0.0, 0.0)
    new_pos, _ = compute_focus_pose(
        lock, (0.0, 0.0, 0.0), t=0.1,
    )
    assert new_pos[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# forward_vector
# ---------------------------------------------------------------------------


def test_forward_vector_unit_length_along_x():
    fv = forward_vector((0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    assert fv == (1.0, 0.0, 0.0)


def test_forward_vector_returns_none_for_coincident_points():
    assert forward_vector((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)) is None


def test_forward_vector_normalizes_arbitrary_direction():
    fv = forward_vector((0.0, 0.0, 0.0), (3.0, 4.0, 0.0))
    assert fv is not None
    assert fv[0] == pytest.approx(0.6)
    assert fv[1] == pytest.approx(0.8)
    assert fv[2] == 0.0


# ---------------------------------------------------------------------------
# Safety check vs clip range
# ---------------------------------------------------------------------------


def test_safety_in_range_when_distance_inside_clip():
    obj = _build_obj_with_position("g:1", 100.0, 0.0, 0.0)
    lookup = MetadataLookup([obj])
    lock = acquire_target("g:1", lookup, navigator_position_c4d=(0.0, 0.0, 0.0))
    report = evaluate_target_against_clip(lock, near_clip_pc=10.0, far_clip_pc=1000.0)
    assert report.in_range
    assert report.distance_pc == pytest.approx(100.0)


def test_safety_out_of_range_when_target_beyond_far_clip():
    obj = _build_obj_with_position("g:1", 5000.0, 0.0, 0.0)
    lookup = MetadataLookup([obj])
    lock = acquire_target("g:1", lookup, navigator_position_c4d=(0.0, 0.0, 0.0))
    report = evaluate_target_against_clip(lock, near_clip_pc=0.0, far_clip_pc=1000.0)
    assert not report.in_range
    assert "OUTSIDE" in report.short_summary()
