"""Tests for core.search (v0.6 search system)."""

from __future__ import annotations

import pytest

from core.metadata_lookup import MetadataLookup
from core.search import (
    DEFAULT_MAX_RESULTS,
    HARD_MAX_RESULTS,
    SearchQuery,
    SearchResult,
    render_results,
    search_lookup,
    search_objects,
)
from data.schema import CatalogObject


def _obj(uid, **kw) -> CatalogObject:
    base = dict(
        uid=uid, catalog_source="Gaia DR3", object_type="star",
        ra_deg=10.0, dec_deg=20.0,
    )
    base.update(kw)
    return CatalogObject(**base)


# ---------------------------------------------------------------------------
# SearchQuery validation
# ---------------------------------------------------------------------------


def test_query_rejects_zero_or_negative_max_results():
    with pytest.raises(ValueError):
        SearchQuery(text="x", max_results=0)
    with pytest.raises(ValueError):
        SearchQuery(text="x", max_results=-1)


def test_query_clamps_max_results_to_hard_ceiling():
    q = SearchQuery(text="x", max_results=10_000)
    assert q.max_results == HARD_MAX_RESULTS


def test_query_tokens_lowercase_and_strip_whitespace():
    q = SearchQuery(text="  Sirius  GAIA  ")
    assert q.tokens == ["sirius", "gaia"]


def test_query_empty_text_yields_empty_tokens():
    assert SearchQuery(text="").tokens == []
    assert SearchQuery(text="   ").tokens == []


# ---------------------------------------------------------------------------
# search_objects core matching
# ---------------------------------------------------------------------------


def test_match_on_name_substring_case_insensitive():
    objs = [
        _obj("gaia:1", name="Sirius A"),
        _obj("gaia:2", name="Vega"),
    ]
    results = search_objects(objs, SearchQuery(text="sirius"))
    assert [r.uid for r in results] == ["gaia:1"]


def test_match_on_uid():
    objs = [
        _obj("gaia:12345", name="Foo"),
        _obj("gaia:99999", name="Bar"),
    ]
    results = search_objects(objs, SearchQuery(text="123"))
    assert [r.uid for r in results] == ["gaia:12345"]


def test_match_on_catalog_source():
    objs = [
        _obj("gaia:1", catalog_source="SDSS"),
        _obj("gaia:2", catalog_source="DESI"),
        _obj("gaia:3", catalog_source="Gaia DR3"),
    ]
    results = search_objects(objs, SearchQuery(text="sdss"))
    assert [r.uid for r in results] == ["gaia:1"]


def test_match_on_object_type():
    objs = [
        _obj("a", object_type="star"),
        _obj("b", object_type="galaxy"),
        _obj("c", object_type="quasar"),
    ]
    results = search_objects(objs, SearchQuery(text="quasar"))
    assert [r.uid for r in results] == ["c"]


def test_match_on_common_name():
    objs = [
        _obj("gaia:1", name="HIP 32349", common_name="Sirius"),
        _obj("gaia:2", name="other"),
    ]
    results = search_objects(objs, SearchQuery(text="sirius"))
    assert [r.uid for r in results] == ["gaia:1"]


def test_token_AND_semantics():
    """All tokens must hit at least one field."""
    objs = [
        _obj("starA", name="Sirius A", catalog_source="Gaia DR3"),
        _obj("starB", name="Sirius B", catalog_source="Hipparcos"),
        _obj("starV", name="Vega", catalog_source="Gaia DR3"),
    ]
    # Both "sirius" and "gaia" must appear → only the Gaia Sirius.
    results = search_objects(objs, SearchQuery(text="sirius gaia"))
    assert [r.uid for r in results] == ["starA"]


def test_no_matches_returns_empty():
    objs = [_obj("gaia:1", name="Sirius")]
    assert search_objects(objs, SearchQuery(text="totallyabsent")) == []


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_catalog_source_filter_excludes_other_sources():
    objs = [
        _obj("gaia:1", name="X", catalog_source="Gaia DR3"),
        _obj("sdss:1", name="X", catalog_source="SDSS"),
    ]
    q = SearchQuery(text="x", catalog_source_filter="SDSS")
    assert [r.uid for r in search_objects(objs, q)] == ["sdss:1"]


