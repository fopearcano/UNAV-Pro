"""v0.5 cross-cutting integration tests.

Covers the contracts that span connectors / encoder / inspector /
registry: mixed Gaia + JPL + SDSS + DESI uid namespacing, the
redshift visual encoding under the new ``"SDSS"`` / ``"DESI"`` source
labels, and the metadata-inspector approximate-distance warning.
"""

from __future__ import annotations

import json

from core.dataset_registry import DatasetEntry, DatasetRegistry
from core.metadata_lookup import MetadataLookup
from core.visual_encoding import (
    VisualEncodingParams,
    color_by_catalog_source,
    encode,
    encode_color,
)
from data.connectors.redshift_distance import (
    DISTANCE_METHOD_REDSHIFT_PROXY,
    DISTANCE_PROXY_WARNING_TEXT,
)
from data.schema import CatalogObject
from ui.metadata_panel import (
    STATUS_FOUND_FULL,
    InspectionResult,
)


# ---------------------------------------------------------------------------
# Mixed uid namespacing
# ---------------------------------------------------------------------------


def test_mixed_dataset_uids_disjoint_by_connector_prefix():
    """Each connector emits a different prefix; the registry's
    namespace layer is not even necessary for the connector prefixes
    to stay disjoint."""
    gaia = CatalogObject(
        uid="gaia:1234567890", catalog_source="Gaia DR3", object_type="star",
        ra_deg=10.0, dec_deg=20.0,
    )
    jpl = CatalogObject(
        uid="jpl:Mars:2026-01-01", catalog_source="JPL Horizons",
        object_type="planet", ra_deg=0.0, dec_deg=0.0,
    )
    sdss = CatalogObject(
        uid="sdss:9001", catalog_source="SDSS", object_type="galaxy",
        ra_deg=180.0, dec_deg=30.0,
    )
    desi = CatalogObject(
        uid="desi:39633072104341543", catalog_source="DESI",
        object_type="galaxy", ra_deg=180.0, dec_deg=30.0,
    )
    uids = {o.uid for o in (gaia, jpl, sdss, desi)}
    # All four uids are distinct.
    assert len(uids) == 4
    # Prefix is the connector token.
    assert gaia.uid.split(":")[0] == "gaia"
    assert jpl.uid.split(":")[0] == "jpl"
    assert sdss.uid.split(":")[0] == "sdss"
    assert desi.uid.split(":")[0] == "desi"


def test_metadata_lookup_mixed_dataset_resolution():
    """The lookup table works with mixed connector prefixes."""
    rows = [
        CatalogObject(
            uid="gaia:1", catalog_source="Gaia DR3", object_type="star",
            ra_deg=10.0, dec_deg=20.0,
        ),
        CatalogObject(
            uid="jpl:Mars:2026-01-01", catalog_source="JPL Horizons",
            object_type="planet", ra_deg=0.0, dec_deg=0.0,
        ),
        CatalogObject(
            uid="sdss:9001", catalog_source="SDSS", object_type="galaxy",
            ra_deg=180.0, dec_deg=30.0,
        ),
        CatalogObject(
            uid="desi:1", catalog_source="DESI", object_type="galaxy",
            ra_deg=180.0, dec_deg=30.0,
        ),
    ]
    lookup = MetadataLookup(rows)
    for r in rows:
        assert lookup.lookup(r.uid) is r


def test_registry_namespace_prevents_intra_connector_collisions(tmp_path):
    """Two SDSS dataset files that happen to share an objID stay
    disjoint under the ``<entry.name>:`` namespace."""
    p1 = tmp_path / "sdss_a.jsonl"
    p2 = tmp_path / "sdss_b.jsonl"
    row = {
        "uid": "sdss:9001", "catalog_source": "SDSS", "object_type": "galaxy",
        "ra_deg": 10.0, "dec_deg": 20.0, "redshift": 0.05,
        "metadata_json": "{}",
    }
    p1.write_text(json.dumps(row) + "\n", encoding="utf-8")
    p2.write_text(json.dumps(row) + "\n", encoding="utf-8")

    reg = DatasetRegistry()
    reg.add(DatasetEntry(name="A", path=str(p1), namespace=True))
    reg.add(DatasetEntry(name="B", path=str(p2), namespace=True))
    result = reg.merge_active(on_error="raise")
    # Both rows kept thanks to namespace prefix.
    assert result.duplicates_skipped == 0
    assert {o.uid for o in result.objects} == {"A:sdss:9001", "B:sdss:9001"}


