"""v2.0 Cinema 4D overlay builder.

Materialises the polylines + label anchors produced by
``procedural/overlays.build_overlay_bundle`` into Cinema 4D
scene objects under a single root ``UNAV_Overlays`` null.

Key contracts:

* **Idempotent.** Re-running the build with the same bundle
  reuses the same scene objects (named off a stable per-
  overlay-kind container). Two builds in a row produce one
  scene tree, not two.
* **Decoupled.** The overlays root is a sibling of the v0.1
  ``UNAV_Starfield`` root — the visible-sector pipeline never
  walks under ``UNAV_Overlays`` and the overlay builder never
  touches anything under ``UNAV_Starfield``.
* **C4D-only.** Importing this module from a non-C4D
  process is safe; every helper no-ops + returns a sentinel.

The pure-Python overlay computation lives in
``procedural/overlays.py``; tests drive that module directly.
This module is the thin c4d-bound applier.
"""

from __future__ import annotations

from typing import List, Optional

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from core.logging_util import get_logger
from procedural.overlays import (
    OVERLAY_KINDS,
    OverlayBundle,
    OverlayLabel,
    OverlayPolyline,
)

_log = get_logger("c4d_objects.overlays_builder")


#: Stable name of the root UNAV_Overlays null. The builder
#: keys off this name so a rebuild can find + replace.
OVERLAYS_ROOT_NAME: str = "UNAV_Overlays"

#: v2.1: stable name of the root UNAV_ScienceLayers null. A
#: separate sibling to ``OVERLAYS_ROOT_NAME`` so v2.0
#: navigation overlays and v2.1 science layers can coexist
#: without one builder eating the other's children.
SCIENCE_LAYERS_ROOT_NAME: str = "UNAV_ScienceLayers"

#: Stable per-kind container name. Lives directly under
#: ``OVERLAYS_ROOT_NAME``.
def _container_name(kind: str) -> str:
    return f"UNAV_Overlay_{kind}"


def _science_container_name(layer_id: str) -> str:
    """v2.1 per-layer container name. Lives under
    ``SCIENCE_LAYERS_ROOT_NAME``; the prefix is distinct from
    the v2.0 ``UNAV_Overlay_`` so a stray name collision
    can't confuse the builders."""
    return f"UNAV_ScienceLayer_{layer_id}"


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def apply_overlay_bundle(
    bundle: OverlayBundle,
    *,
    doc=None,
) -> int:
    """Materialise ``bundle`` under ``OVERLAYS_ROOT_NAME``.

    Each polyline becomes a ``c4d.SplineObject``; each label
    becomes a ``c4d.Onull`` whose name carries the label
    text. Per-kind containers are reused on re-build (the
    builder removes the previous container's children before
    re-inserting the new ones).

    Returns the total number of scene objects inserted (or
    0 when Cinema 4D isn't available).

    Empty bundle → the overlays root + every per-kind
    container is removed entirely; the scene goes back to its
    pre-overlay state.
    """
    if not _C4D_AVAILABLE:
        return 0
    if doc is None:
        try:
            from c4d import documents  # type: ignore
            doc = documents.GetActiveDocument()
        except Exception:  # noqa: BLE001
            return 0
    if doc is None:
        return 0

    # Find or create the overlays root.
    root = _find_root(doc)
    if bundle.empty():
        if root is not None:
            _remove(root)
            try:
                c4d.EventAdd()
            except Exception:  # noqa: BLE001
                pass
        return 0

    if root is None:
        root = c4d.BaseObject(c4d.Onull)
        root.SetName(OVERLAYS_ROOT_NAME)
        doc.InsertObject(root)

    # Remove every existing per-kind container so the build
    # is fully idempotent (no stale children left over from a
    # previous build with different kinds).
    _clear_overlay_containers(root)

    written = 0

    # Group polylines by kind so each kind goes into one
    # container.
    kinds_seen: List[str] = []
    polylines_by_kind: dict = {}
    for poly in bundle.polylines:
        polylines_by_kind.setdefault(poly.kind, []).append(poly)
        if poly.kind not in kinds_seen:
            kinds_seen.append(poly.kind)

    for kind in kinds_seen:
        container = c4d.BaseObject(c4d.Onull)
        container.SetName(_container_name(kind))
        container.InsertUnder(root)
        for poly in polylines_by_kind[kind]:
            obj = _spline_from_polyline(poly)
            if obj is not None:
                obj.InsertUnder(container)
                written += 1

    if bundle.labels:
        container = c4d.BaseObject(c4d.Onull)
        container.SetName(_container_name("waypoint_labels"))
        container.InsertUnder(root)
        for lbl in bundle.labels:
            obj = _null_from_label(lbl)
            if obj is not None:
                obj.InsertUnder(container)
                written += 1

    try:
        c4d.EventAdd()
    except Exception:  # noqa: BLE001
        pass
    return written


