"""Route panel — c4d-bound glue between the UI buttons and the
``core.route`` data model.

Pure functions and the ``Route`` dataclass live in
``unav_pro/core/route.py``. This module owns the operations that
need Cinema 4D: reading the active selection, building a route
``SplineObject``, and moving the navigator to focus on a waypoint.

Hierarchy
---------

The route lives at the scene root, peer to ``UNAV_Starfield``::

    UNAV_Route                 (null)
    └── UNAV_RoutePath         (linear SplineObject)

The null carries the standard ``BC_ID_UNAV_MARKER`` container so
``clear_starfield`` removes the route subtree the same way it
removes everything else UNAV ever made.
"""

from __future__ import annotations

from typing import Optional, Tuple

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from c4d_objects.point_cloud_builder import (
    MARKER_KEY_CATALOG_SOURCE,
    MARKER_KEY_NAME,
    MARKER_KEY_OBJECT_TYPE,
    MARKER_KEY_UID,
    _named_kind_marker,
    _read_marker,
    _write_marker,
)
from core.logging_util import get_logger
from core.metadata_lookup import MetadataLookup, default_lookup
from core.route import (
    Route,
    Waypoint,
    compute_route,
    make_lookup_resolver,
    render_summary,
)

_log = get_logger("ui.route_panel")

ROUTE_NULL_NAME = "UNAV_Route"
ROUTE_SPLINE_NAME = "UNAV_RoutePath"

KIND_ROUTE_ROOT = "route_root"
KIND_ROUTE_SPLINE = "route_spline"


def _require_c4d() -> None:
    if not _C4D_AVAILABLE:
        raise RuntimeError(
            "route_panel requires Cinema 4D; this code path is "
            "unavailable outside the C4D host."
        )


# ---------------------------------------------------------------------------
# Hierarchy helpers
# ---------------------------------------------------------------------------


def _find_route_root(
    doc: "c4d.documents.BaseDocument",
) -> Optional["c4d.BaseObject"]:
    _require_c4d()
    obj = doc.GetFirstObject()
    while obj is not None:
        marker = _read_marker(obj)
        from c4d_objects.point_cloud_builder import MARKER_KEY_KIND  # local
        if marker is not None and marker.get(MARKER_KEY_KIND) == KIND_ROUTE_ROOT:
            return obj
        if obj.GetName() == ROUTE_NULL_NAME:
            return obj
        obj = obj.GetNext()
    return None


def _ensure_route_root(
    doc: "c4d.documents.BaseDocument",
) -> "c4d.BaseObject":
    _require_c4d()
    existing = _find_route_root(doc)
    if existing is not None:
        return existing
    null = c4d.BaseObject(c4d.Onull)
    null.SetName(ROUTE_NULL_NAME)
    null[c4d.NULLOBJECT_DISPLAY] = c4d.NULLOBJECT_DISPLAY_NONE
    _write_marker(null, _named_kind_marker(KIND_ROUTE_ROOT, ROUTE_NULL_NAME))
    doc.InsertObject(null)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, null)
    return null


def _remove_route_spline(route_root: "c4d.BaseObject") -> bool:
    _require_c4d()
    from c4d_objects.point_cloud_builder import MARKER_KEY_KIND
    child = route_root.GetDown()
    while child is not None:
        nxt = child.GetNext()
        marker = _read_marker(child)
        if marker is not None and marker.get(MARKER_KEY_KIND) == KIND_ROUTE_SPLINE:
            child.Remove()
            return True
        child = nxt
    return False


# ---------------------------------------------------------------------------
# Add Selected Object as Waypoint
# ---------------------------------------------------------------------------


def add_selected_as_waypoint(
    doc: "c4d.documents.BaseDocument",
    route: Route,
    lookup: Optional[MetadataLookup] = None,
) -> Tuple[Optional[Waypoint], str]:
    """Read the active selection and append a matching waypoint to
    ``route``. Returns ``(waypoint, status_line)``.

    Selection rules:

      * UNAV-tagged object → ``Waypoint(kind="object")`` with uid /
        source / type filled from the marker, plus the object's
        current world-space position. If the lookup contains the
        uid, parsec coords are also attached.
      * Non-UNAV object → ``Waypoint(kind="coordinate")`` using the
        object's name and world-space position.
      * Nothing selected → status line, no mutation.
    """
    _require_c4d()
    selected = doc.GetActiveObject()
    if selected is None:
        return None, "Add Waypoint: nothing selected."

    pos = selected.GetMg().off
    name = selected.GetName() or "<unnamed>"
    marker = _read_marker(selected)

    if marker is None:
        wp = Waypoint(
            kind="coordinate",
            label=name,
            x_c4d=float(pos.x), y_c4d=float(pos.y), z_c4d=float(pos.z),
        )
        route.add(wp)
        return wp, f"Add Waypoint: '{name}' (free coordinate)."

    uid = str(marker.get(MARKER_KEY_UID) or "")
    source = marker.get(MARKER_KEY_CATALOG_SOURCE) or None
    obj_type = marker.get(MARKER_KEY_OBJECT_TYPE) or None
    label = marker.get(MARKER_KEY_NAME) or name or uid

    if not uid:
        # Marker present but no uid (e.g. a navigator child) — fall
        # back to a coordinate waypoint so the user always gets
        # something useful.
        wp = Waypoint(
            kind="coordinate",
            label=label,
            x_c4d=float(pos.x), y_c4d=float(pos.y), z_c4d=float(pos.z),
        )
        route.add(wp)
        return wp, f"Add Waypoint: '{label}' (free coordinate; no uid on marker)."

    table = lookup if lookup is not None else default_lookup()
    resolved = table.lookup(uid) if table is not None else None

    wp = Waypoint(
        kind="object",
        label=label,
        uid=uid,
        catalog_source=source,
        object_type=obj_type,
        x_c4d=float(pos.x), y_c4d=float(pos.y), z_c4d=float(pos.z),
    )
    if resolved is not None and resolved.cartesian_x is not None:
        wp.x_pc = resolved.cartesian_x
        wp.y_pc = resolved.cartesian_y
        wp.z_pc = resolved.cartesian_z
    route.add(wp)
    suffix = ""
    if resolved is None:
        suffix = " (catalog miss; pc distance unavailable)"
    return wp, f"Add Waypoint: '{label}' [{uid}]{suffix}."


