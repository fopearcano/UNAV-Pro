"""v3.2 export-package integration tests.

Verify the export package's manifest gains the four
self-describing fields (``provenance_summary``,
``audit_summary``, ``coordinate_conventions``,
``known_limitations``) and that they round-trip
through the build → read pipeline.
"""

from __future__ import annotations

import json
import os

import pytest

from data import (
    CatalogObject,
    attach_provenance, build_record,
    summarise_provenance,
    validate_objects,
)
from export.export_package import (
    PackageManifest,
    PackagePayload,
    build_export_package,
    read_export_package,
)


def _row(uid: str = "u") -> CatalogObject:
    return CatalogObject(
        uid=uid, catalog_source="Test",
        object_type="star", ra_deg=1.0, dec_deg=2.0,
    )


# ---------------------------------------------------------------------------
# Manifest round-trip
# ---------------------------------------------------------------------------


def test_manifest_round_trip_with_v32_fields():
    m = PackageManifest(
        plugin_version="3.2.0",
        coordinate_conventions="ICRS Cartesian parsec",
        known_limitations=[
            "redshift→distance proxy", "no extinction applied",
        ],
        provenance_summary={
            "distinct_sources": ["Gaia DR3"],
            "rows_with_provenance": 5,
        },
        audit_summary={
            "rows_total": 5,
            "total_issues": 0,
        },
    )
    rt = PackageManifest.from_dict(m.to_dict())
    assert rt.coordinate_conventions == "ICRS Cartesian parsec"
    assert rt.known_limitations == [
        "redshift→distance proxy", "no extinction applied",
    ]
    assert rt.provenance_summary == {
        "distinct_sources": ["Gaia DR3"], "rows_with_provenance": 5,
    }
    assert rt.audit_summary == {"rows_total": 5, "total_issues": 0}


def test_manifest_skips_unset_fields_in_to_dict():
    m = PackageManifest(plugin_version="3.2.0")
    d = m.to_dict()
    assert "provenance_summary" not in d
    assert "audit_summary" not in d
    assert "known_limitations" not in d
    assert "coordinate_conventions" not in d


def test_manifest_handles_legacy_dict_without_v32_fields():
    """Loading a v2.3 / v3.1 manifest must not raise."""
    legacy = {
        "manifest_version": 1,
        "exported_at_iso": "2026-05-10T00:00:00Z",
        "plugin_version": "3.1.0",
        "coordinate_convention": "C4D world units, Y-up",
        "units": {},
        "package_name": "unav_export",
        "notes": "",
        "active_datasets": [],
        "included_assets": {},
    }
    m = PackageManifest.from_dict(legacy)
    assert m.provenance_summary is None
    assert m.audit_summary is None
    assert m.known_limitations == []


def test_manifest_rejects_non_dict_provenance():
    """Defensive: a malformed manifest payload with a
    non-dict ``provenance_summary`` becomes ``None`` rather
    than crashing the loader."""
    payload = {
        "manifest_version": 1,
        "exported_at_iso": "now",
        "plugin_version": "3.2.0",
        "coordinate_convention": "x",
        "units": {},
        "provenance_summary": "not a dict",
    }
    m = PackageManifest.from_dict(payload)
    assert m.provenance_summary is None


# ---------------------------------------------------------------------------
# End-to-end build with provenance + audit summary
# ---------------------------------------------------------------------------


def test_build_export_package_writes_manifest_with_v32_fields(tmp_path):
    rows = [_row(f"u{i}") for i in range(3)]
    rec = build_record(
        catalog_source="Test", connector="test_connector",
        connector_version="1.0",
        coordinate_system="ICRS",
        units={"ra": "deg", "dec": "deg"},
        known_limitations=["sample dataset only"],
    )
    for r in rows:
        attach_provenance(r, rec)

    audit = validate_objects(
        rows, include_no_provenance_probe=False,
    )
    summary = summarise_provenance(rows)

    manifest = PackageManifest(
        plugin_version="3.2.0",
        coordinate_conventions="ICRS Cartesian parsec",
        known_limitations=summary.aggregated_known_limitations,
        provenance_summary=summary.to_dict(),
        audit_summary=audit.export_summary(),
    )
    payload = PackagePayload(
        missions={"demo.json": json.dumps({"title": "demo"})},
    )
    report = build_export_package(
        str(tmp_path / "pkg"), payload, manifest=manifest,
    )
    assert report.success is True
    # Manifest exists and round-trips with the v3.2 fields.
    rt = read_export_package(str(tmp_path / "pkg"))
    assert rt is not None
    assert rt.coordinate_conventions == "ICRS Cartesian parsec"
    assert "sample dataset only" in rt.known_limitations
    assert rt.provenance_summary["distinct_sources"] == ["Test"]
    assert rt.audit_summary["rows_total"] == 3


def test_provenance_and_audit_survive_disk_round_trip(tmp_path):
    """Read the manifest.json from disk directly to make
    sure the JSON shape is what we documented."""
    rows = [_row("a"), _row("b")]
    for r in rows:
        attach_provenance(r, build_record(
            catalog_source="Source", connector="c", connector_version="1.0",
            coordinate_system="ICRS",
        ))
    audit = validate_objects(rows, include_no_provenance_probe=False)
    summary = summarise_provenance(rows)
    manifest = PackageManifest(
        plugin_version="3.2.0",
        provenance_summary=summary.to_dict(),
        audit_summary=audit.export_summary(),
        known_limitations=["caveat"],
        coordinate_conventions="ICRS pc",
    )
    payload = PackagePayload(
        missions={"x.json": json.dumps({"a": 1})},
    )
    out_dir = str(tmp_path / "p")
    report = build_export_package(out_dir, payload, manifest=manifest)
    assert report.success
    with open(os.path.join(out_dir, "manifest.json"), encoding="utf-8") as fh:
        decoded = json.loads(fh.read())
    # The on-disk JSON shape matches what tests assert.
    assert decoded["coordinate_conventions"] == "ICRS pc"
    assert decoded["known_limitations"] == ["caveat"]
    assert decoded["provenance_summary"]["distinct_sources"] == ["Source"]
    assert decoded["audit_summary"]["rows_total"] == 2
