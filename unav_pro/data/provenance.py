"""v3.2 data provenance.

Every catalog row UNAV ingests carries a story: which
catalog it came from, what query produced it, when, with
which connector version, what the source field names
were before normalisation, what coordinate system /
units the source uses, and what the known limitations
are.

The v3.2 provenance layer captures that story as a
**``ProvenanceRecord``** the connectors stamp into the
``metadata_json`` slot of every emitted ``CatalogObject``.
The metadata inspector reads it back; the dataset audit
CLI summarises it; export packages embed it.

This module is **pure stdlib + JSON-serialisable**. No
network calls, no Cinema 4D imports.

Schema policy
-------------

* The provenance shape is keyed in ``metadata_json``
  under the well-known top-level key ``"provenance"``
  (``PROVENANCE_METADATA_KEY``). Any pre-existing
  metadata stays untouched.
* ``schema_version`` bumps when the provenance shape
  changes incompatibly. v3.2 ships ``v=1``.
* Loaders accept missing fields (defaulted) but reject
  unknown ``schema_version`` values fail-closed.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Iterable, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


#: Key under ``CatalogObject.metadata_json`` where the
#: provenance dict lives.
PROVENANCE_METADATA_KEY: str = "provenance"

#: Schema version of the provenance record.
PROVENANCE_SCHEMA_VERSION: int = 1


#: Canonical coordinate-system tags. Free-form strings are
#: accepted but the audit tooling renders unknown values
#: with a "(custom)" suffix.
COORDINATE_SYSTEM_ICRS: str = "ICRS"
COORDINATE_SYSTEM_GALACTIC: str = "Galactic"
COORDINATE_SYSTEM_ECLIPTIC: str = "Ecliptic"
COORDINATE_SYSTEM_BARYCENTRIC: str = "Barycentric"

KNOWN_COORDINATE_SYSTEMS: Sequence[str] = (
    COORDINATE_SYSTEM_ICRS,
    COORDINATE_SYSTEM_GALACTIC,
    COORDINATE_SYSTEM_ECLIPTIC,
    COORDINATE_SYSTEM_BARYCENTRIC,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProvenanceError(ValueError):
    """Raised when provenance JSON is malformed or carries
    a future schema version."""


# ---------------------------------------------------------------------------
# ProvenanceRecord
# ---------------------------------------------------------------------------


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class ProvenanceRecord:
    """One row's provenance.

    Most fields are optional so connectors can fill what
    they know and leave the rest. The ``catalog_source``
    duplicates the row's ``catalog_source`` string so the
    record stays useful even when separated from its row
    (e.g. when displayed alone in the metadata inspector).
    """

    catalog_source: str = ""
    connector: str = ""
    connector_version: str = ""
    normalisation_version: str = ""
    fetched_at_iso: str = ""
    query_parameters: Dict[str, Any] = field(default_factory=dict)

    #: Mapping from canonical UNAV field → original source
    #: column (e.g. ``{"ra_deg": "ra", "parallax_mas":
    #: "parallax"}``). The audit tooling highlights every
    #: row whose mapping diverges from the connector
    #: default.
    original_field_names: Dict[str, str] = field(default_factory=dict)

    coordinate_system: str = ""
    units: Dict[str, str] = field(default_factory=dict)
    known_limitations: List[str] = field(default_factory=list)

    schema_version: int = PROVENANCE_SCHEMA_VERSION

    # ---------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "catalog_source": self.catalog_source,
            "connector": self.connector,
            "connector_version": self.connector_version,
            "normalisation_version": self.normalisation_version,
            "fetched_at_iso": self.fetched_at_iso,
            "query_parameters": dict(self.query_parameters),
            "original_field_names": dict(self.original_field_names),
            "coordinate_system": self.coordinate_system,
            "units": dict(self.units),
            "known_limitations": list(self.known_limitations),
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "ProvenanceRecord":
        if d is None:
            return cls()
        if not isinstance(d, dict):
            raise ProvenanceError(
                "provenance payload is not an object",
            )
        version = d.get("schema_version", PROVENANCE_SCHEMA_VERSION)
        try:
            version_i = int(version)
        except (TypeError, ValueError) as exc:
            raise ProvenanceError(
                f"provenance schema_version not an integer: {version!r}",
            ) from exc
        if version_i > PROVENANCE_SCHEMA_VERSION:
            raise ProvenanceError(
                f"provenance schema_version {version_i} is newer "
                f"than this build understands "
                f"({PROVENANCE_SCHEMA_VERSION})."
            )
        return cls(
            schema_version=version_i,
            catalog_source=str(d.get("catalog_source", "") or ""),
            connector=str(d.get("connector", "") or ""),
            connector_version=str(d.get("connector_version", "") or ""),
            normalisation_version=str(
                d.get("normalisation_version", "") or "",
            ),
            fetched_at_iso=str(d.get("fetched_at_iso", "") or ""),
            query_parameters=dict(d.get("query_parameters") or {}),
            original_field_names=dict(d.get("original_field_names") or {}),
            coordinate_system=str(d.get("coordinate_system", "") or ""),
            units=dict(d.get("units") or {}),
            known_limitations=[
                str(x) for x in (d.get("known_limitations") or []) if str(x)
            ],
        )

    # ---------------------------------------------------- helpers
    def is_empty(self) -> bool:
        """True iff no field carries information beyond the
        defaults. Connectors that haven't been updated to
        emit provenance hand back ``None``; we treat
        ``ProvenanceRecord()`` as a synonym for "no
        provenance."
        """
        return self == ProvenanceRecord()

    def short_summary(self) -> str:
        """One-line summary for log lines + status panels."""
        parts: List[str] = []
        if self.catalog_source:
            parts.append(self.catalog_source)
        if self.connector:
            ver = (
                f" v{self.connector_version}"
                if self.connector_version else ""
            )
            parts.append(f"via {self.connector}{ver}")
        if self.fetched_at_iso:
            parts.append(f"fetched {self.fetched_at_iso}")
        if self.coordinate_system:
            parts.append(f"coords={self.coordinate_system}")
        return " · ".join(parts) if parts else "(no provenance)"

    def render(self) -> str:
        """Multi-line human-readable rendering. Used by the
        metadata inspector and the audit-CLI."""
        if self.is_empty():
            return "(no provenance recorded)"
        lines: List[str] = []
        lines.append(f"Catalog source : {self.catalog_source or '(unknown)'}")
        if self.connector:
            ver = (
                f" v{self.connector_version}"
                if self.connector_version else ""
            )
            lines.append(f"Connector      : {self.connector}{ver}")
        if self.normalisation_version:
            lines.append(
                f"Normalisation  : v{self.normalisation_version}",
            )
        if self.fetched_at_iso:
            lines.append(f"Fetched at     : {self.fetched_at_iso}")
        if self.coordinate_system:
            tag = self.coordinate_system
            if tag not in KNOWN_COORDINATE_SYSTEMS:
                tag = f"{tag} (custom)"
            lines.append(f"Coordinate sys : {tag}")
        if self.units:
            unit_str = ", ".join(
                f"{k}={v}" for k, v in sorted(self.units.items())
            )
            lines.append(f"Units          : {unit_str}")
        if self.original_field_names:
            mappings = ", ".join(
                f"{k}←{v}"
                for k, v in sorted(self.original_field_names.items())
            )
            lines.append(f"Field mapping  : {mappings}")
        if self.query_parameters:
            qp = ", ".join(
                f"{k}={v}"
                for k, v in sorted(self.query_parameters.items())
            )
            lines.append(f"Query params   : {qp}")
        if self.known_limitations:
            lines.append("Known limitations:")
            for note in self.known_limitations:
                lines.append(f"  - {note}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CatalogObject integration
# ---------------------------------------------------------------------------


def attach_provenance(
    obj: Any, record: ProvenanceRecord,
) -> Any:
    """Stamp ``record`` into ``obj.metadata_json`` under
    the ``"provenance"`` key.

    ``obj`` is a ``CatalogObject``; we type it loosely so
    this module stays import-agnostic from the rest of
    the data layer (no circular import). Returns ``obj``
    so callers can chain ``attach_provenance(obj, ...)``.
    """
    blob = getattr(obj, "metadata_json", None) or "{}"
    try:
        meta = json.loads(blob)
        if not isinstance(meta, dict):
            meta = {}
    except json.JSONDecodeError:
        meta = {}
    meta[PROVENANCE_METADATA_KEY] = record.to_dict()
    obj.metadata_json = json.dumps(meta, sort_keys=True)
    return obj


def read_provenance(obj: Any) -> Optional[ProvenanceRecord]:
    """Return the row's ``ProvenanceRecord``, or ``None``
    when none is stamped. Defensive against malformed
    metadata: we never raise — a row with broken JSON
    just looks "no provenance" to the inspector."""
    blob = getattr(obj, "metadata_json", None) or "{}"
    try:
        meta = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(meta, dict):
        return None
    payload = meta.get(PROVENANCE_METADATA_KEY)
    if payload is None:
        return None
    try:
        return ProvenanceRecord.from_dict(payload)
    except ProvenanceError:
        return None


def attach_to_iter(
    objects: Iterable[Any], record: ProvenanceRecord,
) -> List[Any]:
    """Bulk variant: stamp every object with the same
    ``record``. Returns the list of stamped objects so
    the caller can feed them straight to a writer."""
    out: List[Any] = []
    for obj in objects:
        attach_provenance(obj, record)
        out.append(obj)
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


@dataclass
class ProvenanceSummary:
    """Aggregate of distinct provenance records seen in a
    catalog. Surfaced in the audit report + the export
    package's manifest."""

    distinct_sources: List[str] = field(default_factory=list)
    distinct_connectors: List[str] = field(default_factory=list)
    distinct_coordinate_systems: List[str] = field(default_factory=list)
    earliest_fetched_iso: str = ""
    latest_fetched_iso: str = ""
    rows_with_provenance: int = 0
    rows_without_provenance: int = 0
    aggregated_known_limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def is_empty(self) -> bool:
        return (
            self.rows_with_provenance == 0
            and self.rows_without_provenance == 0
        )

    def render(self) -> str:
        lines: List[str] = []
        lines.append(
            f"Rows with provenance   : {self.rows_with_provenance}",
        )
        lines.append(
            f"Rows without provenance: {self.rows_without_provenance}",
        )
        if self.distinct_sources:
            lines.append(
                "Distinct sources       : "
                + ", ".join(self.distinct_sources),
            )
        if self.distinct_connectors:
            lines.append(
                "Distinct connectors    : "
                + ", ".join(self.distinct_connectors),
            )
        if self.distinct_coordinate_systems:
            lines.append(
                "Coordinate systems     : "
                + ", ".join(self.distinct_coordinate_systems),
            )
        if self.earliest_fetched_iso:
            lines.append(
                f"Earliest fetch         : {self.earliest_fetched_iso}",
            )
        if self.latest_fetched_iso:
            lines.append(
                f"Latest fetch           : {self.latest_fetched_iso}",
            )
        if self.aggregated_known_limitations:
            lines.append("Aggregated known limitations:")
            for note in self.aggregated_known_limitations:
                lines.append(f"  - {note}")
        return "\n".join(lines)