# ---------------------------------------------------------------------------
# Redshift visual encoding
# ---------------------------------------------------------------------------


def test_color_by_catalog_source_resolves_v05_labels():
    """The new label-style sources resolve to a non-default colour."""
    sdss = color_by_catalog_source("SDSS")
    desi = color_by_catalog_source("DESI")
    gaia = color_by_catalog_source("Gaia DR3")
    jpl = color_by_catalog_source("JPL Horizons")
    fallback = color_by_catalog_source("unav_sample")
    assert sdss != fallback
    assert desi != fallback
    assert gaia != fallback
    assert jpl != fallback
    # Distinct between extragalactic surveys.
    assert sdss != desi


def test_color_by_catalog_source_legacy_release_tokens_still_work():
    """Backwards compatibility: the v0.3-era release tokens stay in
    the palette so v0.3-flagged catalogs still encode correctly."""
    assert color_by_catalog_source("sdss_dr18") == color_by_catalog_source("SDSS")
    assert color_by_catalog_source("desi_edr") == color_by_catalog_source("DESI")
    assert color_by_catalog_source("gaia_dr3") == color_by_catalog_source("Gaia DR3")
    assert color_by_catalog_source("jpl_horizons") == color_by_catalog_source("JPL Horizons")


def test_redshift_color_mode_maps_low_to_blue_high_to_red():
    low = CatalogObject(
        uid="sdss:1", catalog_source="SDSS", object_type="galaxy",
        ra_deg=10, dec_deg=20, redshift=0.0,
    )
    high = CatalogObject(
        uid="sdss:2", catalog_source="SDSS", object_type="galaxy",
        ra_deg=10, dec_deg=20, redshift=3.0,
    )
    p = VisualEncodingParams(color_mode="redshift", redshift_min=0.0, redshift_max=3.0)
    c_low = encode_color(low, p)
    c_high = encode_color(high, p)
    # Cool-warm gradient: low end is blue-leaning, high end is red-leaning.
    assert c_low[2] > c_low[0]   # B > R for low z
    assert c_high[0] > c_high[2]  # R > B for high z


def test_redshift_color_mode_falls_back_when_redshift_missing():
    """Galaxies without redshift fall back to natural / type colour
    rather than crashing."""
    obj = CatalogObject(
        uid="sdss:99", catalog_source="SDSS", object_type="galaxy",
        ra_deg=10, dec_deg=20,  # no redshift
    )
    p = VisualEncodingParams(color_mode="redshift")
    rgb = encode_color(obj, p)
    # Returns *something*; the encoder's contract is to never raise.
    assert isinstance(rgb, tuple) and len(rgb) == 3


def test_redshift_min_max_configurable_via_params():
    """The redshift ramp's vmin/vmax are configurable; mid-z lands at
    the gradient mid-point regardless."""
    obj = CatalogObject(
        uid="sdss:1", catalog_source="SDSS", object_type="galaxy",
        ra_deg=10, dec_deg=20, redshift=0.5,
    )
    a = encode_color(obj, VisualEncodingParams(
        color_mode="redshift", redshift_min=0.0, redshift_max=1.0,
    ))
    b = encode_color(obj, VisualEncodingParams(
        color_mode="redshift", redshift_min=0.0, redshift_max=10.0,
    ))
    # Same object under tighter bounds reads warmer (further along
    # the ramp); under looser bounds reads cooler.
    assert a != b


def test_object_type_size_distinguishes_galaxy_from_star():
    """Galaxies/quasars render visually larger than Gaia stars in the
    object_type size mode."""
    star = CatalogObject(
        uid="g:1", catalog_source="Gaia DR3", object_type="star",
        ra_deg=10, dec_deg=20,
    )
    galaxy = CatalogObject(
        uid="sdss:1", catalog_source="SDSS", object_type="galaxy",
        ra_deg=10, dec_deg=20,
    )
    quasar = CatalogObject(
        uid="desi:1", catalog_source="DESI", object_type="quasar",
        ra_deg=10, dec_deg=20,
    )
    p = VisualEncodingParams(size_mode="object_type")
    _, r_star = encode(star, p)
    _, r_gal = encode(galaxy, p)
    _, r_qso = encode(quasar, p)
    assert r_gal > r_star
    assert r_qso > r_star


