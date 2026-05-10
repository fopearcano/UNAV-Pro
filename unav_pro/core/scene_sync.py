"""Diff-and-update sync between the navigator's filtered set and the
materialized C4D scene.

The plugin's pro workflow is *update in place*: when the user clicks
**Sync Visible Sector**, the scene transitions to match the current
navigator pose without tearing down everything that survived the
filter. Concretely:

  * Objects whose uid is still visible — **kept**, untouched.
  * Objects whose uid is no longer visible — **removed**.
  * Newly visible objects — **added**.

This keeps Cinema 4D's selection / animation / per-object tags
intact across iterations and is dramatically faster than a clear-and-
rebuild for scenes where the navigator only nudged a little.

Hierarchy
---------

::

    UNAV_Starfield                 (root)
    ├── UNAV_VisibleSector         (null — the materialized point set)
    │   ├── point object (uid=...)
    │   └── ...
    └── UNAV_Debug                 (null — debug visualizations)
        └── debug cone             (optional)

The diff lives entirely under ``UNAV_VisibleSector`` so the debug
helpers, the navigator hierarchy, and any user content elsewhere in
the scene are never touched.

C4D guard
---------

Pure helpers (``compute_diff``, ``SyncDiff``) are stdlib-only and
unit-tested without a host. ``sync_visible_sector`` and the debug-
cone updater are c4d-bound and raise ``RuntimeError`` outside the
host so the dialog can route the failure to a friendly status line.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from core.logging_util import get_logger
from data.schema import (
    DEFAULT_SCALE_MODE,
    SCALE_MODES,
    CatalogObject,
)

_log = get_logger("core.scene_sync")

DEBUG_CONE_NAME = "UNAV_DebugCone"


# ---------------------------------------------------------------------------
# Pure diff
# ---------------------------------------------------------------------------


@dataclass
class SyncDiff:
    """Result of a sync pass. Pure data; no c4d types.

    ``backend_stats`` and ``backend_mode`` are populated by the
    v0.7 dispatch path (``sync_visible_sector`` on this module) and
    let the dialog show "mode=instances, build=42 ms, scene≈12 003"
    without re-querying the backend.
    """

    added_uids: List[str] = field(default_factory=list)
    kept_uids: List[str] = field(default_factory=list)
    removed_uids: List[str] = field(default_factory=list)
    capped_uids: int = 0
    backend_mode: Optional[str] = None
    backend_stats: Optional["object"] = None

    @property
    def total_visible(self) -> int:
        return len(self.added_uids) + len(self.kept_uids)

    @property
    def is_unchanged(self) -> bool:
        """v3.0: True iff nothing was added or removed (and the
        cap didn't kick in). Lets the C4D dispatch skip the
        backend round-trip when the artist nudged the navigator
        within the same sector and the visible set is identical."""
        return (
            not self.added_uids
            and not self.removed_uids
            and not self.capped_uids
        )

    def short_summary(self) -> str:
        if self.is_unchanged:
            return f"unchanged ({len(self.kept_uids)} visible)"
        parts = [
            f"+{len(self.added_uids)} added",
            f"={len(self.kept_uids)} kept",
            f"-{len(self.removed_uids)} removed",
        ]
        if self.capped_uids:
            parts.append(f"{self.capped_uids} capped")
        return ", ".join(parts)


def compute_diff(
    current_uids: Iterable[str],
    wanted_uids: Sequence[str],
    max_visible: Optional[int] = None,
) -> SyncDiff:
    """Compute the add/keep/remove sets between currently materialized
    uids and the freshly-filtered desired set.

    The ``wanted_uids`` ordering matters: the ``max_visible`` cap, if
    set, drops everything *past* the first ``max_visible`` entries —
    which is correct because the filter already sorted by distance or
    brightness. Anything dropped by the cap is reported in
    ``capped_uids``.
    """
    current_set = {u for u in current_uids if u}
    seen: set = set()
    new_in_order: List[str] = []
    for uid in wanted_uids:
        if not uid or uid in seen:
            continue
        seen.add(uid)
        new_in_order.append(uid)

    capped = 0
    if max_visible is not None and max_visible >= 0:
        if len(new_in_order) > max_visible:
            capped = len(new_in_order) - max_visible
            new_in_order = new_in_order[:max_visible]

    new_set = set(new_in_order)
    kept = sorted(current_set & new_set)
    added = [u for u in new_in_order if u not in current_set]
    removed = sorted(current_set - new_set)

    return SyncDiff(
        added_uids=added,
        kept_uids=kept,
        removed_uids=removed,
        capped_uids=capped,
    )


# ---------------------------------------------------------------------------
# C4D-bound: visible-sector membership
# ---------------------------------------------------------------------------


def _require_c4d() -> None:
    if not _C4D_AVAILABLE:
        raise RuntimeError(
            "scene_sync requires Cinema 4D; this code path is "
            "unavailable outside the C4D host."
        )


def _current_visible_objects(
    visible_sector: "c4d.BaseObject",
) -> Dict[str, "c4d.BaseObject"]:
    """Walk the immediate children of ``UNAV_VisibleSector`` and
    return ``{uid: c4d_object}`` for every UNAV point object."""
    _require_c4d()
    from c4d_objects.point_cloud_builder import (
        KIND_POINT,
        MARKER_KEY_KIND,
        MARKER_KEY_UID,
        _read_marker,
    )

    out: Dict[str, "c4d.BaseObject"] = {}
    # v1.7: defensive walk. ``GetNext`` is sampled before
    # ``_read_marker`` so a child node that gets pruned during
    # iteration (rare but possible during a back-to-back sync
    # or a render-mode switch race) doesn't break the chain.
    # Marker reads on half-torn-down nodes are caught and
    # logged at warning level; the walk continues.
    child = visible_sector.GetDown()
    while child is not None:
        nxt = child.GetNext()
        try:
            marker = _read_marker(child)
        except Exception as exc:  # noqa: BLE001 — c4d boundary
            _log.warning(
                "Scene-walk: skipping unreadable child: %s", exc,
            )
            child = nxt
            continue
        if (
            marker is not None
            and marker.get(MARKER_KEY_KIND) == KIND_POINT
        ):
            uid = str(marker.get(MARKER_KEY_UID) or "")
            if uid:
                out[uid] = child
        child = nxt
    return out


# ---------------------------------------------------------------------------
# C4D-bound: debug cone
# ---------------------------------------------------------------------------


def _params_for_navigator(navigator: "c4d.BaseObject"):
    """Best-effort read of the navigator's filter params. Falls back
    to defaults so a missing or new navigator does not crash sync."""
    _require_c4d()
    try:
        from c4d_objects.navigation_null import (
            get_navigation_filter_params,
        )

        return get_navigation_filter_params(navigator=navigator)
    except Exception:  # noqa: BLE001
        from core.navigation_state import NavigationParams

        return NavigationParams()


def _remove_debug_cone(debug_root: "c4d.BaseObject") -> bool:
    """Remove the debug cone if present. Returns True iff something
    was removed."""
    _require_c4d()
    from c4d_objects.point_cloud_builder import (
        KIND_DEBUG_CONE,
        _find_child_by_kind,
    )

    existing = _find_child_by_kind(debug_root, KIND_DEBUG_CONE)
    if existing is None:
        return False
    existing.Remove()
    return True


def _build_debug_cone(
    doc: "c4d.documents.BaseDocument",
    debug_root: "c4d.BaseObject",
    navigator: "c4d.BaseObject",
) -> Optional["c4d.BaseObject"]:
    """Create or replace the debug cone under ``debug_root``.

    The cone has its apex at the navigator's origin and points along
    the navigator's local **−Z** (forward). Its dimensions come from
    the navigator's ``cone_angle_deg``, ``far_clip_parsec`` and
    ``c4d_scale`` user-data slots. Render visibility is forced off so
    the cone never leaks into final output; editor visibility stays
    on.
    """
    _require_c4d()
    from c4d_objects.point_cloud_builder import (
        KIND_DEBUG_CONE,
        _named_kind_marker,
        _write_marker,
    )

    params = _params_for_navigator(navigator)
    scale_factor = SCALE_MODES.get(params.c4d_scale, SCALE_MODES[DEFAULT_SCALE_MODE])
    height_c4d = max(0.001, float(params.far_clip_parsec) * scale_factor)
    half_angle_rad = math.radians(
        max(0.001, min(89.99, float(params.cone_angle_deg)))
    )
    bottom_radius = height_c4d * math.tan(half_angle_rad)

    _remove_debug_cone(debug_root)

    cone = c4d.BaseObject(c4d.Ocone)
    cone.SetName(DEBUG_CONE_NAME)
    cone[c4d.PRIM_CONE_TRADIUS] = 0.0
    cone[c4d.PRIM_CONE_BRADIUS] = bottom_radius
    cone[c4d.PRIM_CONE_HEIGHT] = height_c4d
    # Apex at origin; primitive cones are centred along their axis, so
    # we shift the cone backward along its axis by half its height to
    # put the apex at (0,0,0) in local space.
    cone[c4d.PRIM_AXIS] = c4d.PRIM_AXIS_NZ
    cone.SetRelPos(c4d.Vector(0.0, 0.0, -height_c4d * 0.5))

    # Visual style: visible in editor, invisible to renderers.
    cone[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = c4d.MODE_OFF
    cone[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
    cone[c4d.ID_BASEOBJECT_COLOR] = c4d.Vector(0.95, 0.55, 0.20)

    _write_marker(cone, _named_kind_marker(KIND_DEBUG_CONE, DEBUG_CONE_NAME))

    # Wrap in an extra null so we can position the apex at the
    # navigator's pose without competing with the cone's own
    # primitive offset.
    holder = c4d.BaseObject(c4d.Onull)
    holder.SetName(f"{DEBUG_CONE_NAME}_pose")
    holder.SetMg(navigator.GetMg())
    _write_marker(holder, _named_kind_marker(KIND_DEBUG_CONE, DEBUG_CONE_NAME))

    cone.InsertUnder(holder)
    holder.InsertUnder(debug_root)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, holder)
    return holder


def update_debug_cone(
    doc: "c4d.documents.BaseDocument",
    show: bool,
) -> str:
    """Public-facing helper: toggle the debug cone for the active
    navigator. Returns a status string suitable for the dialog log."""
    _require_c4d()
    from c4d_objects.navigation_null import find_navigator
    from c4d_objects.point_cloud_builder import ensure_starfield_hierarchy

    navigator = find_navigator(doc)
    if not show:
        debug_root = None
        from c4d_objects.point_cloud_builder import find_debug_root

        debug_root = find_debug_root(doc)
        if debug_root is None:
            return "Debug cone: none in scene."
        removed = _remove_debug_cone(debug_root)
        c4d.EventAdd()
        return "Debug cone: hidden." if removed else "Debug cone: none in scene."

    if navigator is None:
        return "Debug cone: no UNAV_Navigator in scene."

    _, _visible, debug_root = ensure_starfield_hierarchy(doc)
    doc.StartUndo()
    try:
        _build_debug_cone(doc, debug_root, navigator)
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    return "Debug cone: shown."


# ---------------------------------------------------------------------------
# C4D-bound: top-level sync
# ---------------------------------------------------------------------------


def sync_visible_sector(
    doc: "c4d.documents.BaseDocument",
    objects: Sequence[CatalogObject],
    encoding=None,
    scale_mode: str = DEFAULT_SCALE_MODE,
    max_visible: Optional[int] = None,
    show_debug_cone: bool = False,
    render_mode: Optional[str] = None,
    backend: Optional[object] = None,
) -> SyncDiff:
    """Add/keep/remove the visible-sector children to match
    ``objects``.

    ``objects`` must already be filter results — this routine does
    not call into ``spatial_filter``. The caller (typically the
    dialog or ``mock_actions``) is responsible for filtering against
    the navigator beforehand.

    ``render_mode`` (v0.7) selects which backend materialises the
    sector. ``None`` keeps the v0.6 behaviour
    (``debug_objects``-equivalent) so callers that have not been
    updated yet continue to work. ``backend`` is an explicit backend
    instance for tests that want to inject a fake — the typical
    runtime path is to pass ``render_mode`` and let the factory build
    a fresh backend.

    Returns the ``SyncDiff`` summary. The whole pass runs inside an
    undo block so a single Ctrl-Z reverts every add and remove.
    """
    _require_c4d()
    from c4d_objects.navigation_null import find_navigator
    from c4d_objects.point_cloud_builder import ensure_starfield_hierarchy

    _starfield, visible_sector, debug_root = ensure_starfield_hierarchy(
        doc, scale_mode=scale_mode,
    )

    if backend is None:
        from c4d_objects.render_backend import backend_for_mode
        from core.render_mode import DEFAULT_RENDER_MODE, validate_mode

        token = validate_mode(render_mode) if render_mode else DEFAULT_RENDER_MODE
        backend = backend_for_mode(token)

    # Collect what is already in the scene under whichever backend
    # owns the sector. We use the legacy reader so a backend switch
    # cleans up the previous backend's children before we rebuild.
    current = _current_visible_objects(visible_sector)
    wanted_uids = [str(o.uid) for o in objects if getattr(o, "uid", None)]
    diff = compute_diff(current.keys(), wanted_uids, max_visible=max_visible)

    if diff.capped_uids:
        _log.warning(
            "Sync: max_visible=%d capped %d new uids.",
            max_visible, diff.capped_uids,
        )

    by_uid = {str(o.uid): o for o in objects if getattr(o, "uid", None)}
    added_objects = [
        by_uid[u] for u in diff.added_uids if u in by_uid
    ]

    backend.update_visible_sector(
        doc,
        added=added_objects,
        removed_uids=diff.removed_uids,
        kept_uids=diff.kept_uids,
        encoding=encoding,
        scale_mode=scale_mode,
    )
    diff.backend_mode = getattr(backend, "mode", None)
    diff.backend_stats = backend.get_stats()

    # Debug cone — request driven, not implicit.
    doc.StartUndo()
    try:
        if show_debug_cone:
            navigator = find_navigator(doc)
            if navigator is not None:
                _build_debug_cone(doc, debug_root, navigator)
        else:
            _remove_debug_cone(debug_root)
    finally:
        doc.EndUndo()

    c4d.EventAdd()
    _log.info(
        "Sync visible sector: %s (kept=%d, total=%d, mode=%s).",
        diff.short_summary(),
        len(diff.kept_uids),
        diff.total_visible,
        getattr(backend, "mode", "?"),
    )
    return diff


# ---------------------------------------------------------------------------
# v3.0: partial-rebuild planning
# ---------------------------------------------------------------------------


@dataclass
class OverlayRebuildPlan:
    """Result of comparing two ``OverlaySettings`` snapshots.

    The C4D builder uses ``rebuild_required`` to decide whether
    to tear the overlays down and rebuild from scratch
    (the v2.0 behaviour) or short-circuit and leave the existing
    geometry alone (the v3.0 fast path).
    """

    rebuild_required: bool = False
    changed_kinds: List[str] = field(default_factory=list)
    geometry_dirty: bool = False
    visibility_only: bool = False
    reason: str = ""


def plan_overlay_rebuild(
    previous: Optional[Any],
    current: Optional[Any],
) -> OverlayRebuildPlan:
    """Compare two ``OverlaySettings`` snapshots and decide
    whether the overlays need a rebuild.

    Pure helper; no c4d. ``previous`` is ``None`` on first run,
    in which case the plan always reports ``rebuild_required``.

    The fields driving rebuild are: any ``show_*`` flag flip
    (visibility only — cheap rebuild), and any geometry knob
    change (``radius_pc``, ``segment_count``, ``grid_step_pc``,
    ``grid_extent_pc``, ``distance_ring_radii_pc``,
    ``corridor_width_pc``, ``label_height_pc``, ``opacity``).
    """
    if previous is None and current is None:
        return OverlayRebuildPlan(
            rebuild_required=False, reason="no overlays in either state",
        )
    if previous is None or current is None:
        return OverlayRebuildPlan(
            rebuild_required=True,
            geometry_dirty=True,
            reason="overlay state appeared or disappeared",
        )

    visibility_fields = (
        "show_grid", "show_galactic_plane", "show_ecliptic_plane",
        "show_distance_rings", "show_sector_cone",
        "show_route_corridor", "show_waypoint_labels",
    )
    geometry_fields = (
        "radius_pc", "segment_count", "grid_step_pc",
        "grid_extent_pc", "corridor_width_pc",
        "label_height_pc", "opacity",
    )

    changed_kinds: List[str] = []
    for fname in visibility_fields:
        if getattr(previous, fname, None) != getattr(current, fname, None):
            changed_kinds.append(fname.replace("show_", ""))

    geometry_dirty = False
    for fname in geometry_fields:
        if getattr(previous, fname, None) != getattr(current, fname, None):
            geometry_dirty = True
            break

    prev_rings = list(getattr(previous, "distance_ring_radii_pc", []) or [])
    cur_rings = list(getattr(current, "distance_ring_radii_pc", []) or [])
    if prev_rings != cur_rings:
        geometry_dirty = True

    if not changed_kinds and not geometry_dirty:
        return OverlayRebuildPlan(
            rebuild_required=False,
            reason="overlay settings unchanged",
        )

    visibility_only = bool(changed_kinds) and not geometry_dirty
    return OverlayRebuildPlan(
        rebuild_required=True,
        changed_kinds=changed_kinds,
        geometry_dirty=geometry_dirty,
        visibility_only=visibility_only,
        reason=(
            "visibility flag(s) toggled"
            if visibility_only
            else "geometry parameters changed"
        ),
    )


@dataclass
class ScienceRebuildPlan:
    """Same shape as ``OverlayRebuildPlan`` for science layers."""

    rebuild_required: bool = False
    changed_kinds: List[str] = field(default_factory=list)
    reason: str = ""


def plan_science_rebuild(
    previous: Optional[Any],
    current: Optional[Any],
) -> ScienceRebuildPlan:
    """Compare two ``ScienceLayerSettings`` snapshots.

    Each ``show_*`` flag flip triggers a rebuild for that
    kind only — the C4D builder can preserve other kinds'
    children. Numeric parameter changes (``shell_radii_pc``,
    ``vector_scale``, etc.) trigger a full rebuild because
    the geometry is shell- / arrow- / region-shaped per
    setting.
    """
    if previous is None and current is None:
        return ScienceRebuildPlan(reason="no science state in either")
    if previous is None or current is None:
        return ScienceRebuildPlan(
            rebuild_required=True, reason="science state appeared or disappeared",
        )

    visibility_fields = (
        "show_distance_shells", "show_redshift_shells",
        "show_magnitude_shells", "show_motion_vectors",
        "show_catalog_source_regions", "show_solar_system_orbits",
        "show_constellation_boundaries", "show_object_density_volume",
    )
    changed: List[str] = []
    for fname in visibility_fields:
        if getattr(previous, fname, None) != getattr(current, fname, None):
            changed.append(fname.replace("show_", ""))

    # Any field that isn't a visibility flag is a parameter
    # field; we treat any change as a full rebuild trigger
    # rather than a per-kind rebuild.
    all_prev = {
        f: getattr(previous, f, None)
        for f in dir(previous)
        if not f.startswith("_") and not callable(getattr(previous, f))
    }
    all_cur = {
        f: getattr(current, f, None)
        for f in dir(current)
        if not f.startswith("_") and not callable(getattr(current, f))
    }
    parameters_dirty = False
    for fname in set(all_prev) | set(all_cur):
        if fname in visibility_fields:
            continue
        if all_prev.get(fname) != all_cur.get(fname):
            parameters_dirty = True
            break

    if not changed and not parameters_dirty:
        return ScienceRebuildPlan(reason="science settings unchanged")

    return ScienceRebuildPlan(
        rebuild_required=True,
        changed_kinds=changed,
        reason=(
            "science visibility flag(s) toggled"
            if changed and not parameters_dirty
            else "science parameter(s) changed"
        ),
    )


@dataclass
class MissionUpdatePlan:
    """Result of comparing two ``Mission`` snapshots.

    The C4D mission-preview builder uses this to decide whether
    to rebuild the spline + label nulls. ``waypoint_changes``
    lists (index, kind) tuples for inspector logging.
    """

    rebuild_required: bool = False
    waypoint_changes: List[Tuple[int, str]] = field(default_factory=list)
    title_changed: bool = False
    description_changed: bool = False
    reason: str = ""


def _waypoint_signature(wp: Any) -> Tuple:
    """Stable signature of a mission waypoint for comparison.

    Pulls only the path-affecting fields. Tags / notes don't
    affect the spline so they're excluded; rebuilding the
    preview because the artist edited a note would be wasteful.
    """
    return (
        getattr(wp, "kind", None),
        getattr(wp, "uid", None),
        getattr(wp, "label", None),
        getattr(wp, "x_c4d", None),
        getattr(wp, "y_c4d", None),
        getattr(wp, "z_c4d", None),
        getattr(wp, "duration_seconds", None),
        getattr(wp, "epoch_jd", None),
    )


def plan_mission_update(
    previous: Optional[Any],
    current: Optional[Any],
) -> MissionUpdatePlan:
    """Compare two ``Mission`` snapshots and report the
    minimum rebuild scope.

    ``waypoint_changes`` reports per-index transitions —
    ``"added"``, ``"removed"``, or ``"changed"``. The
    C4D builder can use this to decide whether to rebuild
    just the affected waypoint nulls or the whole spline.
    """
    if previous is None and current is None:
        return MissionUpdatePlan(reason="no mission in either state")
    if previous is None or current is None:
        return MissionUpdatePlan(
            rebuild_required=True,
            reason="mission appeared or disappeared",
        )

    title_changed = getattr(previous, "title", None) != getattr(current, "title", None)
    desc_changed = getattr(previous, "description", None) != getattr(current, "description", None)

    prev_wps = list(getattr(previous, "waypoints", []) or [])
    cur_wps = list(getattr(current, "waypoints", []) or [])

    changes: List[Tuple[int, str]] = []
    n = max(len(prev_wps), len(cur_wps))
    for i in range(n):
        prev_sig = _waypoint_signature(prev_wps[i]) if i < len(prev_wps) else None
        cur_sig = _waypoint_signature(cur_wps[i]) if i < len(cur_wps) else None
        if prev_sig is None and cur_sig is not None:
            changes.append((i, "added"))
        elif cur_sig is None and prev_sig is not None:
            changes.append((i, "removed"))
        elif prev_sig != cur_sig:
            changes.append((i, "changed"))

    rebuild = bool(changes)
    if not rebuild and not title_changed and not desc_changed:
        return MissionUpdatePlan(reason="mission unchanged")

    return MissionUpdatePlan(
        rebuild_required=rebuild,
        waypoint_changes=changes,
        title_changed=title_changed,
        description_changed=desc_changed,
        reason=(
            "waypoint(s) changed"
            if rebuild
            else "metadata only (title/description); preview unaffected"
        ),
    )
