"""Tests for core.visual_encoding. Pure CPython, no Cinema 4D."""

from __future__ import annotations

import pytest

from core.visual_encoding import (
    COLOR_MODE_LABELS,
    COLOR_MODES,
    SIZE_MODE_LABELS,
    SIZE_MODES,
    VisualEncodingParams,
    apply_to_object,
    apply_to_objects,
    color_by_bp_rp,
    color_by_catalog_source,
    color_by_magnitude,
    color_by_object_type,
    color_by_redshift,
    color_mode_for_label,
    color_natural,
    encode,
    encode_color,
    encode_size,
    label_for_color_mode,
    label_for_size_mode,
    size_by_magnitude,
    size_by_object_type,
    size_mode_for_label,
    size_uniform,
)
from data.schema import CatalogObject


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _star(**overrides) -> CatalogObject:
    base = dict(
        uid="s1",
        catalog_source="gaia_dr3",
        object_type="star",
        ra_deg=10.0,
        dec_deg=-20.0,
        spectral_type="G2V",
        apparent_magnitude=5.0,
        color_index=0.6,
    )
    base.update(overrides)
    return CatalogObject(**base)


def _galaxy(**overrides) -> CatalogObject:
    base = dict(
        uid="g1",
        catalog_source="sdss_dr18",
        object_type="galaxy",
        ra_deg=180.0,
        dec_deg=30.0,
        redshift=0.05,
        apparent_magnitude=18.0,
    )
    base.update(overrides)
    return CatalogObject(**base)


# ---------------------------------------------------------------------------
# Constants and label helpers
# ---------------------------------------------------------------------------


def test_color_modes_match_dropdown_labels():
    label_tokens = {tok for _lbl, tok in COLOR_MODE_LABELS}
    assert label_tokens == set(COLOR_MODES)


def test_size_modes_match_dropdown_labels():
    label_tokens = {tok for _lbl, tok in SIZE_MODE_LABELS}
    assert label_tokens == set(SIZE_MODES)


def test_user_facing_labels_contain_required_options():
    labels = {lbl for lbl, _tok in COLOR_MODE_LABELS}
    for required in ("Natural Star Color", "Catalog Source", "Object Type",
                     "Redshift", "Magnitude"):
        assert required in labels


def test_label_token_round_trip():
    for label, token in COLOR_MODE_LABELS:
        assert color_mode_for_label(label) == token
        assert label_for_color_mode(token) == label
    for label, token in SIZE_MODE_LABELS:
        assert size_mode_for_label(label) == token
        assert label_for_size_mode(token) == label


def test_unknown_label_falls_back_safely():
    assert color_mode_for_label("Quantum Foam Mode") == "natural"
    assert size_mode_for_label("Tachyon") == "magnitude"


# ---------------------------------------------------------------------------
# VisualEncodingParams validation
# ---------------------------------------------------------------------------


def test_params_defaults_validate():
    p = VisualEncodingParams()
    assert p.color_mode == "natural"
    assert p.size_mode == "magnitude"
    assert p.size_scale == 1.0
    assert p.brightness_scale == 1.0
    assert p.brightness_exaggeration == 1.0


def test_params_rejects_unknown_color_mode():
    with pytest.raises(ValueError):
        VisualEncodingParams(color_mode="warp_drive")


def test_params_rejects_unknown_size_mode():
    with pytest.raises(ValueError):
        VisualEncodingParams(size_mode="quantum")


def test_params_rejects_nonpositive_scales():
    with pytest.raises(ValueError):
        VisualEncodingParams(size_scale=0.0)
    with pytest.raises(ValueError):
        VisualEncodingParams(brightness_scale=-1.0)
    with pytest.raises(ValueError):
        VisualEncodingParams(brightness_exaggeration=0.0)


def test_params_rejects_inverted_ranges():
    with pytest.raises(ValueError):
        VisualEncodingParams(redshift_min=2.0, redshift_max=1.0)
    with pytest.raises(ValueError):
        VisualEncodingParams(magnitude_min=10.0, magnitude_max=5.0)
    with pytest.raises(ValueError):
        VisualEncodingParams(bp_rp_min=1.0, bp_rp_max=0.5)


# ---------------------------------------------------------------------------
# Per-mode colour: spectral / type / source
# ---------------------------------------------------------------------------