# ---------------------------------------------------------------------------
# Metadata inspector — new fields
# ---------------------------------------------------------------------------


def _sdss_galaxy_with_proxy_distance() -> CatalogObject:
    extra = {
        "objid": "PHOTO123",
        "specobjid": "9001",
        "release": "sdss_dr18",
        "spec_class": "GALAXY",
        "spec_subclass": "STARBURST",
        "distance_method": DISTANCE_METHOD_REDSHIFT_PROXY,
        "distance_proxy_warning": DISTANCE_PROXY_WARNING_TEXT,
        "distance_proxy_z": 0.05,
        "distance_proxy_h0_km_s_mpc": 70.0,
        "distance_proxy_max_z": 0.1,
    }
    return CatalogObject(
        uid="sdss:9001",
        catalog_source="SDSS",
        object_type="galaxy",
        ra_deg=180.0,
        dec_deg=30.0,
        distance_parsec=2.14e8,
        redshift=0.05,
        apparent_magnitude=18.7,
        color_index=0.5,
        name="PHOTO123",
        metadata_json=json.dumps(extra, sort_keys=True),
    )


def _desi_quasar_high_z() -> CatalogObject:
    extra = {
        "targetid": "1",
        "release": "desi_edr",
        "spectype": "QSO",
        "subtype": "",
        "survey": "sv1",
        "program": "dark",
        "zerr": 0.001,
        "zwarn": 0,
    }
    return CatalogObject(
        uid="desi:1",
        catalog_source="DESI",
        object_type="quasar",
        ra_deg=180.0,
        dec_deg=30.0,
        distance_parsec=None,
        redshift=1.5,
        name="1",
        metadata_json=json.dumps(extra, sort_keys=True),
    )


def test_inspector_displays_redshift_and_survey_fields_for_desi():
    obj = _desi_quasar_high_z()
    result = InspectionResult(
        status=STATUS_FOUND_FULL, object_name="UNAV_DESI_1",
        marker={}, catalog_object=obj,
    )
    text = result.display_text
    assert "Redshift z" in text
    assert "1.500000" in text
    # Catalog Notes section appears with DESI fields.
    assert "Catalog Notes" in text
    assert "Spec type      : QSO" in text
    assert "Survey         : sv1" in text
    assert "Program        : dark" in text
    assert "Release        : desi_edr" in text


def test_inspector_displays_proxy_distance_warning_for_sdss_galaxy():
    obj = _sdss_galaxy_with_proxy_distance()
    result = InspectionResult(
        status=STATUS_FOUND_FULL, object_name="UNAV_SDSS_PHOTO123",
        marker={}, catalog_object=obj,
    )
    text = result.display_text
    # The astrometry section flags the distance as APPROXIMATE.
    assert "APPROXIMATE" in text
    assert "Hubble" in text or "approximate" in text.lower()
    # Catalog Notes section shows SDSS spec class.
    assert "Spec class     : GALAXY" in text
    assert "Spec subclass  : STARBURST" in text
    assert "Release        : sdss_dr18" in text


def test_inspector_does_not_warn_on_explicit_gaia_distance():
    """Gaia stars carry an explicit parallax-derived distance; the
    inspector must NOT flag those as approximate."""
    obj = CatalogObject(
        uid="gaia:1", catalog_source="Gaia DR3", object_type="star",
        ra_deg=10.0, dec_deg=20.0,
        distance_parsec=42.5, parallax_mas=23.5,
        metadata_json=json.dumps({"release": "gaia_dr3", "source_id": 1}),
    )
    result = InspectionResult(
        status=STATUS_FOUND_FULL, object_name="g", marker={},
        catalog_object=obj,
    )
    text = result.display_text
    assert "APPROXIMATE" not in text
