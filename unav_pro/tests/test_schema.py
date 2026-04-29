"""Tests for data.schema: validation, coordinate conversion, scaling,
and derived fields. Runs without Cinema 4D."""

from __future__ import annotations

import json
import math

import pytest

from data import schema
from data.schema import (
    CatalogObject,
    DEFAULT_SCALE_MODE,
    SCALE_MODES,
    compute_derived_fields,
    display_color_for,
    equatorial_to_cartesian_pc,
    pc_to_c4d_units,
    render_radius_from_magnitude,
    resolve_distance_pc,
    validate_object,
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _good_obj(**overrides) -> CatalogObject:
    base = dict(
        uid="x",
        catalog_source="unav_sample",
        object_type="star",
        ra_deg=10.0,
        dec_deg=-20.0,
    )
    base.update(overrides)
    return CatalogObject(**base)


def test_validate_object_accepts_minimal():
    assert validate_object(_good_obj()) == []


def test_validate_object_rejects_missing_required():
    obj = _good_obj()
    obj.uid = ""
    issues = validate_object(obj)
    assert any("uid" in i for i in issues)


def test_validate_object_rejects_out_of_range_ra_dec():
    issues = validate_object(_good_obj(ra_deg=400.0))
    assert any("ra_deg" in i for i in issues)
    issues = validate_object(_good_obj(dec_deg=-91.0))
    assert any("dec_deg" in i for i in issues)


def test_validate_object_rejects_unknown_type():
    issues = validate_object(_good_obj(object_type="dyson_sphere"))
    assert any("object_type" in i for i in issues)


def test_validate_object_rejects_negative_distance():
    issues = validate_object(_good_obj(distance_parsec=-3.0))
    assert any("distance_parsec" in i for i in issues)


def test_validate_object_rejects_zero_parallax():
    issues = validate_object(_good_obj(parallax_mas=0.0))
    assert any("parallax_mas" in i for i in issues)


def test_validate_object_rejects_bad_metadata_json():
    issues = validate_object(_good_obj(metadata_json="{not json"))
    assert any("metadata_json" in i for i in issues)


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


def test_equatorial_to_cartesian_origin_axis():
    # (ra=0, dec=0, d=1) should land on +x axis.
    x, y, z = equatorial_to_cartesian_pc(0.0, 0.0, 1.0)
    assert math.isclose(x, 1.0, abs_tol=1e-12)
    assert math.isclose(y, 0.0, abs_tol=1e-12)
    assert math.isclose(z, 0.0, abs_tol=1e-12)


def test_equatorial_to_cartesian_y_axis():
    # (ra=90°, dec=0) should land on +y axis.
    x, y, z = equatorial_to_cartesian_pc(90.0, 0.0, 1.0)
    assert math.isclose(x, 0.0, abs_tol=1e-12)
    assert math.isclose(y, 1.0, abs_tol=1e-12)
    assert math.isclose(z, 0.0, abs_tol=1e-12)


def test_equatorial_to_cartesian_z_axis():
    # (any ra, dec=+90°) should land on +z axis.
    x, y, z = equatorial_to_cartesian_pc(123.4, 90.0, 1.0)
    assert math.isclose(x, 0.0, abs_tol=1e-12)
    assert math.isclose(y, 0.0, abs_tol=1e-12)
    assert math.isclose(z, 1.0, abs_tol=1e-12)


def test_equatorial_to_cartesian_distance_scales():
    x, y, z = equatorial_to_cartesian_pc(45.0, 30.0, 100.0)
    r = math.sqrt(x * x + y * y + z * z)
    assert math.isclose(r, 100.0, rel_tol=1e-12)


def test_equatorial_to_cartesian_rejects_bad_distance():
    with pytest.raises(ValueError):
        equatorial_to_cartesian_pc(0.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        equatorial_to_cartesian_pc(0.0, 0.0, -1.0)


# ---------------------------------------------------------------------------
# Distance resolution
# ---------------------------------------------------------------------------


def test_resolve_distance_explicit():
    obj = _good_obj(distance_parsec=42.0, parallax_mas=1.0)
    d, m = resolve_distance_pc(obj)
    assert d == 42.0
    assert m == "explicit"


def test_resolve_distance_from_parallax():
    obj = _good_obj(parallax_mas=10.0)  # => 100 pc
    d, m = resolve_distance_pc(obj)
    assert math.isclose(d, 100.0)
    assert m == "parallax"


def test_resolve_distance_falls_back_to_placeholder():
    obj = _good_obj()
    d, m = resolve_distance_pc(obj)
    assert d == schema.PLACEHOLDER_SPHERE_PC
    assert m == "placeholder_sphere"


# ---------------------------------------------------------------------------
# C4D scale conversion
# ---------------------------------------------------------------------------


def test_pc_to_c4d_units_pc_mode_identity():
    out = pc_to_c4d_units(1.0, 2.0, 3.0, "pc")
    assert out == (1.0, 2.0, 3.0)


def test_pc_to_c4d_units_kpc_mode_scales_down():
    out = pc_to_c4d_units(1000.0, 0.0, 0.0, "kpc")
    assert math.isclose(out[0], 1.0)


def test_pc_to_c4d_units_mpc_mode():
    out = pc_to_c4d_units(1.0e6, 0.0, 0.0, "mpc")
    assert math.isclose(out[0], 1.0)


def test_pc_to_c4d_units_rejects_unknown_scale():
    with pytest.raises(ValueError):
        pc_to_c4d_units(1.0, 0.0, 0.0, "lightyears_squared")


def test_all_scale_modes_are_positive():
    for mode, factor in SCALE_MODES.items():
        assert factor > 0, mode


# ---------------------------------------------------------------------------
# Render attributes
# ---------------------------------------------------------------------------


def test_render_radius_brighter_is_larger():
    bright = render_radius_from_magnitude(0.0)
    dim = render_radius_from_magnitude(15.0)
    assert bright > dim


def test_render_radius_unknown_returns_base():
    assert render_radius_from_magnitude(None) == 1.0


def test_render_radius_clamps():
    huge = render_radius_from_magnitude(-1000.0)
    tiny = render_radius_from_magnitude(1000.0)
    assert huge <= 50.0
    assert tiny >= 0.05


def test_display_color_star_uses_spectral():
    g_color = display_color_for("star", "G2V")
    o_color = display_color_for("star", "O5V")
    assert g_color != o_color
    # O is bluer than G — its blue channel should be >= G's blue channel.
    assert o_color[2] >= g_color[2]


def test_display_color_galaxy_falls_back_to_type():
    c = display_color_for("galaxy", None)
    assert c == display_color_for("galaxy", "G2V")  # spectral ignored


def test_display_color_unknown_type_is_grey():
    c = display_color_for("dyson_sphere")  # not in OBJECT_TYPES
    assert c == (180, 180, 180)


# ---------------------------------------------------------------------------
# Derived-field population
# ---------------------------------------------------------------------------


def test_compute_derived_fields_populates_all():
    obj = _good_obj(distance_parsec=10.0, apparent_magnitude=5.0, spectral_type="G2V")
    compute_derived_fields(obj, scale_mode="pc")
    assert obj.cartesian_x is not None
    assert obj.cartesian_y is not None
    assert obj.cartesian_z is not None
    assert obj.c4d_x is not None
    assert obj.render_radius is not None
    assert obj.display_color_rgb is not None


def test_compute_derived_fields_placeholder_tags_metadata():
    obj = _good_obj()  # no distance, no parallax
    compute_derived_fields(obj)
    meta = json.loads(obj.metadata_json)
    assert meta.get("distance_method") == "placeholder_sphere"


def test_compute_derived_fields_idempotent():
    obj = _good_obj(distance_parsec=10.0)
    compute_derived_fields(obj)
    first = (obj.cartesian_x, obj.cartesian_y, obj.cartesian_z)
    compute_derived_fields(obj)
    second = (obj.cartesian_x, obj.cartesian_y, obj.cartesian_z)
    assert first == second


def test_compute_derived_fields_default_scale_is_pc():
    assert DEFAULT_SCALE_MODE == "pc"
    obj = _good_obj(distance_parsec=5.0)
    compute_derived_fields(obj)
    assert obj.c4d_x == obj.cartesian_x
    assert obj.c4d_y == obj.cartesian_y
    assert obj.c4d_z == obj.cartesian_z
