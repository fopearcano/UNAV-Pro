"""v3.2 validation-report tests."""

from __future__ import annotations

import json

import pytest

from data import (
    CatalogObject,
    ALL_CODES,
    CODE_DUPLICATE_UID,
    CODE_INVALID_PARALLAX,
    CODE_INVALID_REDSHIFT,
    CODE_MALFORMED_METADATA,
    CODE_MISSING_COORDINATES,
    CODE_MISSING_EPOCH,
    CODE_NO_PROVENANCE,
    CODE_SUSPICIOUS_DISTANCE,
    CODE_UNSUPPORTED_UNITS,
    KNOWN_UNITS,
    SEVERITY_ERROR,
    SEVERITY_WARN,
    ValidationCounts,
    ValidationIssue,
    ValidationReport,
    attach_provenance,
    build_record,
    validate_objects,
)


def _obj(uid="u", *, metadata="{}", **kw) -> CatalogObject:
    base = dict(
        uid=uid, catalog_source="Test",
        object_type="star", ra_deg=0.0, dec_deg=0.0,
        metadata_json=metadata,
    )
    base.update(kw)
    return CatalogObject(**base)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_all_codes_listed():
    expected = {
        CODE_MISSING_COORDINATES, CODE_INVALID_PARALLAX,
        CODE_MISSING_EPOCH, CODE_INVALID_REDSHIFT,
        CODE_DUPLICATE_UID, CODE_MALFORMED_METADATA,
        CODE_SUSPICIOUS_DISTANCE, CODE_UNSUPPORTED_UNITS,
        CODE_NO_PROVENANCE,
    }
    assert expected.issubset(ALL_CODES)


def test_known_units_includes_canonical_categories():
    for k in ("ra", "dec", "parallax", "distance", "magnitude"):
        assert k in KNOWN_UNITS


# ---------------------------------------------------------------------------
# Missing coordinates
# ---------------------------------------------------------------------------


def test_missing_ra_flagged_as_error():
    o = _obj()
    o.ra_deg = float("nan")  # type: ignore[assignment]
    rep = validate_objects([o], include_no_provenance_probe=False)
    codes = [i.code for i in rep.issues]
    assert CODE_MISSING_COORDINATES in codes


def test_valid_coordinates_pass():
    o = _obj(ra_deg=10.0, dec_deg=20.0)
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_MISSING_COORDINATES not in [i.code for i in rep.issues]


# ---------------------------------------------------------------------------
# Invalid parallax
# ---------------------------------------------------------------------------


def test_negative_parallax_flagged():
    o = _obj(parallax_mas=-1.0)
    rep = validate_objects([o], include_no_provenance_probe=False)
    codes = [i.code for i in rep.issues]
    assert CODE_INVALID_PARALLAX in codes


def test_zero_parallax_flagged():
    o = _obj(parallax_mas=0.0)
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_INVALID_PARALLAX in [i.code for i in rep.issues]


def test_huge_parallax_flagged():
    o = _obj(parallax_mas=20_000.0)
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_INVALID_PARALLAX in [i.code for i in rep.issues]


def test_normal_parallax_passes():
    o = _obj(parallax_mas=10.0)
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_INVALID_PARALLAX not in [i.code for i in rep.issues]


def test_no_parallax_skips_check():
    o = _obj()
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_INVALID_PARALLAX not in [i.code for i in rep.issues]


# ---------------------------------------------------------------------------
# Missing epoch
# ---------------------------------------------------------------------------


def test_pm_without_epoch_flagged():
    o = _obj(proper_motion_ra=12.5, proper_motion_dec=3.4)
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_MISSING_EPOCH in [i.code for i in rep.issues]


def test_pm_with_epoch_passes():
    o = _obj(
        proper_motion_ra=12.5, proper_motion_dec=3.4,
        metadata=json.dumps({"epoch": "2016-01-01"}),
    )
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_MISSING_EPOCH not in [i.code for i in rep.issues]


def test_pm_with_epoch_jd_passes():
    o = _obj(
        proper_motion_ra=12.5,
        metadata=json.dumps({"epoch_jd": 2461041.5}),
    )
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_MISSING_EPOCH not in [i.code for i in rep.issues]


