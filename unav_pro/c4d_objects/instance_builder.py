"""Instance Mode backend.

Lighter alternative to the per-null Debug Objects mode: build one
**template** ``c4d.Onull`` per visible-sector pass and create one
``c4d.Oinstance`` per visible row. Instances share the template's
geometry and per-render data; they still have their own
position / colour / display radius and a tiny marker container
carrying just the ``uid`` so the metadata inspector can still
resolve a click.

Why ``Oinstance`` instead of ``MoGraph`` ``MatrixObject``? Two
reasons:

  * **MoGraph is paid.** The plugin must not assume the user has the
    MoGraph license; ``Oinstance`` ships with every C4D edition,
    Free / Studio / Maxon One alike.
  * **Per-instance selection works.** Each ``Oinstance`` is a real
    BaseObject with its own marker BaseContainer, so clicking it in
    the Object Manager still yields a uid the v0.1 metadata
    inspector can resolve.

The trade-off is documented in
``docs/INSTANCE_MODE_LIMITATIONS.md``: instances render lighter than
nulls but are not as light as a true GPU point buffer. The full
upgrade path lands in v0.8+ via ``PointCloudBackend``.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from core.logging_util import get_logger
from core.plugin_ids import BC_ID_UNAV_MARKER  # noqa: F401
from core.render_mode import RENDER_MODE_INSTANCES
from core.visual_encoding import VisualEncodingParams, encode as encode_visuals
from data.schema import (
    DEFAULT_SCALE_MODE,
    CatalogObject,
    compute_derived_fields,
    display_color_for,
    render_radius_from_magnitude,
)

_log = get_logger("c4d_objects.instance_builder")

#: Name of the (single) shared template null. Lives under the
#: starfield's debug root so it does not leak into the visible-sector
#: child count or the safety advisory.
INSTANCE_TEMPLATE_NAME = "UNAV_InstanceTemplate"

#: Multiplier matching ``point_cloud_builder.NULL_RADIUS_SCALE`` so
#: the two backends produce visually-identical dots at the same
#: encoding params.
NULL_RADIUS_SCALE = 2.0


# ---------------------------------------------------------------------------
# Pure helpers (no c4d dependency, fully unit-tested)
# ---------------------------------------------------------------------------


def encoded_color_radius(
    obj: CatalogObject,
    encoding: Optional[VisualEncodingParams],
) -> Tuple[Tuple[float, float, float], float]:
    """Run the shared visual encoder for ``obj`` and return
    ``((r, g, b), radius)`` in C4D-native units.

    This helper is the *only* entry point the InstanceBackend uses
    for colour / radius decisions, so it cannot diverge from the
    DebugObjectsBackend's path: both delegate to
    ``core.visual_encoding.encode``.
    """
    if encoding is None:
        # Mirror point_cloud_builder's "natural" path so a freshly
        # constructed object renders identically across backends.
        from c4d_objects.point_cloud_builder import (
            color_for_object, radius_for_object,
        )
        rgb = color_for_object(obj)
        radius = radius_for_object(obj)
        return rgb, radius

    rgb_int, raw_radius = encode_visuals(obj, encoding)
    rgb = (
        max(0.0, min(1.0, rgb_int[0] / 255.0)),
        max(0.0, min(1.0, rgb_int[1] / 255.0)),
        max(0.0, min(1.0, rgb_int[2] / 255.0)),
    )
    radius = float(raw_radius) * NULL_RADIUS_SCALE
    return rgb, radius


def position_for(obj: CatalogObject, scale_mode: str = DEFAULT_SCALE_MODE) -> Tuple[float, float, float]:
    """Return the C4D world-space position for ``obj``."""
    if (
        obj.c4d_x is not None
        and obj.c4d_y is not None
        and obj.c4d_z is not None
        and scale_mode == DEFAULT_SCALE_MODE
    ):
        return float(obj.c4d_x), float(obj.c4d_y), float(obj.c4d_z)
    compute_derived_fields(obj, scale_mode=scale_mode)
    return float(obj.c4d_x), float(obj.c4d_y), float(obj.c4d_z)


def instance_marker_payload(uid: str) -> Dict[int, Any]:
    """Minimal marker for an instance. Carries just enough for the
    inspector to resolve a click via the active ``MetadataLookup``.

    Deliberately omits ``name``/``catalog_source``/``object_type``
    that the DebugObjects backend stuffs into the marker — those
    fields are pulled fresh from the lookup when the inspector runs.
    """
    from c4d_objects.point_cloud_builder import (
        MARKER_KEY_IS_UNAV,
        MARKER_KEY_KIND,
        MARKER_KEY_UID,
        MARKER_KEY_SCHEMA_VERSION,
        KIND_POINT,
    )
    return {
        MARKER_KEY_IS_UNAV: True,
        MARKER_KEY_KIND: KIND_POINT,
        MARKER_KEY_UID: uid or "",
        MARKER_KEY_SCHEMA_VERSION: 1,
    }


# ---------------------------------------------------------------------------
# C4D-bound implementation
# ---------------------------------------------------------------------------


def _require_c4d() -> None:
    if not _C4D_AVAILABLE:
        raise RuntimeError(
            "instance_builder requires Cinema 4D; this code path is "
            "unavailable outside the C4D host."
        )


def _ensure_template(doc: "c4d.documents.BaseDocument") -> "c4d.BaseObject":
    """Return (creating if necessary) the shared ``Oinstance`` template
    null. Lives under the starfield's debug root so it does not show
    up in the visible-sector count."""
    _require_c4d()
    from c4d_objects.point_cloud_builder import (
        KIND_DEBUG_ROOT, _find_child_by_kind, ensure_starfield_hierarchy,
        _named_kind_marker, _write_marker, KIND_POINT,
    )
    _starfield, _visible, debug_root = ensure_starfield_hierarchy(doc)
    # Search by name first (deterministic across versions).
    child = debug_root.GetDown()
    while child is not None:
        if child.GetName() == INSTANCE_TEMPLATE_NAME:
            return child
        child = child.GetNext()
    template = c4d.BaseObject(c4d.Onull)
    template.SetName(INSTANCE_TEMPLATE_NAME)
    template[c4d.NULLOBJECT_DISPLAY] = c4d.NULLOBJECT_DISPLAY_DOT
    template[c4d.NULLOBJECT_RADIUS] = 1.0
    # Hidden in editor + render — only the instances are user-visible.
    template[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = c4d.MODE_OFF
    template[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = c4d.MODE_OFF
    _write_marker(
        template,
        _named_kind_marker(KIND_POINT, INSTANCE_TEMPLATE_NAME),
    )
    template.InsertUnder(debug_root)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, template)
    return template


def _build_instance(
    obj: CatalogObject,
    template: "c4d.BaseObject",
    *,
    scale_mode: str,
    encoding: Optional[VisualEncodingParams],
) -> "c4d.BaseObject":
    """Create one ``Oinstance`` for ``obj``. Not yet inserted."""
    _require_c4d()
    from c4d_objects.point_cloud_builder import _write_marker

    inst = c4d.BaseObject(c4d.Oinstance)
    inst.SetName(obj.common_name or obj.name or obj.uid or "instance")
    inst[c4d.INSTANCEOBJECT_LINK] = template

    x, y, z = position_for(obj, scale_mode=scale_mode)
    inst.SetAbsPos(c4d.Vector(x, y, z))

    rgb, radius = encoded_color_radius(obj, encoding)
    # Per-instance colour. Available on every C4D edition.
    inst[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
    inst[c4d.ID_BASEOBJECT_COLOR] = c4d.Vector(*rgb)
    # Per-instance radius via local scale on the instance — the
    # template's radius is the unit dot, instance scale modulates it.
    if radius > 0:
        inst.SetRelScale(c4d.Vector(radius, radius, radius))

    _write_marker(inst, instance_marker_payload(obj.uid))
    return inst


def _current_instances(
    visible_sector: "c4d.BaseObject",
) -> Dict[str, "c4d.BaseObject"]:
    """Walk the visible-sector children and return ``{uid: instance}``.

    Mirrors ``scene_sync._current_visible_objects`` but is local to
    the instance builder so the two backends stay decoupled.
    """
    _require_c4d()
    from c4d_objects.point_cloud_builder import (
        KIND_POINT, MARKER_KEY_KIND, MARKER_KEY_UID, _read_marker,
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
# Backend
# ---------------------------------------------------------------------------


# Late import so this module can be imported from tests without the
# whole render_backend chain firing.
from c4d_objects.render_backend import (  # noqa: E402
    BackendStats, BackendUpdateResult, RenderBackend,
)


class InstanceBackend(RenderBackend):
    """Render backend that uses ``c4d.Oinstance`` per visible row."""

    mode = RENDER_MODE_INSTANCES

    def clear(self, doc) -> int:
        """Remove every UNAV-managed object from ``doc``. Mirrors
        ``DebugObjectsBackend.clear`` so a mode switch is a single
        clear-and-rebuild."""
        if not _C4D_AVAILABLE:
            self._uid_to_object.clear()
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
        encoding: Optional[VisualEncodingParams] = None,
        scale_mode: str = DEFAULT_SCALE_MODE,
        max_visible: Optional[int] = None,
    ) -> BackendUpdateResult:
        if not _C4D_AVAILABLE:
            return BackendUpdateResult(warnings=["c4d unavailable"])
        from c4d_objects.point_cloud_builder import (
            ensure_starfield_hierarchy, clear_starfield,
        )

        result = BackendUpdateResult()
        capped = list(objects)
        if max_visible is not None and len(capped) > max_visible:
            result.skipped = len(capped) - max_visible
            capped = capped[: max_visible]

        start = time.monotonic()
        doc.StartUndo()
        try:
            removed = clear_starfield(doc, _within_undo=True)
            if removed:
                _log.info("Removed %d pre-existing UNAV objects.", removed)
            _starfield, visible_sector, _debug = ensure_starfield_hierarchy(
                doc, scale_mode=scale_mode,
            )
            template = _ensure_template(doc)
            for src in capped:
                try:
                    inst = _build_instance(
                        src, template,
                        scale_mode=scale_mode, encoding=encoding,
                    )
                except Exception:  # noqa: BLE001 — never let one bad row stop the build
                    _log.exception(
                        "InstanceBackend: build failed for uid=%r",
                        getattr(src, "uid", None),
                    )
                    result.skipped += 1
                    continue
                inst.InsertUnder(visible_sector)
                doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, inst)
                result.added += 1
        finally:
            doc.EndUndo()

        c4d.EventAdd()
        elapsed = time.monotonic() - start

        self._uid_to_object = {
            o.uid: o for o in capped if getattr(o, "uid", None)
        }
        # Generated count = instances + 1 template + 3 hierarchy nulls.
        self._record_stats(
            build_seconds=elapsed,
            visible=result.added,
            generated=result.added + 1,
            estimated_scene_objects=result.added + 4,
        )
        return result

    def update_visible_sector(
        self,
        doc,
        *,
        added: Sequence[CatalogObject],
        removed_uids: Sequence[str],
        kept_uids: Sequence[str],
        encoding: Optional[VisualEncodingParams] = None,
        scale_mode: str = DEFAULT_SCALE_MODE,
    ) -> BackendUpdateResult:
        if not _C4D_AVAILABLE:
            return BackendUpdateResult(warnings=["c4d unavailable"])
        from c4d_objects.point_cloud_builder import ensure_starfield_hierarchy

        start = time.monotonic()
        _starfield, visible_sector, _debug = ensure_starfield_hierarchy(
            doc, scale_mode=scale_mode,
        )
        template = _ensure_template(doc)
        current = _current_instances(visible_sector)

        result = BackendUpdateResult()
        for uid in removed_uids:
            inst = current.get(uid)
            if inst is None:
                continue
            doc.AddUndo(c4d.UNDOTYPE_DELETE, inst)
            inst.Remove()
            result.removed += 1
            self._uid_to_object.pop(uid, None)
        for src in added:
            try:
                inst = _build_instance(
                    src, template,
                    scale_mode=scale_mode, encoding=encoding,
                )
            except Exception:  # noqa: BLE001
                _log.exception(
                    "InstanceBackend: build failed for uid=%r",
                    getattr(src, "uid", None),
                )
                result.skipped += 1
                continue
            inst.InsertUnder(visible_sector)
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, inst)
            result.added += 1
            self._uid_to_object[src.uid] = src
        result.kept = len(kept_uids)

        elapsed = time.monotonic() - start

        visible = result.added + result.kept
        self._record_stats(
            build_seconds=elapsed,
            visible=visible,
            generated=result.added,
            estimated_scene_objects=visible + 4,
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
