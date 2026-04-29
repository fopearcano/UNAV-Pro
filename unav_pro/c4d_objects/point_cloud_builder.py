"""Build a Cinema 4D point cloud from a UNAV catalog.

Strategy (MVP, ≤ 10 k objects)
------------------------------

Each catalog row becomes a single ``c4d.Onull`` whose display style is
set to a small dot. Nulls are the lightest cross-version primitive in
the C4D Python API: they have no geometry, no normals, no UV maps, and
are still selectable, taggable, and parentable. All UNAV nulls are
parented under one ``UNAV_Starfield`` null so the user can hide /
delete the entire field with a single click.

Per-object metadata (``uid``, ``catalog_source``, ``object_type``,
``name``, ``metadata_json``, plus core astrometry) is stored in a
sub-``BaseContainer`` at ``BC_ID_UNAV_MARKER`` on each object. This is
the same mechanism C4D uses for built-in object data — it round-trips
through ``.c4d`` save/load and is visible to any future inspector.

Larger fields (10 k → 1 M points) require switching from per-object
nulls to a single ``MatrixObject`` (instance matrix array) or a custom
``BaseDraw`` callback drawing a packed point buffer; see
``docs/POINT_CLOUD_GENERATION.md``. The MVP keeps to nulls because they
are correct and obvious; performance migration is a separate track.

This module is c4d-guarded so it can be imported during pytest. Pure
helpers (color, radius, marker payload, position) are exported and
unit-tested directly. The C4D-bound helpers raise a clean
``RuntimeError`` if invoked outside Cinema 4D.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from core.logging_util import get_logger
from core.plugin_ids import BC_ID_UNAV_MARKER
from core.visual_encoding import VisualEncodingParams, encode as encode_visuals
from data.schema import (
    DEFAULT_SCALE_MODE,
    CatalogObject,
    compute_derived_fields,
    display_color_for,
    render_radius_from_magnitude,
)

_log = get_logger("c4d_objects.point_cloud_builder")

#: Name of the parent null that holds every UNAV-generated object in a
#: scene. ``find_starfield`` looks this up by marker first, by name
#: second.
STARFIELD_NAME = "UNAV_Starfield"
VISIBLE_SECTOR_NAME = "UNAV_VisibleSector"
DEBUG_ROOT_NAME = "UNAV_Debug"

#: Marker ``kind`` values for the wider hierarchy. Each is part of the
#: same ``BC_ID_UNAV_MARKER`` container, distinguished by
#: ``MARKER_KEY_KIND``.
KIND_STARFIELD = "starfield"
KIND_POINT = "point"
KIND_VISIBLE_SECTOR = "visible_sector"
KIND_DEBUG_ROOT = "debug_root"
KIND_DEBUG_CONE = "debug_cone"

#: Sub-IDs inside the marker BaseContainer. Stable across versions —
#: changing them is a save-file-breaking change.
MARKER_KEY_IS_UNAV = 1
MARKER_KEY_KIND = 2          # "starfield" | "point"
MARKER_KEY_UID = 3
MARKER_KEY_CATALOG_SOURCE = 4
MARKER_KEY_OBJECT_TYPE = 5
MARKER_KEY_NAME = 6
MARKER_KEY_METADATA_JSON = 7
MARKER_KEY_RA_DEG = 8
MARKER_KEY_DEC_DEG = 9
MARKER_KEY_DISTANCE_PC = 10
MARKER_KEY_SCHEMA_VERSION = 11

#: Multiplier that turns ``schema.render_radius_from_magnitude``'s output
#: into a viewport-visible null radius. The schema's radius is normalized
#: around 1.0; nulls need a few units to be perceptible.
NULL_RADIUS_SCALE = 2.0


# ---------------------------------------------------------------------------
# Pure helpers (no c4d dependency, fully unit-tested)
# ---------------------------------------------------------------------------


def position_for_object(
    obj: CatalogObject, scale_mode: str = DEFAULT_SCALE_MODE
) -> Tuple[float, float, float]:
    """Return the C4D world-space (x, y, z) for ``obj``.

    Uses the cached ``c4d_x/y/z`` if they are already populated and the
    requested scale matches; otherwise re-runs ``compute_derived_fields``
    so a freshly-constructed object Just Works.
    """
    if (
        obj.c4d_x is not None
        and obj.c4d_y is not None
        and obj.c4d_z is not None
        and scale_mode == DEFAULT_SCALE_MODE
    ):
        return float(obj.c4d_x), float(obj.c4d_y), float(obj.c4d_z)

    compute_derived_fields(obj, scale_mode=scale_mode)
    assert obj.c4d_x is not None and obj.c4d_y is not None and obj.c4d_z is not None
    return float(obj.c4d_x), float(obj.c4d_y), float(obj.c4d_z)


def radius_for_object(obj: CatalogObject) -> float:
    """Return the viewport null radius (C4D units) for ``obj``."""
    base_radius = obj.render_radius
    if base_radius is None:
        base_radius = render_radius_from_magnitude(obj.apparent_magnitude)
    return float(base_radius) * NULL_RADIUS_SCALE


def color_for_object(obj: CatalogObject) -> Tuple[float, float, float]:
    """Return a (r, g, b) float triple in [0, 1] suitable for a c4d.Vector."""
    rgb = obj.display_color_rgb or display_color_for(obj.object_type, obj.spectral_type)
    return _rgb_int_to_float(rgb)


def _rgb_int_to_float(
    rgb: Tuple[int, int, int]
) -> Tuple[float, float, float]:
    """Convert sRGB 0–255 ints into 0–1 floats, clamping out-of-range input."""
    def clamp(v: int) -> float:
        if v < 0:
            return 0.0
        if v > 255:
            return 1.0
        return v / 255.0
    return clamp(rgb[0]), clamp(rgb[1]), clamp(rgb[2])


def marker_for_object(
    obj: CatalogObject,
    kind: str = "point",
    include_full_metadata: bool = False,
) -> Dict[int, Any]:
    """Return the dict that will be written into the object's marker
    BaseContainer. Pure data — no c4d types involved.

    ``include_full_metadata=False`` (the safety default) omits the
    schema's ``metadata_json`` blob from the marker so the .c4d
    stays small. The metadata inspector pulls the full record from
    the external ``MetadataLookup`` via the uid; only the offline
    "carry the scene to a machine without the catalog" workflow
    needs ``include_full_metadata=True``.
    """
    payload: Dict[int, Any] = {
        MARKER_KEY_IS_UNAV: True,
        MARKER_KEY_KIND: kind,
        MARKER_KEY_UID: obj.uid or "",
        MARKER_KEY_CATALOG_SOURCE: obj.catalog_source or "",
        MARKER_KEY_OBJECT_TYPE: obj.object_type or "",
        MARKER_KEY_NAME: obj.name or obj.common_name or "",
        MARKER_KEY_RA_DEG: float(obj.ra_deg),
        MARKER_KEY_DEC_DEG: float(obj.dec_deg),
        MARKER_KEY_DISTANCE_PC: float(obj.distance_parsec) if obj.distance_parsec is not None else 0.0,
        MARKER_KEY_SCHEMA_VERSION: 1,
    }
    if include_full_metadata:
        payload[MARKER_KEY_METADATA_JSON] = obj.metadata_json or "{}"
    return payload


def starfield_marker(scale_mode: str = DEFAULT_SCALE_MODE) -> Dict[int, Any]:
    """Marker payload for the parent ``UNAV_Starfield`` null."""
    return {
        MARKER_KEY_IS_UNAV: True,
        MARKER_KEY_KIND: KIND_STARFIELD,
        MARKER_KEY_NAME: STARFIELD_NAME,
        MARKER_KEY_METADATA_JSON: f'{{"scale_mode": "{scale_mode}"}}',
        MARKER_KEY_SCHEMA_VERSION: 1,
    }


def _named_kind_marker(kind: str, name: str) -> Dict[int, Any]:
    return {
        MARKER_KEY_IS_UNAV: True,
        MARKER_KEY_KIND: kind,
        MARKER_KEY_NAME: name,
        MARKER_KEY_SCHEMA_VERSION: 1,
    }


def display_label(obj: CatalogObject) -> str:
    """Pick a human-friendly label for the C4D object name."""
    return obj.common_name or obj.name or obj.uid


# ---------------------------------------------------------------------------
# C4D-bound implementation
# ---------------------------------------------------------------------------


def _require_c4d() -> None:
    if not _C4D_AVAILABLE:
        raise RuntimeError(
            "point_cloud_builder requires Cinema 4D; "
            "this code path is unavailable outside the C4D host."
        )


def _write_marker(c4d_obj: "c4d.BaseObject", payload: Dict[int, Any]) -> None:
    _require_c4d()
    bc = c4d.BaseContainer()
    for key, value in payload.items():
        bc[key] = value
    c4d_obj.GetDataInstance().SetContainer(BC_ID_UNAV_MARKER, bc)


def _read_marker(c4d_obj: "c4d.BaseObject") -> Optional[Dict[int, Any]]:
    """Read the UNAV marker container off ``c4d_obj``. Returns None if
    the object is not one of ours."""
    _require_c4d()
    data = c4d_obj.GetDataInstance()
    if data is None:
        return None
    sub = data.GetContainerInstance(BC_ID_UNAV_MARKER)
    if sub is None:
        return None
    out: Dict[int, Any] = {}
    for key, value in sub:
        out[key] = value
    if not out.get(MARKER_KEY_IS_UNAV):
        return None
    return out


def is_unav_object(c4d_obj: "c4d.BaseObject") -> bool:
    """True if ``c4d_obj`` was generated by UNAV Pro."""
    if not _C4D_AVAILABLE:
        return False
    try:
        return _read_marker(c4d_obj) is not None
    except Exception:  # noqa: BLE001 — defensive
        return False


def build_point_object(
    obj: CatalogObject,
    scale_mode: str = DEFAULT_SCALE_MODE,
    encoding: Optional[VisualEncodingParams] = None,
    include_full_metadata: bool = False,
) -> "c4d.BaseObject":
    """Create one C4D ``Onull`` representing ``obj``. Not yet inserted
    into a document.

    If ``encoding`` is given, it overrides the schema's default colour
    and radius for this null. ``encoding=None`` keeps the schema's
    natural-star rendering exactly as it was before this argument
    existed.
    """
    _require_c4d()
    null = c4d.BaseObject(c4d.Onull)
    null.SetName(display_label(obj))

    x, y, z = position_for_object(obj, scale_mode=scale_mode)
    null.SetAbsPos(c4d.Vector(x, y, z))

    if encoding is None:
        radius = radius_for_object(obj)
        r, g, b = color_for_object(obj)
    else:
        rgb, raw_radius = encode_visuals(obj, encoding)
        radius = float(raw_radius) * NULL_RADIUS_SCALE
        r, g, b = (
            max(0.0, min(1.0, rgb[0] / 255.0)),
            max(0.0, min(1.0, rgb[1] / 255.0)),
            max(0.0, min(1.0, rgb[2] / 255.0)),
        )

    # Display: small dot, with our colour.
    null[c4d.NULLOBJECT_DISPLAY] = c4d.NULLOBJECT_DISPLAY_DOT
    null[c4d.NULLOBJECT_RADIUS] = radius
    null[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
    null[c4d.ID_BASEOBJECT_COLOR] = c4d.Vector(r, g, b)

    _write_marker(null, marker_for_object(
        obj, kind="point", include_full_metadata=include_full_metadata,
    ))
    return null


def find_starfield(doc: "c4d.documents.BaseDocument") -> Optional["c4d.BaseObject"]:
    """Return an existing ``UNAV_Starfield`` null in ``doc``, if any.

    Looks for the marker first, then falls back to the canonical name —
    so a starfield created by a future schema version is still found
    even if marker keys change.
    """
    _require_c4d()
    obj = doc.GetFirstObject()
    while obj is not None:
        marker = _read_marker(obj)
        if marker is not None and marker.get(MARKER_KEY_KIND) == KIND_STARFIELD:
            return obj
        if obj.GetName() == STARFIELD_NAME:
            return obj
        obj = obj.GetNext()
    return None


def _find_child_by_kind(
    parent: "c4d.BaseObject", kind: str,
) -> Optional["c4d.BaseObject"]:
    """Return the first immediate child of ``parent`` whose marker
    ``kind`` matches, or None."""
    _require_c4d()
    child = parent.GetDown()
    while child is not None:
        marker = _read_marker(child)
        if marker is not None and marker.get(MARKER_KEY_KIND) == kind:
            return child
        child = child.GetNext()
    return None


def _ensure_kind_child(
    doc: "c4d.documents.BaseDocument",
    parent: "c4d.BaseObject",
    kind: str,
    name: str,
) -> "c4d.BaseObject":
    """Find or create a child null under ``parent`` carrying ``kind``."""
    _require_c4d()
    existing = _find_child_by_kind(parent, kind)
    if existing is not None:
        return existing
    null = c4d.BaseObject(c4d.Onull)
    null.SetName(name)
    null[c4d.NULLOBJECT_DISPLAY] = c4d.NULLOBJECT_DISPLAY_NONE
    _write_marker(null, _named_kind_marker(kind, name))
    null.InsertUnder(parent)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, null)
    return null


def find_visible_sector(
    doc: "c4d.documents.BaseDocument",
) -> Optional["c4d.BaseObject"]:
    """Return the ``UNAV_VisibleSector`` null under the starfield, or None."""
    _require_c4d()
    starfield = find_starfield(doc)
    if starfield is None:
        return None
    return _find_child_by_kind(starfield, KIND_VISIBLE_SECTOR)


def find_debug_root(
    doc: "c4d.documents.BaseDocument",
) -> Optional["c4d.BaseObject"]:
    """Return the ``UNAV_Debug`` null under the starfield, or None."""
    _require_c4d()
    starfield = find_starfield(doc)
    if starfield is None:
        return None
    return _find_child_by_kind(starfield, KIND_DEBUG_ROOT)


def ensure_starfield_hierarchy(
    doc: "c4d.documents.BaseDocument",
    scale_mode: str = DEFAULT_SCALE_MODE,
) -> Tuple["c4d.BaseObject", "c4d.BaseObject", "c4d.BaseObject"]:
    """Find or create ``UNAV_Starfield`` plus its two children
    (``UNAV_VisibleSector`` and ``UNAV_Debug``).

    Returns ``(starfield, visible_sector, debug_root)``. Existing
    nodes are reused; only what is missing gets created (and its
    creation is recorded for undo).
    """
    _require_c4d()
    starfield = find_starfield(doc)
    if starfield is None:
        starfield = _create_starfield_null(doc, scale_mode=scale_mode)
    visible = _ensure_kind_child(
        doc, starfield, KIND_VISIBLE_SECTOR, VISIBLE_SECTOR_NAME,
    )
    debug = _ensure_kind_child(
        doc, starfield, KIND_DEBUG_ROOT, DEBUG_ROOT_NAME,
    )
    return starfield, visible, debug


def _create_starfield_null(
    doc: "c4d.documents.BaseDocument",
    scale_mode: str,
) -> "c4d.BaseObject":
    _require_c4d()
    parent = c4d.BaseObject(c4d.Onull)
    parent.SetName(STARFIELD_NAME)
    parent[c4d.NULLOBJECT_DISPLAY] = c4d.NULLOBJECT_DISPLAY_NONE
    _write_marker(parent, starfield_marker(scale_mode=scale_mode))
    doc.InsertObject(parent)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, parent)
    return parent


def build_starfield(
    doc: "c4d.documents.BaseDocument",
    objects: Iterable[CatalogObject],
    scale_mode: str = DEFAULT_SCALE_MODE,
    replace_existing: bool = True,
    encoding: Optional[VisualEncodingParams] = None,
    include_full_metadata: bool = False,
) -> Tuple["c4d.BaseObject", int]:
    """Create the UNAV_Starfield null and one child per catalog object.

    Returns ``(starfield_null, count_created)``. If ``replace_existing``
    is True (default), any existing UNAV objects in the scene are
    removed first so re-running the action does not duplicate. The
    operation runs inside an undo block so a single Ctrl-Z reverts it.

    ``encoding`` overrides the natural colour / radius mapping for
    every child. ``None`` keeps the schema-default rendering.
    """
    _require_c4d()

    doc.StartUndo()
    try:
        if replace_existing:
            removed = clear_starfield(doc, _within_undo=True)
            if removed:
                _log.info("Removed %d pre-existing UNAV objects.", removed)

        _starfield, visible_sector, _debug = ensure_starfield_hierarchy(
            doc, scale_mode=scale_mode,
        )

        count = 0
        for obj in objects:
            try:
                child = build_point_object(
                    obj, scale_mode=scale_mode, encoding=encoding,
                    include_full_metadata=include_full_metadata,
                )
            except Exception:  # noqa: BLE001 — never let one bad row stop the build
                _log.exception("Skipping bad object during build: uid=%r", getattr(obj, "uid", None))
                continue
            child.InsertUnder(visible_sector)
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, child)
            count += 1
        parent = _starfield
    finally:
        doc.EndUndo()

    c4d.EventAdd()
    _log.info(
        "Built UNAV starfield with %d objects (scale=%s, color=%s, size=%s).",
        count, scale_mode,
        encoding.color_mode if encoding else "natural",
        encoding.size_mode if encoding else "magnitude",
    )
    return parent, count


def clear_starfield(
    doc: "c4d.documents.BaseDocument",
    _within_undo: bool = False,
) -> int:
    """Remove every UNAV-tagged object from ``doc``. Returns the count
    removed.

    Walks the entire object hierarchy, not just the top level — a user
    may have re-parented an UNAV object elsewhere. Non-UNAV objects are
    untouched.
    """
    _require_c4d()

    targets: List["c4d.BaseObject"] = []
    _collect_unav(doc.GetFirstObject(), targets)

    if not targets:
        return 0

    if not _within_undo:
        doc.StartUndo()
    try:
        for obj in targets:
            doc.AddUndo(c4d.UNDOTYPE_DELETE, obj)
            obj.Remove()
    finally:
        if not _within_undo:
            doc.EndUndo()

    if not _within_undo:
        c4d.EventAdd()
    _log.info("Cleared %d UNAV objects from document.", len(targets))
    return len(targets)


def _collect_unav(
    obj: Optional["c4d.BaseObject"],
    out: List["c4d.BaseObject"],
) -> None:
    """Depth-first collect of UNAV objects starting at ``obj``."""
    while obj is not None:
        # Recurse children first so we can remove the parent last; in
        # practice we delete via Remove() which handles children, but
        # collecting depth-first lets us be order-agnostic.
        _collect_unav(obj.GetDown(), out)
        if is_unav_object(obj):
            out.append(obj)
        obj = obj.GetNext()