def clear_overlays(doc=None) -> bool:
    """Remove the entire ``UNAV_Overlays`` subtree from the
    active document. Returns True if the root was found and
    removed; False otherwise (or when Cinema 4D isn't
    available)."""
    if not _C4D_AVAILABLE:
        return False
    if doc is None:
        try:
            from c4d import documents  # type: ignore
            doc = documents.GetActiveDocument()
        except Exception:  # noqa: BLE001
            return False
    if doc is None:
        return False
    root = _find_root(doc)
    if root is None:
        return False
    _remove(root)
    try:
        c4d.EventAdd()
    except Exception:  # noqa: BLE001
        pass
    return True


# ---------------------------------------------------------------------------
# Helpers (c4d-bound but defensive)
# ---------------------------------------------------------------------------


def _find_root(doc):
    """Locate the existing ``UNAV_Overlays`` null in the
    document. Returns ``None`` when no such object exists."""
    if not _C4D_AVAILABLE or doc is None:
        return None
    try:
        return doc.SearchObject(OVERLAYS_ROOT_NAME)
    except Exception:  # noqa: BLE001
        return None


def _clear_overlay_containers(root) -> None:
    """Drop every per-kind container under ``root``. Keeps
    the root itself in place so the artist's parenting /
    transformations on the root survive a rebuild."""
    if not _C4D_AVAILABLE or root is None:
        return
    child = root.GetDown()
    to_remove = []
    while child is not None:
        nxt = child.GetNext()
        name = child.GetName() or ""
        if name.startswith("UNAV_Overlay_"):
            to_remove.append(child)
        child = nxt
    for obj in to_remove:
        try:
            obj.Remove()
        except Exception:  # noqa: BLE001
            _log.warning("overlays builder: failed to remove %s", obj)


def _spline_from_polyline(poly: OverlayPolyline):
    """Build a ``c4d.SplineObject`` from one polyline. Returns
    ``None`` when the polyline has fewer than 2 points (not a
    valid spline)."""
    if not _C4D_AVAILABLE:
        return None
    pts = list(poly.points)
    if len(pts) < 2:
        return None
    try:
        spline = c4d.SplineObject(len(pts), c4d.SPLINETYPE_LINEAR)
    except Exception:  # noqa: BLE001
        return None
    if poly.label:
        spline.SetName(f"{poly.label} ({poly.kind}#{poly.index})")
    else:
        spline.SetName(f"{poly.kind}#{poly.index}")
    for i, (x, y, z) in enumerate(pts):
        spline.SetPoint(i, c4d.Vector(float(x), float(y), float(z)))
    if poly.closed:
        try:
            spline[c4d.SPLINEOBJECT_CLOSED] = True
        except Exception:  # noqa: BLE001
            pass
    spline.Message(c4d.MSG_UPDATE)
    return spline


def _null_from_label(label: OverlayLabel):
    if not _C4D_AVAILABLE:
        return None
    try:
        obj = c4d.BaseObject(c4d.Onull)
    except Exception:  # noqa: BLE001
        return None
    obj.SetName(f"{label.text}")
    obj.SetRelPos(c4d.Vector(
        float(label.position[0]),
        float(label.position[1]),
        float(label.position[2]),
    ))
    return obj


def _remove(obj) -> None:
    if not _C4D_AVAILABLE or obj is None:
        return
    try:
        obj.Remove()
    except Exception:  # noqa: BLE001
        _log.warning("overlays builder: failed to remove %s", obj)


# ---------------------------------------------------------------------------
# Diagnostic helpers (pure-Python; usable in tests)
# ---------------------------------------------------------------------------


def overlays_root_name() -> str:
    """Stable name of the overlays root null. Lives here so
    tests don't have to import the constant directly."""
    return OVERLAYS_ROOT_NAME


