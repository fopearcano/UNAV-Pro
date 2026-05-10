"""v3.2 dataset validation report.

Walks a stream of ``CatalogObject`` rows and produces a
**``ValidationReport``** that calls out every row whose
data fails a science-correctness rule:

* missing coordinates,
* invalid parallax (≤ 0 or comically large),
* missing epoch (when proper-motion / ephemeris fields
  imply one is required),
* invalid redshift (negative; or absurdly large for a
  galaxy / quasar source),
* duplicate uid,
* malformed ``metadata_json``,
* suspicious distance values (negative; > 14.5 Gpc),
* unsupported / unknown units in the row's provenance.

The report is **structured**: each issue is a
``ValidationIssue`` with a stable ``code``, a severity
band, the affected uid, and a human description. The
audit CLI renders the report as Markdown; the export
package embeds a counts-only summary; the dialog's
*Dataset Audit* panel renders the warnings count.

Pure stdlib; no Cinema 4D imports. Defensive against
unknown row shapes — every probe is duck-typed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .provenance import (
    ProvenanceRecord,
    ProvenanceSummary,
    read_provenance,
    summarise_provenance,
)


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------


SEVERITY_INFO: str = "info"
SEVERITY_WARN: str = "warn"
SEVERITY_ERROR: str = "error"

SEVERITY_ORDER: Tuple[str, ...] = (
    SEVERITY_INFO, SEVERITY_WARN, SEVERITY_ERROR,
)


# ---------------------------------------------------------------------------
# Validation issue codes
# ---------------------------------------------------------------------------


CODE_MISSING_COORDINATES: str = "missing_coordinates"
CODE_INVALID_PARALLAX: str = "invalid_parallax"
CODE_MISSING_EPOCH: str = "missing_epoch"
CODE_INVALID_REDSHIFT: str = "invalid_redshift"
CODE_DUPLICATE_UID: str = "duplicate_uid"
CODE_MALFORMED_METADATA: str = "malformed_metadata_json"
CODE_SUSPICIOUS_DISTANCE: str = "suspicious_distance"
CODE_UNSUPPORTED_UNITS: str = "unsupported_units"
CODE_NO_PROVENANCE: str = "no_provenance"

ALL_CODES: Tuple[str, ...] = (
    CODE_MISSING_COORDINATES, CODE_INVALID_PARALLAX,
    CODE_MISSING_EPOCH, CODE_INVALID_REDSHIFT,
    CODE_DUPLICATE_UID, CODE_MALFORMED_METADATA,
    CODE_SUSPICIOUS_DISTANCE, CODE_UNSUPPORTED_UNITS,
    CODE_NO_PROVENANCE,
)


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


#: Anything beyond this is treated as suspicious. The
#: edge of the observable universe is ~14 Gpc; stretching
#: a hair past that catches negative-distance bugs and
#: clearly unphysical placeholder values.
MAX_DISTANCE_PC: float = 14.5e9

#: Parallaxes larger than this are unphysical (the closest
#: star is Proxima Centauri at ~770 mas).
MAX_PARALLAX_MAS: float = 10_000.0

#: Redshift sanity bound. Real high-z surveys reach z≈10;
#: anything past ~15 is a placeholder bug.
MAX_REDSHIFT: float = 15.0

#: Canonical UNAV unit strings. The provenance unit
#: validator treats anything outside this set as
#: "unsupported" (warning, not error).
KNOWN_UNITS: Dict[str, Tuple[str, ...]] = {
    "ra": ("deg",),
    "dec": ("deg",),
    "parallax": ("mas",),
    "distance": ("pc", "kpc", "Mpc"),
    "magnitude": ("mag", "vega_mag", "AB_mag"),
    "epoch": ("julian_date", "modified_julian_date", "year"),
    "proper_motion": ("mas/yr", "arcsec/yr"),
    "redshift": ("dimensionless", ""),
    "color": ("mag", ""),
    "radial_velocity": ("km/s",),
    "position": ("pc", "C4D_world_units"),
    "rotation": ("radians_HPB",),
    "fov": ("radians_horizontal",),
    "time": ("seconds",),
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ValidationIssue:
    """One finding. ``uid`` is the row id (or ``""`` when
    the issue is row-agnostic); ``code`` is a stable
    machine identifier; ``severity`` is one of
    ``SEVERITY_*``; ``detail`` is human prose."""

    code: str
    severity: str
    uid: str
    detail: str
    field: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationCounts:
    """Aggregate per-code counters."""

    rows_total: int = 0
    rows_with_issues: int = 0
    by_code: Dict[str, int] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)

    def total(self) -> int:
        return sum(self.by_code.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rows_total": self.rows_total,
            "rows_with_issues": self.rows_with_issues,
            "by_code": dict(self.by_code),
            "by_severity": dict(self.by_severity),
            "total_issues": self.total(),
        }


@dataclass
class ValidationReport:
    """Top-level report. ``issues`` is an ordered list
    (input order, then severity-stable). ``counts`` is the
    aggregate the dialog renders."""

    counts: ValidationCounts = field(default_factory=ValidationCounts)
    issues: List[ValidationIssue] = field(default_factory=list)
    provenance: Optional[ProvenanceSummary] = None
    notes: List[str] = field(default_factory=list)

    # ---------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        return {
            "counts": self.counts.to_dict(),
            "issues": [i.to_dict() for i in self.issues],
            "provenance": (
                self.provenance.to_dict() if self.provenance else None
            ),
            "notes": list(self.notes),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True,
        )

    # ---------------------------------------------------- helpers
    def has_issues(self) -> bool:
        return bool(self.issues)

    def issues_by_code(self) -> Dict[str, List[ValidationIssue]]:
        out: Dict[str, List[ValidationIssue]] = {}
        for issue in self.issues:
            out.setdefault(issue.code, []).append(issue)
        return out

    def short_summary(self) -> str:
        if not self.has_issues():
            return f"audit ok ({self.counts.rows_total:,} rows, no issues)"
        return (
            f"{self.counts.total()} issue(s) across "
            f"{self.counts.rows_with_issues}/"
            f"{self.counts.rows_total} rows"
        )

    def render_markdown(self) -> str:
        """Render the report as a Markdown document. Used
        by the audit CLI + the export package's audit
        summary."""
        lines: List[str] = []
        lines.append("# UNAV Pro — Dataset Audit Report")
        lines.append("")
        lines.append(f"**{self.short_summary()}**")
        lines.append("")
        if self.provenance is not None and not self.provenance.is_empty():
            lines.append("## Provenance summary")
            lines.append("")
            for line in self.provenance.render().splitlines():
                lines.append(line)
            lines.append("")
        lines.append("## Counts")
        lines.append("")
        lines.append(f"- Rows total: {self.counts.rows_total}")
        lines.append(
            f"- Rows with issues: {self.counts.rows_with_issues}",
        )
        lines.append(f"- Total issues: {self.counts.total()}")
        if self.counts.by_severity:
            lines.append("- By severity:")
            for sev in SEVERITY_ORDER:
                count = self.counts.by_severity.get(sev, 0)
                if count:
                    lines.append(f"  - {sev}: {count}")
        if self.counts.by_code:
            lines.append("- By code:")
            for code in sorted(self.counts.by_code):
                lines.append(
                    f"  - `{code}`: {self.counts.by_code[code]}",
                )
        lines.append("")
        if self.has_issues():
            lines.append("## Issues")
            lines.append("")
            grouped = self.issues_by_code()
            for code in sorted(grouped):
                bucket = grouped[code]
                lines.append(f"### `{code}` ({len(bucket)})")
                lines.append("")
                for issue in bucket[:50]:
                    uid_part = (
                        f"`{issue.uid}`" if issue.uid else "(row-agnostic)"
                    )
                    field_part = (
                        f" [field={issue.field}]" if issue.field else ""
                    )
                    lines.append(
                        f"- **{issue.severity}** {uid_part}"
                        f"{field_part} — {issue.detail}",
                    )
                if len(bucket) > 50:
                    lines.append(
                        f"- *(… {len(bucket) - 50} more not shown)*",
                    )
                lines.append("")
        if self.notes:
            lines.append("## Notes")
            lines.append("")
            for note in self.notes:
                lines.append(f"- {note}")
            lines.append("")
        return "\n".join(lines)

    def export_summary(self) -> Dict[str, Any]:
        """Compact summary suitable for embedding inside an
        export package's manifest. Counts only (no full
        issue list to keep manifests small)."""
        return {
            "rows_total": self.counts.rows_total,
            "rows_with_issues": self.counts.rows_with_issues,
            "total_issues": self.counts.total(),
            "by_code": dict(self.counts.by_code),
            "by_severity": dict(self.counts.by_severity),
            "provenance": (
                self.provenance.to_dict()
                if self.provenance is not None
                else None
            ),
        }


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------


def _is_finite_number(value: Any) -> bool:
    if value is None:
        return False
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    if f != f:  # NaN
        return False
    if f in (float("inf"), float("-inf")):
        return False
    return True


def _probe_missing_coordinates(obj: Any) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    uid = str(getattr(obj, "uid", "") or "")
    for fname in ("ra_deg", "dec_deg"):
        v = getattr(obj, fname, None)
        if not _is_finite_number(v):
            issues.append(ValidationIssue(
                code=CODE_MISSING_COORDINATES,
                severity=SEVERITY_ERROR,
                uid=uid, field=fname,
                detail=f"missing or non-finite {fname}",
            ))
    return issues


def _probe_invalid_parallax(obj: Any) -> List[ValidationIssue]:
    p = getattr(obj, "parallax_mas", None)
    if p is None:
        return []
    if not _is_finite_number(p):
        return [ValidationIssue(
            code=CODE_INVALID_PARALLAX,
            severity=SEVERITY_WARN,
            uid=str(getattr(obj, "uid", "") or ""),
            field="parallax_mas",
            detail=f"non-finite parallax_mas: {p!r}",
        )]
    pf = float(p)
    if pf <= 0.0:
        return [ValidationIssue(
            code=CODE_INVALID_PARALLAX,
            severity=SEVERITY_WARN,
            uid=str(getattr(obj, "uid", "") or ""),
            field="parallax_mas",
            detail=(
                f"parallax_mas {pf:.4f} ≤ 0; cannot be inverted "
                "to a distance"
            ),
        )]
    if pf > MAX_PARALLAX_MAS:
        return [ValidationIssue(
            code=CODE_INVALID_PARALLAX,
            severity=SEVERITY_WARN,
            uid=str(getattr(obj, "uid", "") or ""),
            field="parallax_mas",
            detail=(
                f"parallax_mas {pf:.1f} exceeds the largest "
                f"physical value (~770 mas for Proxima Centauri)"
            ),
        )]
    return []


def _probe_missing_epoch(obj: Any) -> List[ValidationIssue]:
    """Rows with proper-motion or radial-velocity values
    typically need an epoch reference for time
    propagation. UNAV stores epoch in
    ``metadata_json["epoch"]`` (the v0.4 JPL convention
    + v1.2 time navigator). When PM is set but the
    metadata doesn't carry an epoch, flag it."""
    pm_ra = getattr(obj, "proper_motion_ra", None)
    pm_dec = getattr(obj, "proper_motion_dec", None)
    if pm_ra is None and pm_dec is None:
        return []
    blob = getattr(obj, "metadata_json", None) or "{}"
    try:
        meta = json.loads(blob)
    except json.JSONDecodeError:
        # Malformed metadata is reported by its own probe;
        # don't double-count here.
        return []
    if not isinstance(meta, dict):
        return []
    if "epoch" in meta or "epoch_jd" in meta or "reference_epoch_jd" in meta:
        return []
    return [ValidationIssue(
        code=CODE_MISSING_EPOCH,
        severity=SEVERITY_WARN,
        uid=str(getattr(obj, "uid", "") or ""),
        field="metadata_json.epoch",
        detail=(
            "row carries proper-motion but no epoch; "
            "time propagation will assume J2000"
        ),
    )]


