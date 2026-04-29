"""Tests for core.metadata_lookup. Runs without Cinema 4D."""

from __future__ import annotations

import pytest

from core import metadata_lookup
from core.metadata_lookup import (
    MetadataLookup,
    default_lookup,
    set_default_lookup,
)
from data.schema import CatalogObject


def _obj(uid: str, source: str = "unav_sample") -> CatalogObject:
    return CatalogObject(
        uid=uid,
        catalog_source=source,
        object_type="star",
        ra_deg=10.0,
        dec_deg=-20.0,
    )


# ---------------------------------------------------------------------------
# MetadataLookup
# ---------------------------------------------------------------------------


def test_lookup_indexes_by_uid_and_supports_membership():
    lk = MetadataLookup([_obj("a"), _obj("b")])
    assert len(lk) == 2
    assert "a" in lk and "b" in lk and "c" not in lk
    assert lk.lookup("a").uid == "a"
    assert lk.lookup("missing") is None


def test_lookup_skips_objects_without_uid():
    bad = CatalogObject(
        uid="", catalog_source="x", object_type="star",
        ra_deg=0.0, dec_deg=0.0,
    )
    lk = MetadataLookup([bad, _obj("a")])
    assert len(lk) == 1
    assert "a" in lk


def test_lookup_add_returns_count_and_overwrites_duplicates():
    lk = MetadataLookup([_obj("a", "src1")])
    n = lk.add([_obj("a", "src2"), _obj("b")])
    assert n == 2
    assert lk.lookup("a").catalog_source == "src2"
    assert "b" in lk


def test_lookup_sources_is_sorted_and_deduplicated():
    lk = MetadataLookup([
        _obj("a", "gaia_dr3"),
        _obj("b", "sdss_dr18"),
        _obj("c", "gaia_dr3"),
    ])
    assert lk.sources() == ["gaia_dr3", "sdss_dr18"]


def test_lookup_empty_uid_returns_none():
    lk = MetadataLookup([_obj("a")])
    assert lk.lookup("") is None
    assert lk.lookup(None) is None  # type: ignore[arg-type]


def test_lookup_clear_resets_state():
    lk = MetadataLookup([_obj("a"), _obj("b", "other")])
    lk.clear()
    assert len(lk) == 0
    assert lk.sources() == []


def test_from_catalog_path_loads_bundled_sample():
    from data.catalog_io import default_sample_catalog_path

    lk = MetadataLookup.from_catalog_path(default_sample_catalog_path())
    assert len(lk) > 0
    assert any(uid.startswith("sample-") for uid in lk.uids())


# ---------------------------------------------------------------------------
# default_lookup
# ---------------------------------------------------------------------------


def test_default_lookup_lazy_loads_bundled_sample():
    set_default_lookup(None)  # force a fresh load
    lk = default_lookup()
    assert len(lk) == 100  # bundled sample size


def test_default_lookup_is_idempotent():
    set_default_lookup(None)
    a = default_lookup()
    b = default_lookup()
    assert a is b


def test_default_lookup_reload_replaces_singleton():
    set_default_lookup(None)
    a = default_lookup()
    b = default_lookup(reload=True)
    assert a is not b
    assert len(a) == len(b)


def test_default_lookup_returns_empty_when_sample_missing(monkeypatch):
    set_default_lookup(None)

    def fake_path():
        return "/path/that/does/not/exist.jsonl"

    monkeypatch.setattr(
        metadata_lookup, "default_sample_catalog_path", fake_path,
    )
    lk = default_lookup(reload=True)
    assert len(lk) == 0


def test_set_default_lookup_overrides_singleton():
    custom = MetadataLookup([_obj("custom-1")])
    set_default_lookup(custom)
    assert default_lookup() is custom
    set_default_lookup(None)  # cleanup
