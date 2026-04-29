"""Tests for data.catalog_io: JSONL/CSV roundtrips, validation summary,
error handling. Runs without Cinema 4D."""

from __future__ import annotations

import json
import os

import pytest

from data import catalog_io
from data.catalog_io import (
    CatalogIOError,
    load_catalog,
    validate_catalog,
    write_catalog,
)
from data.schema import CatalogObject


def _objs():
    return [
        CatalogObject(
            uid="a-001",
            catalog_source="unav_sample",
            object_type="star",
            ra_deg=10.0,
            dec_deg=-20.0,
            distance_parsec=10.0,
            apparent_magnitude=5.0,
            spectral_type="G2V",
            name="Alpha One",
            metadata_json=json.dumps({"k": "v"}),
        ),
        CatalogObject(
            uid="b-002",
            catalog_source="unav_sample",
            object_type="galaxy",
            ra_deg=180.0,
            dec_deg=45.0,
            distance_parsec=1.0e7,
            redshift=0.05,
            apparent_magnitude=18.0,
        ),
        CatalogObject(  # no distance: should land on placeholder sphere
            uid="c-003",
            catalog_source="unav_sample",
            object_type="quasar",
            ra_deg=300.0,
            dec_deg=-60.0,
        ),
    ]


# ---------------------------------------------------------------------------
# JSONL
# ---------------------------------------------------------------------------


def test_jsonl_roundtrip(tmp_path):
    path = str(tmp_path / "out.jsonl")
    n = write_catalog(_objs(), path)
    assert n == 3
    loaded = load_catalog(path)
    assert len(loaded) == 3
    by_uid = {o.uid: o for o in loaded}
    assert by_uid["a-001"].spectral_type == "G2V"
    assert by_uid["b-002"].redshift == 0.05
    # Computed fields should be present after roundtrip.
    assert by_uid["a-001"].cartesian_x is not None
    assert by_uid["a-001"].display_color_rgb is not None


def test_jsonl_skips_blank_lines(tmp_path):
    path = str(tmp_path / "out.jsonl")
    write_catalog(_objs()[:1], path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n\n")
    loaded = load_catalog(path)
    assert len(loaded) == 1


def test_jsonl_bad_row_skipped_by_default(tmp_path):
    path = str(tmp_path / "bad.jsonl")
    write_catalog(_objs()[:1], path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{not valid json}\n")
    loaded = load_catalog(path)
    assert len(loaded) == 1  # bad row dropped, good row kept


def test_jsonl_strict_raises_on_bad_row(tmp_path):
    path = str(tmp_path / "bad.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not valid json}\n")
    with pytest.raises(CatalogIOError):
        load_catalog(path, strict=True)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def test_csv_roundtrip(tmp_path):
    path = str(tmp_path / "out.csv")
    n = write_catalog(_objs(), path)
    assert n == 3
    loaded = load_catalog(path)
    assert len(loaded) == 3
    by_uid = {o.uid: o for o in loaded}
    a = by_uid["a-001"]
    assert a.ra_deg == 10.0
    assert a.dec_deg == -20.0
    assert a.spectral_type == "G2V"
    assert isinstance(a.display_color_rgb, tuple)
    assert len(a.display_color_rgb) == 3


def test_csv_optional_fields_decode_to_none(tmp_path):
    path = str(tmp_path / "out.csv")
    write_catalog(_objs(), path)
    loaded = load_catalog(path)
    c = next(o for o in loaded if o.uid == "c-003")
    # No explicit distance was provided; we *did* compute the placeholder
    # cartesian, so distance_parsec is still None on the original object
    # but the computed Cartesian should be populated.
    assert c.distance_parsec is None
    assert c.cartesian_x is not None


# ---------------------------------------------------------------------------
# Format dispatch
# ---------------------------------------------------------------------------


def test_unknown_extension_raises(tmp_path):
    path = str(tmp_path / "out.xyz")
    with pytest.raises(CatalogIOError):
        write_catalog(_objs(), path)


def test_reserved_format_says_not_implemented(tmp_path):
    path = str(tmp_path / "out.sqlite")
    with pytest.raises(CatalogIOError) as exc:
        write_catalog(_objs(), path, fmt="sqlite")
    assert "future" in str(exc.value) or "not implemented" in str(exc.value)


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(CatalogIOError):
        load_catalog(str(tmp_path / "does_not_exist.jsonl"))


def test_explicit_format_overrides_extension(tmp_path):
    path = str(tmp_path / "noext")
    write_catalog(_objs()[:1], path, fmt="jsonl")
    loaded = load_catalog(path, fmt="jsonl")
    assert len(loaded) == 1


# ---------------------------------------------------------------------------
# Validation summary
# ---------------------------------------------------------------------------


def test_validate_catalog_all_good():
    summary = validate_catalog(_objs())
    assert summary["total"] == 3
    assert summary["valid"] == 3
    assert summary["invalid"] == 0
    assert summary["issues"] == {}


def test_validate_catalog_reports_issues():
    objs = _objs()
    objs[0].ra_deg = 999.0  # out of range
    objs[1].object_type = "wormhole"  # unknown type
    summary = validate_catalog(objs)
    assert summary["total"] == 3
    assert summary["valid"] == 1
    assert summary["invalid"] == 2
    assert summary["issues"]
    assert any(s["uid"] == "a-001" for s in summary["samples"])


def test_validate_catalog_sample_limit_respected():
    # Generate 50 invalid objects and confirm the report caps samples.
    bad = []
    for i in range(50):
        bad.append(
            CatalogObject(
                uid=f"bad-{i}",
                catalog_source="x",
                object_type="star",
                ra_deg=999.0,  # invalid
                dec_deg=0.0,
            )
        )
    summary = validate_catalog(bad, sample_limit=5)
    assert len(summary["samples"]) == 5
    assert summary["invalid"] == 50