def _probe_invalid_redshift(obj: Any) -> List[ValidationIssue]:
    z = getattr(obj, "redshift", None)
    if z is None:
        return []
    if not _is_finite_number(z):
        return [ValidationIssue(
            code=CODE_INVALID_REDSHIFT,
            severity=SEVERITY_WARN,
            uid=str(getattr(obj, "uid", "") or ""),
            field="redshift",
            detail=f"non-finite redshift: {z!r}",
        )]
    zf = float(z)
    if zf < 0.0:
        return [ValidationIssue(
            code=CODE_INVALID_REDSHIFT,
            severity=SEVERITY_ERROR,
            uid=str(getattr(obj, "uid", "") or ""),
            field="redshift",
            detail=(
                f"redshift {zf:.4f} is negative; only blueshifted "
                "members of a local group should have z<0"
            ),
        )]
    if zf > MAX_REDSHIFT:
        return [ValidationIssue(
            code=CODE_INVALID_REDSHIFT,
            severity=SEVERITY_WARN,
            uid=str(getattr(obj, "uid", "") or ""),
            field="redshift",
            detail=(
                f"redshift {zf:.4f} exceeds the practical observed "
                f"range (~10); likely a placeholder"
            ),
        )]
    return []


def _probe_malformed_metadata(obj: Any) -> List[ValidationIssue]:
    blob = getattr(obj, "metadata_json", None)
    if blob is None or blob == "":
        return []
    try:
        decoded = json.loads(blob)
    except json.JSONDecodeError as exc:
        return [ValidationIssue(
            code=CODE_MALFORMED_METADATA,
            severity=SEVERITY_ERROR,
            uid=str(getattr(obj, "uid", "") or ""),
            field="metadata_json",
            detail=f"metadata_json is not valid JSON: {exc.msg}",
        )]
    if not isinstance(decoded, dict):
        return [ValidationIssue(
            code=CODE_MALFORMED_METADATA,
            severity=SEVERITY_WARN,
            uid=str(getattr(obj, "uid", "") or ""),
            field="metadata_json",
            detail=(
                f"metadata_json must decode to an object; got "
                f"{type(decoded).__name__}"
            ),
        )]
    return []


