"""v3.7 advanced-query engine tests."""

from __future__ import annotations

import pytest

from data import CatalogObject
from query import (
    AdvancedQuery,
    DEFAULT_MAX_RESULTS,
    QUERY_KINDS,
    QueryKind,
    QueryReport,
    QueryResult,
    SortOrder,
    SORT_ORDERS,
    run_query,
)


def _row(uid, **kw):
    base = dict(
        uid=uid, catalog_source="Test",
        object_type="star", ra_deg=0.0, dec_deg=0.0,
    )
    base.update(kw)
    return CatalogObject(**base)


# ---------------------------------------------------------------------------
# Constants + enum coverage
# ---------------------------------------------------------------------------


def test_query_kinds_complete():
    expected = {
        QueryKind.NEAREST, QueryKind.BRIGHTEST,
        QueryKind.HIGHEST_REDSHIFT,
        QueryKind.DISTANCE_RANGE, QueryKind.MAGNITUDE_RANGE,
        QueryKind.REDSHIFT_RANGE,
        QueryKind.BY_SOURCE, QueryKind.BY_TYPE,
        QueryKind.WITHIN_VISIBLE_SECTOR,
        QueryKind.NEAR_SELECTED, QueryKind.NEAR_ROUTE,
    }
    assert expected == set(QUERY_KINDS)


def test_sort_orders_complete():
    expected = {
        SortOrder.NONE, SortOrder.DISTANCE_ASC,
        SortOrder.MAGNITUDE_ASC, SortOrder.REDSHIFT_DESC,
        SortOrder.UID_ASC,
    }
    assert expected == set(SORT_ORDERS)


def test_default_max_results_reasonable():
    assert 50 <= DEFAULT_MAX_RESULTS <= 1000


# ---------------------------------------------------------------------------
# Effective sort order
# ---------------------------------------------------------------------------


def test_effective_sort_order_nearest_default():
    q = AdvancedQuery(kind=QueryKind.NEAREST)
    assert q.effective_sort_order() is SortOrder.DISTANCE_ASC


def test_effective_sort_order_brightest_default():
    q = AdvancedQuery(kind=QueryKind.BRIGHTEST)
    assert q.effective_sort_order() is SortOrder.MAGNITUDE_ASC


def test_effective_sort_order_redshift_default():
    q = AdvancedQuery(kind=QueryKind.HIGHEST_REDSHIFT)
    assert q.effective_sort_order() is SortOrder.REDSHIFT_DESC


def test_effective_sort_order_explicit_override():
    q = AdvancedQuery(
        kind=QueryKind.NEAREST,
        sort_order=SortOrder.UID_ASC,
    )
    assert q.effective_sort_order() is SortOrder.UID_ASC


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_run_query_rejects_zero_max():
    q = AdvancedQuery(kind=QueryKind.NEAREST, max_results=0)
    with pytest.raises(ValueError):
        run_query(q, [])


# ---------------------------------------------------------------------------
# Nearest
# ---------------------------------------------------------------------------


def test_nearest_orders_by_distance():
    rows = [
        _row("a", cartesian_x=10, cartesian_y=0, cartesian_z=0),
        _row("b", cartesian_x=1, cartesian_y=0, cartesian_z=0),
        _row("c", cartesian_x=5, cartesian_y=0, cartesian_z=0),
    ]
    q = AdvancedQuery(
        kind=QueryKind.NEAREST,
        reference_point_pc=(0, 0, 0),
        max_results=10,
    )
    rep = run_query(q, rows)
    uids = [r.uid for r in rep.results]
    assert uids == ["b", "c", "a"]


def test_nearest_caps_results():
    rows = [
        _row(f"u{i}", cartesian_x=i, cartesian_y=0, cartesian_z=0)
        for i in range(20)
    ]
    q = AdvancedQuery(
        kind=QueryKind.NEAREST,
        reference_point_pc=(0, 0, 0),
        max_results=5,
    )
    rep = run_query(q, rows)
    assert rep.returned == 5
    assert rep.matched_before_cap == 20


def test_nearest_warns_without_reference():
    rows = [_row("a"), _row("b")]
    q = AdvancedQuery(kind=QueryKind.NEAREST, max_results=10)
    rep = run_query(q, rows)
    assert rep.warnings  # surface "no reference point"


