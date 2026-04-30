"""Tests for the Instance Mode backend's pure helpers."""

from __future__ import annotations

import pytest

from c4d_objects.instance_builder import (
    INSTANCE_TEMPLATE_NAME,
    NULL_RADIUS_SCALE,
    encoded_color_radius,
    instance_marker_payload,
    position_for,
)
from c4d_objects.point_cloud_builder import (
    KIND_POINT,
    MARKER_KEY_IS_UNAV,
    MARKER_KEY_KIND,
    MARKER_KEY_UID,
)
from core.visual_encoding import VisualEncodingParams
from data.schema import CatalogObject, compute_derived_fields


def _star() -> CatalogObject:
    o = CatalogObject(
        uid="gaia:1", catalog_source="Gaia DR3", object_type="star",
        ra_deg=10.0, dec_deg=20.0, distance_parsec=10.0,
        apparent_magnitude=5.0, spectral_type="G2V",
    )
    compute_derived_fields(o)
    return o


# ---------------------------------------------------------------------------
# instance_marker_payload
# ---------------------------------------------------------------------------


def test_marker_payload_carries_uid_only():
    payload = instance_marker_payload("gaia:42")
    assert payload[MARKER_KEY_IS_UNAV] is True
    assert payload[MARKER_KEY_KIND] == KIND_POINT
    assert payload[MARKER_KEY_UID] == "gaia:42"


def test_marker_payload_omits_metadata_blob():
    """v0.7 contract: instance markers do NOT carry the heavy
    metadata fields. The inspector pulls them from the lookup."""
    payload = instance_marker_payload("gaia:42")
    # Specifically the heavy/optional ones the DebugObjects backend
    # writes:
    from c4d_objects.point_cloud_builder import (
        MARKER_KEY_CATALOG_SOURCE,
        MARKER_KEY_METADATA_JSON,
        MARKER_KEY_NAME,
        MARKER_KEY_OBJECT_TYPE,
        MARKER_KEY_RA_DEG,
    )
    assert MARKER_KEY_NAME not in payload
    assert MARKER_KEY_CATALOG_SOURCE not in payload
    assert MARKER_KEY_OBJECT_TYPE not in payload
    assert MARKER_KEY_METADATA_JSON not in payload
    assert MARKER_KEY_RA_DEG not in payload


def test_marker_payload_handles_empty_uid():
    payload = instance_marker_payload("")
    assert payload[MARKER_KEY_UID] == ""


# ---------------------------------------------------------------------------
# encoded_color_radius
# ---------------------------------------------------------------------------


def test_natural_path_returns_color_and_radius():
    rgb, radius = encoded_color_radius(_star(), encoding=None)
    assert len(rgb) == 3
    for c in rgb:
        assert 0.0 <= c <= 1.0
    assert radius > 0


def test_encoded_path_consults_visual_encoding():
    """Confirms the backend never reimplements colour logic — both
    paths route through the same encoder."""
    star = _star()
    encoding = VisualEncodingParams(color_mode="object_type", size_mode="uniform")
    rgb, radius = encoded_color_radius(star, encoding=encoding)
    assert len(rgb) == 3
    # uniform size mode * NULL_RADIUS_SCALE (instance backend's bump).
    assert radius == pytest.approx(1.0 * NULL_RADIUS_SCALE)


def test_redshift_mode_returns_warmer_color_for_high_z():
    obj = CatalogObject(
        uid="x", catalog_source="DESI", object_type="quasar",
        ra_deg=10.0, dec_deg=20.0, redshift=2.5,
    )
    cool, _ = encoded_color_radius(
        CatalogObject(
            uid="y", catalog_source="DESI", object_type="quasar",
            ra_deg=10.0, dec_deg=20.0, redshift=0.0,
        ),
        encoding=VisualEncodingParams(
            color_mode="redshift", redshift_min=0.0, redshift_max=3.0,
        ),
    )
    warm, _ = encoded_color_radius(
        obj,
        encoding=VisualEncodingParams(
            color_mode="redshift", redshift_min=0.0, redshift_max=3.0,
        ),
    )
    # Warm-end has more red than blue; cool-end has the reverse.
    assert warm[0] > warm[2]
    assert cool[2] > cool[0]


# ---------------------------------------------------------------------------
# position_for
# ---------------------------------------------------------------------------


def test_position_uses_cached_c4d_when_present():
    star = _star()
    star.c4d_x = 1.0
    star.c4d_y = 2.0
    star.c4d_z = 3.0
    assert position_for(star) == (1.0, 2.0, 3.0)


def test_position_recomputes_when_c4d_missing():
    obj = CatalogObject(
        uid="g:1", catalog_source="Gaia DR3", object_type="star",
        ra_deg=0.0, dec_deg=0.0, distance_parsec=10.0,
    )
    pos = position_for(obj)
    # ra=0,dec=0,d=10 → x=10,y=0,z=0 in pc.
    assert pos[0] == pytest.approx(10.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_template_name_is_distinct_from_visible_sector_children():
    """Template lives under UNAV_Debug, never in the visible sector,
    so the safety advisory does not double-count it."""
    assert INSTANCE_TEMPLATE_NAME == "UNAV_InstanceTemplate"


def test_null_radius_scale_matches_debug_backend():
    """The two backends produce identical-looking dots for the same
    encoding params; if these constants drift, the visual parity
    test is the canary."""
    from c4d_objects.point_cloud_builder import NULL_RADIUS_SCALE as DEBUG_SCALE
    assert NULL_RADIUS_SCALE == DEBUG_SCALE
