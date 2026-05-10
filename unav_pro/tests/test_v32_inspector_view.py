"""v3.2 inspector provenance-view tests."""

from __future__ import annotations

import json

import pytest

from data import (
    CatalogObject,
    attach_provenance,
    build_record,
)
from knowledge.provenance_view import (
    InspectorProvenanceView,
    build_provenance_view,
)


def _row(uid: str = "u", **kw) -> CatalogObject:
    base = dict(
        uid=uid, catalog_source="Test",
        object_type="star", ra_deg=1.0, dec_deg=2.0,
    )
    base.update(kw)
    return CatalogObject(**base)


def test_view_for_clean_unprovenanced_row_is_empty():
    """A row with no provenance and no findings should
    produce an empty render so the inspector skips the
    section."""
    obj = _row()
    view = build_provenance_view(obj)
    assert view.has_provenance is False
    assert view.render() == ""


def test_view_with_provenance_shows_provenance_section():
    obj = _row()
    attach_provenance(obj, build_record(
        catalog_source="Gaia DR3", connector="gaia",
        connector_version="0.3.0",
        coordinate_system="ICRS",
    ))
    view = build_provenance_view(obj)
    text = view.render()
    assert "Provenance" in text
    assert "Gaia DR3" in text
    assert "ICRS" in text


def test_view_lists_validation_findings():
    obj = _row(parallax_mas=-1.0)
    view = build_provenance_view(obj)
    assert view.warning_count() >= 1
    text = view.render()
    assert "Data integrity findings" in text
    assert "WARN" in text


def test_view_shows_error_findings():
    obj = _row(redshift=-0.5)
    view = build_provenance_view(obj)
    assert view.error_count() >= 1
    text = view.render()
    assert "ERROR" in text


def test_view_skips_no_provenance_info_when_provenance_present():
    """If the row has provenance, we don't surface the
    'no provenance' info-level finding (the section
    already shows it)."""
    obj = _row()
    attach_provenance(obj, build_record(
        catalog_source="x", connector="y",
    ))
    view = build_provenance_view(obj)
    text = view.render()
    # 'no provenance' should not be emitted when it is.
    assert "no provenance" not in text.lower()


def test_view_render_skips_empty_sections():
    """Row with provenance but no integrity findings: the
    body should still render the provenance block but
    not a 'findings' header."""
    obj = _row()
    attach_provenance(obj, build_record(
        catalog_source="x", connector="y",
    ))
    view = build_provenance_view(obj)
    text = view.render()
    assert "Provenance" in text
    assert "findings" not in text.lower()


def test_view_with_unsupported_units_flagged():
    obj = _row()
    attach_provenance(obj, build_record(
        catalog_source="x", connector="y",
        units={"ra": "rad"},  # not deg
    ))
    view = build_provenance_view(obj)
    assert view.warning_count() >= 1


def test_view_handles_non_catalog_object():
    """The view layer is duck-typed — anything with the
    right attributes works. A bare dict-like object
    triggers 'missing coordinates'."""
    class Obj:
        uid = "x"
        metadata_json = "{}"
        catalog_source = "Test"
        object_type = "star"
        ra_deg = None
        dec_deg = None
    view = build_provenance_view(Obj())
    assert view.error_count() >= 2  # missing ra + missing dec
