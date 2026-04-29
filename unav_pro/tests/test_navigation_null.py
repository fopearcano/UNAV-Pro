"""Tests for c4d_objects.navigation_null pure helpers and the c4d guard."""

from __future__ import annotations

import pytest

from c4d_objects import navigation_null as nav
from c4d_objects.navigation_null import (
    CAMERA_NAME,
    KIND_NAVIGATOR,
    KIND_NAVIGATOR_CAMERA,
    KIND_NAVIGATOR_RAY,
    NAVIGATOR_NAME,
    RAY_NAME,
    USER_DATA_FIELD_NAMES,
    user_data_defaults,
    _kind_marker,
    _navigator_marker,
)
from c4d_objects.point_cloud_builder import (
    MARKER_KEY_IS_UNAV,
    MARKER_KEY_KIND,
    MARKER_KEY_METADATA_JSON,
    MARKER_KEY_NAME,
)
from core.navigation_state import NavigationParams


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_names_are_unique_and_canonical():
    names = {NAVIGATOR_NAME, CAMERA_NAME, RAY_NAME}
    assert len(names) == 3
    assert NAVIGATOR_NAME == "UNAV_Navigator"
    assert CAMERA_NAME == "UNAV_Camera"
    assert RAY_NAME == "UNAV_ViewRay"


def test_user_data_field_names_match_dataclass():
    expected = {
        "max_distance_parsec",
        "field_of_view_deg",
        "cone_angle_deg",
        "near_clip_parsec",
        "far_clip_parsec",
        "selected_catalog_sources",
        "max_visible_objects",
        "c4d_scale",
    }
    assert set(USER_DATA_FIELD_NAMES) == expected


def test_user_data_defaults_match_dataclass_defaults():
    defaults = user_data_defaults()
    p = NavigationParams()
    assert defaults["max_distance_parsec"] == p.max_distance_parsec
    assert defaults["field_of_view_deg"] == p.field_of_view_deg
    assert defaults["cone_angle_deg"] == p.cone_angle_deg
    assert defaults["near_clip_parsec"] == p.near_clip_parsec
    assert defaults["far_clip_parsec"] == p.far_clip_parsec
    assert defaults["max_visible_objects"] == p.max_visible_objects
    assert defaults["c4d_scale"] == p.c4d_scale


# ---------------------------------------------------------------------------
# Marker payloads
# ---------------------------------------------------------------------------


def test_navigator_marker_carries_params_json():
    p = NavigationParams(c4d_scale="kpc")
    m = _navigator_marker(p)
    assert m[MARKER_KEY_IS_UNAV] is True
    assert m[MARKER_KEY_KIND] == KIND_NAVIGATOR
    assert m[MARKER_KEY_NAME] == NAVIGATOR_NAME
    # Round-trip the embedded JSON back to params.
    out = NavigationParams.from_json(m[MARKER_KEY_METADATA_JSON])
    assert out.c4d_scale == "kpc"


def test_kind_marker_for_camera_and_ray():
    cam = _kind_marker(KIND_NAVIGATOR_CAMERA, CAMERA_NAME)
    ray = _kind_marker(KIND_NAVIGATOR_RAY, RAY_NAME)
    assert cam[MARKER_KEY_KIND] == KIND_NAVIGATOR_CAMERA
    assert cam[MARKER_KEY_NAME] == CAMERA_NAME
    assert ray[MARKER_KEY_KIND] == KIND_NAVIGATOR_RAY
    assert ray[MARKER_KEY_NAME] == RAY_NAME


def test_kinds_are_distinct():
    assert len({KIND_NAVIGATOR, KIND_NAVIGATOR_CAMERA, KIND_NAVIGATOR_RAY}) == 3


# ---------------------------------------------------------------------------
# C4D guard
# ---------------------------------------------------------------------------


def test_c4d_bound_helpers_raise_outside_host():
    # All three accessors and ensure_navigator must fail with a clean
    # RuntimeError outside Cinema 4D, not an ImportError or
    # AttributeError.
    with pytest.raises(RuntimeError):
        nav.ensure_navigator(None)
    with pytest.raises(RuntimeError):
        nav.find_navigator(None)
    with pytest.raises(RuntimeError):
        nav.get_navigation_origin(None)
    with pytest.raises(RuntimeError):
        nav.get_navigation_forward_vector(None)
    with pytest.raises(RuntimeError):
        nav.get_navigation_filter_params(None)