def _probe_suspicious_distance(obj: Any) -> List[ValidationIssue]:
    d = getattr(obj, "distance_parsec", None)
    if d is None:
        return []
    if not _is_finite_number(d):
        return [ValidationIssue(
            code=CODE_SUSPICIOUS_DISTANCE,
            severity=SEVERITY_WARN,
            uid=str(getattr(obj, "uid", "") or ""),
            field="distance_parsec",
            detail=f"non-finite distance_parsec: {d!r}",
        )]
    df = float(d)
    if df < 0.0:
        return [ValidationIssue(
            code=CODE_SUSPICIOUS_DISTANCE,
            severity=SEVERITY_ERROR,
            uid=str(getattr(obj, "uid", "") or ""),
            field="distance_parsec",
            detail=f"distance_parsec {df:.3f} is negative",
        )]
    if df > MAX_DISTANCE_PC:
        return [ValidationIssue(
            code=CODE_SUSPICIOUS_DISTANCE,
            severity=SEVERITY_WARN,
            uid=str(getattr(obj, "uid", "") or ""),
            field="distance_parsec",
            detail=(
                f"distance_parsec {df:.3e} exceeds the observable-"
                f"universe scale ({MAX_DISTANCE_PC:.1e} pc)"
            ),
        )]
    return []


