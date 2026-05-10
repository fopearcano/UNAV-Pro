"""UNAV Pro v3.7 advanced-query package.

Pure-Python query engine + presets + route-aware
queries + result actions + exporters. Stdlib-only;
no Cinema 4D, no network calls.

Modules:

* :mod:`advanced_query` — `AdvancedQuery`,
  `QueryReport`, `QueryResult`, `run_query`.
* :mod:`query_presets` — registry of named
  presets (`PRESET_REGISTRY`) + factory builders.
* :mod:`route_query` — polyline-corridor + per-
  waypoint nearest-neighbour helpers.
* :mod:`result_actions` — pure helpers translating
  results into bookmark / route / mission / focus
  / inspect deltas.
* :mod:`export` — JSON / CSV / Markdown exporters.
"""

from __future__ import annotations

from .advanced_query import (
    DEFAULT_MAX_RESULTS,
    QUERY_KINDS,
    SORT_ORDERS,
    AdvancedQuery,
    QueryKind,
    QueryReport,
    QueryResult,
    SortOrder,
    run_query,
)
from .query_presets import (
    PRESET_REGISTRY,
    QueryPresetDescriptor,
    along_route,
    around_navigator,
    brightest_stars,
    get_preset,
    high_redshift_galaxies,
    high_redshift_quasars,
    list_presets,
    nearby_gaia_objects,
    nearest_stars,
    preset_names,
    selected_dataset_summary,
    solar_system_at_epoch,
)
from .route_query import (
    DEFAULT_CORRIDOR_RADIUS_PC,
    ClosestPerWaypoint,
    RouteQueryReport,
    RouteSummary,
    closest_object_to_each_waypoint,
    distance_point_to_polyline,
    distance_point_to_segment,
    find_objects_between_waypoints,
    find_objects_near_route,
    polyline_from_waypoints,
    summarise_route_distribution,
)
from .result_actions import (
    BookmarkDelta,
    InspectorRequest,
    MissionWaypointDelta,
    NavigationFocus,
    RouteWaypointDelta,
    add_all_to_mission,
    add_all_to_route,
    add_to_mission_action,
    add_to_route_action,
    bookmark_action,
    bookmark_all,
    focus_navigator_action,
    inspect_action,
)
from .export import (
    CSV_FIELDS,
    render_csv,
    render_json,
    render_markdown,
    write_csv_report,
    write_json_report,
    write_markdown_report,
)

__all__ = [
    # advanced_query
    "QueryKind", "QUERY_KINDS",
    "SortOrder", "SORT_ORDERS",
    "AdvancedQuery", "QueryResult", "QueryReport",
    "run_query", "DEFAULT_MAX_RESULTS",
    # presets
    "QueryPresetDescriptor", "PRESET_REGISTRY",
    "list_presets", "get_preset", "preset_names",
    "nearest_stars", "brightest_stars",
    "nearby_gaia_objects",
    "high_redshift_galaxies", "high_redshift_quasars",
    "solar_system_at_epoch",
    "around_navigator", "along_route",
    "selected_dataset_summary",
    # route_query
    "DEFAULT_CORRIDOR_RADIUS_PC",
    "RouteQueryReport", "RouteSummary",
    "ClosestPerWaypoint",
    "find_objects_near_route",
    "find_objects_between_waypoints",
    "closest_object_to_each_waypoint",
    "summarise_route_distribution",
    "polyline_from_waypoints",
    "distance_point_to_segment",
    "distance_point_to_polyline",
    # result_actions
    "NavigationFocus", "BookmarkDelta",
    "RouteWaypointDelta", "MissionWaypointDelta",
    "InspectorRequest",
    "focus_navigator_action", "bookmark_action",
    "add_to_route_action", "add_to_mission_action",
    "inspect_action",
    "bookmark_all", "add_all_to_route",
    "add_all_to_mission",
    # export
    "CSV_FIELDS",
    "render_json", "render_csv", "render_markdown",
    "write_json_report", "write_csv_report",
    "write_markdown_report",
]