# ---------------------------------------------------------------------------
# Brightest
# ---------------------------------------------------------------------------


def test_brightest_orders_by_magnitude():
    rows = [
        _row("a", apparent_magnitude=4.0),
        _row("b", apparent_magnitude=1.0),
        _row("c", apparent_magnitude=10.0),
    ]
    q = AdvancedQuery(kind=QueryKind.BRIGHTEST, max_results=5)
    rep = run_query(q, rows)
    uids = [r.uid for r in rep.results]
    assert uids == ["b", "a", "c"]


def test_brightest_drops_rows_without_magnitude():
    rows = [
        _row("a", apparent_magnitude=4.0),
        _row("b"),  # no magnitude
        _row("c", apparent_magnitude=2.0),
    ]
    q = AdvancedQuery(kind=QueryKind.BRIGHTEST, max_results=5)
    rep = run_query(q, rows)
    uids = [r.uid for r in rep.results]
    assert uids == ["c", "a"]


# ---------------------------------------------------------------------------
# Highest redshift
# ---------------------------------------------------------------------------


def test_highest_redshift_orders_descending():
    rows = [
        _row("a", redshift=0.1, object_type="galaxy"),
        _row("b", redshift=2.5, object_type="galaxy"),
        _row("c", redshift=0.5, object_type="galaxy"),
    ]
    q = AdvancedQuery(kind=QueryKind.HIGHEST_REDSHIFT, max_results=5)
    rep = run_query(q, rows)
    uids = [r.uid for r in rep.results]
    assert uids == ["b", "c", "a"]


def test_highest_redshift_drops_rows_without_redshift():
    rows = [
        _row("a", redshift=0.5),
        _row("b"),  # no redshift
    ]
    q = AdvancedQuery(kind=QueryKind.HIGHEST_REDSHIFT, max_results=5)
    rep = run_query(q, rows)
    uids = [r.uid for r in rep.results]
    assert uids == ["a"]


# ---------------------------------------------------------------------------
# Range queries
# ---------------------------------------------------------------------------


def test_distance_range_filter():
    rows = [
        _row("a", distance_parsec=5.0),
        _row("b", distance_parsec=50.0),
        _row("c", distance_parsec=500.0),
    ]
    q = AdvancedQuery(
        kind=QueryKind.DISTANCE_RANGE,
        distance_min_pc=10.0, distance_max_pc=100.0,
        max_results=10,
    )
    rep = run_query(q, rows)
    uids = [r.uid for r in rep.results]
    assert uids == ["b"]


def test_magnitude_range_filter():
    rows = [
        _row("a", apparent_magnitude=1.0),
        _row("b", apparent_magnitude=5.0),
        _row("c", apparent_magnitude=10.0),
    ]
    q = AdvancedQuery(
        kind=QueryKind.MAGNITUDE_RANGE,
        magnitude_min=2.0, magnitude_max=8.0,
        max_results=10,
    )
    rep = run_query(q, rows)
    uids = [r.uid for r in rep.results]
    assert uids == ["b"]


def test_redshift_range_filter():
    rows = [
        _row("a", redshift=0.1),
        _row("b", redshift=1.0),
        _row("c", redshift=3.0),
    ]
    q = AdvancedQuery(
        kind=QueryKind.REDSHIFT_RANGE,
        redshift_min=0.5, redshift_max=2.0,
        max_results=10,
    )
    rep = run_query(q, rows)
    uids = [r.uid for r in rep.results]
    assert uids == ["b"]


# ---------------------------------------------------------------------------
# Source / type filters
# ---------------------------------------------------------------------------


def test_by_source_filters():
    rows = [
        _row("a", catalog_source="Gaia DR3"),
        _row("b", catalog_source="SDSS"),
        _row("c", catalog_source="Gaia DR3"),
    ]
    q = AdvancedQuery(
        kind=QueryKind.BY_SOURCE,
        sources=("Gaia DR3",),
        max_results=10,
    )
    rep = run_query(q, rows)
    uids = sorted(r.uid for r in rep.results)
    assert uids == ["a", "c"]


def test_by_type_filters():
    rows = [
        _row("a", object_type="star"),
        _row("b", object_type="galaxy"),
        _row("c", object_type="quasar"),
    ]
    q = AdvancedQuery(
        kind=QueryKind.BY_TYPE,
        object_types=("galaxy", "quasar"),
        max_results=10,
    )
    rep = run_query(q, rows)
    uids = sorted(r.uid for r in rep.results)
    assert uids == ["b", "c"]


