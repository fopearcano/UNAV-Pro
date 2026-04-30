"""Tests for the v1.3 ``knowledge.object_summary``."""

from __future__ import annotations

import json

import pytest

from data.connectors.redshift_distance import DISTANCE_METHOD_REDSHIFT_PROXY
from data.schema import CatalogObject
from knowledge.object_summary import summarize_object


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


def _bare_star() -> CatalogObject:
    """Bare-bones row — RA/Dec only. Tests the missing-data path."""
    return CatalogObject(
        uid="x:1", catalog_source="UnknownSurvey",
        object_type="",
        ra_deg=0.0, dec_deg=0.0,
    )


def _jpl_mars() -> CatalogObject:
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
            "distance_method": DISTANCE_METHOD_REDSHIFT_PROXY,
        }),
    )


# ---------------------------------------------------------------------------
# Lead paragraph
# ---------------------------------------------------------------------------


def test_summary_lead_includes_class_and_catalog():
    s = summarize_object(_gaia_star())
    assert s.classification.object_class == "star"
    text = s.as_text()
    assert "star" in text.lower()
    assert "Gaia DR3" in text


def test_summary_lead_for_unknown_object_says_so():
    s = summarize_object(_bare_star())
    text = s.as_text()
    assert "could not be determined" in text


# ---------------------------------------------------------------------------
# Position paragraph
# ---------------------------------------------------------------------------


def test_summary_position_includes_ra_dec_and_distance():
    s = summarize_object(_gaia_star())
    text = s.as_text()
    assert "10.0000" in text  # RA
    assert "+20.0000" in text  # Dec
    assert "100" in text       # distance


def test_summary_unknown_distance_path_says_unknown():
    s = summarize_object(_bare_star())
    text = s.as_text()
    assert "unknown" in text.lower()


# ---------------------------------------------------------------------------
# Motion paragraph
# ---------------------------------------------------------------------------


def test_summary_motion_describes_proper_motion_and_rv():
    s = summarize_object(_gaia_star())
    text = s.as_text()
    assert "drifting" in text.lower()
    assert "km/s" in text
    assert "receding" in text.lower()


def test_summary_omits_motion_section_when_no_motion():
    s = summarize_object(_bare_star())
    text = s.as_text()
    assert "drifting" not in text.lower()
    assert "km/s" not in text


# ---------------------------------------------------------------------------
# Cosmology paragraph
# ---------------------------------------------------------------------------


def test_summary_redshift_paragraph_for_galaxy():
    s = summarize_object(_proxy_galaxy())
    text = s.as_text()
    assert "redshift" in text.lower()
    assert "0.0800" in text
    assert "Hubble-law" in text or "approximate" in text.lower()


# ---------------------------------------------------------------------------
# Solar-system / time-domain paragraph
# ---------------------------------------------------------------------------


def test_summary_for_jpl_planet_mentions_epoch():
    s = summarize_object(_jpl_mars())
    text = s.as_text()
    assert "Mars" in text
    assert "epoch" in text.lower()
    assert "2026-01-01T00:00:00" in text


def test_summary_for_jpl_planet_mentions_center_frame():
    s = summarize_object(_jpl_mars())
    text = s.as_text()
    assert "500@10" in text


# ---------------------------------------------------------------------------
# Caveats / missing data
# ---------------------------------------------------------------------------


def test_summary_lists_missing_fields():
    s = summarize_object(_bare_star())
    assert "distance" in s.missing_fields
    assert "redshift" in s.missing_fields
    assert "proper motion (RA)" in s.missing_fields
    text = s.as_text()
    assert "Caveats" in text


def test_summary_does_not_list_missing_when_complete():
    s = summarize_object(_gaia_star())
    # Star row has every field except absolute magnitude; that's
    # the only thing flagged.
    assert "absolute magnitude" in s.missing_fields
    # Distance / parallax / RV / pm / colour / spectral type all
    # populated.
    for filled in (
        "distance", "parallax", "redshift",  # redshift is missing on a star
        "radial velocity", "proper motion (RA)",
        "proper motion (Dec)", "apparent magnitude",
        "colour index", "spectral type",
    ):
        if filled == "redshift":
            assert filled in s.missing_fields
        else:
            assert filled not in s.missing_fields


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_summary_is_deterministic():
    a = summarize_object(_gaia_star()).as_text()
    b = summarize_object(_gaia_star()).as_text()
    assert a == b


def test_summary_paragraphs_are_non_empty():
    s = summarize_object(_gaia_star())
    assert len(s.paragraphs) >= 2
    assert all(p.strip() for p in s.paragraphs)
