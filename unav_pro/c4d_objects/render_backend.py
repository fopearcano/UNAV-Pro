"""Render-backend interface and the built-in backends.

The v0.7 performance layer pulls "how do we put visible objects on
screen" out of ``point_cloud_builder``/``scene_sync`` and into a
small interface every backend implements:

  * ``clear(doc)`` — remove every backend-managed object from
    ``doc``.
  * ``build_visible_sector(doc, objects, encoding)`` — initial,
    full build of the visible sector.
  * ``update_visible_sector(doc, added, removed, kept, encoding)``
    — incremental update against an already-built sector.
  * ``get_object_uid_from_selection(doc, c4d_object)`` — read the
    uid off a selected node, or return ``None``.
  * ``supports_metadata_selection()`` — whether the backend's
    nodes carry enough info for the v0.1 metadata inspector to
    resolve them directly. Backends that return ``False`` rely
    on the v0.6 search-based fallback.
  * ``get_stats()`` — last-pass timings + counts the dialog can
    surface.

Three backends are shipped in v0.7:

  * ``DebugObjectsBackend`` — wraps the existing
    ``point_cloud_builder.build_point_object`` flow. The same
    one-null-per-point behaviour the plugin shipped with from v0.1.
  * ``InstanceBackend`` — lives in
    ``c4d_objects/instance_builder.py``; one shared template plus
    ``c4d.Oinstance`` children. Only re-imported here for the
    ``backend_for_mode`` factory.
  * ``PointCloudBackend`` — placeholder. Records visible uids in an
    in-memory map (so the search-based inspector can still resolve
    them) and surfaces a single placeholder marker null per cluster
    for editor visibility. No real GPU drawing yet.

This module's pure-Python parts (the dataclasses, the abstract base,
the factory) are unit-tested without Cinema 4D. The c4d-bound
build/update halves of each backend are guarded with the same
``_C4D_AVAILABLE`` pattern used elsewhere in the plugin.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from core.logging_util import get_logger
from core.render_mode import (
    DEFAULT_RENDER_MODE,
    RENDER_MODE_DEBUG_OBJECTS,
    RENDER_MODE_INSTANCES,
    RENDER_MODE_POINT_CLOUD,
    capabilities_for,
    validate_mode,
)
from data.schema import DEFAULT_SCALE_MODE, CatalogObject

_log = get_logger("c4d_objects.render_backend")


# ---------------------------------------------------------------------------
# Stats / results
# ---------------------------------------------------------------------------


@dataclass
class BackendStats:
    """What the dialog surfaces in the Render Mode info strip.

    ``last_build_seconds`` is wall-clock time for the last
    ``build_visible_sector`` or ``update_visible_sector`` call;
    ``visible_count`` is the total objects (or instances, or
    placeholder pegs) currently in the scene; ``generated_count``
    is the number of C4D nodes the backend actually created in the
    last pass (added + template, etc.). ``estimated_scene_objects``
    is what the safety advisory should treat as the scene's pending
    contribution to C4D's object total.
    """

    mode: str = DEFAULT_RENDER_MODE
    last_build_seconds: float = 0.0
    visible_count: int = 0
    generated_count: int = 0
    estimated_scene_objects: int = 0

    def short_summary(self) -> str:
        return (
            f"mode={self.mode}, visible={self.visible_count}, "
            f"generated={self.generated_count}, "
            f"scene≈{self.estimated_scene_objects}, "
            f"build={self.last_build_seconds * 1000:.0f}ms"
        )


@dataclass
class BackendUpdateResult:
    """Outcome of an ``update_visible_sector`` call."""

    added: int = 0
    removed: int = 0
    kept: int = 0
    skipped: int = 0
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class RenderBackend:
    """Abstract base class for v0.7 render backends.

    Concrete backends override ``clear``, ``build_visible_sector``,
    ``update_visible_sector``, ``get_object_uid_from_selection``, and
    ``supports_metadata_selection``. The base class implements the
    stats bookkeeping so subclasses just record their own values.
    """

    #: Stable token identifying this backend. Set by subclasses.
    mode: str = DEFAULT_RENDER_MODE

    def __init__(self) -> None:
        self._stats = BackendStats(mode=self.mode)
        self._uid_map: Dict[str, Any] = {}
        # The last list of CatalogObjects this backend built / updated
        # against, keyed by uid. Used by Point Cloud Mode's selection
        # fallback.
        self._uid_to_object: Dict[str, CatalogObject] = {}

    # ----------------------------------------------------------- contract
    def clear(self, doc) -> int:  # noqa: D401
        """Remove every backend-managed object from ``doc``. Returns
        the count removed."""
        raise NotImplementedError

    def build_visible_sector(
        self,
        doc,
        objects: Sequence[CatalogObject],
        *,
        encoding=None,
        scale_mode: str = DEFAULT_SCALE_MODE,
        max_visible: Optional[int] = None,
    ) -> BackendUpdateResult:
        """Initial (full) build of the visible sector.

        ``encoding`` is a ``VisualEncodingParams`` instance (or
        ``None`` for the schema default); the backend hands it to
        the shared visual encoder and never duplicates colour / size
        logic. ``max_visible`` is the per-mode hard cap; objects past
        it are reported in ``BackendUpdateResult.skipped``.
        """
        raise NotImplementedError

    def update_visible_sector(
        self,
        doc,
        *,
        added: Sequence[CatalogObject],
        removed_uids: Sequence[str],
        kept_uids: Sequence[str],
        encoding=None,
        scale_mode: str = DEFAULT_SCALE_MODE,
    ) -> BackendUpdateResult:
        """Incremental sync. ``added`` are freshly-visible objects to
        materialize; ``removed_uids`` are uids to drop from the scene;
        ``kept_uids`` are unchanged."""
        raise NotImplementedError

    def get_object_uid_from_selection(self, doc, c4d_object) -> Optional[str]:
        """Return the uid for ``c4d_object`` (the active selection),
        or ``None`` if the backend does not own that object or cannot
        resolve a uid for it."""
        return None

    def supports_metadata_selection(self) -> bool:
        """True iff a click in the C4D viewport / Object Manager can
        directly resolve to a uid this backend manages. Backends that
        return False rely on the search-based fallback."""
        return capabilities_for(self.mode).supports_per_object_selection

    # -------------------------------------------------------------- stats
    def get_stats(self) -> BackendStats:
        return self._stats

    def _record_stats(
        self, *, build_seconds: float, visible: int, generated: int,
        estimated_scene_objects: Optional[int] = None,
    ) -> None:
        self._stats.last_build_seconds = float(build_seconds)
        self._stats.visible_count = int(visible)
        self._stats.generated_count = int(generated)
        self._stats.estimated_scene_objects = (
            int(estimated_scene_objects)
            if estimated_scene_objects is not None
            else int(generated)
        )

    # ----------------------------------------------------- uid bookkeeping
    def remembered_uids(self) -> List[str]:
        """Return the set of uids the backend currently has in its
        sector, in insertion order. The search-based metadata
        fallback uses this."""
        return list(self._uid_to_object.keys())

    def remembered_object(self, uid: str) -> Optional[CatalogObject]:
        return self._uid_to_object.get(uid)


# ---------------------------------------------------------------------------
# Debug Objects Mode — the v0.1 behaviour, preserved
# ---------------------------------------------------------------------------


class DebugObjectsBackend(RenderBackend):
    """Backwards-compatible backend: one ``c4d.Onull`` per visible row.

    Wraps the existing ``point_cloud_builder``/``scene_sync`` flow so
    the v0.7 layer can dispatch through the same interface as the
    other backends. The marker payload, the BaseContainer handling,
    and the metadata inspector path are all unchanged.
    """

    mode = RENDER_MODE_DEBUG_OBJECTS

    def clear(self, doc) -> int:
        if not _C4D_AVAILABLE:
            return 0
        from c4d_objects.point_cloud_builder import clear_starfield
        n = clear_starfield(doc)
        self._uid_to_object.clear()
        return n

    def build_visible_sector(
        self,
        doc,
        objects: Sequence[CatalogObject],
        *,
        encoding=None,
        scale_mode: str = DEFAULT_SCALE_MODE,
        max_visible: Optional[int] = None,
    ) -> BackendUpdateResult:
        if not _C4D_AVAILABLE:
            return BackendUpdateResult(warnings=["c4d unavailable"])
        from c4d_objects.point_cloud_builder import build_starfield

        result = BackendUpdateResult()
        capped = list(objects)
        if max_visible is not None and len(capped) > max_visible:
            result.skipped = len(capped) - max_visible
            capped = capped[: max_visible]

        start = time.monotonic()
        _starfield, count = build_starfield(
            doc, capped, scale_mode=scale_mode, encoding=encoding,
            replace_existing=True,
        )
        elapsed = time.monotonic() - start

        result.added = int(count)
        result.kept = 0
        result.removed = 0

        # Remember the build for the search-based fallback.
        self._uid_to_object = {
            o.uid: o for o in capped if getattr(o, "uid", None)
        }

        self._record_stats(
            build_seconds=elapsed,
            visible=count,
            generated=count + 1,  # nulls + parent starfield
            estimated_scene_objects=count + 3,  # +visible_sector + debug_root
        )
        return result

    def update_visible_sector(
        self,
        doc,
        *,
        added: Sequence[CatalogObject],
        removed_uids: Sequence[str],
        kept_uids: Sequence[str],
        encoding=None,
        scale_mode: str = DEFAULT_SCALE_MODE,
    ) -> BackendUpdateResult:
        if not _C4D_AVAILABLE:
            return BackendUpdateResult(warnings=["c4d unavailable"])
        from c4d_objects.point_cloud_builder import (
            build_point_object,
            ensure_starfield_hierarchy,
        )
        from core.scene_sync import _current_visible_objects

        start = time.monotonic()
        _starfield, visible_sector, _debug = ensure_starfield_hierarchy(
            doc, scale_mode=scale_mode,
        )
        # Pull the currently materialized children once so the
        # backend can find c4d objects by uid for the remove pass.
        current = _current_visible_objects(visible_sector)

        result = BackendUpdateResult()
        for uid in removed_uids:
            obj = current.get(uid)
            if obj is None:
                continue
            doc.AddUndo(c4d.UNDOTYPE_DELETE, obj)
            obj.Remove()
            result.removed += 1
            self._uid_to_object.pop(uid, None)
        for src in added:
            try:
                child = build_point_object(
                    src, scale_mode=scale_mode, encoding=encoding,
                )
            except Exception:  # noqa: BLE001
                _log.exception("DebugObjectsBackend: build failed for %r", src.uid)
                result.skipped += 1
                continue
            child.InsertUnder(visible_sector)
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, child)
            result.added += 1
            self._uid_to_object[src.uid] = src
        result.kept = len(kept_uids)

        elapsed = time.monotonic() - start

        visible = result.added + result.kept
        self._record_stats(
            build_seconds=elapsed,
            visible=visible,
            generated=result.added,
            estimated_scene_objects=visible + 3,
        )
        return result

    def get_object_uid_from_selection(self, doc, c4d_object) -> Optional[str]:
        if not _C4D_AVAILABLE or c4d_object is None:
            return None
        from c4d_objects.point_cloud_builder import (
            MARKER_KEY_UID, _read_marker,
        )
        marker = _read_marker(c4d_object)
        if marker is None:
            return None
        uid = marker.get(MARKER_KEY_UID)
        return str(uid) if uid else None


# ---------------------------------------------------------------------------
# Point Cloud Mode — placeholder
# ---------------------------------------------------------------------------


class PointCloudBackend(RenderBackend):
    """Placeholder backend for the future native / GPU point renderer.

    Today's behaviour:

    * Creates a single ``UNAV_PointCloudPlaceholder`` null under the
      starfield's visible-sector parent so the editor knows something
      is there.
    * Stores ``uid → CatalogObject`` in memory so the v0.6 search
      panel and the inspector's search-based fallback can resolve a
      uid even though the cloud has no per-object selectable nodes.
    * Reports stats so the dialog can show "0 generated, N visible
      in cloud" and the artist understands the scene weight.

    The real implementation will replace
    ``build_visible_sector`` with a ``BaseDraw`` callback that pushes
    a packed buffer to the C4D viewport (and, eventually, to a native
    GPU path). This module is the contract; that work lands in v0.8+.
    See ``docs/FUTURE_GPU_POINT_RENDERER.md``.
    """

    mode = RENDER_MODE_POINT_CLOUD

    PLACEHOLDER_NAME = "UNAV_PointCloudPlaceholder"

    def clear(self, doc) -> int:
        if not _C4D_AVAILABLE:
            self._uid_to_object.clear()
            return 0
        # Remove the placeholder null if present and forget the uid map.
        from c4d_objects.point_cloud_builder import (
            KIND_VISIBLE_SECTOR,
            _find_child_by_kind,
            _read_marker,
            find_starfield,
        )
        from core.plugin_ids import BC_ID_UNAV_MARKER  # noqa: F401
        starfield = find_starfield(doc)
        n = 0
        if starfield is not None:
            visible_sector = _find_child_by_kind(starfield, KIND_VISIBLE_SECTOR)
            if visible_sector is not None:
                child = visible_sector.GetDown()
                while child is not None:
                    nxt = child.GetNext()
                    if child.GetName() == self.PLACEHOLDER_NAME:
                        child.Remove()
                        n += 1
                    child = nxt
        self._uid_to_object.clear()
        return n

    def build_visible_sector(
        self,
        doc,
        objects: Sequence[CatalogObject],
        *,
        encoding=None,
        scale_mode: str = DEFAULT_SCALE_MODE,
        max_visible: Optional[int] = None,
    ) -> BackendUpdateResult:
        result = BackendUpdateResult()
        capped = list(objects)
        if max_visible is not None and len(capped) > max_visible:
            result.skipped = len(capped) - max_visible
            capped = capped[: max_visible]

        start = time.monotonic()
        # Remember the cloud's contents so the inspector and the
        # search panel can still answer queries.
        self._uid_to_object = {
            o.uid: o for o in capped if getattr(o, "uid", None)
        }

        if _C4D_AVAILABLE:
            self._ensure_placeholder(doc, scale_mode=scale_mode, count=len(capped))

        elapsed = time.monotonic() - start
        result.added = len(capped)
        self._record_stats(
            build_seconds=elapsed,
            visible=len(capped),
            generated=1 if _C4D_AVAILABLE and capped else 0,
            estimated_scene_objects=1,
        )
        return result

    def update_visible_sector(
        self,
        doc,
        *,
        added: Sequence[CatalogObject],
        removed_uids: Sequence[str],
        kept_uids: Sequence[str],
        encoding=None,
        scale_mode: str = DEFAULT_SCALE_MODE,
    ) -> BackendUpdateResult:
        result = BackendUpdateResult()
        start = time.monotonic()
        for uid in removed_uids:
            if self._uid_to_object.pop(uid, None) is not None:
                result.removed += 1
        for src in added:
            uid = getattr(src, "uid", None)
            if not uid:
                result.skipped += 1
                continue
            self._uid_to_object[uid] = src
            result.added += 1
        result.kept = len(kept_uids)
        if _C4D_AVAILABLE:
            self._ensure_placeholder(
                doc, scale_mode=scale_mode,
                count=len(self._uid_to_object),
            )
        elapsed = time.monotonic() - start
        self._record_stats(
            build_seconds=elapsed,
            visible=len(self._uid_to_object),
            generated=0,
            estimated_scene_objects=1,
        )
        return result

    def get_object_uid_from_selection(self, doc, c4d_object) -> Optional[str]:
        # No per-object selection in cloud mode — the dialog must use
        # the search-based fallback (``_uid_to_object`` lookup driven
        # by the search panel).
        return None

    def supports_metadata_selection(self) -> bool:
        return False

    # ------------------------------------------------------------ helpers
    def _ensure_placeholder(self, doc, scale_mode: str, count: int) -> None:
        if not _C4D_AVAILABLE:
            return
        from c4d_objects.point_cloud_builder import (
            ensure_starfield_hierarchy,
            _named_kind_marker,
            _write_marker,
            KIND_POINT,
        )
        _starfield, visible_sector, _debug = ensure_starfield_hierarchy(
            doc, scale_mode=scale_mode,
        )
        # Wipe any previous placeholder and rebuild.
        child = visible_sector.GetDown()
        while child is not None:
            nxt = child.GetNext()
            if child.GetName() == self.PLACEHOLDER_NAME:
                child.Remove()
            child = nxt
        if count <= 0:
            return
        null = c4d.BaseObject(c4d.Onull)
        null.SetName(self.PLACEHOLDER_NAME)
        null[c4d.NULLOBJECT_DISPLAY] = c4d.NULLOBJECT_DISPLAY_DOT
        null[c4d.NULLOBJECT_RADIUS] = 5.0
        null[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
        null[c4d.ID_BASEOBJECT_COLOR] = c4d.Vector(0.4, 0.7, 1.0)
        _write_marker(
            null,
            _named_kind_marker(KIND_POINT, f"{self.PLACEHOLDER_NAME} ({count})"),
        )
        null.InsertUnder(visible_sector)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, null)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def backend_for_mode(mode: str) -> RenderBackend:
    """Build a fresh backend for ``mode``. Unknown tokens fall back
    to ``DEFAULT_RENDER_MODE``."""
    token = validate_mode(mode)
    if token == RENDER_MODE_INSTANCES:
        # Late import so the abstract base / debug / cloud backends
        # are usable in pytest without dragging in the c4d-bound
        # instance_builder module.
        from c4d_objects.instance_builder import InstanceBackend
        return InstanceBackend()
    if token == RENDER_MODE_POINT_CLOUD:
        return PointCloudBackend()
    return DebugObjectsBackend()
