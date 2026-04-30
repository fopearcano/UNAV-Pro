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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

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

    def short_summary(self) -> str:
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
    child = visible_sector.GetDown()
    while child is not None:
        nxt = child.GetNext()
        marker = _read_marker(child)
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
