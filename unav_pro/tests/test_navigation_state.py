"""Tests for core.navigation_state. Runs without Cinema 4D."""

from __future__ import annotations

import json

from core.navigation_state import (
    DEFAULT_C4D_SCALE,
    DEFAULT_FAR_CLIP_PARSEC,
    DEFAULT_FIELD_OF_VIEW_DEG,
    DEFAULT_MAX_DISTANCE_PARSEC,
    DEFAULT_MAX_VISIBLE_OBJECTS,
    DEFAULT_NEAR_CLIP_PARSEC,
    NavigationParams,
    _coerce_source_list,
    sources_to_string,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_defaults_validate_clean():
    p = NavigationParams()
    assert p.validate() == []
    assert p.max_distance_parsec == DEFAULT_MAX_DISTANCE_PARSEC
    assert p.field_of_view_deg == DEFAULT_FIELD_OF_VIEW_DEG
    assert p.near_clip_parsec == DEFAULT_NEAR_CLIP_PARSEC
    assert p.far_clip_parsec == DEFAULT_FAR_CLIP_PARSEC
    assert p.max_visible_objects == DEFAULT_MAX_VISIBLE_OBJECTS
    assert p.c4d_scale == DEFAULT_C4D_SCALE


def test_defaults_independent_per_instance():
    a = NavigationParams()
    b = NavigationParams()
    a.selected_catalog_sources.append("gaia_dr3")
    assert "gaia_dr3" not in b.selected_catalog_sources


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_rejects_negative_distance():
    p = NavigationParams(max_distance_parsec=-1.0)
    issues = p.validate()
    assert any("max_distance_parsec" in i for i in issues)


def test_validate_rejects_invalid_fov():
    assert NavigationParams(field_of_view_deg=0.0).validate()
    assert NavigationParams(field_of_view_deg=180.0).validate()
    assert NavigationParams(field_of_view_deg=200.0).validate()


def test_validate_rejects_inverted_clip_range():
    p = NavigationParams(near_clip_parsec=10.0, far_clip_parsec=5.0)
    assert any("far_clip" in i for i in p.validate())


def test_validate_rejects_unknown_scale():
    p = NavigationParams(c4d_scale="banana")
    assert any("c4d_scale" in i for i in p.validate())


def test_validate_rejects_invalid_source_entry():
    p = NavigationParams(selected_catalog_sources=["ok", ""])  # empty string
    assert any("selected_catalog_sources" in i for i in p.validate())


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------


def test_clamped_fixes_negative_distance():
    p = NavigationParams(max_distance_parsec=-5.0)
    out = p.clamped()
    assert out.max_distance_parsec > 0


def test_clamped_fixes_inverted_clip_range():
    p = NavigationParams(near_clip_parsec=100.0, far_clip_parsec=1.0)
    out = p.clamped()
    assert out.far_clip_parsec > out.near_clip_parsec


def test_clamped_fixes_unknown_scale():
    p = NavigationParams(c4d_scale="banana")
    out = p.clamped()
    assert out.c4d_scale == DEFAULT_C4D_SCALE


def test_clamped_keeps_valid_values():
    p = NavigationParams(max_distance_parsec=42.0, c4d_scale="kpc")
    out = p.clamped()
    assert out.max_distance_parsec == 42.0
    assert out.c4d_scale == "kpc"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_to_dict_from_dict_roundtrip():
    p = NavigationParams(
        max_distance_parsec=1234.0,
        field_of_view_deg=45.0,
        cone_angle_deg=15.0,
        near_clip_parsec=1.0,
        far_clip_parsec=20000.0,
        selected_catalog_sources=["gaia_dr3", "sdss_dr18"],
        max_visible_objects=50_000,
        c4d_scale="kpc",
    )
    out = NavigationParams.from_dict(p.to_dict())
    assert out == p


def test_to_json_from_json_roundtrip():
    p = NavigationParams(c4d_scale="ly")
    out = NavigationParams.from_json(p.to_json())
    assert out == p


def test_from_json_handles_garbage():
    out = NavigationParams.from_json("{not valid")
    # Falls back to defaults rather than raising.
    assert out.c4d_scale == DEFAULT_C4D_SCALE


def test_from_dict_drops_unknown_keys():
    out = NavigationParams.from_dict({"c4d_scale": "ly", "warp_drive": True})
    assert out.c4d_scale == "ly"


# ---------------------------------------------------------------------------
# Source list coercion
# ---------------------------------------------------------------------------


def test_coerce_source_list_from_csv():
    assert _coerce_source_list("gaia_dr3, sdss_dr18 ,  desi_edr ") == [
        "gaia_dr3",
        "sdss_dr18",
        "desi_edr",
    ]


def test_coerce_source_list_from_json_string():
    assert _coerce_source_list('["a", "b"]') == ["a", "b"]


def test_coerce_source_list_from_list():
    assert _coerce_source_list(["a", "", None, "b"]) == ["a", "b"]


def test_coerce_source_list_empty_string():
    assert _coerce_source_list("") == []


def test_sources_to_string():
    assert sources_to_string(["a", "b", "c"]) == "a,b,c"
    assert sources_to_string([]) == ""


def test_from_dict_decodes_csv_sources():
    out = NavigationParams.from_dict({"selected_catalog_sources": "a, b"})
    assert out.selected_catalog_sources == ["a", "b"]