def test_color_natural_uses_spectral_for_stars():
    g_star = _star(spectral_type="G2V")
    o_star = _star(spectral_type="O5V")
    assert color_natural(g_star) != color_natural(o_star)


def test_color_natural_unknown_spectral_falls_back():
    obj = _star(spectral_type=None)
    rgb = color_natural(obj)
    assert all(0 <= c <= 255 for c in rgb)


def test_color_by_catalog_source_known_palette():
    assert color_by_catalog_source("gaia_dr3") != color_by_catalog_source("sdss_dr18")
    assert color_by_catalog_source("gaia_dr3") == color_by_catalog_source("gaia_dr2")


def test_color_by_catalog_source_unknown_grey_default():
    rgb = color_by_catalog_source("unknown_release")
    assert all(0 <= c <= 255 for c in rgb)
    # Falls back to the unav_sample neutral grey.
    assert rgb == color_by_catalog_source("unav_sample")


def test_color_by_object_type_distinguishes_galaxy_from_quasar():
    assert color_by_object_type("galaxy") != color_by_object_type("quasar")


# ---------------------------------------------------------------------------
# Per-mode colour: redshift
# ---------------------------------------------------------------------------


def test_color_by_redshift_increases_red_channel_with_z():
    low = color_by_redshift(0.01, 0.0, 3.0)
    high = color_by_redshift(2.5, 0.0, 3.0)
    assert low is not None and high is not None
    assert high[0] > low[0]   # more red at higher z
    assert high[2] < low[2]   # less blue at higher z


def test_color_by_redshift_clamps_outside_range():
    very_low = color_by_redshift(-1.0, 0.0, 3.0)
    bottom = color_by_redshift(0.0, 0.0, 3.0)
    assert very_low == bottom
    very_high = color_by_redshift(10.0, 0.0, 3.0)
    top = color_by_redshift(3.0, 0.0, 3.0)
    assert very_high == top


def test_color_by_redshift_returns_none_for_missing():
    assert color_by_redshift(None, 0.0, 3.0) is None


# ---------------------------------------------------------------------------
# Per-mode colour: magnitude / bp_rp
# ---------------------------------------------------------------------------


def test_color_by_magnitude_bright_lighter_than_dim():
    bright = color_by_magnitude(0.0, -1.5, 22.0)
    dim = color_by_magnitude(20.0, -1.5, 22.0)
    assert bright is not None and dim is not None
    # Bright objects are warmer/lighter; their luminance dominates dim.
    bright_lum = sum(bright)
    dim_lum = sum(dim)
    assert bright_lum > dim_lum


def test_color_by_magnitude_returns_none_for_missing():
    assert color_by_magnitude(None, -1.5, 22.0) is None


def test_color_by_bp_rp_negative_blue_positive_red():
    blue = color_by_bp_rp(-0.5, -0.5, 3.0)
    red = color_by_bp_rp(3.0, -0.5, 3.0)
    assert blue is not None and red is not None
    assert red[0] > blue[0]    # more red at higher BP-RP
    assert blue[2] > red[2]    # more blue at lower BP-RP


def test_color_by_bp_rp_returns_none_for_missing():
    assert color_by_bp_rp(None, -0.5, 3.0) is None


# ---------------------------------------------------------------------------
# Per-mode size
# ---------------------------------------------------------------------------


def test_size_by_magnitude_brighter_is_larger():
    bright = size_by_magnitude(0.0)
    dim = size_by_magnitude(15.0)
    assert bright > dim


def test_size_by_magnitude_unknown_returns_base():
    assert size_by_magnitude(None) == 1.0


def test_size_by_magnitude_exaggeration_widens_contrast():
    bright = size_by_magnitude(0.0)
    dim = size_by_magnitude(10.0)
    bright_e = size_by_magnitude(0.0, exaggeration=2.0)
    dim_e = size_by_magnitude(10.0, exaggeration=2.0)
    assert (bright_e / dim_e) > (bright / dim)


def test_size_by_magnitude_clamps_to_floor_and_ceiling():
    huge = size_by_magnitude(-1000.0)
    tiny = size_by_magnitude(1000.0)
    assert tiny >= 0.05
    assert huge <= 50.0


def test_size_by_object_type_distinguishes_categories():
    star = size_by_object_type("star")
    galaxy = size_by_object_type("galaxy")
    asteroid = size_by_object_type("asteroid")
    assert galaxy > star
    assert star > asteroid


