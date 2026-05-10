"""v3.2 provenance tests."""

from __future__ import annotations

import json

import pytest

from data import (
    CatalogObject,
    KNOWN_COORDINATE_SYSTEMS,
    PROVENANCE_METADATA_KEY,
    PROVENANCE_SCHEMA_VERSION,
    ProvenanceError,
    ProvenanceRecord,
    ProvenanceSummary,
    attach_provenance,
    build_record,
    read_provenance,
    summarise_provenance,
)


def _mk_obj(uid: str = "u1", *, metadata: str = "{}") -> CatalogObject:
    return CatalogObject(
        uid=uid, catalog_source="Test",
        object_type="star", ra_deg=0.0, dec_deg=0.0,
        metadata_json=metadata,
    )


# ---------------------------------------------------------------------------
# ProvenanceRecord round-trip
# ---------------------------------------------------------------------------


def test_record_round_trip_via_dict():
    rec = build_record(
        catalog_source="Gaia DR3",
        connector="gaia_connector",
        connector_version="0.3.0",
        normalisation_version="0.3.0",
        query_parameters={"ra_min": 0.0, "ra_max": 1.0},
        original_field_names={"ra_deg": "ra"},
        coordinate_system="ICRS",
        units={"ra": "deg", "parallax": "mas"},
        known_limitations=["proxy distance"],
    )
    rt = ProvenanceRecord.from_dict(rec.to_dict())
    assert rt.catalog_source == "Gaia DR3"
    assert rt.connector == "gaia_connector"
    assert rt.connector_version == "0.3.0"
    assert rt.coordinate_system == "ICRS"
    assert rt.units == {"ra": "deg", "parallax": "mas"}
    assert rt.known_limitations == ["proxy distance"]
    assert rt.fetched_at_iso  # stamped


def test_record_default_is_empty():
    assert ProvenanceRecord().is_empty() is True


def test_record_built_from_connector_is_not_empty():
    rec = build_record(catalog_source="x", connector="y")
    assert rec.is_empty() is False


def test_record_short_summary_includes_source_and_connector():
    rec = build_record(
        catalog_source="Gaia DR3", connector="gaia",
        connector_version="0.3.0",
    )
    s = rec.short_summary()
    assert "Gaia DR3" in s
    assert "gaia" in s


def test_record_short_summary_handles_empty():
    assert "no provenance" in ProvenanceRecord().short_summary()


def test_record_render_handles_empty():
    assert "(no provenance recorded)" in ProvenanceRecord().render()


def test_record_render_includes_known_limitations():
    rec = ProvenanceRecord(
        catalog_source="src",
        known_limitations=["caveat A", "caveat B"],
    )
    text = rec.render()
    assert "caveat A" in text
    assert "caveat B" in text


def test_record_render_flags_custom_coordinate_system():
    rec = ProvenanceRecord(
        catalog_source="x",
        coordinate_system="WeirdNonStandard",
    )
    assert "(custom)" in rec.render()


def test_record_rejects_newer_schema_version():
    payload = {"schema_version": 999, "catalog_source": "x"}
    with pytest.raises(ProvenanceError):
        ProvenanceRecord.from_dict(payload)


def test_record_handles_missing_optional_fields():
    rec = ProvenanceRecord.from_dict({"schema_version": 1})
    assert rec.catalog_source == ""
    assert rec.units == {}


def test_record_rejects_non_object_payload():
    with pytest.raises(ProvenanceError):
        ProvenanceRecord.from_dict([])  # type: ignore[arg-type]


def test_record_from_none_yields_empty():
    rec = ProvenanceRecord.from_dict(None)
    assert rec.is_empty()


def test_known_coordinate_systems_includes_icrs():
    assert "ICRS" in KNOWN_COORDINATE_SYSTEMS


# ---------------------------------------------------------------------------
# attach_provenance / read_provenance
# ---------------------------------------------------------------------------


def test_attach_and_read_round_trip():
    obj = _mk_obj()
    rec = build_record(catalog_source="Gaia", connector="gaia")
    attach_provenance(obj, rec)
    rt = read_provenance(obj)
    assert rt is not None
    assert rt.catalog_source == "Gaia"


