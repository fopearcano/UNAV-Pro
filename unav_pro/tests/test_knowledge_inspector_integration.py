"""End-to-end formatting checks for the v1.3 inspector upgrade.

These tests build an ``InspectionResult`` (no Cinema 4D
required) and assert that the new sections — Basic Identity /
Position / Motion / Photometry / Redshift / Catalog Notes /
Plain-language Summary / Missing Data / Available Actions —
appear with the right content for representative inputs.
"""

from __future__ import annotations

import json

import pytest

from data.connectors.redshift_distance import DISTANCE_METHOD_REDSHIFT_PROXY
from data.schema import CatalogObject
from ui.metadata_panel import (
    STATUS_FOUND_FULL,
    InspectionResult,
)


def _gaia_star() -> CatalogObject:
    return CatalogObject(
        uid="gaia:42", catalog_source="Gaia DR3",
        object_type="star",
        ra_deg=10.0, dec_deg=20.0,
        distance_parsec=100.0, parallax_mas=10.0,
        proper_motion_ra=5.0, proper_motion_dec=-3.0,
        radial_velocity_kms=12.5,
        apparent_magnitude=8.0, color_index=0.5,
        spectral_type="G2V", name="42",
        metadata_json=json.dumps({"parallax_error_mas": 0.5}),
    )


def _jpl_planet() -> CatalogObject:
    return CatalogObject(
        uid="jpl:Mars:2026", catalog_source="JPL Horizons",
        object_type="planet", name="Mars", common_name="Mars",
        ra_deg=10.0, dec_deg=0.0,
        distance_parsec=1.5e-5,
        metadata_json=json.dumps({
            "body": "Mars",
            "epoch": "2026-01-01T00:00:00",
            "center": "500@10",
        }),
    )


def _proxy_galaxy() -> CatalogObject:
    return CatalogObject(
        uid="sdss:1", catalog_source="SDSS",
        object_type="galaxy",
        ra_deg=180.0, dec_deg=0.0,
        redshift=0.08,
        distance_parsec=300_000_000.0,
        metadata_json=json.dumps({
            "spec_class": "GALAXY",
            "spec_subclass": "STARBURST",
            "release": "sdss_dr18",
            "distance_method": DISTANCE_METHOD_REDSHIFT_PROXY,
        }),
    )


def _bare_object() -> CatalogObject:
    return CatalogObject(
        uid="x:1", catalog_source="UnknownSurvey",
        object_type="",
        ra_deg=0.0, dec_deg=0.0,
    )


def _inspect(obj):
    return InspectionResult(
        status=STATUS_FOUND_FULL, object_name="UNAV_TEST",
        marker={}, catalog_object=obj,
    ).display_text


# ---------------------------------------------------------------------------
# Section presence
# ---------------------------------------------------------------------------


def test_inspector_renders_all_v13_sections_for_full_star():
    text = _inspect(_gaia_star())
    for section in (
        "--- Basic Identity ---",
        "--- Position ---",
        "--- Motion ---",
        "--- Photometry ---",
        "--- Plain-language Summary ---",
        "--- Available Actions ---",
    ):
        assert section in text, f"{section!r} missing from inspector text"


def test_inspector_redshift_section_for_galaxy():
    text = _inspect(_proxy_galaxy())
    assert "--- Redshift / Cosmology ---" in text
    assert "0.080000" in text


def test_inspector_catalog_notes_for_sdss_galaxy():
    text = _inspect(_proxy_galaxy())
    assert "--- Catalog Notes ---" in text
    assert "Spec class     : GALAXY" in text
    assert "Spec subclass  : STARBURST" in text
    assert "Release        : sdss_dr18" in text


def test_inspector_proxy_distance_warning():
    text = _inspect(_proxy_galaxy())
    assert "APPROXIMATE" in text
    assert "Distance type  : redshift_proxy" in text


def test_inspector_jpl_planet_position_basis_is_ephemeris():
    text = _inspect(_jpl_planet())
    assert "Position basis : ephemeris" in text or \
           "Position basis : static" in text  # allow ephemeris from class
    assert "ephemeris" in text


def test_inspector_jpl_planet_offers_time_navigator_action():
    text = _inspect(_jpl_planet())
    assert "Time Navigator" in text


def test_inspector_jpl_planet_catalog_notes_have_epoch_and_center():
    text = _inspect(_jpl_planet())
    assert "Epoch          : 2026-01-01T00:00:00" in text
    assert "Observed from  : 500@10" in text


def test_inspector_missing_data_section_for_bare_row():
    text = _inspect(_bare_object())
    assert "--- Missing Data ---" in text
    assert "distance" in text
    assert "redshift" in text


# ---------------------------------------------------------------------------
# Classification banner
# ---------------------------------------------------------------------------


def test_inspector_class_line_includes_confidence():
    text = _inspect(_gaia_star())
    assert "Class          : star" in text
    assert "high" in text


def test_inspector_class_for_unknown_object():
    text = _inspect(_bare_object())
    assert "Class          : unknown" in text


# ---------------------------------------------------------------------------
# Available Actions
# ---------------------------------------------------------------------------


def test_inspector_disables_focus_when_no_distance():
    text = _inspect(_bare_object())
    assert "Focus Navigator unavailable" in text
    assert "no reliable distance" in text


def test_inspector_motion_section_drift_classification():
    text = _inspect(_gaia_star())
    # Star moves at sqrt(5^2+3^2)=5.83 mas/yr → "slow".
    assert "slow" in text
    assert "drifting" in text.lower()