def test_no_pm_no_epoch_check():
    o = _obj()
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_MISSING_EPOCH not in [i.code for i in rep.issues]


# ---------------------------------------------------------------------------
# Invalid redshift
# ---------------------------------------------------------------------------


def test_negative_redshift_is_error():
    o = _obj(redshift=-0.5)
    rep = validate_objects([o], include_no_provenance_probe=False)
    issues = [i for i in rep.issues if i.code == CODE_INVALID_REDSHIFT]
    assert any(i.severity == SEVERITY_ERROR for i in issues)


def test_huge_redshift_is_warn():
    o = _obj(redshift=42.0)
    rep = validate_objects([o], include_no_provenance_probe=False)
    issues = [i for i in rep.issues if i.code == CODE_INVALID_REDSHIFT]
    assert any(i.severity == SEVERITY_WARN for i in issues)


def test_normal_redshift_passes():
    o = _obj(redshift=0.5)
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_INVALID_REDSHIFT not in [i.code for i in rep.issues]


def test_blueshift_local_passes():
    o = _obj()
    o.redshift = 0.0
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_INVALID_REDSHIFT not in [i.code for i in rep.issues]


# ---------------------------------------------------------------------------
# Duplicate UID
# ---------------------------------------------------------------------------


def test_duplicate_uid_flagged():
    a = _obj(uid="x")
    b = _obj(uid="x")
    rep = validate_objects([a, b], include_no_provenance_probe=False)
    assert CODE_DUPLICATE_UID in [i.code for i in rep.issues]


def test_unique_uids_pass():
    a = _obj(uid="x")
    b = _obj(uid="y")
    rep = validate_objects([a, b], include_no_provenance_probe=False)
    assert CODE_DUPLICATE_UID not in [i.code for i in rep.issues]


def test_three_duplicates_yield_two_issues():
    """Each duplicate (occurrence #2 onward) gets its own
    issue so the report tells the artist how many copies
    of the row exist."""
    rep = validate_objects(
        [_obj(uid="x"), _obj(uid="x"), _obj(uid="x")],
        include_no_provenance_probe=False,
    )
    dup_issues = [i for i in rep.issues if i.code == CODE_DUPLICATE_UID]
    assert len(dup_issues) == 2


# ---------------------------------------------------------------------------
# Malformed metadata
# ---------------------------------------------------------------------------


def test_garbage_metadata_flagged_as_error():
    o = _obj(metadata="not valid json")
    rep = validate_objects([o], include_no_provenance_probe=False)
    issues = [i for i in rep.issues if i.code == CODE_MALFORMED_METADATA]
    assert any(i.severity == SEVERITY_ERROR for i in issues)


def test_array_metadata_flagged_as_warn():
    o = _obj(metadata="[1, 2, 3]")
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_MALFORMED_METADATA in [i.code for i in rep.issues]


def test_empty_metadata_passes():
    o = _obj(metadata="{}")
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_MALFORMED_METADATA not in [i.code for i in rep.issues]


# ---------------------------------------------------------------------------
# Suspicious distance
# ---------------------------------------------------------------------------


def test_negative_distance_is_error():
    o = _obj(distance_parsec=-5.0)
    rep = validate_objects([o], include_no_provenance_probe=False)
    issues = [i for i in rep.issues if i.code == CODE_SUSPICIOUS_DISTANCE]
    assert any(i.severity == SEVERITY_ERROR for i in issues)


def test_huge_distance_is_warn():
    o = _obj(distance_parsec=1.0e12)
    rep = validate_objects([o], include_no_provenance_probe=False)
    issues = [i for i in rep.issues if i.code == CODE_SUSPICIOUS_DISTANCE]
    assert any(i.severity == SEVERITY_WARN for i in issues)


def test_normal_distance_passes():
    o = _obj(distance_parsec=100.0)
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_SUSPICIOUS_DISTANCE not in [i.code for i in rep.issues]


# ---------------------------------------------------------------------------
# Unsupported units
# ---------------------------------------------------------------------------


