"""v3.7 advanced-query panel-action tests."""

from __future__ import annotations

import os

import pytest

from data import CatalogObject
from query import (
    AdvancedQuery,
    QueryKind,
    QueryReport,
    QueryResult,
    SortOrder,
)
from ui.advanced_query_panel import (
    AdvancedQueryPanelError,
    QueryFormFields,
    export_results_csv_action,
    export_results_json_action,
    export_results_markdown_action,
    list_presets_action,
    query_from_form,
    run_query_action,
    run_route_query_action,
    select_preset_action,
)


def _row(uid, **kw):
    base = dict(
        uid=uid, catalog_source="Test",
        object_type="star", ra_deg=0.0, dec_deg=0.0,
    )
    base.update(kw)
    return CatalogObject(**base)


# ---------------------------------------------------------------------------
# query_from_form
# ---------------------------------------------------------------------------


def test_query_from_form_basic():
    q = query_from_form(QueryFormFields(
        kind=QueryKind.BRIGHTEST,
        max_results=10,
    ))
    assert isinstance(q, AdvancedQuery)
    assert q.kind is QueryKind.BRIGHTEST


def test_query_from_form_validates_max_results():
    with pytest.raises(AdvancedQueryPanelError):
        query_from_form(QueryFormFields(
            kind=QueryKind.NEAREST, max_results=0,
        ))


def test_query_from_form_validates_distance_range():
    with pytest.raises(AdvancedQueryPanelError):
        query_from_form(QueryFormFields(
            kind=QueryKind.DISTANCE_RANGE,
            distance_min_pc=100.0,
            distance_max_pc=10.0,
        ))


def test_query_from_form_validates_magnitude_range():
    with pytest.raises(AdvancedQueryPanelError):
        query_from_form(QueryFormFields(
            kind=QueryKind.MAGNITUDE_RANGE,
            magnitude_min=10.0,
            magnitude_max=1.0,
        ))


def test_query_from_form_validates_redshift_range():
    with pytest.raises(AdvancedQueryPanelError):
        query_from_form(QueryFormFields(
            kind=QueryKind.REDSHIFT_RANGE,
            redshift_min=2.0,
            redshift_max=0.5,
        ))


def test_query_from_form_propagates_filters():
    form = QueryFormFields(
        kind=QueryKind.BY_SOURCE,
        sources=("Gaia DR3", "SDSS"),
        object_types=("galaxy",),
        magnitude_max=12.0,
    )
    q = query_from_form(form)
    assert q.sources == ("Gaia DR3", "SDSS")
    assert q.object_types == ("galaxy",)
    assert q.magnitude_max == 12.0


# ---------------------------------------------------------------------------
# run_query_action
# ---------------------------------------------------------------------------


def test_run_query_action_returns_report():
    q = AdvancedQuery(kind=QueryKind.NEAREST, max_results=10)
    out = run_query_action(query=q, candidates=[_row("a"), _row("b")])
    assert isinstance(out, QueryReport)


def test_run_query_action_rejects_none_query():
    with pytest.raises(AdvancedQueryPanelError):
        run_query_action(query=None, candidates=[])


# ---------------------------------------------------------------------------
# Preset picker
# ---------------------------------------------------------------------------


def test_list_presets_returns_descriptors():
    out = list_presets_action()
    assert len(out) >= 9


def test_select_preset_known():
    q = select_preset_action("nearest_stars", max_results=10)
    assert q.kind is QueryKind.NEAREST


def test_select_preset_unknown_raises():
    with pytest.raises(AdvancedQueryPanelError):
        select_preset_action("not_a_preset")


def test_select_preset_blank_raises():
    with pytest.raises(AdvancedQueryPanelError):
        select_preset_action("")


def test_select_preset_bad_kwarg_raises():
    """Passing an unknown kwarg surfaces a panel
    error rather than a raw TypeError."""
    with pytest.raises(AdvancedQueryPanelError):
        select_preset_action("nearest_stars", weird_kwarg=True)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _sample_report():
    q = AdvancedQuery(kind=QueryKind.NEAREST, max_results=5)
    return run_query_action(query=q, candidates=[_row("a"), _row("b")])


def test_export_json_writes_file(tmp_path):
    rep = _sample_report()
    path = str(tmp_path / "out.json")
    export_results_json_action(rep, path)
    assert os.path.isfile(path)


def test_export_csv_writes_file(tmp_path):
    rep = _sample_report()
    path = str(tmp_path / "out.csv")
    export_results_csv_action(rep, path)
    assert os.path.isfile(path)


def test_export_markdown_writes_file(tmp_path):
    rep = _sample_report()
    path = str(tmp_path / "out.md")
    export_results_markdown_action(rep, path)
    assert os.path.isfile(path)


def test_export_rejects_none_report(tmp_path):
    path = str(tmp_path / "out.json")
    with pytest.raises(AdvancedQueryPanelError):
        export_results_json_action(None, path)


def test_export_rejects_blank_path():
    rep = _sample_report()
    with pytest.raises(AdvancedQueryPanelError):
        export_results_json_action(rep, "")


# ---------------------------------------------------------------------------
# Route query
# ---------------------------------------------------------------------------


def test_run_route_query_action():
    rows = [
        _row("a", cartesian_x=5, cartesian_y=0, cartesian_z=0),
    ]
    rep = run_route_query_action(
        polyline=[(0, 0, 0), (10, 0, 0)],
        candidates=rows,
        corridor_radius_pc=5.0,
    )
    assert rep.returned == 1


def test_run_route_query_rejects_empty_polyline():
    with pytest.raises(AdvancedQueryPanelError):
        run_route_query_action(
            polyline=[],
            candidates=[],
        )


def test_run_route_query_rejects_zero_radius():
    with pytest.raises(AdvancedQueryPanelError):
        run_route_query_action(
            polyline=[(0, 0, 0), (1, 0, 0)],
            candidates=[],
            corridor_radius_pc=0.0,
        )