def summarise_provenance(
    objects: Iterable[Any],
) -> ProvenanceSummary:
    """Walk a sequence of catalog rows and produce a
    ``ProvenanceSummary``. Pure helper; no I/O. Stable
    iteration: the resulting lists are sorted so a
    summary is byte-identical across runs."""
    summary = ProvenanceSummary()
    sources: set = set()
    connectors: set = set()
    coords: set = set()
    notes: set = set()
    earliest: Optional[str] = None
    latest: Optional[str] = None
    with_prov = 0
    without_prov = 0
    for obj in objects:
        rec = read_provenance(obj)
        if rec is None or rec.is_empty():
            without_prov += 1
            continue
        with_prov += 1
        if rec.catalog_source:
            sources.add(rec.catalog_source)
        if rec.connector:
            connectors.add(rec.connector)
        if rec.coordinate_system:
            coords.add(rec.coordinate_system)
        for note in rec.known_limitations:
            notes.add(note)
        stamp = rec.fetched_at_iso
        if stamp:
            if earliest is None or stamp < earliest:
                earliest = stamp
            if latest is None or stamp > latest:
                latest = stamp
    summary.distinct_sources = sorted(sources)
    summary.distinct_connectors = sorted(connectors)
    summary.distinct_coordinate_systems = sorted(coords)
    summary.aggregated_known_limitations = sorted(notes)
    summary.earliest_fetched_iso = earliest or ""
    summary.latest_fetched_iso = latest or ""
    summary.rows_with_provenance = with_prov
    summary.rows_without_provenance = without_prov
    return summary


# ---------------------------------------------------------------------------
# Connector-side builder
# ---------------------------------------------------------------------------


def build_record(
    *,
    catalog_source: str,
    connector: str,
    connector_version: str = "",
    normalisation_version: str = "",
    query_parameters: Optional[Dict[str, Any]] = None,
    original_field_names: Optional[Dict[str, str]] = None,
    coordinate_system: str = COORDINATE_SYSTEM_ICRS,
    units: Optional[Dict[str, str]] = None,
    known_limitations: Optional[Iterable[str]] = None,
) -> ProvenanceRecord:
    """Convenience constructor connectors call. Stamps the
    fetch timestamp + normalises the inputs so a connector
    can hand bare dicts in."""
    return ProvenanceRecord(
        catalog_source=catalog_source,
        connector=connector,
        connector_version=connector_version,
        normalisation_version=normalisation_version,
        fetched_at_iso=_utc_iso(),
        query_parameters=dict(query_parameters or {}),
        original_field_names=dict(original_field_names or {}),
        coordinate_system=coordinate_system,
        units=dict(units or {}),
        known_limitations=[
            str(x) for x in (known_limitations or []) if str(x)
        ],
    )