def _probe_unsupported_units(obj: Any) -> List[ValidationIssue]:
    rec = read_provenance(obj)
    if rec is None or not rec.units:
        return []
    issues: List[ValidationIssue] = []
    uid = str(getattr(obj, "uid", "") or "")
    for category, unit in rec.units.items():
        allowed = KNOWN_UNITS.get(category)
        if allowed is None:
            continue  # unknown category; not flagged
        if unit not in allowed:
            issues.append(ValidationIssue(
                code=CODE_UNSUPPORTED_UNITS,
                severity=SEVERITY_WARN,
                uid=uid,
                field=f"provenance.units.{category}",
                detail=(
                    f"unit {unit!r} for {category!r} is not in the "
                    f"recognised set {allowed}"
                ),
            ))
    return issues


def _probe_no_provenance(obj: Any) -> List[ValidationIssue]:
    rec = read_provenance(obj)
    if rec is not None and not rec.is_empty():
        return []
    return [ValidationIssue(
        code=CODE_NO_PROVENANCE,
        severity=SEVERITY_INFO,
        uid=str(getattr(obj, "uid", "") or ""),
        detail="row has no provenance record stamped",
    )]


_ROW_PROBES = (
    _probe_missing_coordinates,
    _probe_invalid_parallax,
    _probe_missing_epoch,
    _probe_invalid_redshift,
    _probe_malformed_metadata,
    _probe_suspicious_distance,
    _probe_unsupported_units,
    _probe_no_provenance,
)


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------


