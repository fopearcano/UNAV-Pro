"""v3.7 advanced-query panel — pure-Python facade.

The dialog's *Advanced Query* panel surfaces:

* a query-kind selector;
* object type + source allow-lists;
* magnitude / distance / redshift range fields;
* a max-results spinner;
* a *Run Query* button;
* a *Save Query Preset* button (placeholder);
* an *Export Results* button (JSON / CSV /
  Markdown).

Each helper is a pure function over the existing
v3.7 query types — the dialog handles the
OS-level "pick a save location" + "draw the result
table" parts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

from query import (
    AdvancedQuery, QueryKind, QueryReport,
    QueryPresetDescriptor, RouteQueryReport,
    SortOrder,
    find_objects_near_route,
    get_preset, list_presets, run_query,
    write_csv_report, write_json_report,
    write_markdown_report,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AdvancedQueryPanelError(RuntimeError):
    """Raised on panel-action failures."""


# ---------------------------------------------------------------------------
# Build a query from form fields
# ---------------------------------------------------------------------------


@dataclass
class QueryFormFields:
    """Pure-data form-state record. The dialog
    populates this from its widget values + hands
    it to ``query_from_form``."""

    kind: QueryKind = QueryKind.NEAREST
    max_results: int = 100
    distance_min_pc: Optional[float] = None
    distance_max_pc: Optional[float] = None
    magnitude_min: Optional[float] = None
    magnitude_max: Optional[float] = None
    redshift_min: Optional[float] = None
    redshift_max: Optional[float] = None
    sources: Tuple[str, ...] = ()
    object_types: Tuple[str, ...] = ()
    visible_sector_uids: Tuple[str, ...] = ()
    reference_point_pc: Optional[Tuple[float, float, float]] = None
    selected_uid: Optional[str] = None
    sort_order: SortOrder = SortOrder.NONE
    epoch_jd: Optional[float] = None
    interpolate_ephemeris: bool = False


def query_from_form(form: QueryFormFields) -> AdvancedQuery:
    """Compose an ``AdvancedQuery`` from the
    panel's form fields. Validates the obvious
    inputs (max_results > 0, ranges sane)."""
    if form.max_results <= 0:
        raise AdvancedQueryPanelError(
            "max_results must be > 0"
        )
    for lo, hi, name in (
        (form.distance_min_pc, form.distance_max_pc, "distance"),
        (form.magnitude_min, form.magnitude_max, "magnitude"),
        (form.redshift_min, form.redshift_max, "redshift"),
    ):
        if lo is not None and hi is not None and lo > hi:
            raise AdvancedQueryPanelError(
                f"{name} range invalid: min ({lo}) > max ({hi})"
            )
    return AdvancedQuery(
        kind=form.kind,
        max_results=int(form.max_results),
        distance_min_pc=form.distance_min_pc,
        distance_max_pc=form.distance_max_pc,
        magnitude_min=form.magnitude_min,
        magnitude_max=form.magnitude_max,
        redshift_min=form.redshift_min,
        redshift_max=form.redshift_max,
        sources=tuple(form.sources),
        object_types=tuple(form.object_types),
        visible_sector_uids=tuple(form.visible_sector_uids),
        reference_point_pc=form.reference_point_pc,
        selected_uid=form.selected_uid,
        sort_order=form.sort_order,
        epoch_jd=form.epoch_jd,
        interpolate_ephemeris=bool(form.interpolate_ephemeris),
    )


# ---------------------------------------------------------------------------
# Run query
# ---------------------------------------------------------------------------


def run_query_action(
    *,
    query: AdvancedQuery,
    candidates: Iterable[Any],
) -> QueryReport:
    """Run the query against ``candidates``."""
    if query is None:
        raise AdvancedQueryPanelError("query is required")
    return run_query(query, candidates)


# ---------------------------------------------------------------------------
# Preset picker
# ---------------------------------------------------------------------------


def list_presets_action() -> List[QueryPresetDescriptor]:
    """Return the registry. The dialog uses this to
    populate its preset menu."""
    return list_presets()


def select_preset_action(
    name: str, **kwargs: Any,
) -> AdvancedQuery:
    """Build the query for ``name`` with the
    optional kwargs passed straight through to the
    preset's builder."""
    if not name:
        raise AdvancedQueryPanelError("preset name is empty")
    preset = get_preset(name)
    if preset is None:
        raise AdvancedQueryPanelError(
            f"unknown preset: {name!r}; "
            f"valid: {[p.name for p in list_presets()]}"
        )
    try:
        return preset.builder(**kwargs)
    except (TypeError, ValueError) as exc:
        raise AdvancedQueryPanelError(
            f"preset {name!r} build failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_results_json_action(
    report: QueryReport, path: str,
) -> str:
    if report is None:
        raise AdvancedQueryPanelError("no report to export")
    if not path:
        raise AdvancedQueryPanelError("export path is empty")
    return write_json_report(report, path)


def export_results_csv_action(
    report: QueryReport, path: str,
) -> str:
    if report is None:
        raise AdvancedQueryPanelError("no report to export")
    if not path:
        raise AdvancedQueryPanelError("export path is empty")
    return write_csv_report(report, path)


def export_results_markdown_action(
    report: QueryReport, path: str,
) -> str:
    if report is None:
        raise AdvancedQueryPanelError("no report to export")
    if not path:
        raise AdvancedQueryPanelError("export path is empty")
    return write_markdown_report(report, path)


# ---------------------------------------------------------------------------
# Route-aware query
# ---------------------------------------------------------------------------


def run_route_query_action(
    *,
    polyline,
    candidates: Iterable[Any],
    corridor_radius_pc: float = 5.0,
    max_results: int = 200,
) -> RouteQueryReport:
    """Run a route-aware query. ``polyline`` is the
    list of route / mission Cartesian-pc waypoints;
    the dialog computes it via
    ``polyline_from_waypoints``."""
    if not polyline:
        raise AdvancedQueryPanelError(
            "polyline is empty; load a route first"
        )
    if corridor_radius_pc <= 0:
        raise AdvancedQueryPanelError(
            "corridor_radius_pc must be > 0"
        )
    return find_objects_near_route(
        polyline=polyline,
        candidates=candidates,
        corridor_radius_pc=corridor_radius_pc,
        max_results=max_results,
    )
