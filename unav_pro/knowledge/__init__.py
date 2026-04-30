"""UNAV Pro v1.3 knowledge layer.

Pure-stdlib helpers that turn a ``CatalogObject`` plus its
``metadata_json`` into a *classification* + *plain-language
summary* + *physical interpretation*. No AI / no network /
no hallucinations: the rules are deterministic and the output
is unit-tested.

The four submodules:

* ``object_classifier`` — coarse class for the inspector's
  "what is this?" header line.
* ``object_summary`` — multi-paragraph plain-text description.
* ``catalog_glossary`` — definitions of the field names the
  inspector renders.
* ``physical_interpretation`` — astrophysical helpers
  (absolute magnitude → luminosity-class hint; redshift →
  distance method note; proper-motion → drift summary).
"""

from __future__ import annotations

from .catalog_glossary import (
    GLOSSARY,
    GlossaryEntry,
    glossary_lookup,
    glossary_terms,
)
from .object_classifier import (
    KNOWN_CLASSES,
    ObjectClass,
    ObjectClassification,
    classify_object,
)
from .object_summary import (
    ObjectSummary,
    summarize_object,
)
from .physical_interpretation import (
    PROPER_MOTION_THRESHOLD_MASYR,
    distance_quality,
    motion_summary,
    spectral_class_hint,
)

__all__ = [
    "GLOSSARY", "GlossaryEntry", "glossary_lookup", "glossary_terms",
    "KNOWN_CLASSES", "ObjectClass", "ObjectClassification",
    "classify_object",
    "ObjectSummary", "summarize_object",
    "PROPER_MOTION_THRESHOLD_MASYR",
    "distance_quality", "motion_summary", "spectral_class_hint",
]
