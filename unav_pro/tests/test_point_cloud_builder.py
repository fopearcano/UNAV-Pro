"""Tests for the c4d-free helpers in point_cloud_builder.

The C4D-bound functions (build_starfield, build_point_object,
clear_starfield) require the Cinema 4D host and are out of scope for
this test module — they are exercised by manually loading the plugin
in C4D 2023+."""

from __future__ import annotations

import math

import pytest

from c4d_objects import point_cloud_builder as builder
from c4d_objects.point_cloud_builder import (
    MARKER_KEY_CATALOG_SOURCE,
    MARKER_KEY_DEC_DEG,
    MARKER_KEY_DISTANCE_PC,
    MARKER_KEY_IS_UNAV,
    MARKER_KEY_KIND,
    MARKER_KEY_METADATA_JSON,
    MARKER_KEY_NAME,
    MARKER_KEY_OBJECT_TYPE,
    MARKER_KEY_RA_DEG,
    MARKER_KEY_UID,
    NULL_RADIUS_SCALE,
    STARFIELD_NAME,
    color_for_object,
    display_label,
    marker_for_object,
    position_for_object,
    radius_for_object,
    starfield_marker,
    _rgb_int_to_float,
)
from data.schema import (
    CatalogObject,
    SCALE_MODES,
    compute_derived_fields,
)


def _star(**overrides) -> CatalogObject:
    base = dict(
        uid="star-1",
        catalog_source="unav_sample",
        object_type="star",
        ra_deg=10.0,
        dec_deg=-20.0,
        distance_parsec=10.0,
        apparent_magnitude=5.0,
        spectral_type="G2V",
        name="Alpha One",
    )
    base.update(overrides)
    return CatalogObject(**base)


# ---------------------------------------------------------------------------
# position_for_object
# ---------------------------------------------------------------------------


def test_position_for_object_uses_cached_when_present():
    obj = _star()
    compute_derived_fields(obj)
    cached = (obj.c4d_x, obj.c4d_y, obj.c4d_z)
    out = position_for_object(obj)
    assert out == cached


def test_position_for_object_recomputes_for_alternate_scale():
    obj = _star()
    compute_derived_fields(obj, scale_mode="pc")
    out_pc = position_for_object(obj, scale_mode="pc")
    out_kpc = position_for_object(obj, scale_mode="kpc")
    # kpc scale shrinks coordinates by 1000.
    assert math.isclose(out_kpc[0], out_pc[0] / 1000.0, rel_tol=1e-9)


def test_position_for_object_handles_uninitialized():
    obj = _star()
    # No compute_derived_fields() yet.
    out = position_for_object(obj)
    assert out is not None and len(out) == 3
    # After the call the cache should be populated.
    assert obj.c4d_x is not None


# ---------------------------------------------------------------------------
# radius_for_object
# ---------------------------------------------------------------------------


def test_radius_uses_render_radius_with_scale():
    obj = _star()
    compute_derived_fields(obj)
    expected = obj.render_radius * NULL_RADIUS_SCALE
    assert math.isclose(radius_for_object(obj), expected)


def test_radius_falls_back_when_render_radius_missing():
    obj = _star(apparent_magnitude=None)
    # Skip compute_derived_fields so render_radius stays None.
    obj.render_radius = None
    r = radius_for_object(obj)
    assert r == 1.0 * NULL_RADIUS_SCALE  # default base=1.0 from helper


def test_radius_brighter_is_larger():
    bright = _star(apparent_magnitude=0.0)
    dim = _star(apparent_magnitude=15.0)
    compute_derived_fields(bright)
    compute_derived_fields(dim)
    assert radius_for_object(bright) > radius_for_object(dim)


# ---------------------------------------------------------------------------
# color_for_object / _rgb_int_to_float
# ---------------------------------------------------------------------------


def test_color_for_object_returns_floats_in_range():
    obj = _star()
    compute_derived_fields(obj)
    r, g, b = color_for_object(obj)
    assert all(0.0 <= c <= 1.0 for c in (r, g, b))


def test_color_for_object_uses_spectral():
    g_star = _star(spectral_type="G2V")
    o_star = _star(spectral_type="O5V")
    compute_derived_fields(g_star)
    compute_derived_fields(o_star)
    assert color_for_object(g_star) != color_for_object(o_star)


