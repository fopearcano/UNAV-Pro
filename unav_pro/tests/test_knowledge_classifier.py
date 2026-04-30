"""Tests for the v1.3 ``knowledge.object_classifier``."""

from __future__ import annotations

import json

import pytest

from data.schema import CatalogObject
from knowledge.object_classifier import (
    KNOWN_CLASSES,
    classify_object,
)


def _gaia_star() -> CatalogObject:
    return CatalogObject(
        uid="gaia:42", catalog_source="Gaia DR3",
        object_type="star",
        ra_deg=10.0, dec_deg=20.0,
        distance_parsec=100.0,
        spectral_type="G2V",
        metadata_json=json.dumps({"source_id": "42"}),
    )


def _sdss_galaxy(spec_class="GALAXY") -> CatalogObject:
    return CatalogObject(
        uid="sdss:1", catalog_source="SDSS",
        object_type="galaxy",
        ra_deg=180.0, dec_deg=0.0,
        redshift=0.05,
        metadata_json=json.dumps({
            "objid": "1", "spec_class": spec_class,
        }),
    )


def _desi_quasar(*, zwarn=0) -> CatalogObject:
    return CatalogObject(
        uid="desi:1", catalog_source="DESI",
        object_type="quasar",
        ra_deg=180.0, dec_deg=0.0,
        redshift=2.0,
        metadata_json=json.dumps({
            "spectype": "QSO", "zwarn": zwarn,
        }),
    )


def _jpl_planet(otype="planet") -> CatalogObject:
    return CatalogObject(
        uid="jpl:Mars:2026", catalog_source="JPL Horizons",
        object_type=otype,
        ra_deg=10.0, dec_deg=0.0,
        distance_parsec=1e-5,
        name="Mars",
        metadata_json=json.dumps({
            "body": "Mars", "epoch": "2026-01-01T00:00:00",
        }),
    )


# ---------------------------------------------------------------------------
# Source-level rules
# ---------------------------------------------------------------------------


def test_gaia_row_classifies_as_star():
    cls = classify_object(_gaia_star())
    assert cls.object_class == "star"
    assert cls.confidence == "high"
    assert "Gaia" in cls.reason


def test_jpl_planet_classifies_as_planet():
    cls = classify_object(_jpl_planet("planet"))
    assert cls.object_class == "planet"
    assert cls.confidence == "high"


def test_jpl_moon_classifies_as_moon():
    cls = classify_object(_jpl_planet("moon"))
    assert cls.object_class == "moon"


def test_jpl_spacecraft_classifies_as_spacecraft():
    cls = classify_object(_jpl_planet("spacecraft"))
    assert cls.object_class == "spacecraft"


def test_sdss_spec_class_galaxy():
    cls = classify_object(_sdss_galaxy("GALAXY"))
    assert cls.object_class == "galaxy"
    assert cls.confidence == "high"
    assert "SDSS spec_class" in cls.reason


def test_sdss_spec_class_qso_maps_to_quasar():
    cls = classify_object(_sdss_galaxy("QSO"))
    assert cls.object_class == "quasar"


def test_desi_quasar_high_confidence_when_zwarn_zero():
    cls = classify_object(_desi_quasar(zwarn=0))
    assert cls.object_class == "quasar"
    assert cls.confidence == "high"


def test_desi_quasar_medium_confidence_when_zwarn_set():
    cls = classify_object(_desi_quasar(zwarn=4))
    assert cls.object_class == "quasar"
    assert cls.confidence == "medium"
    assert "zwarn" in cls.reason


# ---------------------------------------------------------------------------
# Fallbacks
# ---------------------------------------------------------------------------


def test_unknown_source_with_canonical_object_type_falls_through():
    obj = CatalogObject(
        uid="x:1", catalog_source="MyCatalog",
        object_type="comet",
        ra_deg=0.0, dec_deg=0.0,
    )
    cls = classify_object(obj)
    assert cls.object_class == "comet"
    assert cls.confidence == "medium"


def test_unknown_source_with_spectral_type_falls_through_to_star():
    obj = CatalogObject(
        uid="x:1", catalog_source="MyCatalog",
        object_type="",  # unknown to the schema
        ra_deg=0.0, dec_deg=0.0,
        spectral_type="K0",
    )
    cls = classify_object(obj)
    assert cls.object_class == "star"
    assert cls.confidence == "low"


def test_unknown_source_with_redshift_implies_galaxy():
    obj = CatalogObject(
        uid="x:1", catalog_source="MyCatalog",
        object_type="",
        ra_deg=0.0, dec_deg=0.0,
        redshift=0.5,
    )
    cls = classify_object(obj)
    assert cls.object_class == "galaxy"
    assert cls.confidence == "low"


def test_no_signal_returns_unknown():
    obj = CatalogObject(
        uid="x:1", catalog_source="UnknownSurvey",
        object_type="",
        ra_deg=0.0, dec_deg=0.0,
    )
    cls = classify_object(obj)
    assert cls.object_class == "unknown"
    assert cls.confidence == "unknown"


def test_classifier_never_raises_on_bad_metadata():
    obj = CatalogObject(
        uid="x:1", catalog_source="SDSS",
        object_type="galaxy",
        ra_deg=0.0, dec_deg=0.0,
        metadata_json="not valid json{",
    )
    cls = classify_object(obj)
    assert cls.object_class in KNOWN_CLASSES


def test_classify_none_returns_unknown():
    cls = classify_object(None)
    assert cls.object_class == "unknown"
    assert not cls.is_known()
