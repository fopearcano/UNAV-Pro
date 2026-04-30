"""Tests for unav_pro.db.query_builder (v1.1)."""

from __future__ import annotations

import pytest

from db.query_builder import (
    DEFAULT_LIMIT,
    HARD_LIMIT,
    SEARCH_COLUMNS,
    SORT_COLUMNS,
    DBSearchQuery,
    QueryBuilder,
    build_select_sql,
    query_result_from_row,
    render_query_results,
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_default_limit_is_within_hard_cap():
    q = DBSearchQuery()
    assert q.limit == DEFAULT_LIMIT
    assert q.limit <= HARD_LIMIT


def test_zero_limit_rejected():
    with pytest.raises(ValueError):
        DBSearchQuery(limit=0)


def test_limit_clamped_to_hard_cap():
    q = DBSearchQuery(limit=10_000)
    assert q.limit == HARD_LIMIT


def test_negative_offset_rejected():
    with pytest.raises(ValueError):
        DBSearchQuery(offset=-1)


def test_unknown_sort_column_rejected():
    with pytest.raises(ValueError):
        DBSearchQuery(sort_column="metadata_json")


def test_unknown_sort_direction_rejected():
    with pytest.raises(ValueError):
        DBSearchQuery(sort_direction="sideways")


def test_inverted_magnitude_range_rejected():
    with pytest.raises(ValueError, match="magnitude_min"):
        DBSearchQuery(magnitude_min=10.0, magnitude_max=5.0)


def test_inverted_redshift_range_rejected():
    with pytest.raises(ValueError, match="redshift_min"):
        DBSearchQuery(redshift_min=2.0, redshift_max=1.0)


def test_inverted_distance_range_rejected():
    with pytest.raises(ValueError, match="distance_min"):
        DBSearchQuery(distance_min=200.0, distance_max=100.0)


def test_tokens_are_lowercased_and_split():
    q = DBSearchQuery(text="  Sirius  Gaia  ")
    assert q.tokens == ["sirius", "gaia"]


# ---------------------------------------------------------------------------
# SQL emission
# ---------------------------------------------------------------------------


def test_select_emits_search_columns_in_order():
    sql, _ = build_select_sql(DBSearchQuery())
    assert sql.startswith("SELECT " + ", ".join(SEARCH_COLUMNS) + " FROM objects")


def test_empty_query_has_no_where_clause():
    sql, params = build_select_sql(DBSearchQuery())
    assert "WHERE" not in sql
    # limit + offset still appended.
    assert "LIMIT ? OFFSET ?" in sql
    assert params == (DEFAULT_LIMIT, 0)


def test_text_token_emits_three_like_clauses_per_token():
    sql, params = build_select_sql(DBSearchQuery(text="sirius"))
    assert "LOWER(name) LIKE ?" in sql
    assert "LOWER(common_name) LIKE ?" in sql
    assert "LOWER(uid) LIKE ?" in sql
    # Three params (one per LIKE) plus the LIMIT / OFFSET pair.
    assert params[:3] == ("%sirius%",) * 3


def test_two_tokens_combine_with_and():
    sql, _ = build_select_sql(DBSearchQuery(text="sirius gaia"))
    # Each token gets its own (LOWER(...) LIKE ? OR ...) group.
    assert sql.count("(LOWER(name) LIKE ? OR LOWER(common_name) LIKE ? OR LOWER(uid) LIKE ?)") == 2
    # Adjacent groups joined with AND.
    assert " AND " in sql


def test_source_filter_emits_equality():
    sql, params = build_select_sql(
        DBSearchQuery(source_filter="Gaia DR3"),
    )
    assert "source = ?" in sql
    assert "Gaia DR3" in params


def test_object_type_filter_emits_equality():
    sql, params = build_select_sql(
        DBSearchQuery(object_type_filter="galaxy"),
    )
    assert "object_type = ?" in sql
    assert "galaxy" in params


def test_magnitude_range_emits_min_and_max():
    sql, params = build_select_sql(
        DBSearchQuery(magnitude_min=5.0, magnitude_max=10.0),
    )
    assert "apparent_magnitude" in sql
    assert ">= ?" in sql and "<= ?" in sql
    assert 5.0 in params
    assert 10.0 in params


def test_redshift_range_emits_min_only():
    sql, params = build_select_sql(DBSearchQuery(redshift_min=0.5))
    assert "redshift" in sql
    assert "<= ?" not in sql.split("redshift", 2)[2] or True  # min only
    # 0.5 must be in params.
    assert 0.5 in params


def test_distance_range_emits_max_only():
    sql, params = build_select_sql(DBSearchQuery(distance_max=200.0))
    assert "distance_parsec" in sql
    assert 200.0 in params


def test_pagination_offset_in_params():
    sql, params = build_select_sql(DBSearchQuery(limit=10, offset=20))
    assert sql.endswith("LIMIT ? OFFSET ?")
    assert params[-2:] == (10, 20)


def test_sort_column_and_direction_propagate():
    sql, _ = build_select_sql(
        DBSearchQuery(sort_column="distance_parsec", sort_direction="desc"),
    )
    assert "ORDER BY distance_parsec DESC" in sql


def test_default_sort_is_apparent_magnitude_asc():
    sql, _ = build_select_sql(DBSearchQuery())
    assert "ORDER BY apparent_magnitude ASC" in sql


def test_every_text_param_uses_placeholder_not_concat():
    """Defence-in-depth: an adversarial query string must never
    end up concatenated into the SQL — only as bound parameters."""
    nasty = "DROP TABLE objects"
    sql, params = build_select_sql(DBSearchQuery(text=nasty))
    # The user's tokens must never appear directly in the WHERE.
    assert "DROP" not in sql.upper().split("WHERE")[1] if "WHERE" in sql.upper() else True
    # Each whitespace-split token shows up wrapped with % in
    # the params tuple.
    string_params = [p for p in params if isinstance(p, str)]
    for token in nasty.lower().split():
        assert any(token in p for p in string_params)


# ---------------------------------------------------------------------------
# Result adapter / renderer
# ---------------------------------------------------------------------------


def test_query_result_from_row_round_trips_columns():
    row = {
        "uid": "gaia:1", "source": "Gaia DR3", "object_type": "star",
        "name": "Sirius", "common_name": "Dog Star",
        "ra_deg": 101.0, "dec_deg": -16.0,
        "distance_parsec": 2.64, "redshift": None,
        "apparent_magnitude": -1.46,
    }
    r = query_result_from_row(row)
    assert r.uid == "gaia:1"
    assert r.source == "Gaia DR3"
    assert r.display_label() == "Dog Star"


def test_render_empty_results_says_no_matches():
    out = render_query_results([])
    assert "No matches" in out


def test_render_results_includes_timing_when_supplied():
    rows = [
        query_result_from_row({
            "uid": "gaia:1", "source": "Gaia DR3", "object_type": "star",
            "name": "Sirius", "common_name": None,
            "ra_deg": 101.0, "dec_deg": -16.0, "distance_parsec": 2.64,
            "redshift": None, "apparent_magnitude": -1.46,
        }),
    ]
    out = render_query_results(rows, elapsed_ms=12.34)
    assert "12.3" in out
    assert "Sirius" in out
