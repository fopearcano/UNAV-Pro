"""v3.7 query-result exporters.

Three output formats:

* **JSON** — full result list + per-result fields +
  the query that produced them.
* **CSV** — flat per-result rows for spreadsheets.
* **Markdown** — a one-page summary the artist can
  paste into notes.

Pure stdlib + ``json`` + ``csv``. No Cinema 4D, no
network. Atomic file writes via temp + rename.
"""

from __future__ import annotations

import csv
import io
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .advanced_query import (
    AdvancedQuery, QueryReport, QueryResult,
)


# ---------------------------------------------------------------------------
# CSV columns
# ---------------------------------------------------------------------------


CSV_FIELDS = (
    "uid", "catalog_source", "object_type", "common_name",
    "score", "distance_pc", "apparent_magnitude", "redshift",
)


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _result_to_dict(r: QueryResult) -> Dict[str, Any]:
    return {
        "uid": r.uid,
        "catalog_source": r.catalog_source,
        "object_type": r.object_type,
        "common_name": r.common_name,
        "score": float(r.score),
        "distance_pc": r.distance_pc,
        "apparent_magnitude": r.apparent_magnitude,
        "redshift": r.redshift,
    }


def _query_to_dict(q: AdvancedQuery) -> Dict[str, Any]:
    return {
        "kind": q.kind.value,
        "max_results": int(q.max_results),
        "distance_min_pc": q.distance_min_pc,
        "distance_max_pc": q.distance_max_pc,
        "magnitude_min": q.magnitude_min,
        "magnitude_max": q.magnitude_max,
        "redshift_min": q.redshift_min,
        "redshift_max": q.redshift_max,
        "sources": list(q.sources),
        "object_types": list(q.object_types),
        "visible_sector_uids": list(q.visible_sector_uids),
        "reference_point_pc": (
            list(q.reference_point_pc)
            if q.reference_point_pc is not None else None
        ),
        "selected_uid": q.selected_uid,
        "sort_order": q.sort_order.value,
        "epoch_jd": q.epoch_jd,
        "interpolate_ephemeris": q.interpolate_ephemeris,
    }


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def render_json(report: QueryReport, *, indent: int = 2) -> str:
    """Render the report as JSON."""
    payload = {
        "schema_version": 1,
        "generated_at_iso": _utc_iso(),
        "query": _query_to_dict(report.query),
        "candidates_scanned": int(report.candidates_scanned),
        "matched_before_cap": int(report.matched_before_cap),
        "returned": int(report.returned),
        "warnings": list(report.warnings),
        "notes": list(report.notes),
        "results": [_result_to_dict(r) for r in report.results],
    }
    return json.dumps(
        payload, indent=indent, ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def render_csv(report: QueryReport) -> str:
    """Render the report's results as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_FIELDS)
    for r in report.results:
        d = _result_to_dict(r)
        writer.writerow([
            "" if d.get(c) is None else d[c] for c in CSV_FIELDS
        ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def render_markdown(report: QueryReport) -> str:
    """Render the report as a single Markdown page.

    Layout:
    1. heading + summary line;
    2. query parameters block;
    3. counts block;
    4. results table (uid / source / type / name /
       distance / magnitude / redshift);
    5. warnings + notes.
    """
    lines: List[str] = []
    lines.append("# UNAV Pro — Advanced Query Results")
    lines.append("")
    lines.append(f"*Generated: {_utc_iso()}*")
    lines.append("")
    lines.append(f"**{report.short_summary()}**")
    lines.append("")
    lines.append("## Query")
    lines.append("")
    lines.append(f"- Kind: `{report.query.kind.value}`")
    lines.append(f"- Sort order: `{report.query.effective_sort_order().value}`")
    lines.append(f"- Max results: {report.query.max_results}")
    if report.query.sources:
        lines.append("- Sources: " + ", ".join(
            f"`{s}`" for s in report.query.sources
        ))
    if report.query.object_types:
        lines.append("- Object types: " + ", ".join(
            f"`{t}`" for t in report.query.object_types
        ))
    if (
        report.query.distance_min_pc is not None
        or report.query.distance_max_pc is not None
    ):
        lo = (
            "" if report.query.distance_min_pc is None
            else f"{report.query.distance_min_pc:g}"
        )
        hi = (
            "" if report.query.distance_max_pc is None
            else f"{report.query.distance_max_pc:g}"
        )
        lines.append(f"- Distance (pc): `[{lo}, {hi}]`")
    if (
        report.query.magnitude_min is not None
        or report.query.magnitude_max is not None
    ):
        lo = (
            "" if report.query.magnitude_min is None
            else f"{report.query.magnitude_min:g}"
        )
        hi = (
            "" if report.query.magnitude_max is None
            else f"{report.query.magnitude_max:g}"
        )
        lines.append(f"- Magnitude: `[{lo}, {hi}]`")
    if (
        report.query.redshift_min is not None
        or report.query.redshift_max is not None
    ):
        lo = (
            "" if report.query.redshift_min is None
            else f"{report.query.redshift_min:g}"
        )
        hi = (
            "" if report.query.redshift_max is None
            else f"{report.query.redshift_max:g}"
        )
        lines.append(f"- Redshift: `[{lo}, {hi}]`")
    if report.query.reference_point_pc is not None:
        x, y, z = report.query.reference_point_pc
        lines.append(f"- Reference point (pc): `({x:.3f}, {y:.3f}, {z:.3f})`")
    if report.query.epoch_jd is not None:
        lines.append(f"- Epoch (JD): {report.query.epoch_jd:.4f}")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- Candidates scanned: {report.candidates_scanned}")
    lines.append(f"- Matched before cap: {report.matched_before_cap}")
    lines.append(f"- Returned (after cap): {report.returned}")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    if not report.results:
        lines.append("(no results)")
        lines.append("")
    else:
        lines.append(
            "| # | uid | source | type | name | dist (pc) | mag | z |"
        )
        lines.append(
            "| --: | --- | --- | --- | --- | --: | --: | --: |"
        )
        for i, r in enumerate(report.results, start=1):
            lines.append(
                f"| {i} | `{r.uid}` | {r.catalog_source} | "
                f"{r.object_type} | {r.common_name} | "
                f"{'' if r.distance_pc is None else f'{r.distance_pc:.3f}'} | "
                f"{'' if r.apparent_magnitude is None else f'{r.apparent_magnitude:.2f}'} | "
                f"{'' if r.redshift is None else f'{r.redshift:.4f}'} |"
            )
        lines.append("")
    if report.warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in report.warnings:
            lines.append(f"- {w}")
        lines.append("")
    if report.notes:
        lines.append("## Notes")
        lines.append("")
        for n in report.notes:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------


def _safe_write(path: str, body: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
        if not body.endswith("\n"):
            fh.write("\n")
    os.replace(tmp, path)


def write_json_report(report: QueryReport, path: str) -> str:
    _safe_write(path, render_json(report))
    return os.path.abspath(path)


def write_csv_report(report: QueryReport, path: str) -> str:
    _safe_write(path, render_csv(report))
    return os.path.abspath(path)


def write_markdown_report(report: QueryReport, path: str) -> str:
    _safe_write(path, render_markdown(report))
    return os.path.abspath(path)
