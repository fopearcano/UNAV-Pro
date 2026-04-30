"""Plain-text summary generator for the v1.3 knowledge layer.

Turns a ``CatalogObject`` into a deterministic, multi-section
plain-text description the metadata inspector can render under
the "Plain-language Summary" heading.

Design rules:

* **Deterministic.** Same input → byte-identical output.
* **No invention.** If a field is missing the summary either
  skips that sentence or says "unknown" explicitly.
* **No external services.** No AI, no network, no astropy.
* **One narrator voice.** Carefully chosen lead-ins so the
  output reads as continuous prose rather than a bullet list.

The output structure has up to seven paragraphs:

1. **Lead** — what it is + which catalog it came from.
2. **Position** — direction + distance + how the distance was
   determined (and a warning if it's a proxy).
3. **Brightness** — apparent / absolute magnitude + colour or
   spectral hint.
4. **Motion** — proper motion + radial velocity (with v1.2
   "drift" framing).
5. **Cosmology** — redshift-only paragraph for galaxies / quasars.
6. **Time-domain** — present only for solar-system bodies (the
   epoch the position is valid for + the body's center frame).
7. **Caveats** — explicit list of unknown fields the artist
   should be aware of.

Sections that can't be filled are simply omitted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from data.connectors.redshift_distance import (
    DISTANCE_METHOD_REDSHIFT_PROXY,
)
from data.schema import CatalogObject

from .object_classifier import ObjectClassification, classify_object
from .physical_interpretation import (
    distance_quality,
    motion_summary,
    spectral_class_hint,
)


@dataclass
class ObjectSummary:
    """One generated summary.

    ``paragraphs`` is the structured list of section strings.
    ``classification`` is the classifier's verdict, surfaced
    here so callers can drive the inspector header without
    re-running ``classify_object``. ``missing_fields`` is the
    list of catalog fields the summary couldn't fill in — the
    inspector renders this under the "Missing Data" heading.
    """

    classification: ObjectClassification
    paragraphs: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)

    def as_text(self) -> str:
        """Stitch the paragraphs together with blank-line
        separators. Returns the empty string when no paragraphs
        could be produced."""
        return "\n\n".join(p for p in self.paragraphs if p)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_CLASS_ARTICLES: Dict[str, str] = {
    "star":       "a",
    "galaxy":     "a",
    "quasar":     "a",
    "planet":     "a",
    "moon":       "a",
    "asteroid":   "an",
    "comet":      "a",
    "spacecraft": "a",
    "unknown":    "an",
}


def _safe_parse_meta(blob: Optional[str]) -> Dict[str, Any]:
    if not blob:
        return {}
    try:
        parsed = json.loads(blob)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _label_for(obj: CatalogObject) -> str:
    """Best human-readable label for ``obj`` — common name, then
    name, then uid."""
    if obj.common_name:
        return obj.common_name
    if obj.name:
        return obj.name
    return obj.uid or "<no uid>"


def _format_distance(distance_pc: float) -> str:
    """Render ``distance_pc`` in the most artist-friendly unit."""
    d = float(distance_pc)
    if d < 0.001:
        return f"{d * 206264.806:.1f} AU"
    if d < 1.0:
        return f"{d * 1000.0:.1f} mpc"
    if d < 1_000.0:
        return f"{d:.2f} pc"
    if d < 1_000_000.0:
        return f"{d / 1_000.0:.2f} kpc"
    return f"{d / 1_000_000.0:.2f} Mpc"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_lead(obj: CatalogObject, cls: ObjectClassification) -> str:
    label = _label_for(obj)
    article = _CLASS_ARTICLES.get(cls.object_class, "a")
    catalog = obj.catalog_source or "an unspecified catalog"
    if cls.object_class == "unknown":
        return (
            f"{label} is an object catalogued in {catalog}. "
            "Its class could not be determined from the available "
            "metadata."
        )
    return (
        f"{label} is {article} {cls.object_class} catalogued in "
        f"{catalog}."
    )


def _build_position(obj: CatalogObject, meta: Dict[str, Any]) -> str:
    parts: List[str] = []
    parts.append(
        f"It sits at RA {obj.ra_deg:.4f}°, Dec {obj.dec_deg:+.4f}° "
        f"in the ICRS frame."
    )
    label, note = distance_quality(
        distance_parsec=obj.distance_parsec,
        parallax_mas=obj.parallax_mas,
        distance_method=meta.get("distance_method"),
        parallax_error_mas=meta.get("parallax_error_mas"),
    )
    if obj.distance_parsec is not None and obj.distance_parsec > 0.0:
        parts.append(
            f"Distance is {_format_distance(obj.distance_parsec)} ({note})"
        )
    elif label == "unknown":
        parts.append("Distance is unknown.")
    else:
        parts.append(f"Distance is {note}")
    return " ".join(parts)


def _build_brightness(
    obj: CatalogObject, cls: ObjectClassification,
) -> Optional[str]:
    bits: List[str] = []
    if obj.apparent_magnitude is not None:
        bits.append(f"apparent magnitude {obj.apparent_magnitude:+.2f}")
    if obj.absolute_magnitude is not None:
        bits.append(f"absolute magnitude {obj.absolute_magnitude:+.2f}")
    if obj.color_index is not None:
        bits.append(f"colour index {obj.color_index:+.3f}")
    spectral = spectral_class_hint(obj.spectral_type)
    if spectral:
        bits.append(f"spectral hint: {spectral}")
    if not bits:
        return None
    return "Photometry — " + ", ".join(bits) + "."


def _build_motion(obj: CatalogObject) -> Optional[str]:
    drift = motion_summary(obj.proper_motion_ra, obj.proper_motion_dec)
    rv_part: Optional[str] = None
    if obj.radial_velocity_kms is not None:
        rv = float(obj.radial_velocity_kms)
        verb = "receding" if rv > 0 else "approaching"
        rv_part = (
            f"radial velocity {rv:+.1f} km/s ({verb} along the line of sight)"
        )
    if not drift and not rv_part:
        return None
    pieces: List[str] = []
    if drift:
        pieces.append(drift)
    if rv_part:
        pieces.append(rv_part)
    return "Motion — " + "; ".join(pieces) + "."


def _build_cosmology(obj: CatalogObject, meta: Dict[str, Any]) -> Optional[str]:
    if obj.redshift is None:
        return None
    z = float(obj.redshift)
    proxy = meta.get("distance_method") == DISTANCE_METHOD_REDSHIFT_PROXY
    line = f"Measured redshift z = {z:.4f}"
    if proxy:
        line += (
            "; the catalogued distance is a Hubble-law proxy and is "
            "approximate."
        )
    else:
        line += "."
    return line


def _build_solar_system(
    obj: CatalogObject, meta: Dict[str, Any], cls: ObjectClassification,
) -> Optional[str]:
    """Solar-system rows carry ``epoch`` / ``center`` / ``ref_plane``
    in their metadata. Surface those so the artist knows the
    position is *not* a fixed star."""
    if cls.object_class not in {"planet", "moon", "asteroid", "comet", "spacecraft"}:
        return None
    epoch = meta.get("epoch")
    center = meta.get("center")
    bits: List[str] = []
    if epoch:
        bits.append(f"position is reported for epoch {epoch}")
    if center:
        bits.append(f"observed from center frame {center}")
    if not bits:
        return (
            "This is a solar-system body — its position is "
            "epoch-dependent (the position you see was valid for the "
            "epoch when the row was fetched)."
        )
    return "Solar-system context — " + "; ".join(bits) + "."


def _build_caveats(obj: CatalogObject, missing: List[str]) -> Optional[str]:
    """Render the caveat paragraph from the ``missing`` field list,
    plus any general per-class caveats."""
    if not missing:
        return None
    return (
        "Caveats — fields not reported by the source catalog: "
        + ", ".join(sorted(missing))
        + "."
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


# Map each catalog field to the heading the caveat list shows
# the user. Keep names short; the inspector can prefix
# "missing:" itself.
_CAVEAT_FIELD_LABELS = {
    "distance_parsec":      "distance",
    "parallax_mas":         "parallax",
    "redshift":             "redshift",
    "radial_velocity_kms":  "radial velocity",
    "proper_motion_ra":     "proper motion (RA)",
    "proper_motion_dec":    "proper motion (Dec)",
    "apparent_magnitude":   "apparent magnitude",
    "absolute_magnitude":   "absolute magnitude",
    "color_index":          "colour index",
    "spectral_type":        "spectral type",
}


def _collect_missing(obj: CatalogObject) -> List[str]:
    """List the human-readable labels of fields that are absent
    on ``obj``. RA/Dec are always required so we don't list
    them; we only flag the optional astrometric / photometric
    fields."""
    out: List[str] = []
    for name, label in _CAVEAT_FIELD_LABELS.items():
        if getattr(obj, name, None) in (None, ""):
            out.append(label)
    return out


def summarize_object(obj: CatalogObject) -> ObjectSummary:
    """Build a deterministic, plain-text ``ObjectSummary`` for
    ``obj``. Runs the classifier internally; the caller can
    extract ``summary.classification`` for the inspector header
    instead of double-classifying.

    Never raises: malformed metadata is silently treated as
    missing. The returned summary's ``paragraphs`` field is
    always at least one element long (the lead paragraph)."""
    cls = classify_object(obj)
    meta = _safe_parse_meta(obj.metadata_json) if obj is not None else {}

    paragraphs: List[str] = []
    paragraphs.append(_build_lead(obj, cls))
    paragraphs.append(_build_position(obj, meta))

    bright = _build_brightness(obj, cls)
    if bright:
        paragraphs.append(bright)

    motion = _build_motion(obj)
    if motion:
        paragraphs.append(motion)

    cosmo = _build_cosmology(obj, meta)
    if cosmo:
        paragraphs.append(cosmo)

    solar = _build_solar_system(obj, meta, cls)
    if solar:
        paragraphs.append(solar)

    missing = _collect_missing(obj)
    caveats = _build_caveats(obj, missing)
    if caveats:
        paragraphs.append(caveats)

    return ObjectSummary(
        classification=cls,
        paragraphs=paragraphs,
        missing_fields=missing,
    )