def validate_objects(
    objects: Iterable[Any],
    *,
    include_provenance_summary: bool = True,
    include_no_provenance_probe: bool = True,
) -> ValidationReport:
    """Walk a sequence of ``CatalogObject`` rows and produce
    a ``ValidationReport``.

    Single pass; bounded memory (issues are appended to a
    list, but the audit CLI streams them straight to disk
    when the dataset is huge — see the CLI implementation
    for the streaming wrapper).

    ``include_provenance_summary`` aggregates provenance
    across every row. ``include_no_provenance_probe``
    emits an info-level issue for every row missing a
    record; turn it off when scanning a synthetic test
    dataset.
    """
    report = ValidationReport()
    counts = report.counts
    seen_uids: Dict[str, int] = {}
    rows_with_any_issue = 0

    # Materialise lazily — we want to walk twice (once for
    # row issues, once for the provenance summary).
    # Materialising into a list is fine; the dataset audit
    # CLI is the heavy-data path and uses the streaming
    # variant below.
    materialised = list(objects)
    counts.rows_total = len(materialised)
    counts.by_code = {code: 0 for code in ALL_CODES}
    counts.by_severity = {sev: 0 for sev in SEVERITY_ORDER}

    for obj in materialised:
        row_had_issue = False
        # Per-row probes.
        for probe in _ROW_PROBES:
            if probe is _probe_no_provenance and not include_no_provenance_probe:
                continue
            for issue in probe(obj):
                report.issues.append(issue)
                counts.by_code[issue.code] = counts.by_code.get(issue.code, 0) + 1
                counts.by_severity[issue.severity] = (
                    counts.by_severity.get(issue.severity, 0) + 1
                )
                row_had_issue = True
        # Duplicate-uid check.
        uid = str(getattr(obj, "uid", "") or "")
        if uid:
            seen = seen_uids.get(uid, 0)
            if seen >= 1:
                issue = ValidationIssue(
                    code=CODE_DUPLICATE_UID,
                    severity=SEVERITY_ERROR,
                    uid=uid,
                    detail=(
                        f"uid '{uid}' appears more than once "
                        f"(occurrence #{seen + 1})"
                    ),
                )
                report.issues.append(issue)
                counts.by_code[CODE_DUPLICATE_UID] = (
                    counts.by_code.get(CODE_DUPLICATE_UID, 0) + 1
                )
                counts.by_severity[SEVERITY_ERROR] = (
                    counts.by_severity.get(SEVERITY_ERROR, 0) + 1
                )
                row_had_issue = True
            seen_uids[uid] = seen + 1
        if row_had_issue:
            rows_with_any_issue += 1
    counts.rows_with_issues = rows_with_any_issue

    # Drop zero-count code entries so the rendered report
    # is tighter.
    counts.by_code = {c: n for c, n in counts.by_code.items() if n}
    counts.by_severity = {s: n for s, n in counts.by_severity.items() if n}

    if include_provenance_summary:
        report.provenance = summarise_provenance(materialised)
    return report