# ---------------------------------------------------------------------------
# Clear Route
# ---------------------------------------------------------------------------


def clear_route(
    route: Route,
    doc: Optional["c4d.documents.BaseDocument"] = None,
) -> str:
    """Empty ``route`` in place. If ``doc`` is provided, the existing
    route spline (if any) is also removed."""
    n = route.clear()
    if doc is not None and _C4D_AVAILABLE:
        root = _find_route_root(doc)
        if root is not None:
            doc.StartUndo()
            try:
                if _remove_route_spline(root):
                    pass
            finally:
                doc.EndUndo()
            c4d.EventAdd()
    return f"Clear Route: removed {n} waypoint(s)."


# ---------------------------------------------------------------------------
# Build Route Spline
# ---------------------------------------------------------------------------


def build_route_spline(
    doc: "c4d.documents.BaseDocument",
    route: Route,
    lookup: Optional[MetadataLookup] = None,
) -> str:
    """Create a linear ``SplineObject`` through the resolvable
    waypoints. Returns a status string."""
    _require_c4d()

    if len(route) < 2:
        return "Build Route Spline: need at least 2 waypoints."

    resolver = make_lookup_resolver(
        lookup if lookup is not None else default_lookup()
    )
    points = []
    for wp in route.waypoints:
        pos = resolver(wp)
        if pos is None:
            continue
        points.append((pos.x_c4d, pos.y_c4d, pos.z_c4d))

    if len(points) < 2:
        return (
            "Build Route Spline: fewer than 2 waypoints have resolvable "
            "positions; nothing to draw."
        )

    root = _ensure_route_root(doc)
    doc.StartUndo()
    try:
        _remove_route_spline(root)
        spline = c4d.SplineObject(len(points), c4d.SPLINETYPE_LINEAR)
        spline.SetName(ROUTE_SPLINE_NAME)
        for i, p in enumerate(points):
            spline.SetPoint(i, c4d.Vector(*p))
        spline.Message(c4d.MSG_UPDATE)
        spline[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
        spline[c4d.ID_BASEOBJECT_COLOR] = c4d.Vector(0.95, 0.85, 0.30)
        _write_marker(
            spline, _named_kind_marker(KIND_ROUTE_SPLINE, ROUTE_SPLINE_NAME),
        )
        spline.InsertUnder(root)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, spline)
    finally:
        doc.EndUndo()

    c4d.EventAdd()
    return f"Build Route Spline: drew path with {len(points)} knots."


# ---------------------------------------------------------------------------
# Focus Navigator on Waypoint
# ---------------------------------------------------------------------------


def focus_navigator_on(
    doc: "c4d.documents.BaseDocument",
    route: Route,
    waypoint_index: Optional[int] = None,
    lookup: Optional[MetadataLookup] = None,
) -> str:
    """Move ``UNAV_Navigator`` so its origin coincides with the
    selected waypoint. Rotation is left untouched.

    ``waypoint_index=None`` focuses on the last waypoint added (the
    common "I just added one, now look at it" workflow).
    """
    _require_c4d()
    from c4d_objects.navigation_null import find_navigator

    if len(route) == 0:
        return "Focus Navigator: route is empty."

    if waypoint_index is None:
        waypoint_index = len(route) - 1
    if not (0 <= waypoint_index < len(route)):
        return f"Focus Navigator: waypoint index {waypoint_index} out of range."

    wp = route.waypoints[waypoint_index]
    resolver = make_lookup_resolver(
        lookup if lookup is not None else default_lookup()
    )
    pos = resolver(wp)
    if pos is None:
        return (
            f"Focus Navigator: waypoint '{wp.display_label()}' has no "
            "resolvable position."
        )

    nav = find_navigator(doc)
    if nav is None:
        return "Focus Navigator: no UNAV_Navigator in scene."

    doc.StartUndo()
    try:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, nav)
        mg = nav.GetMg()
        mg.off = c4d.Vector(pos.x_c4d, pos.y_c4d, pos.z_c4d)
        nav.SetMg(mg)
    finally:
        doc.EndUndo()

    c4d.EventAdd()
    return (
        f"Focus Navigator: moved to '{wp.display_label()}' "
        f"(waypoint {waypoint_index})."
    )


# ---------------------------------------------------------------------------
# Convenience: render the panel text
# ---------------------------------------------------------------------------


def panel_text(
    route: Route,
    lookup: Optional[MetadataLookup] = None,
) -> str:
    """Compute the route summary against the active lookup and render
    it as a multi-line text block for the dialog's route panel."""
    resolver = make_lookup_resolver(
        lookup if lookup is not None else default_lookup()
    )
    summary = compute_route(route, resolver)
    return render_summary(route, summary)


def empty_panel_text() -> str:
    return (
        "No waypoints yet. Select an UNAV object in the Object Manager "
        "and click 'Add Selected Object as Waypoint'."
    )
