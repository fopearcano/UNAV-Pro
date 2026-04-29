"""Tests for ui.metadata_panel pure formatters and the c4d guard."""

from __future__ import annotations

import json

from c4d_objects.point_cloud_builder import (
    MARKER_KEY_CATALOG_SOURCE,
    MARKER_KEY_DEC_DEG,
    MARKER_KEY_DISTANCE_PC,
    MARKER_KEY_IS_UNAV,
    MARKER_KEY_KIND,
    MARKER_KEY_METADATA_JSON,
    MARKER_KEY_NAME,
    MARKER_KEY_OBJECT_TYPE,
    MARKER_KEY_RA_DEG,
    MARKER_KEY_UID,
)
from core.metadata_lookup import MetadataLookup
from data.schema import CatalogObject
from ui import metadata_panel
from ui.metadata_panel import (
    InspectionResult,
    STATUS_FOUND_FULL,
    STATUS_FOUND_MARKER_ONLY,
    STATUS_NO_DOC,
    STATUS_NO_INSPECTION,
    STATUS_NO_SELECTION,
    STATUS_NOT_UNAV,
    empty_panel_text,
    inspect_active_selection,
    no_inspection_result,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _full_obj(uid: str = "demo:1", **overrides) -> CatalogObject:
    base = dict(
        uid=uid,
        catalog_source="unav_sample",
        object_type="star",
        ra_deg=10.123456,
        dec_deg=-20.654321,
        distance_parsec=42.5,
        parallax_mas=23.5,
        radial_velocity_kms=12.3,
        proper_motion_ra=1.5,
        proper_motion_dec=-2.3,
        apparent_magnitude=5.4,
        absolute_magnitude=2.1,
        color_index=0.65,
        spectral_type="G2V",
        name="Alpha One",
        common_name="Test Star",
        metadata_json=json.dumps({"synth": True, "kind": "star"}),
    )
    base.update(overrides)
    return CatalogObject(**base)


def _marker(uid: str = "demo:1", **kwargs) -> dict:
    base = {
        MARKER_KEY_IS_UNAV: True,
        MARKER_KEY_KIND: "point",
        MARKER_KEY_UID: uid,
        MARKER_KEY_CATALOG_SOURCE: "unav_sample",
        MARKER_KEY_OBJECT_TYPE: "star",
        MARKER_KEY_NAME: "Alpha One",
        MARKER_KEY_RA_DEG: 10.123456,
        MARKER_KEY_DEC_DEG: -20.654321,
        MARKER_KEY_DISTANCE_PC: 42.5,
        MARKER_KEY_METADATA_JSON: json.dumps({"synth": True}),
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# InspectionResult — display text
# ---------------------------------------------------------------------------


def test_no_doc_status_yields_clear_message():
    r = InspectionResult(status=STATUS_NO_DOC)
    text = r.display_text
    assert "No active document" in text
    assert "Inspect:" in r.status_line


def test_no_selection_status_prompts_user():
    r = InspectionResult(status=STATUS_NO_SELECTION)
    text = r.display_text
    assert "Nothing selected" in text
    assert "Object Manager" in text


def test_not_unav_status_names_the_object():
    r = InspectionResult(status=STATUS_NOT_UNAV, object_name="Cube")
    assert "Cube" in r.display_text
    assert "not a UNAV object" in r.display_text
    assert "Cube" in r.status_line


def test_found_full_renders_all_field_groups():
    obj = _full_obj()
    r = InspectionResult(
        status=STATUS_FOUND_FULL,
        object_name="Alpha One",
        marker=_marker(),
        catalog_object=obj,
    )
    text = r.display_text
    # Identity
    assert "UID            : demo:1" in text
    assert "Catalog source : unav_sample" in text
    assert "Object type    : star" in text
    assert "Common name    : Test Star" in text
    # Astrometry
    assert "RA  (deg)      : 10.123456" in text
    assert "Dec (deg)      : -20.654321" in text
    assert "Distance (pc)" in text
    assert "Parallax (mas)" in text
    assert "RV (km/s)" in text
    assert "PM (mas/yr)    : RA +1.500, Dec -2.300" in text
    # Photometry
    assert "Apparent mag" in text
    assert "Absolute mag" in text
    assert "Color index    : +0.650" in text
    assert "Spectral type  : G2V" in text
    # Raw JSON preview present
    assert "Raw metadata JSON" in text


def test_found_marker_only_falls_back_to_marker_data():
    r = InspectionResult(
        status=STATUS_FOUND_MARKER_ONLY,
        object_name="Alpha One",
        marker=_marker(),
    )
    text = r.display_text
    assert "marker only" in text or "marker data" in text
    # Identity from the marker
    assert "demo:1" in text
    assert "unav_sample" in text
    # Astrometry from the marker
    assert "10.123456" in text
    assert "-20.654321" in text
    assert "42.5" in text  # distance


def test_marker_distance_zero_treated_as_unknown():
    marker = _marker()
    marker[MARKER_KEY_DISTANCE_PC] = 0.0
    r = InspectionResult(
        status=STATUS_FOUND_MARKER_ONLY,
        object_name="Alpha",
        marker=marker,
    )
    # Zero distance is the marker's "no distance" sentinel — should
    # not appear as a 0.0 distance line.
    assert "Distance (pc)  : 0" not in r.display_text


def test_redshift_and_no_proper_motion_galaxy():
    galaxy = _full_obj(
        object_type="galaxy",
        spectral_type=None,
        parallax_mas=None,
        proper_motion_ra=None,
        proper_motion_dec=None,
        redshift=0.05,
    )
    r = InspectionResult(
        status=STATUS_FOUND_FULL,
        object_name="G",
        marker=_marker(),
        catalog_object=galaxy,
    )
    text = r.display_text
    assert "Redshift z     : 0.050000" in text
    assert "PM (mas/yr)" not in text
    assert "Parallax" not in text
    # Photometry section without spectral type still renders.
    assert "Apparent mag" in text


# ---------------------------------------------------------------------------
# Status line variants
# ---------------------------------------------------------------------------


def test_status_line_full_record():
    r = InspectionResult(
        status=STATUS_FOUND_FULL,
        object_name="Alpha One",
        marker=_marker(uid="gaia_dr3:42"),
        catalog_object=_full_obj("gaia_dr3:42"),
    )
    line = r.status_line
    assert "Alpha One" in line
    assert "gaia_dr3:42" in line
    assert "full record" in line


def test_status_line_marker_only_calls_out_miss():
    r = InspectionResult(
        status=STATUS_FOUND_MARKER_ONLY,
        object_name="Alpha One",
        marker=_marker(uid="x:1"),
    )
    line = r.status_line
    assert "x:1" in line
    assert "marker only" in line


def test_status_line_no_inspection():
    r = no_inspection_result()
    assert r.status == STATUS_NO_INSPECTION
    assert "click Inspect first" in r.status_line


# ---------------------------------------------------------------------------
# Clipboard JSON
# ---------------------------------------------------------------------------


def test_clipboard_json_full_object_includes_parsed_metadata():
    r = InspectionResult(
        status=STATUS_FOUND_FULL,
        object_name="Alpha",
        catalog_object=_full_obj(),
    )
    payload = r.clipboard_json
    decoded = json.loads(payload)
    assert decoded["uid"] == "demo:1"
    assert decoded["catalog_source"] == "unav_sample"
    assert decoded["spectral_type"] == "G2V"
    # Parsed metadata blob is exposed for convenience.
    assert decoded["metadata_json_parsed"]["synth"] is True


def test_clipboard_json_marker_only_uses_named_keys():
    r = InspectionResult(
        status=STATUS_FOUND_MARKER_ONLY,
        object_name="Alpha",
        marker=_marker(),
    )
    payload = r.clipboard_json
    decoded = json.loads(payload)
    # Numeric marker keys are translated to readable names.
    assert decoded["uid"] == "demo:1"
    assert decoded["catalog_source"] == "unav_sample"
    assert decoded["object_type"] == "star"
    # Parsed metadata blob present.
    assert decoded["metadata_json_parsed"]["synth"] is True


def test_clipboard_json_empty_when_no_data():
    r = InspectionResult(status=STATUS_NO_SELECTION)
    assert r.clipboard_json == "{}"


def test_clipboard_json_handles_corrupt_metadata_blob():
    obj = _full_obj()
    obj.metadata_json = "{not valid json"
    r = InspectionResult(
        status=STATUS_FOUND_FULL,
        catalog_object=obj,
    )
    decoded = json.loads(r.clipboard_json)
    assert decoded["uid"] == "demo:1"
    # No parsed entry when the blob is unparseable.
    assert "metadata_json_parsed" not in decoded


# ---------------------------------------------------------------------------
# C4D guard
# ---------------------------------------------------------------------------


def test_inspect_active_selection_outside_c4d_returns_no_doc():
    # Without the c4d host, the function must return cleanly with the
    # NO_DOC status, not raise.
    result = inspect_active_selection()
    assert result.status == STATUS_NO_DOC


def test_copy_to_clipboard_outside_c4d_returns_false():
    assert metadata_panel.copy_to_clipboard("hello") is False


def test_empty_panel_text_is_user_friendly():
    text = empty_panel_text()
    assert "Inspect" in text
    assert "UNAV" in text


# ---------------------------------------------------------------------------
# Truncation of large JSON previews
# ---------------------------------------------------------------------------


def test_display_text_truncates_long_metadata_json():
    huge_blob = "x" * 10_000
    obj = _full_obj()
    obj.metadata_json = json.dumps({"big": huge_blob})
    r = InspectionResult(
        status=STATUS_FOUND_FULL,
        object_name="Big",
        catalog_object=obj,
    )
    text = r.display_text
    assert "truncated" in text
    # Even though the inline preview is truncated, the clipboard copy
    # remains full-fidelity.
    assert len(r.clipboard_json) > len(text.split("--- Raw metadata JSON ---")[1])
