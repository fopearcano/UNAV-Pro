"""v3.2 provenance view for the metadata inspector.

Renders the v3.2 provenance + science-correctness signals
the inspector should show alongside the v1.3 nine-section
summary:

* the row's ``ProvenanceRecord`` (catalog source, query
  parameters, units);
* coordinate-system + unit assumptions;
* approximation warnings (e.g. v0.5 redshift→distance
  proxy);
* per-row validation findings, computed by running the
  v3.2 probes against the single row.

The view is **pure data + plain text**; the C4D dialog
stitches the rendered string into the metadata panel
between sections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from data.provenance import (
    ProvenanceRecord,
    read_provenance,
)
from data.validation_report import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARN,
    ValidationIssue,
    validate_objects,
)


@dataclass
class InspectorProvenanceView:
    """Aggregate of provenance + science findings for one
    row. The inspector renders the body verbatim."""

    provenance: Optional[ProvenanceRecord] = None
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def has_provenance(self) -> bool:
        return (
            self.provenance is not None
            and not self.provenance.is_empty()
        )

    def warning_count(self) -> int:
        return sum(
            1 for i in self.issues if i.severity == SEVERITY_WARN
        )

    def error_count(self) -> int:
        return sum(
            1 for i in self.issues if i.severity == SEVERITY_ERROR
        )

    def render(self) -> str:
        """Multi-line block the metadata panel inserts. Two
        sections: provenance, then findings.

        Returns ``""`` (empty string) when the row has no
        provenance and no validation findings — the panel
        skips empty sections."""
        body: List[str] = []
        if self.has_provenance:
            body.append("Provenance")
            body.append("----------")
            for line in self.provenance.render().splitlines():  # type: ignore[union-attr]
                body.append(line)
            body.append("")
        if self.issues:
            body.append("Data integrity findings")
            body.append("-----------------------")
            for issue in self.issues:
                # Skip the row-agnostic "no provenance"
                # info when the panel already shows
                # provenance details.
                if issue.severity == SEVERITY_INFO and self.has_provenance:
                    continue
                tag = issue.severity.upper()
                fld = f" [{issue.field}]" if issue.field else ""
                body.append(f"  [{tag}]{fld} {issue.detail}")
        return "\n".join(body).rstrip()


def build_provenance_view(obj: Any) -> InspectorProvenanceView:
    """Build a single-row inspector view.

    Runs the v3.2 row probes against ``obj`` (not the
    duplicate-uid probe — that's a multi-row concern) and
    pulls the row's ``ProvenanceRecord``. Both queries
    are defensive: malformed inputs produce empty fields,
    not exceptions.
    """
    record = read_provenance(obj)
    # Run the v3.2 probes on a single-element sequence;
    # the validator returns a report whose ``issues`` list
    # is the per-row findings. Skip the no-provenance
    # info probe — the inspector already shows whether
    # provenance is present in its dedicated section.
    report = validate_objects(
        [obj],
        include_provenance_summary=False,
        include_no_provenance_probe=False,
    )
    return InspectorProvenanceView(
        provenance=record if record is not None else None,
        issues=list(report.issues),
    )