def test_unknown_unit_for_known_category_flagged():
    o = _obj()
    attach_provenance(o, build_record(
        catalog_source="x", connector="y",
        units={"ra": "radians"},  # not deg
    ))
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_UNSUPPORTED_UNITS in [i.code for i in rep.issues]


def test_known_unit_passes():
    o = _obj()
    attach_provenance(o, build_record(
        catalog_source="x", connector="y",
        units={"ra": "deg", "parallax": "mas"},
    ))
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_UNSUPPORTED_UNITS not in [i.code for i in rep.issues]


def test_unknown_category_does_not_flag():
    """Unknown units category is treated as opaque — only
    *known* categories with *unknown* units get flagged."""
    o = _obj()
    attach_provenance(o, build_record(
        catalog_source="x", connector="y",
        units={"weird_field": "thingies"},
    ))
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_UNSUPPORTED_UNITS not in [i.code for i in rep.issues]


# ---------------------------------------------------------------------------
# No-provenance probe
# ---------------------------------------------------------------------------


def test_no_provenance_emits_info_when_enabled():
    o = _obj()
    rep = validate_objects([o], include_no_provenance_probe=True)
    assert CODE_NO_PROVENANCE in [i.code for i in rep.issues]


def test_no_provenance_skipped_when_disabled():
    o = _obj()
    rep = validate_objects([o], include_no_provenance_probe=False)
    assert CODE_NO_PROVENANCE not in [i.code for i in rep.issues]


def test_with_provenance_skips_no_provenance_issue():
    o = _obj()
    attach_provenance(o, build_record(catalog_source="x", connector="y"))
    rep = validate_objects([o], include_no_provenance_probe=True)
    assert CODE_NO_PROVENANCE not in [i.code for i in rep.issues]


# ---------------------------------------------------------------------------
# Report shape
# ---------------------------------------------------------------------------


def test_clean_report_short_summary():
    rep = validate_objects(
        [_obj(uid="a"), _obj(uid="b")],
        include_no_provenance_probe=False,
    )
    assert "ok" in rep.short_summary().lower()


def test_dirty_report_short_summary():
    rep = validate_objects(
        [_obj(uid="a", parallax_mas=-1.0)],
        include_no_provenance_probe=False,
    )
    assert "issue" in rep.short_summary().lower()


def test_counts_track_total():
    rep = validate_objects(
        [_obj(uid="a"), _obj(uid="b")],
        include_no_provenance_probe=False,
    )
    assert rep.counts.rows_total == 2


def test_render_markdown_includes_header():
    rep = validate_objects(
        [_obj(uid="a")],
        include_no_provenance_probe=False,
    )
    md = rep.render_markdown()
    assert "UNAV Pro" in md
    assert "Counts" in md


def test_render_markdown_groups_issues_by_code():
    rep = validate_objects(
        [_obj(uid="a", parallax_mas=-1.0),
         _obj(uid="b", redshift=-1.0)],
        include_no_provenance_probe=False,
    )
    md = rep.render_markdown()
    assert "invalid_parallax" in md
    assert "invalid_redshift" in md


def test_export_summary_is_compact():
    rep = validate_objects(
        [_obj(uid="a", parallax_mas=-1.0)],
        include_no_provenance_probe=False,
    )
    summary = rep.export_summary()
    assert "rows_total" in summary
    assert "by_code" in summary
    # No full issue list inside.
    assert "issues" not in summary


def test_to_json_round_trip():
    rep = validate_objects(
        [_obj(uid="a", parallax_mas=-1.0)],
        include_no_provenance_probe=False,
    )
    decoded = json.loads(rep.to_json())
    assert "counts" in decoded
    assert "issues" in decoded


def test_provenance_summary_attached_when_enabled():
    o = _obj()
    attach_provenance(o, build_record(catalog_source="x", connector="y"))
    rep = validate_objects(
        [o],
        include_no_provenance_probe=False,
        include_provenance_summary=True,
    )
    assert rep.provenance is not None


def test_provenance_summary_omitted_when_disabled():
    rep = validate_objects(
        [_obj()],
        include_no_provenance_probe=False,
        include_provenance_summary=False,
    )
    assert rep.provenance is None