def test_attach_preserves_existing_metadata():
    obj = _mk_obj(metadata=json.dumps({"epoch": 2461041.5, "extra": 7}))
    rec = build_record(catalog_source="Gaia", connector="gaia")
    attach_provenance(obj, rec)
    decoded = json.loads(obj.metadata_json)
    assert decoded.get("epoch") == 2461041.5
    assert decoded.get("extra") == 7
    assert PROVENANCE_METADATA_KEY in decoded


def test_attach_handles_invalid_existing_metadata():
    obj = _mk_obj(metadata="not json at all")
    rec = build_record(catalog_source="Gaia", connector="gaia")
    attach_provenance(obj, rec)
    decoded = json.loads(obj.metadata_json)
    assert PROVENANCE_METADATA_KEY in decoded


def test_read_returns_none_for_no_provenance():
    obj = _mk_obj()
    assert read_provenance(obj) is None


def test_read_returns_none_for_malformed_metadata():
    obj = _mk_obj(metadata="not json")
    assert read_provenance(obj) is None


def test_read_returns_none_for_non_dict_metadata():
    obj = _mk_obj(metadata="[1, 2, 3]")
    assert read_provenance(obj) is None


def test_read_handles_future_schema_gracefully():
    """Future schema_version → read_provenance returns
    None rather than crashing the inspector."""
    obj = _mk_obj(metadata=json.dumps({
        PROVENANCE_METADATA_KEY: {"schema_version": 999}
    }))
    assert read_provenance(obj) is None


# ---------------------------------------------------------------------------
# summarise_provenance
# ---------------------------------------------------------------------------


def test_summary_distinguishes_with_without_provenance():
    a = _mk_obj("a")
    attach_provenance(a, build_record(
        catalog_source="Gaia", connector="gaia",
    ))
    b = _mk_obj("b")  # no provenance
    summary = summarise_provenance([a, b])
    assert summary.rows_with_provenance == 1
    assert summary.rows_without_provenance == 1


def test_summary_aggregates_distinct_sources():
    a = _mk_obj("a")
    b = _mk_obj("b")
    attach_provenance(a, build_record(catalog_source="Gaia", connector="g"))
    attach_provenance(b, build_record(catalog_source="JPL", connector="j"))
    summary = summarise_provenance([a, b])
    assert summary.distinct_sources == ["Gaia", "JPL"]
    assert summary.distinct_connectors == ["g", "j"]


def test_summary_aggregates_known_limitations_dedup():
    a = _mk_obj("a")
    b = _mk_obj("b")
    attach_provenance(a, build_record(
        catalog_source="x", connector="y",
        known_limitations=["caveat1", "caveat2"],
    ))
    attach_provenance(b, build_record(
        catalog_source="x", connector="y",
        known_limitations=["caveat2", "caveat3"],
    ))
    summary = summarise_provenance([a, b])
    assert summary.aggregated_known_limitations == ["caveat1", "caveat2", "caveat3"]


def test_summary_render_when_empty():
    summary = ProvenanceSummary()
    assert summary.is_empty()
    text = summary.render()
    assert "0" in text


def test_summary_render_when_populated():
    a = _mk_obj("a")
    attach_provenance(a, build_record(
        catalog_source="Gaia", connector="gaia",
        coordinate_system="ICRS",
    ))
    summary = summarise_provenance([a])
    text = summary.render()
    assert "Gaia" in text
    assert "ICRS" in text


def test_summary_earliest_latest_stamps():
    a = _mk_obj("a")
    b = _mk_obj("b")
    rec_a = build_record(catalog_source="x", connector="y")
    rec_a.fetched_at_iso = "2026-01-01T00:00:00Z"
    rec_b = build_record(catalog_source="x", connector="y")
    rec_b.fetched_at_iso = "2026-05-10T00:00:00Z"
    attach_provenance(a, rec_a)
    attach_provenance(b, rec_b)
    summary = summarise_provenance([a, b])
    assert summary.earliest_fetched_iso == "2026-01-01T00:00:00Z"
    assert summary.latest_fetched_iso == "2026-05-10T00:00:00Z"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_provenance_schema_version_is_one():
    assert PROVENANCE_SCHEMA_VERSION == 1


def test_provenance_metadata_key_constant():
    assert PROVENANCE_METADATA_KEY == "provenance"
