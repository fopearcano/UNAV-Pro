"""UNAV Pro local catalog schema.

This module is the single source of truth for the **plugin-side** catalog
format: the compact local representation that the C4D plugin reads. It
deliberately uses only the Python standard library so it is importable
inside Cinema 4D's bundled interpreter without extra dependencies.

The schema is a strict subset of the canonical pipeline schema described
in ``docs/UNAV_PRO_DATA_PIPELINE.md`` §4. The pipeline writes Parquet
tiles for production; the local catalog format implemented here
(JSONL/CSV) is the human-readable, dependency-free interchange format
used for samples, tests, small projects, and engine-less debugging.

Field groups
------------

* **Identity** — ``uid``, ``catalog_source``, ``object_type``, ``name``.
* **Astrometry** — ``ra_deg``, ``dec_deg``, ``distance_parsec``,
  ``parallax_mas``, ``redshift``, ``radial_velocity_kms``,
  ``proper_motion_ra``, ``proper_motion_dec``.
* **Photometry** — ``apparent_magnitude``, ``absolute_magnitude``,
  ``color_index``, ``spectral_type``.
* **Free-form** — ``metadata_json`` (string-encoded JSON for arbitrary
  catalog-specific fields).
* **Computed** — ``cartesian_x/y/z`` (ICRS Cartesian, parsec),
  ``c4d_x/y/z`` (Cinema 4D world units), ``render_radius``,
  ``display_color_rgb`` (3-tuple of ints 0–255).

Coordinate convention
---------------------

ICRS spherical ``(ra_deg, dec_deg, distance_pc)`` is converted to
right-handed Cartesian parsec coordinates with::

    x = d * cos(dec) * cos(ra)
    y = d * cos(dec) * sin(ra)
    z = d * sin(dec)

The plugin's *floating origin* (see ARCHITECTURE §3.6) is applied later,
at query time; storage is barycentric.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

#: Allowed object types. Adapters may extend this list at ingest time, but
#: the plugin treats unknown types as ``"unknown"`` for rendering.
OBJECT_TYPES = (
    "star",
    "galaxy",
    "quasar",
    "nebula",
    "cluster",
    "planet",
    "exoplanet",
    "asteroid",
    "comet",
    "unknown",
)

#: When an object has no distance and no parallax, place it on this
#: "celestial sphere" radius (parsec) for visualization. Flagged via
#: ``metadata_json["distance_method"] = "placeholder_sphere"``.
PLACEHOLDER_SPHERE_PC = 1.0e6

#: Cinema 4D scale modes. Each value is *C4D units per parsec*. The user
#: picks a scene scale that puts the relevant region into a workable
#: float32 viewport range — see ARCHITECTURE §3.6.
SCALE_MODES: Dict[str, float] = {
    "au": 206264.806,    # 1 pc = 206264.806 AU; 1 AU == 1 unit
    "ly": 3.261564,      # 1 pc = 3.261564 ly
    "pc": 1.0,           # 1 pc == 1 unit
    "kpc": 1.0e-3,       # 1 kpc == 1 unit
    "mpc": 1.0e-6,       # 1 Mpc == 1 unit
}

DEFAULT_SCALE_MODE = "pc"

#: Approximate sRGB triplets per spectral class, for the display_color
#: helper. Real rendering should use color temperature; this table is
#: enough for the MVP point-cloud preview.
_SPECTRAL_COLORS: Dict[str, Tuple[int, int, int]] = {
    "O": (155, 176, 255),
    "B": (170, 191, 255),
    "A": (202, 215, 255),
    "F": (248, 247, 255),
    "G": (255, 244, 234),
    "K": (255, 210, 161),
    "M": (255, 204, 111),
    "L": (200,  90,  60),
    "T": (160,  60,  40),
}

_TYPE_COLORS: Dict[str, Tuple[int, int, int]] = {
    "star":     (255, 244, 234),
    "galaxy":   (220, 200, 180),
    "quasar":   (200, 220, 255),
    "nebula":   (200, 120, 220),
    "cluster":  (240, 230, 200),
    "planet":   (170, 170, 200),
    "exoplanet": (170, 170, 200),
    "asteroid": (160, 140, 120),
    "comet":    (180, 220, 240),
    "unknown":  (180, 180, 180),
}

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class CatalogObject:
    """One catalog row, plain old data.

    Only ``uid``, ``catalog_source``, ``object_type``, ``ra_deg``, and
    ``dec_deg`` are required. Every other field is optional and may be
    ``None``. Computed fields are filled by ``compute_derived_fields``;
    they are kept on the dataclass so the same object roundtrips cleanly
    through JSONL/CSV.
    """

    # --- required ----------------------------------------------------------
    uid: str
    catalog_source: str
    object_type: str
    ra_deg: float
    dec_deg: float

    # --- optional astrometry / photometry ----------------------------------
    distance_parsec: Optional[float] = None
    parallax_mas: Optional[float] = None
    redshift: Optional[float] = None
    radial_velocity_kms: Optional[float] = None
    proper_motion_ra: Optional[float] = None
    proper_motion_dec: Optional[float] = None
    apparent_magnitude: Optional[float] = None
    absolute_magnitude: Optional[float] = None
    color_index: Optional[float] = None
    spectral_type: Optional[str] = None
    name: Optional[str] = None
    common_name: Optional[str] = None

    # --- free form ---------------------------------------------------------
    metadata_json: str = "{}"

    # --- computed ----------------------------------------------------------
    cartesian_x: Optional[float] = None
    cartesian_y: Optional[float] = None
    cartesian_z: Optional[float] = None
    c4d_x: Optional[float] = None
    c4d_y: Optional[float] = None
    c4d_z: Optional[float] = None
    render_radius: Optional[float] = None
    display_color_rgb: Optional[Tuple[int, int, int]] = None

    # ------------------------------------------------------------------ dict
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Tuples don't roundtrip through JSON as tuples; keep as list.
        if d.get("display_color_rgb") is not None:
            d["display_color_rgb"] = list(d["display_color_rgb"])
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CatalogObject":
        # Accept either tuple or list for display_color_rgb.
        if "display_color_rgb" in d and d["display_color_rgb"] is not None:
            d = dict(d)
            d["display_color_rgb"] = tuple(d["display_color_rgb"])  # type: ignore[arg-type]
        # Drop unknown keys to stay forward-compatible.
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in d.items() if k in known}
        return cls(**clean)


# Stable column order for CSV output. Required first, then optional, then
# computed. Tests rely on this order.
CSV_FIELDS: Tuple[str, ...] = tuple(f.name for f in fields(CatalogObject))

REQUIRED_FIELDS: Tuple[str, ...] = (
    "uid", "catalog_source", "object_type", "ra_deg", "dec_deg",
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_object(obj: CatalogObject) -> List[str]:
    """Return a list of human-readable issues for ``obj``. Empty == valid."""
    issues: List[str] = []

    for name in REQUIRED_FIELDS:
        value = getattr(obj, name, None)
        if value is None or (isinstance(value, str) and value == ""):
            issues.append(f"missing required field '{name}'")

    if obj.object_type and obj.object_type not in OBJECT_TYPES:
        issues.append(
            f"object_type '{obj.object_type}' not in known set "
            f"(allowed: {', '.join(OBJECT_TYPES)})"
        )

    try:
        ra = float(obj.ra_deg)
        if not (0.0 <= ra < 360.0):
            issues.append(f"ra_deg out of range [0, 360): {ra}")
    except (TypeError, ValueError):
        issues.append("ra_deg is not a number")

    try:
        dec = float(obj.dec_deg)
        if not (-90.0 <= dec <= 90.0):
            issues.append(f"dec_deg out of range [-90, 90]: {dec}")
    except (TypeError, ValueError):
        issues.append("dec_deg is not a number")

    if obj.distance_parsec is not None and obj.distance_parsec <= 0:
        issues.append(f"distance_parsec must be > 0: {obj.distance_parsec}")
    if obj.parallax_mas is not None and obj.parallax_mas == 0:
        issues.append("parallax_mas == 0 is invalid (would imply infinite distance)")
    if obj.metadata_json:
        try:
            json.loads(obj.metadata_json)
        except (TypeError, ValueError) as exc:
            issues.append(f"metadata_json is not valid JSON: {exc}")

    return issues


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


def equatorial_to_cartesian_pc(
    ra_deg: float, dec_deg: float, distance_pc: float
) -> Tuple[float, float, float]:
    """Convert ICRS spherical coordinates to ICRS Cartesian (parsec).

    Right-handed system with:
      * +x toward (ra=0, dec=0)
      * +y toward (ra=90°, dec=0)
      * +z toward the north celestial pole
    """
    if distance_pc <= 0:
        raise ValueError("distance_pc must be > 0")
    ra = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    cos_dec = math.cos(dec)
    x = distance_pc * cos_dec * math.cos(ra)
    y = distance_pc * cos_dec * math.sin(ra)
    z = distance_pc * math.sin(dec)
    return x, y, z


def resolve_distance_pc(obj: CatalogObject) -> Tuple[float, str]:
    """Pick the best available distance for ``obj`` and return (pc, method).

    Order of preference:
      1. explicit ``distance_parsec``
      2. ``parallax_mas``  →  d = 1000 / parallax_mas
      3. fall back to ``PLACEHOLDER_SPHERE_PC``
    """
    if obj.distance_parsec is not None and obj.distance_parsec > 0:
        return float(obj.distance_parsec), "explicit"
    if obj.parallax_mas is not None and obj.parallax_mas > 0:
        return 1000.0 / float(obj.parallax_mas), "parallax"
    return PLACEHOLDER_SPHERE_PC, "placeholder_sphere"


def pc_to_c4d_units(
    x_pc: float, y_pc: float, z_pc: float, scale_mode: str = DEFAULT_SCALE_MODE
) -> Tuple[float, float, float]:
    """Scale parsec Cartesian coordinates into Cinema 4D world units."""
    if scale_mode not in SCALE_MODES:
        raise ValueError(
            f"unknown scale_mode '{scale_mode}'; "
            f"valid: {', '.join(SCALE_MODES.keys())}"
        )
    s = SCALE_MODES[scale_mode]
    return x_pc * s, y_pc * s, z_pc * s


# ---------------------------------------------------------------------------
# Render attribute helpers
# ---------------------------------------------------------------------------


def render_radius_from_magnitude(
    apparent_magnitude: Optional[float],
    base: float = 1.0,
    floor: float = 0.05,
    ceiling: float = 50.0,
) -> float:
    """Map apparent magnitude to a render radius in C4D units.

    Brighter objects (lower magnitude) get larger radii. The formula is a
    soft mapping ``base * 10**(-m/10)`` clamped to ``[floor, ceiling]``;
    if magnitude is unknown, returns ``base``.
    """
    if apparent_magnitude is None:
        return base
    try:
        r = base * (10.0 ** (-float(apparent_magnitude) / 10.0))
    except (TypeError, ValueError, OverflowError):
        return base
    if r < floor:
        return floor
    if r > ceiling:
        return ceiling
    return r


def _spectral_class_letter(spectral_type: Optional[str]) -> Optional[str]:
    if not spectral_type:
        return None
    s = spectral_type.strip().upper()
    if not s:
        return None
    return s[0] if s[0] in _SPECTRAL_COLORS else None


def display_color_for(
    object_type: str, spectral_type: Optional[str] = None
) -> Tuple[int, int, int]:
    """Return an sRGB triplet (0–255) for an object given its type and
    optional spectral class. Falls back through:

      1. spectral type lookup (stars only),
      2. object-type lookup,
      3. neutral grey.
    """
    if (object_type == "star" or object_type == "unknown"):
        letter = _spectral_class_letter(spectral_type)
        if letter is not None:
            return _SPECTRAL_COLORS[letter]
    return _TYPE_COLORS.get(object_type, _TYPE_COLORS["unknown"])


# ---------------------------------------------------------------------------
# Derived-field population
# ---------------------------------------------------------------------------


def compute_derived_fields(
    obj: CatalogObject, scale_mode: str = DEFAULT_SCALE_MODE
) -> CatalogObject:
    """Populate Cartesian, C4D, render-radius, and display-color fields.

    Mutates and returns ``obj``. Safe to call multiple times. If the
    object lacks both distance and parallax, it is placed on a
    placeholder sphere and tagged accordingly via ``metadata_json``.
    """
    distance_pc, method = resolve_distance_pc(obj)
    x_pc, y_pc, z_pc = equatorial_to_cartesian_pc(obj.ra_deg, obj.dec_deg, distance_pc)
    obj.cartesian_x = x_pc
    obj.cartesian_y = y_pc
    obj.cartesian_z = z_pc

    cx, cy, cz = pc_to_c4d_units(x_pc, y_pc, z_pc, scale_mode)
    obj.c4d_x, obj.c4d_y, obj.c4d_z = cx, cy, cz

    obj.render_radius = render_radius_from_magnitude(obj.apparent_magnitude)
    obj.display_color_rgb = display_color_for(obj.object_type, obj.spectral_type)

    if method == "placeholder_sphere":
        try:
            meta = json.loads(obj.metadata_json or "{}")
        except (TypeError, ValueError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {"_original_metadata": meta}
        meta.setdefault("distance_method", "placeholder_sphere")
        meta.setdefault("placeholder_sphere_pc", PLACEHOLDER_SPHERE_PC)
        obj.metadata_json = json.dumps(meta, sort_keys=True)

    return obj


def compute_derived_for_all(
    objs: Iterable[CatalogObject], scale_mode: str = DEFAULT_SCALE_MODE
) -> List[CatalogObject]:
    """Apply ``compute_derived_fields`` to every object; return as list."""
    out: List[CatalogObject] = []
    for o in objs:
        out.append(compute_derived_fields(o, scale_mode=scale_mode))
    return out