def test_object_type_filter_excludes_other_types():
    objs = [
        _obj("a", name="X", object_type="star"),
        _obj("b", name="X", object_type="galaxy"),
    ]
    q = SearchQuery(text="x", object_type_filter="galaxy")
    assert [r.uid for r in search_objects(objs, q)] == ["b"]


def test_filters_with_empty_text_lists_everything_passing_filters():
    objs = [
        _obj("a", catalog_source="DESI"),
        _obj("b", catalog_source="DESI"),
        _obj("c", catalog_source="Gaia DR3"),
    ]
    q = SearchQuery(text="", catalog_source_filter="DESI")
    results = search_objects(objs, q)
    assert {r.uid for r in results} == {"a", "b"}


# ---------------------------------------------------------------------------
# Result limit + ordering
# ---------------------------------------------------------------------------


def test_max_results_caps_output():
    objs = [_obj(f"id:{i}", name=f"thing{i}") for i in range(20)]
    q = SearchQuery(text="thing", max_results=5)
    assert len(search_objects(objs, q)) == 5


def test_exact_match_outranks_substring_match():
    objs = [
        _obj("a", name="Mars-Rover-1"),  # substring
        _obj("b", name="Mars"),          # exact equal
    ]
    results = search_objects(objs, SearchQuery(text="mars"))
    assert results[0].uid == "b"


def test_starts_with_outranks_substring():
    objs = [
        _obj("a", name="Voyager 2"),       # starts-with for "voyager"
        _obj("b", name="My-Voyager-Plan"), # contained substring
    ]
    results = search_objects(objs, SearchQuery(text="voyager"))
    assert results[0].uid == "a"


def test_results_are_lightweight_no_metadata_blob():
    """Result rows do NOT carry the source CatalogObject."""
    objs = [_obj("a", name="x", metadata_json='{"big": "blob"}')]
    r = search_objects(objs, SearchQuery(text="x"))[0]
    assert isinstance(r, SearchResult)
    # Result should have no field that holds the parsed metadata.
    assert not hasattr(r, "metadata_json")
    assert r.uid == "a"


def test_results_record_match_field():
    objs = [
        _obj("a", name="Sirius"),
        _obj("b", catalog_source="Sirius Cluster"),
    ]
    r = search_objects(objs, SearchQuery(text="sirius"))
    by_uid = {x.uid: x for x in r}
    assert by_uid["a"].match_field == "name"
    assert by_uid["b"].match_field == "catalog_source"


# ---------------------------------------------------------------------------
# search_lookup convenience
# ---------------------------------------------------------------------------


def test_search_lookup_works_against_metadata_lookup():
    objs = [
        _obj("gaia:1", name="Sirius"),
        _obj("gaia:2", name="Vega"),
    ]
    lookup = MetadataLookup(objs)
    results = search_lookup(lookup, SearchQuery(text="sirius"))
    assert [r.uid for r in results] == ["gaia:1"]


def test_search_lookup_handles_none():
    assert search_lookup(None, SearchQuery(text="x")) == []


# ---------------------------------------------------------------------------
# render_results
# ---------------------------------------------------------------------------


def test_render_empty_results_with_query_says_no_matches():
    out = render_results([], SearchQuery(text="zzz"))
    assert "No matches" in out


def test_render_empty_results_no_query_says_type_to_search():
    out = render_results([])
    assert "Type a name" in out or "Search" in out


def test_render_results_lists_each_match():
    objs = [
        _obj("gaia:1", name="Sirius"),
        _obj("gaia:2", name="Vega"),
    ]
    results = search_objects(objs, SearchQuery(text="ir"))
    out = render_results(results, SearchQuery(text="ir"))
    assert "match(es)" in out
    assert "Sirius" in out