def test_rgb_int_to_float_clamps():
    assert _rgb_int_to_float((-10, 0, 300)) == (0.0, 0.0, 1.0)


def test_color_falls_back_when_no_cached():
    obj = _star()  # no compute_derived_fields call
    obj.display_color_rgb = None
    r, g, b = color_for_object(obj)
    assert all(0.0 <= c <= 1.0 for c in (r, g, b))


# ---------------------------------------------------------------------------
# marker_for_object
# ---------------------------------------------------------------------------


def test_marker_for_object_contains_required_fields():
    obj = _star(name="Alpha One")
    m = marker_for_object(obj)
    assert m[MARKER_KEY_IS_UNAV] is True
    assert m[MARKER_KEY_KIND] == "point"
    assert m[MARKER_KEY_UID] == "star-1"
    assert m[MARKER_KEY_CATALOG_SOURCE] == "unav_sample"
    assert m[MARKER_KEY_OBJECT_TYPE] == "star"
    assert m[MARKER_KEY_NAME] == "Alpha One"
    assert m[MARKER_KEY_RA_DEG] == 10.0
    assert m[MARKER_KEY_DEC_DEG] == -20.0
    assert m[MARKER_KEY_DISTANCE_PC] == 10.0


def test_marker_for_object_handles_missing_optional_fields():
    obj = CatalogObject(
        uid="x", catalog_source="y", object_type="star",
        ra_deg=0.0, dec_deg=0.0,
    )
    m = marker_for_object(obj)
    assert m[MARKER_KEY_NAME] == ""
    assert m[MARKER_KEY_DISTANCE_PC] == 0.0
    # Safety default: full metadata blob is NOT embedded.
    assert MARKER_KEY_METADATA_JSON not in m


def test_marker_for_object_excludes_metadata_blob_by_default():
    obj = CatalogObject(
        uid="u", catalog_source="src", object_type="star",
        ra_deg=0.0, dec_deg=0.0,
        metadata_json='{"big": "blob"}',
    )
    m = marker_for_object(obj)
    assert MARKER_KEY_METADATA_JSON not in m


def test_marker_for_object_opt_in_includes_metadata_blob():
    obj = CatalogObject(
        uid="u", catalog_source="src", object_type="star",
        ra_deg=0.0, dec_deg=0.0,
        metadata_json='{"big": "blob"}',
    )
    m = marker_for_object(obj, include_full_metadata=True)
    assert m[MARKER_KEY_METADATA_JSON] == '{"big": "blob"}'


def test_marker_keys_are_unique():
    keys = [
        MARKER_KEY_IS_UNAV, MARKER_KEY_KIND, MARKER_KEY_UID,
        MARKER_KEY_CATALOG_SOURCE, MARKER_KEY_OBJECT_TYPE,
        MARKER_KEY_NAME, MARKER_KEY_METADATA_JSON,
        MARKER_KEY_RA_DEG, MARKER_KEY_DEC_DEG, MARKER_KEY_DISTANCE_PC,
    ]
    assert len(keys) == len(set(keys))


def test_starfield_marker_is_kind_starfield():
    m = starfield_marker()
    assert m[MARKER_KEY_KIND] == "starfield"
    assert m[MARKER_KEY_NAME] == STARFIELD_NAME


# ---------------------------------------------------------------------------
# display_label
# ---------------------------------------------------------------------------


def test_display_label_prefers_common_name():
    obj = _star(name="X", common_name="Alpha")
    assert display_label(obj) == "Alpha"


def test_display_label_falls_back_to_name_then_uid():
    obj = _star(name="X", common_name=None)
    assert display_label(obj) == "X"
    obj2 = _star(name=None, common_name=None)
    assert display_label(obj2) == "star-1"


# ---------------------------------------------------------------------------
# C4D-only paths: ensure they refuse cleanly outside the host
# ---------------------------------------------------------------------------


def test_c4d_bound_helpers_raise_outside_host():
    # In the test environment c4d is not importable; exercising the
    # _require_c4d guard should produce a RuntimeError (not an
    # ImportError or AttributeError).
    obj = _star()
    with pytest.raises(RuntimeError):
        builder.build_point_object(obj)