def test_size_by_object_type_unknown_uses_default():
    assert size_by_object_type("dyson_sphere") == size_by_object_type("unknown")


def test_size_by_object_type_covers_all_required_categories():
    for t in ("star", "galaxy", "quasar", "nebula", "planet", "moon",
              "asteroid", "spacecraft", "unknown"):
        assert size_by_object_type(t) > 0


def test_size_uniform_returns_base():
    assert size_uniform() == 1.0


# ---------------------------------------------------------------------------
# encode_color / encode_size dispatch + fallbacks
# ---------------------------------------------------------------------------


def test_encode_color_natural_matches_helper():
    obj = _star(spectral_type="K3III")
    p = VisualEncodingParams(color_mode="natural")
    assert encode_color(obj, p) == color_natural(obj)


def test_encode_color_redshift_falls_back_when_z_missing():
    obj = _star(redshift=None, spectral_type="G2V")
    p = VisualEncodingParams(color_mode="redshift")
    # With no redshift on a star, fall back to natural — must not be the
    # neutral grey of the unknown-source bucket.
    assert encode_color(obj, p) == color_natural(obj)


def test_encode_color_magnitude_falls_back_when_mag_missing():
    obj = _star(apparent_magnitude=None)
    p = VisualEncodingParams(color_mode="magnitude")
    assert encode_color(obj, p) == color_natural(obj)


def test_encode_color_bp_rp_falls_back_when_color_index_missing():
    obj = _star(color_index=None)
    p = VisualEncodingParams(color_mode="bp_rp")
    assert encode_color(obj, p) == color_natural(obj)


def test_encode_color_galaxy_redshift_uses_ramp():
    near = _galaxy(redshift=0.01)
    far = _galaxy(redshift=2.5)
    p = VisualEncodingParams(color_mode="redshift", redshift_min=0.0, redshift_max=3.0)
    assert encode_color(far, p) != encode_color(near, p)


def test_encode_color_catalog_source_distinguishes_sources():
    a = _star(catalog_source="gaia_dr3")
    b = _star(catalog_source="sdss_dr18")
    p = VisualEncodingParams(color_mode="catalog_source")
    assert encode_color(a, p) != encode_color(b, p)


def test_encode_size_modes_have_distinct_outputs():
    obj = _star(apparent_magnitude=5.0, object_type="galaxy")
    a = encode_size(obj, VisualEncodingParams(size_mode="magnitude"))
    b = encode_size(obj, VisualEncodingParams(size_mode="object_type"))
    c = encode_size(obj, VisualEncodingParams(size_mode="uniform"))
    assert a != b or b != c or a != c
    assert all(x > 0 for x in (a, b, c))


# ---------------------------------------------------------------------------
# encode() top-level (rgb, radius)
# ---------------------------------------------------------------------------


def test_encode_default_matches_natural_and_magnitude_path():
    obj = _star()
    rgb, radius = encode(obj)
    assert rgb == color_natural(obj)
    assert radius == pytest.approx(size_by_magnitude(obj.apparent_magnitude))


def test_encode_size_scale_multiplies_radius():
    obj = _star()
    _, base = encode(obj, VisualEncodingParams(size_scale=1.0))
    _, doubled = encode(obj, VisualEncodingParams(size_scale=2.0))
    assert doubled == pytest.approx(base * 2.0)


def test_encode_brightness_scale_multiplies_after_size():
    obj = _star()
    _, base = encode(obj, VisualEncodingParams())
    _, twice = encode(
        obj, VisualEncodingParams(size_scale=2.0, brightness_scale=2.0),
    )
    assert twice == pytest.approx(base * 4.0)


# ---------------------------------------------------------------------------
# apply_to_object / apply_to_objects
# ---------------------------------------------------------------------------


def test_apply_to_object_writes_back_cached_fields():
    obj = _star()
    apply_to_object(obj, VisualEncodingParams(color_mode="catalog_source"))
    assert obj.display_color_rgb == color_by_catalog_source(obj.catalog_source)
    assert obj.render_radius is not None and obj.render_radius > 0


def test_apply_to_objects_returns_list_and_mutates():
    objs = [_star(uid="a"), _galaxy(uid="b")]
    out = apply_to_objects(objs, VisualEncodingParams(color_mode="object_type"))
    assert out == objs
    for o in objs:
        assert o.display_color_rgb is not None
        assert o.render_radius is not None