# ---------------------------------------------------------------------------
# Visible-sector restriction
# ---------------------------------------------------------------------------


def test_within_visible_sector_filters():
    rows = [_row(f"u{i}") for i in range(5)]
    q = AdvancedQuery(
        kind=QueryKind.WITHIN_VISIBLE_SECTOR,
        visible_sector_uids=("u1", "u3"),
        max_results=10,
    )
    rep = run_query(q, rows)
    uids = sorted(r.uid for r in rep.results)
    assert uids == ["u1", "u3"]


def test_within_visible_sector_empty_uid_set_passes_all():
    rows = [_row("u1"), _row("u2")]
    q = AdvancedQuery(
        kind=QueryKind.WITHIN_VISIBLE_SECTOR,
        max_results=10,
    )
    rep = run_query(q, rows)
    assert rep.matched_before_cap == 2


# ---------------------------------------------------------------------------
# Near selected
# ---------------------------------------------------------------------------


def test_near_selected_excludes_self():
    rows = [
        _row("a", cartesian_x=0, cartesian_y=0, cartesian_z=0),
        _row("b", cartesian_x=1, cartesian_y=0, cartesian_z=0),
        _row("c", cartesian_x=2, cartesian_y=0, cartesian_z=0),
    ]
    q = AdvancedQuery(
        kind=QueryKind.NEAR_SELECTED,
        selected_uid="a",
        max_results=10,
    )
    rep = run_query(q, rows)
    uids = [r.uid for r in rep.results]
    assert "a" not in uids
    # b is closer than c.
    assert uids == ["b", "c"]


# ---------------------------------------------------------------------------
# Epoch warnings
# ---------------------------------------------------------------------------


def test_epoch_without_interpolation_warns():
    rows = [_row("a")]
    q = AdvancedQuery(
        kind=QueryKind.BY_TYPE,
        object_types=("star",),
        epoch_jd=2461041.5,
        interpolate_ephemeris=False,
    )
    rep = run_query(q, rows)
    assert any("static" in w.lower() for w in rep.warnings)


def test_epoch_with_interpolation_emits_note():
    rows = [_row("a")]
    q = AdvancedQuery(
        kind=QueryKind.BY_TYPE,
        object_types=("star",),
        epoch_jd=2461041.5,
        interpolate_ephemeris=True,
    )
    rep = run_query(q, rows)
    assert any("epoch" in n.lower() for n in rep.notes)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_run_query_deterministic():
    rows = [
        _row("a", cartesian_x=1, cartesian_y=0, cartesian_z=0),
        _row("b", cartesian_x=2, cartesian_y=0, cartesian_z=0),
    ]
    q = AdvancedQuery(
        kind=QueryKind.NEAREST,
        reference_point_pc=(0, 0, 0),
        max_results=10,
    )
    a = run_query(q, rows)
    b = run_query(q, rows)
    assert [r.uid for r in a.results] == [r.uid for r in b.results]


def test_uid_tiebreak_when_distances_equal():
    """Two rows at the same distance should sort by
    uid for determinism."""
    rows = [
        _row("z", cartesian_x=5, cartesian_y=0, cartesian_z=0),
        _row("a", cartesian_x=5, cartesian_y=0, cartesian_z=0),
    ]
    q = AdvancedQuery(
        kind=QueryKind.NEAREST,
        reference_point_pc=(0, 0, 0),
        max_results=10,
    )
    rep = run_query(q, rows)
    uids = [r.uid for r in rep.results]
    assert uids == ["a", "z"]


# ---------------------------------------------------------------------------
# Report shape
# ---------------------------------------------------------------------------


def test_report_short_summary_shape():
    q = AdvancedQuery(kind=QueryKind.NEAREST, max_results=5)
    rep = run_query(q, [_row("a"), _row("b")])
    s = rep.short_summary()
    assert "result(s)" in s
    assert "match" in s


def test_query_short_summary_shape():
    q = AdvancedQuery(
        kind=QueryKind.DISTANCE_RANGE,
        distance_min_pc=1.0, distance_max_pc=10.0,
    )
    s = q.short_summary()
    assert "distance_range" in s
    assert "d=" in s
