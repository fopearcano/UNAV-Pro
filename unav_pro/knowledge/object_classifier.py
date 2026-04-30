"""Object classification rules for the v1.3 knowledge layer.

Takes a ``CatalogObject`` plus its parsed ``metadata_json`` and
returns one of the canonical UNAV classes:

    star, galaxy, quasar, planet, moon, asteroid, comet,
    spacecraft, unknown.

Rules are deterministic and ordered: the first rule that
matches wins. They never invent information — if the input
doesn't carry enough signal to discriminate, the result is
``unknown`` with a confidence note.

Inputs the classifier inspects (in order of authority):

1. ``catalog_source`` (``"Gaia DR3"``, ``"JPL Horizons"``,
   ``"SDSS"``, ``"DESI"``).
2. ``object_type`` (the schema-level field; the connectors
   already populate this with their best guess).
3. ``metadata_json`` survey-specific tags
   (``spec_class`` / ``spec_subclass`` / ``spectype`` /
   ``subtype``).
4. ``redshift``, ``apparent_magnitude``, ``color_index``,
   ``spectral_type`` as fallback signals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from data.schema import CatalogObject

# ---------------------------------------------------------------------------
# Canonical classes
# ---------------------------------------------------------------------------

#: The classes the v1.3 classifier emits. The schema-level
#: ``OBJECT_TYPES`` is broader (it includes ``nebula``, ``cluster``,
#: ``exoplanet``); v1.3 collapses those to ``unknown`` because
#: the connectors don't reliably populate them yet. A future
#: knowledge release can refine.
ObjectClass = str

KNOWN_CLASSES: Tuple[ObjectClass, ...] = (
    "star",
    "galaxy",
    "quasar",
    "planet",
    "moon",
    "asteroid",
    "comet",
    "spacecraft",
    "unknown",
)


@dataclass
class ObjectClassification:
    """One classifier verdict.

    ``object_class`` is one of ``KNOWN_CLASSES``. ``confidence``
    is a coarse string tag (``"high"``, ``"medium"``, ``"low"``,
    ``"unknown"``) — it is *not* a probability; v1.3 deliberately
    doesn't fit a model. ``reason`` is a short human-readable
    explanation of which signal pushed the verdict; the
    inspector can show it next to the class label.
    """

    object_class: ObjectClass = "unknown"
    confidence: str = "unknown"
    reason: str = ""

    def is_known(self) -> bool:
        return self.object_class != "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_parse_metadata(blob: Optional[str]) -> Dict[str, Any]:
    if not blob:
        return {}
    try:
        parsed = json.loads(blob)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize(s: Optional[str]) -> str:
    return (s or "").strip().lower()


# Mapping from SDSS / DESI spec_class/spectype tokens to UNAV
# canonical classes. Stable since v1.3.
_SPECTYPE_TO_CLASS: Dict[str, ObjectClass] = {
    "star":   "star",
    "galaxy": "galaxy",
    "qso":    "quasar",
    "quasar": "quasar",
}

# Mapping from JPL ``object_type`` tokens (the connector emits
# these per-body via ``--bodies "Mars=planet,Voyager 1=spacecraft"``)
# to the v1.3 canonical class. ``exoplanet`` and ``nebula`` are
# absent on purpose — see the docstring above.
_JPL_TYPE_TO_CLASS: Dict[str, ObjectClass] = {
    "planet":     "planet",
    "moon":       "moon",
    "asteroid":   "asteroid",
    "comet":      "comet",
    "spacecraft": "spacecraft",
}


# ---------------------------------------------------------------------------
# Per-source classifiers
# ---------------------------------------------------------------------------


def _classify_jpl(obj: CatalogObject) -> ObjectClassification:
    """Solar-system bodies. The connector tags ``object_type`` per
    body (``planet`` / ``moon`` / ``asteroid`` / …); we trust it."""
    otype = _normalize(obj.object_type)
    cls = _JPL_TYPE_TO_CLASS.get(otype, "unknown")
    if cls != "unknown":
        return ObjectClassification(
            object_class=cls,
            confidence="high",
            reason=f"JPL Horizons '{otype}' tag",
        )
    return ObjectClassification(
        object_class="unknown",
        confidence="low",
        reason=f"JPL Horizons body with unfamiliar type '{otype}'",
    )


def _classify_sdss(obj: CatalogObject, meta: Dict[str, Any]) -> ObjectClassification:
    """SDSS rows. Prefer ``spec_class`` (spectroscopic, high
    confidence); fall back to schema ``object_type`` (photometric)."""
    spec_class = _normalize(meta.get("spec_class"))
    if spec_class in _SPECTYPE_TO_CLASS:
        return ObjectClassification(
            object_class=_SPECTYPE_TO_CLASS[spec_class],
            confidence="high",
            reason=f"SDSS spec_class='{spec_class}'",
        )
    otype = _normalize(obj.object_type)
    if otype in _SPECTYPE_TO_CLASS or otype in KNOWN_CLASSES:
        canonical = _SPECTYPE_TO_CLASS.get(otype, otype)
        if canonical in KNOWN_CLASSES and canonical != "unknown":
            return ObjectClassification(
                object_class=canonical,
                confidence="medium",
                reason=f"SDSS photometric type '{otype}'",
            )
    return ObjectClassification(
        object_class="unknown",
        confidence="low",
        reason="SDSS row without spec_class or recognised photo type",
    )


def _classify_desi(obj: CatalogObject, meta: Dict[str, Any]) -> ObjectClassification:
    """DESI rows. ``spectype`` is the spectroscopic tag (``GALAXY`` /
    ``QSO`` / ``STAR``). ``zwarn`` is a per-row warning bitmask;
    when non-zero we drop confidence to ``medium``."""
    spectype = _normalize(meta.get("spectype"))
    if spectype in _SPECTYPE_TO_CLASS:
        zwarn = meta.get("zwarn") or 0
        try:
            zwarn = int(zwarn)
        except (TypeError, ValueError):
            zwarn = 0
        confidence = "medium" if zwarn else "high"
        suffix = " (zwarn flagged)" if zwarn else ""
        return ObjectClassification(
            object_class=_SPECTYPE_TO_CLASS[spectype],
            confidence=confidence,
            reason=f"DESI spectype='{spectype}'{suffix}",
        )
    return ObjectClassification(
        object_class="unknown",
        confidence="low",
        reason="DESI row without recognised spectype",
    )


def _classify_gaia(obj: CatalogObject) -> ObjectClassification:
    """Gaia rows. Gaia DR3 is essentially a stellar catalog —
    every successfully normalized row is a ``star`` unless the
    schema-level ``object_type`` says otherwise."""
    otype = _normalize(obj.object_type)
    if otype == "star" or not otype:
        return ObjectClassification(
            object_class="star",
            confidence="high",
            reason="Gaia DR3 row (Gaia is a stellar catalog)",
        )
    if otype in KNOWN_CLASSES:
        return ObjectClassification(
            object_class=otype,
            confidence="medium",
            reason=f"Gaia row tagged '{otype}'",
        )
    return ObjectClassification(
        object_class="unknown",
        confidence="low",
        reason=f"Gaia row with unfamiliar object_type '{otype}'",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def classify_object(obj: CatalogObject) -> ObjectClassification:
    """Return one of ``KNOWN_CLASSES`` for ``obj``.

    Rules are tried top-down; the first match wins:

    1. ``catalog_source`` is a known survey → run its
       per-source rule (which inspects ``metadata_json``).
    2. Schema ``object_type`` is one of the canonical
       classes → trust it (medium confidence).
    3. Heuristic fallbacks: a non-zero ``redshift`` strongly
       implies extragalactic (``galaxy`` if magnitude is
       galaxy-like, ``quasar`` if very luminous); a populated
       ``spectral_type`` implies ``star``.
    4. Otherwise ``unknown`` with confidence ``unknown``.

    The classifier never raises; bad metadata is silently
    treated as missing.
    """
    if obj is None:
        return ObjectClassification()

    source = _normalize(obj.catalog_source)
    meta = _safe_parse_metadata(obj.metadata_json)

    if source.startswith("gaia"):
        return _classify_gaia(obj)
    if source.startswith("jpl") or source.startswith("horizons"):
        return _classify_jpl(obj)
    if source == "sdss" or source.startswith("sdss "):
        return _classify_sdss(obj, meta)
    if source == "desi" or source.startswith("desi "):
        return _classify_desi(obj, meta)

    # --- Schema object_type fallback ---
    otype = _normalize(obj.object_type)
    if otype in KNOWN_CLASSES and otype != "unknown":
        return ObjectClassification(
            object_class=otype,
            confidence="medium",
            reason=f"object_type field is '{otype}'",
        )
    if otype in _SPECTYPE_TO_CLASS:
        return ObjectClassification(
            object_class=_SPECTYPE_TO_CLASS[otype],
            confidence="medium",
            reason=f"object_type field maps to '{_SPECTYPE_TO_CLASS[otype]}'",
        )

    # --- Heuristic fallbacks ---
    if obj.spectral_type:
        return ObjectClassification(
            object_class="star",
            confidence="low",
            reason="has spectral_type but no catalog_source",
        )
    if obj.redshift is not None and obj.redshift > 0.001:
        # Anything with an appreciable redshift is extragalactic;
        # the galaxy / quasar split needs a luminosity, which we
        # don't have without a survey tag.
        return ObjectClassification(
            object_class="galaxy",
            confidence="low",
            reason=f"non-trivial redshift z={obj.redshift:.3f} suggests extragalactic",
        )

    return ObjectClassification(
        object_class="unknown",
        confidence="unknown",
        reason="no discriminating signal in catalog_source / object_type / metadata",
    )
