"""UNAV Pro navigation null hierarchy.

Layout
------

The navigator is a small three-object hierarchy parented at the scene
root::

    UNAV_Navigator (Onull)            <-- position + orientation source
      ├── UNAV_Camera (Ocamera)       <-- viewport / render camera
      └── UNAV_ViewRay (SplineObject) <-- visual forward indicator

The **null** is the source of truth for the navigator's world-space
position and orientation. Filtering reads its global matrix; the
camera and ray are children that inherit it for free.

Convention
----------

The navigator's *forward* direction is its local **−Z** axis, matching
Cinema 4D's camera convention (a fresh camera looks down −Z). The view
ray is a 2-knot linear spline from ``(0, 0, 0)`` to ``(0, 0,
-_RAY_LENGTH_C4D)``; the camera's local transform is identity so it
inherits the null's pose directly.

User data
---------

The navigator null carries the eight ``NavigationParams`` fields as
real C4D user data so artists can edit them in the Attribute Manager.
The same payload is also written into the BC_ID_UNAV_MARKER container
as JSON so the values survive even if the user-data layout changes
between schema versions.

C4D guard
---------

The module imports ``c4d`` defensively so it stays importable in
plain CPython for unit tests. The C4D-bound functions raise a clean
``RuntimeError`` outside the host. Pure helpers are exported and
tested directly.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from core.logging_util import get_logger
from core.navigation_state import (
    NavigationParams,
    sources_to_string,
    _coerce_source_list,
)
from core.plugin_ids import BC_ID_UNAV_MARKER

# Reuse the marker key vocabulary from point_cloud_builder so a single
# inspector can read either object kind.
from .point_cloud_builder import (
    MARKER_KEY_IS_UNAV,
    MARKER_KEY_KIND,
    MARKER_KEY_METADATA_JSON,
    MARKER_KEY_NAME,
    MARKER_KEY_SCHEMA_VERSION,
)

_log = get_logger("c4d_objects.navigation_null")

# ---------------------------------------------------------------------------
# Names and constants
# ---------------------------------------------------------------------------

NAVIGATOR_NAME = "UNAV_Navigator"
CAMERA_NAME = "UNAV_Camera"
RAY_NAME = "UNAV_ViewRay"

KIND_NAVIGATOR = "navigator"
KIND_NAVIGATOR_CAMERA = "navigator_camera"
KIND_NAVIGATOR_RAY = "navigator_ray"

#: View-ray spline length in C4D units. Static for the MVP — the filter
#: system will rescale it from ``max_distance_parsec * c4d_per_pc``.
_RAY_LENGTH_C4D = 100.0


# ---------------------------------------------------------------------------
# User-data spec
# ---------------------------------------------------------------------------

# Each entry: (short_name, c4d_dtype_token, default, label)
# The c4d_dtype_token resolves to a real ``c4d.DTYPE_*`` symbol inside
# the host; outside C4D it stays a string.
_USER_DATA_SPEC: Tuple[Tuple[str, str, Any, str], ...] = (
    ("max_distance_parsec",      "REAL",   1000.0,    "Max Distance (pc)"),
    ("field_of_view_deg",        "REAL",   60.0,      "Field of View (deg)"),
    ("cone_angle_deg",           "REAL",   30.0,      "Cone Half-Angle (deg)"),
    ("near_clip_parsec",         "REAL",   0.1,       "Near Clip (pc)"),
    ("far_clip_parsec",          "REAL",   10000.0,   "Far Clip (pc)"),
    ("selected_catalog_sources", "STRING", "unav_sample", "Catalog Sources (csv)"),
    ("max_visible_objects",      "LONG",   100_000,   "Max Visible Objects"),
    ("c4d_scale",                "STRING", "pc",      "C4D Scale (au|ly|pc|kpc|mpc)"),
)

USER_DATA_FIELD_NAMES: Tuple[str, ...] = tuple(s[0] for s in _USER_DATA_SPEC)


def user_data_defaults() -> Dict[str, Any]:
    """Return the {short_name: default} mapping. Pure, testable."""
    return {name: default for name, _dtype, default, _label in _USER_DATA_SPEC}


# ---------------------------------------------------------------------------
# C4D guard helper
# ---------------------------------------------------------------------------


def _require_c4d() -> None:
    if not _C4D_AVAILABLE:
        raise RuntimeError(
            "navigation_null requires Cinema 4D; this code path is "
            "unavailable outside the C4D host."
        )


# ---------------------------------------------------------------------------
# Marker helpers
# ---------------------------------------------------------------------------


def _write_marker(c4d_obj: "c4d.BaseObject", payload: Dict[int, Any]) -> None:
    _require_c4d()
    bc = c4d.BaseContainer()
    for key, value in payload.items():
        bc[key] = value
    c4d_obj.GetDataInstance().SetContainer(BC_ID_UNAV_MARKER, bc)


def _read_marker(c4d_obj: "c4d.BaseObject") -> Optional[Dict[int, Any]]:
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


def _navigator_marker(params: NavigationParams) -> Dict[int, Any]:
    return {
        MARKER_KEY_IS_UNAV: True,
        MARKER_KEY_KIND: KIND_NAVIGATOR,
        MARKER_KEY_NAME: NAVIGATOR_NAME,
        MARKER_KEY_METADATA_JSON: params.to_json(),
        MARKER_KEY_SCHEMA_VERSION: 1,
    }


def _kind_marker(kind: str, name: str) -> Dict[int, Any]:
    return {
        MARKER_KEY_IS_UNAV: True,
        MARKER_KEY_KIND: kind,
        MARKER_KEY_NAME: name,
        MARKER_KEY_SCHEMA_VERSION: 1,
    }


# ---------------------------------------------------------------------------
# User-data attach/read
# ---------------------------------------------------------------------------


def _dtype_token_to_c4d(token: str) -> int:
    _require_c4d()
    return {
        "REAL":   c4d.DTYPE_REAL,
        "LONG":   c4d.DTYPE_LONG,
        "STRING": c4d.DTYPE_STRING,
        "BOOL":   c4d.DTYPE_BOOL,
    }[token]


def _attach_user_data(
    obj: "c4d.BaseObject", params: NavigationParams
) -> Dict[str, "c4d.DescID"]:
    """Add the eight UNAV navigation parameters as user data on
    ``obj``. Returns ``{short_name: DescID}`` for later writes."""
    _require_c4d()

    values = params.to_dict()
    desc_ids: Dict[str, "c4d.DescID"] = {}

    for short_name, dtype_token, default, label in _USER_DATA_SPEC:
        bc = c4d.GetCustomDataTypeDefault(_dtype_token_to_c4d(dtype_token))
        bc[c4d.DESC_NAME] = label
        bc[c4d.DESC_SHORT_NAME] = short_name
        bc[c4d.DESC_ANIMATE] = c4d.DESC_ANIMATE_OFF

        # Render the dataclass value into the dtype the user data slot
        # expects. Strings (selected_catalog_sources, c4d_scale) get
        # comma-joined / passed through; numbers are coerced.
        v: Any = values.get(short_name, default)
        if short_name == "selected_catalog_sources":
            v = sources_to_string(v if isinstance(v, list) else [str(v)])
        if dtype_token == "REAL":
            v = float(v)
            bc[c4d.DESC_DEFAULT] = v
        elif dtype_token == "LONG":
            v = int(v)
            bc[c4d.DESC_DEFAULT] = v
        elif dtype_token == "STRING":
            v = str(v)
            bc[c4d.DESC_DEFAULT] = v

        desc_id = obj.AddUserData(bc)
        obj[desc_id] = v
        desc_ids[short_name] = desc_id

    return desc_ids


def _read_user_data(obj: "c4d.BaseObject") -> Dict[str, Any]:
    """Read every named UNAV user-data slot off ``obj``. Unknown slots
    are ignored. Missing slots fall back to dataclass defaults later."""
    _require_c4d()
    out: Dict[str, Any] = {}
    user_data = obj.GetUserDataContainer()
    if not user_data:
        return out
    for desc_id, bc in user_data:
        try:
            short = bc[c4d.DESC_SHORT_NAME]
        except Exception:  # noqa: BLE001 — defensive
            continue
        if short in USER_DATA_FIELD_NAMES:
            out[short] = obj[desc_id]
    return out


def _user_data_to_params(values: Dict[str, Any]) -> NavigationParams:
    """Convert a raw {short_name: c4d_value} dict into a clamped
    NavigationParams. Strings are decoded back into lists where
    appropriate. Out-of-range values are clamped, not rejected."""
    d = dict(values)
    if "selected_catalog_sources" in d:
        d["selected_catalog_sources"] = _coerce_source_list(
            d["selected_catalog_sources"]
        )
    return NavigationParams.from_dict(d).clamped()


# ---------------------------------------------------------------------------
# Hierarchy creation
# ---------------------------------------------------------------------------


def _create_navigator_hierarchy(
    doc: "c4d.documents.BaseDocument",
    params: Optional[NavigationParams] = None,
) -> "c4d.BaseObject":
    _require_c4d()
    params = params or NavigationParams()

    nav = c4d.BaseObject(c4d.Onull)
    nav.SetName(NAVIGATOR_NAME)
    nav[c4d.NULLOBJECT_DISPLAY] = c4d.NULLOBJECT_DISPLAY_AXIS
    nav[c4d.NULLOBJECT_RADIUS] = 25.0
    _write_marker(nav, _navigator_marker(params))
    _attach_user_data(nav, params)

    cam = c4d.BaseObject(c4d.Ocamera)
    cam.SetName(CAMERA_NAME)
    _write_marker(cam, _kind_marker(KIND_NAVIGATOR_CAMERA, CAMERA_NAME))

    ray = c4d.SplineObject(2, c4d.SPLINETYPE_LINEAR)
    ray.SetName(RAY_NAME)
    ray.SetPoint(0, c4d.Vector(0.0, 0.0, 0.0))
    ray.SetPoint(1, c4d.Vector(0.0, 0.0, -_RAY_LENGTH_C4D))
    ray.Message(c4d.MSG_UPDATE)
    _write_marker(ray, _kind_marker(KIND_NAVIGATOR_RAY, RAY_NAME))

    doc.InsertObject(nav)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, nav)
    cam.InsertUnder(nav)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, cam)
    ray.InsertUnder(nav)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, ray)

    return nav


def find_navigator(
    doc: "c4d.documents.BaseDocument",
) -> Optional["c4d.BaseObject"]:
    """Return the existing UNAV_Navigator null in ``doc``, or None."""
    _require_c4d()
    obj = doc.GetFirstObject()
    while obj is not None:
        marker = _read_marker(obj)
        if marker is not None and marker.get(MARKER_KEY_KIND) == KIND_NAVIGATOR:
            return obj
        if obj.GetName() == NAVIGATOR_NAME:
            return obj
        obj = obj.GetNext()
    return None


def _select_only(doc: "c4d.documents.BaseDocument", target: "c4d.BaseObject") -> None:
    """Make ``target`` the sole active selection."""
    _require_c4d()
    doc.SetActiveObject(target, c4d.SELECTION_NEW)


def ensure_navigator(
    doc: "c4d.documents.BaseDocument",
    params: Optional[NavigationParams] = None,
) -> Tuple["c4d.BaseObject", bool]:
    """Create the navigator hierarchy if missing, otherwise select the
    existing one. Returns ``(navigator, was_created)``.

    The whole operation is wrapped in an undo block.
    """
    _require_c4d()

    existing = find_navigator(doc)
    if existing is not None:
        _select_only(doc, existing)
        c4d.EventAdd()
        _log.info("UNAV_Navigator already present; selected it.")
        return existing, False

    doc.StartUndo()
    try:
        nav = _create_navigator_hierarchy(doc, params=params)
        _select_only(doc, nav)
    finally:
        doc.EndUndo()
    c4d.EventAdd()
    _log.info("Created UNAV_Navigator hierarchy.")
    return nav, True


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------


def get_navigation_origin(
    navigator: Optional["c4d.BaseObject"] = None,
    doc: Optional["c4d.documents.BaseDocument"] = None,
) -> "c4d.Vector":
    """World-space position of the navigator (its global matrix
    translation). Pass either ``navigator`` directly or ``doc`` to look
    it up. Raises ``RuntimeError`` if there is no navigator in the
    scene."""
    _require_c4d()
    nav = navigator or _resolve_navigator(doc)
    return nav.GetMg().off


def get_navigation_forward_vector(
    navigator: Optional["c4d.BaseObject"] = None,
    doc: Optional["c4d.documents.BaseDocument"] = None,
) -> "c4d.Vector":
    """Unit vector pointing along the navigator's forward direction in
    world space. Forward is defined as the navigator's local **−Z**
    axis (C4D camera convention)."""
    _require_c4d()
    nav = navigator or _resolve_navigator(doc)
    mg = nav.GetMg()
    forward = -mg.v3
    length = forward.GetLength()
    if length == 0.0:
        return c4d.Vector(0, 0, -1)
    return forward.GetNormalized()


def get_navigation_filter_params(
    navigator: Optional["c4d.BaseObject"] = None,
    doc: Optional["c4d.documents.BaseDocument"] = None,
) -> NavigationParams:
    """Read the eight UNAV parameters off the navigator's user data.
    Falls back to the JSON copy in the marker container if the user
    data is incomplete or missing. Always returns a clamped
    ``NavigationParams`` — never raises for bad values."""
    _require_c4d()
    nav = navigator or _resolve_navigator(doc)

    raw = _read_user_data(nav)
    if raw and len(raw) == len(USER_DATA_FIELD_NAMES):
        return _user_data_to_params(raw)

    marker = _read_marker(nav) or {}
    fallback_json = marker.get(MARKER_KEY_METADATA_JSON, "{}")
    params = NavigationParams.from_json(fallback_json).clamped()

    if raw:
        # Partial user data — overlay it on top of the marker fallback.
        merged = params.to_dict()
        merged.update({k: v for k, v in raw.items() if k in merged})
        params = _user_data_to_params(merged)

    return params


def _resolve_navigator(
    doc: Optional["c4d.documents.BaseDocument"],
) -> "c4d.BaseObject":
    _require_c4d()
    if doc is None:
        from c4d import documents  # type: ignore

        doc = documents.GetActiveDocument()
    if doc is None:
        raise RuntimeError("no active C4D document")
    nav = find_navigator(doc)
    if nav is None:
        raise RuntimeError(
            "no UNAV_Navigator in the active scene; create one first"
        )
    return nav
