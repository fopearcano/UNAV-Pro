"""Professional visual-encoding presets for UNAV catalog objects.

This module owns the **rendering style** of a generated point: the
colour and size each catalog row gets when the dialog builds the
``UNAV_Starfield``. The schema's defaults
(``data.schema.display_color_for`` and
``data.schema.render_radius_from_magnitude``) cover the natural-star
case; this module extends them with the four additional encoding
modes the UI dropdown exposes (catalog source, object type, redshift,
magnitude) plus a Gaia ``BP–RP`` colour-index path that is reachable
from the API.

Design
------

  * **Pure CPython.** No c4d, no numpy. Pure functions on
    ``CatalogObject`` returning sRGB int triples and float radii.
  * **Composable.** ``encode(obj, params)`` is the one-shot path the
    point-cloud builder calls; the per-mode helpers are exposed
    individually for tests and for future inspectors that want to
    legend the active mode.
  * **Self-healing.** Every mode falls through to the *natural* one
    when its required field is missing. A galaxy with no redshift
    under "Redshift" mode keeps a sensible neutral colour rather
    than crashing.
  * **Aligned with the schema.** ``natural`` mode goes through
    ``schema.display_color_for`` and ``render_radius_from_magnitude``
    so the encoding stays consistent with anything that uses the
    cached ``display_color_rgb`` / ``render_radius`` directly.

See ``docs/VISUAL_ENCODING.md`` for the user-facing contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from data.schema import (
    CatalogObject,
    OBJECT_TYPES,
    display_color_for,
    render_radius_from_magnitude,
)

# ---------------------------------------------------------------------------
# Mode tokens and human-readable labels
# ---------------------------------------------------------------------------

#: Canonical color modes accepted by ``VisualEncodingParams.color_mode``.
COLOR_MODES: Tuple[str, ...] = (
    "natural",
    "catalog_source",
    "object_type",
    "redshift",
    "magnitude",
    "bp_rp",
)

#: Canonical size modes.
SIZE_MODES: Tuple[str, ...] = (
    "magnitude",
    "object_type",
    "uniform",
)

#: Ordered list of (label, mode) pairs the UI dropdown surfaces.
COLOR_MODE_LABELS: Tuple[Tuple[str, str], ...] = (
    ("Natural Star Color", "natural"),
    ("Catalog Source", "catalog_source"),
    ("Object Type", "object_type"),
    ("Redshift", "redshift"),
    ("Magnitude", "magnitude"),
    ("BP-RP Color Index", "bp_rp"),
)

SIZE_MODE_LABELS: Tuple[Tuple[str, str], ...] = (
    ("Magnitude (default)", "magnitude"),
    ("Object Type", "object_type"),
    ("Uniform", "uniform"),
)


# ---------------------------------------------------------------------------
# Palette tables
# ---------------------------------------------------------------------------

#: Per-source default colour for the ``catalog_source`` mode. Unknown
#: sources fall back to a neutral grey.
_SOURCE_COLORS: Dict[str, Tuple[int, int, int]] = {
    "gaia_dr3":    (170, 191, 255),
    "gaia_dr2":    (170, 191, 255),
    "sdss_dr18":   (255, 200, 130),
    "sdss_dr17":   (255, 200, 130),
    "desi_edr":    (130, 220, 180),
    "desi_dr1":    (130, 220, 180),
    "jpl_horizons": (240, 220, 100),
    "unav_sample": (220, 220, 220),
}

#: Per-type fixed radius (C4D units before ``size_scale``) for the
#: ``object_type`` size mode. Tuned so a galaxy reads as larger than a
#: star at the same screen distance, which is the common artist
#: expectation.
_TYPE_SIZES: Dict[str, float] = {
    "star":       1.0,
    "galaxy":     3.0,
    "quasar":     2.0,
    "nebula":     4.0,
    "cluster":    3.5,
    "planet":     1.5,
    "exoplanet":  1.0,
    "moon":       0.8,
    "asteroid":   0.3,
    "comet":      1.2,
    "spacecraft": 0.6,
    "unknown":    1.0,
}

#: Cool-warm gradient (low value → blue, high value → red). Used by
#: the redshift and BP-RP encodings; physically motivated for both
#: (high-z = redshifted, redder; positive BP-RP = cooler/redder star).
_COOL_WARM_STOPS: Tuple[Tuple[float, Tuple[int, int, int]], ...] = (
    (0.00, (40,  60, 200)),
    (0.25, (40, 200, 200)),
    (0.50, (80, 200,  80)),
    (0.75, (255, 220, 80)),
    (1.00, (220,  60,  60)),
)

#: Brightness gradient (low value = bright = white-warm, high = dim
#: = grey). Used by the magnitude colour mode.
_BRIGHT_DIM_STOPS: Tuple[Tuple[float, Tuple[int, int, int]], ...] = (
    (0.00, (255, 250, 230)),
    (0.50, (180, 180, 180)),
    (1.00, (60,  60,  70)),
)


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


@dataclass
class VisualEncodingParams:
    """All knobs that control a single visual encoding pass.

    Defaults reproduce the schema's "natural" rendering exactly, so
    callers that don't change anything see the same output the
    point-cloud builder always produced.
    """

    color_mode: str = "natural"
    size_mode: str = "magnitude"

    #: Multiplies the final radius. Pure number; 1.0 = unchanged.
    size_scale: float = 1.0

    #: Multiplies the final radius **after** ``size_scale``. Mode
    #: parity with size_scale today; reserved as a separate knob so
    #: future modes can apply it conditionally (e.g. only to bright
    #: stars in a "starfield" preset).
    brightness_scale: float = 1.0

    #: Exponent applied to the magnitude→radius curve in the
    #: ``magnitude`` size mode. ``> 1`` widens the gap between bright
    #: and dim objects; ``< 1`` flattens it. ``1.0`` is the schema
    #: default.
    brightness_exaggeration: float = 1.0

    #: Min / max for the redshift colour ramp (anything outside is
    #: clamped). Defaults span DESI EDR's typical range.
    redshift_min: float = 0.0
    redshift_max: float = 3.0

    #: Min / max for the magnitude colour and size ramps. Defaults
    #: span the visible-bright Gaia range.
    magnitude_min: float = -1.5
    magnitude_max: float = 22.0

    #: Min / max for the BP-RP ramp. Negative = blue (hot O/B), large
    #: positive = red (M dwarfs, very red giants).
    bp_rp_min: float = -0.5
    bp_rp_max: float = 3.0

    def __post_init__(self) -> None:
        if self.color_mode not in COLOR_MODES:
            raise ValueError(
                f"unknown color_mode '{self.color_mode}'; valid: "
                f"{', '.join(COLOR_MODES)}"
            )
        if self.size_mode not in SIZE_MODES:
            raise ValueError(
                f"unknown size_mode '{self.size_mode}'; valid: "
                f"{', '.join(SIZE_MODES)}"
            )
        if self.size_scale <= 0:
            raise ValueError("size_scale must be > 0")
        if self.brightness_scale <= 0:
            raise ValueError("brightness_scale must be > 0")
        if self.brightness_exaggeration <= 0:
            raise ValueError("brightness_exaggeration must be > 0")
        if self.redshift_max <= self.redshift_min:
            raise ValueError("redshift_max must exceed redshift_min")
        if self.magnitude_max <= self.magnitude_min:
            raise ValueError("magnitude_max must exceed magnitude_min")
        if self.bp_rp_max <= self.bp_rp_min:
            raise ValueError("bp_rp_max must exceed bp_rp_min")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _clamp01(t: float) -> float:
    if t < 0.0:
        return 0.0
    if t > 1.0:
        return 1.0
    return t


def _normalize(value: float, vmin: float, vmax: float) -> float:
    if vmax <= vmin:
        return 0.5
    return _clamp01((value - vmin) / (vmax - vmin))


def _sample_gradient(
    stops: Tuple[Tuple[float, Tuple[int, int, int]], ...],
    t: float,
) -> Tuple[int, int, int]:
    """Piecewise-linear interpolation on an sRGB gradient."""
    t = _clamp01(t)
    for i in range(len(stops) - 1):
        ta, ca = stops[i]
        tb, cb = stops[i + 1]
        if t <= tb:
            if tb == ta:
                return ca
            u = (t - ta) / (tb - ta)
            return (
                int(round(ca[0] + (cb[0] - ca[0]) * u)),
                int(round(ca[1] + (cb[1] - ca[1]) * u)),
                int(round(ca[2] + (cb[2] - ca[2]) * u)),
            )
    return stops[-1][1]


# ---------------------------------------------------------------------------
# Per-mode colour functions
# ---------------------------------------------------------------------------


def color_natural(obj: CatalogObject) -> Tuple[int, int, int]:
    """Schema-default rendering: spectral-class palette for stars,
    type-default for everything else."""
    return display_color_for(obj.object_type, obj.spectral_type)


def color_by_catalog_source(source: Optional[str]) -> Tuple[int, int, int]:
    if source and source in _SOURCE_COLORS:
        return _SOURCE_COLORS[source]
    return _SOURCE_COLORS["unav_sample"]


def color_by_object_type(object_type: Optional[str]) -> Tuple[int, int, int]:
    return display_color_for(object_type or "unknown", spectral_type=None)


def color_by_redshift(
    redshift: Optional[float], vmin: float, vmax: float,
) -> Optional[Tuple[int, int, int]]:
    if redshift is None:
        return None
    return _sample_gradient(_COOL_WARM_STOPS, _normalize(redshift, vmin, vmax))


def color_by_magnitude(
    magnitude: Optional[float], vmin: float, vmax: float,
) -> Optional[Tuple[int, int, int]]:
    if magnitude is None:
        return None
    return _sample_gradient(_BRIGHT_DIM_STOPS, _normalize(magnitude, vmin, vmax))


def color_by_bp_rp(
    color_index: Optional[float], vmin: float, vmax: float,
) -> Optional[Tuple[int, int, int]]:
    if color_index is None:
        return None
    return _sample_gradient(_COOL_WARM_STOPS, _normalize(color_index, vmin, vmax))


# ---------------------------------------------------------------------------
# Per-mode size functions
# ---------------------------------------------------------------------------


def size_by_magnitude(
    magnitude: Optional[float],
    exaggeration: float = 1.0,
    base: float = 1.0,
    floor: float = 0.05,
    ceiling: float = 50.0,
) -> float:
    """Magnitude-driven radius. ``exaggeration`` warps the schema's
    default curve: ``r = base · 10**(-mag · exaggeration / 10)``,
    clamped to ``[floor, ceiling]``. ``exaggeration = 1`` exactly
    reproduces ``schema.render_radius_from_magnitude``."""
    if magnitude is None:
        return base
    if exaggeration == 1.0:
        return render_radius_from_magnitude(
            magnitude, base=base, floor=floor, ceiling=ceiling,
        )
    try:
        r = base * (10.0 ** (-float(magnitude) * exaggeration / 10.0))
    except (TypeError, ValueError, OverflowError):
        return base
    if r < floor:
        return floor
    if r > ceiling:
        return ceiling
    return r


def size_by_object_type(object_type: Optional[str]) -> float:
    if object_type and object_type in _TYPE_SIZES:
        return _TYPE_SIZES[object_type]
    return _TYPE_SIZES["unknown"]


def size_uniform(base: float = 1.0) -> float:
    return float(base)


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------


def encode_color(
    obj: CatalogObject, params: VisualEncodingParams,
) -> Tuple[int, int, int]:
    """Return the sRGB triple for ``obj`` under ``params.color_mode``.

    Modes whose required field is missing fall back to ``natural``
    so a legend never lies about silently-grey objects.
    """
    mode = params.color_mode
    if mode == "natural":
        return color_natural(obj)
    if mode == "catalog_source":
        return color_by_catalog_source(obj.catalog_source)
    if mode == "object_type":
        return color_by_object_type(obj.object_type)
    if mode == "redshift":
        c = color_by_redshift(obj.redshift, params.redshift_min, params.redshift_max)
        return c if c is not None else color_natural(obj)
    if mode == "magnitude":
        c = color_by_magnitude(
            obj.apparent_magnitude, params.magnitude_min, params.magnitude_max,
        )
        return c if c is not None else color_natural(obj)
    if mode == "bp_rp":
        c = color_by_bp_rp(obj.color_index, params.bp_rp_min, params.bp_rp_max)
        return c if c is not None else color_natural(obj)
    return color_natural(obj)  # defensive — __post_init__ already validates


def encode_size(
    obj: CatalogObject, params: VisualEncodingParams,
) -> float:
    """Return the radius (C4D units) for ``obj``, before ``size_scale``
    and ``brightness_scale`` are applied."""
    if params.size_mode == "magnitude":
        return size_by_magnitude(
            obj.apparent_magnitude,
            exaggeration=params.brightness_exaggeration,
        )
    if params.size_mode == "object_type":
        return size_by_object_type(obj.object_type)
    if params.size_mode == "uniform":
        return size_uniform()
    return size_by_magnitude(
        obj.apparent_magnitude, exaggeration=params.brightness_exaggeration,
    )


def encode(
    obj: CatalogObject, params: Optional[VisualEncodingParams] = None,
) -> Tuple[Tuple[int, int, int], float]:
    """One-shot: ``(rgb, radius)`` for ``obj`` under ``params``.

    ``params=None`` uses the dataclass defaults, which reproduce the
    schema's "natural" rendering with size_scale = brightness_scale =
    1.0. This is the call site the point-cloud builder uses.
    """
    if params is None:
        params = VisualEncodingParams()
    rgb = encode_color(obj, params)
    radius = encode_size(obj, params) * params.size_scale * params.brightness_scale
    return rgb, radius


def apply_to_object(
    obj: CatalogObject, params: Optional[VisualEncodingParams] = None,
) -> CatalogObject:
    """Mutate ``obj.display_color_rgb`` and ``obj.render_radius`` to
    match ``params``. Returns the same object for chaining."""
    rgb, radius = encode(obj, params)
    obj.display_color_rgb = rgb
    obj.render_radius = radius
    return obj


def apply_to_objects(
    objects, params: Optional[VisualEncodingParams] = None,
) -> List[CatalogObject]:
    """Apply the encoding to a sequence of objects in place. Returns
    the input as a list."""
    out: List[CatalogObject] = []
    for o in objects:
        apply_to_object(o, params)
        out.append(o)
    return out


# ---------------------------------------------------------------------------
# Convenience for the dialog: label ↔ token bidirection
# ---------------------------------------------------------------------------


def color_mode_for_label(label: str) -> str:
    for lbl, token in COLOR_MODE_LABELS:
        if lbl == label:
            return token
    return "natural"


def label_for_color_mode(token: str) -> str:
    for lbl, t in COLOR_MODE_LABELS:
        if t == token:
            return lbl
    return COLOR_MODE_LABELS[0][0]


def size_mode_for_label(label: str) -> str:
    for lbl, token in SIZE_MODE_LABELS:
        if lbl == label:
            return token
    return "magnitude"


def label_for_size_mode(token: str) -> str:
    for lbl, t in SIZE_MODE_LABELS:
        if t == token:
            return lbl
    return SIZE_MODE_LABELS[0][0]