def container_name_for_kind(kind: str) -> str:
    """Stable per-kind container name. Used by tests + by the
    diagnostics renderer."""
    return _container_name(kind)


# ---------------------------------------------------------------------------
# v2.1 science-layer applier
# ---------------------------------------------------------------------------


def apply_science_bundle(
    bundle,
    *,
    doc=None,
) -> int:
    """v2.1: materialise a ``ScienceBundle`` under
    ``UNAV_ScienceLayers``.

    Each layer's polylines + labels go into a single per-
    layer container (``UNAV_ScienceLayer_<layer_id>``).
    Per-layer containers are wiped + rebuilt on every call;
    the root null itself persists so the artist's parent
    transformations survive across rebuilds.

    Empty / all-empty-layers bundle → the entire
    ``UNAV_ScienceLayers`` subtree is removed (matches v2.0's
    overlay-builder convention).

    Returns the total number of scene objects inserted, or
    0 when Cinema 4D isn't available.
    """
    if not _C4D_AVAILABLE:
        return 0
    if doc is None:
        try:
            from c4d import documents  # type: ignore
            doc = documents.GetActiveDocument()
        except Exception:  # noqa: BLE001
            return 0
    if doc is None:
        return 0

    root = _find_science_root(doc)
    if bundle is None or bundle.empty():
        if root is not None:
            _remove(root)
            try:
                c4d.EventAdd()
            except Exception:  # noqa: BLE001
                pass
        return 0

    if root is None:
        root = c4d.BaseObject(c4d.Onull)
        root.SetName(SCIENCE_LAYERS_ROOT_NAME)
        doc.InsertObject(root)

    _clear_science_containers(root)

    written = 0
    for result in bundle.per_layer:
        if not (result.polylines or result.labels):
            continue
        container = c4d.BaseObject(c4d.Onull)
        container.SetName(_science_container_name(result.layer_id))
        container.InsertUnder(root)
        for poly in result.polylines:
            obj = _spline_from_polyline(poly)
            if obj is not None:
                obj.InsertUnder(container)
                written += 1
        for lbl in result.labels:
            obj = _null_from_label(lbl)
            if obj is not None:
                obj.InsertUnder(container)
                written += 1

    try:
        c4d.EventAdd()
    except Exception:  # noqa: BLE001
        pass
    return written


def clear_science_layers(doc=None) -> bool:
    """v2.1: remove the entire ``UNAV_ScienceLayers`` subtree
    from the active document. Returns True when the root was
    found and removed; False otherwise (or when Cinema 4D is
    unavailable). Mirrors ``clear_overlays``."""
    if not _C4D_AVAILABLE:
        return False
    if doc is None:
        try:
            from c4d import documents  # type: ignore
            doc = documents.GetActiveDocument()
        except Exception:  # noqa: BLE001
            return False
    if doc is None:
        return False
    root = _find_science_root(doc)
    if root is None:
        return False
    _remove(root)
    try:
        c4d.EventAdd()
    except Exception:  # noqa: BLE001
        pass
    return True


def science_layers_root_name() -> str:
    """v2.1: stable name of the science-layers root null."""
    return SCIENCE_LAYERS_ROOT_NAME


def container_name_for_layer(layer_id: str) -> str:
    """v2.1: stable per-layer container name. Used by tests
    + by the diagnostics renderer."""
    return _science_container_name(layer_id)


def _find_science_root(doc):
    if not _C4D_AVAILABLE or doc is None:
        return None
    try:
        return doc.SearchObject(SCIENCE_LAYERS_ROOT_NAME)
    except Exception:  # noqa: BLE001
        return None


def _clear_science_containers(root) -> None:
    """Drop every per-layer container under ``root``. Keeps
    the root itself in place so artist transformations on
    the root survive a rebuild."""
    if not _C4D_AVAILABLE or root is None:
        return
    child = root.GetDown()
    to_remove = []
    while child is not None:
        nxt = child.GetNext()
        name = child.GetName() or ""
        if name.startswith("UNAV_ScienceLayer_"):
            to_remove.append(child)
        child = nxt
    for obj in to_remove:
        try:
            obj.Remove()
        except Exception:  # noqa: BLE001
            _log.warning("science builder: failed to remove %s", obj)
