"""v1.9 mission exporters — Markdown + CSV.

Three exporters live here:

* ``mission_to_markdown`` — a human-readable route summary
  with waypoints, distances, tags, and metadata-derived
  notes.
* ``mission_to_csv`` — a flat CSV row per waypoint, suitable
  for hand-editing in a spreadsheet and re-importing later.
* ``mission_to_json_file`` — thin wrapper around the
  existing ``Mission.to_json`` for symmetry; uses the v1.7
  ``safe_write_json`` helper so the write is atomic.

All three are pure stdlib. Tests drive them directly without
Cinema 4D.
"""

from __future__ import annotations

import csv
import io
import json
import os
from typing import List, Optional, Sequence

from .annotations import build_mission_annotations, derive_notes
from .mission import Mission, MissionWaypoint
from .route_analytics import analyse_route


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def mission_to_markdown(
    mission: Mission,
    *,
    include_route_analytics: bool = True,
    include_annotations: bool = True,
) -> str:
    """Render a Markdown summary of ``mission``. The dialog's
    "Export Markdown" button writes this verbatim to disk."""
    lines: List[str] = []
    lines.append(f"# {mission.title}")
    lines.append("")
    if mission.description:
        lines.append(mission.description)
        lines.append("")
    if mission.tags:
        lines.append("**Tags:** " + ", ".join(mission.tags))
        lines.append("")
    lines.append(
        f"**Waypoints:** {len(mission.waypoints)} · "
        f"**Total runtime:** {mission.total_duration_seconds():.1f} s · "
        f"**Mission ID:** `{mission.mission_id}`"
    )
    lines.append("")
    lines.append(f"_Created {mission.created_iso}; "
                 f"modified {mission.modified_iso}._")
    lines.append("")

    # --- Waypoints table ---
    if mission.waypoints:
        lines.append("## Waypoints")
        lines.append("")
        lines.append(
            "| # | Kind | Label | Travel (s) | Pause (s) | Epoch (JD) | Tags |"
        )
        lines.append(
            "|---|------|-------|-----------:|----------:|------------|------|"
        )
        for i, w in enumerate(mission.waypoints):
            epoch = (
                f"{float(w.epoch_jd):.3f}"
                if w.epoch_jd is not None else "—"
            )
            tag_field = ", ".join(w.tags) if w.tags else "—"
            lines.append(
                f"| {i} | `{w.kind}` | {_md_escape(w.display_label())} "
                f"| {w.duration_seconds:.2f} | {w.pause_seconds:.2f} "
                f"| {epoch} | {_md_escape(tag_field)} |"
            )
        lines.append("")

        # --- Per-waypoint annotations ---
        if include_annotations:
            for i, w in enumerate(mission.waypoints):
                derived = derive_notes(w)
                if not (w.notes or derived):
                    continue
                lines.append(f"### Waypoint {i}: {_md_escape(w.display_label())}")
                if w.notes:
                    lines.append("")
                    lines.append(w.notes)
                if derived:
                    lines.append("")
                    for d in derived:
                        lines.append(f"- {d}")
                lines.append("")

    # --- Route analytics ---
    if include_route_analytics and len(mission.waypoints) >= 2:
        rpt = analyse_route(mission)
        lines.append("## Route Analytics")
        lines.append("")
        lines.append(f"- **Segments:** {len(rpt.segments)}")
        lines.append(
            f"- **Total (C4D):** {rpt.total_distance_c4d:.4g} units"
        )
        if rpt.total_distance_pc is not None:
            lines.append(
                f"- **Total (parsec):** {rpt.total_distance_pc:.4g} pc"
            )
        else:
            lines.append("- **Total (parsec):** _unknown — see warnings_")
        if rpt.estimated_travel_seconds is not None:
            lines.append(
                f"- **Estimated travel:** "
                f"{rpt.estimated_travel_seconds:.3g} s"
            )
        if rpt.epoch_min_jd is not None:
            lines.append(
                f"- **Epoch range:** JD {rpt.epoch_min_jd:.3f} → "
                f"{rpt.epoch_max_jd:.3f} "
                f"(spread {rpt.epoch_spread_days:.1f} days)"
            )
        if rpt.has_unknown_distances() or rpt.has_epoch_warning():
            lines.append("")
            lines.append("**Warnings**")
            if rpt.has_unknown_distances():
                lines.append(
                    f"- {len(rpt.waypoints_with_unknown_distance)} "
                    "waypoint(s) have no parsec position; total "
                    "parsec distance is incomplete."
                )
            if rpt.has_epoch_warning():
                lines.append(f"- {rpt.epoch_spread_warning}")
        lines.append("")

    # --- Scene annotations ---
    if include_annotations and getattr(mission, "scene_annotations", None):
        lines.append("## Scene Annotations")
        lines.append("")
        annotations = build_mission_annotations(
            mission, scene_annotations=mission.scene_annotations,
        ).scene_annotations
        for a in annotations:
            lines.append(
                f"- **{_md_escape(a.label)}** — "
                f"({a.x_c4d:.3g}, {a.y_c4d:.3g}, {a.z_c4d:.3g})"
            )
            if a.notes:
                lines.append(f"  - {a.notes}")
        lines.append("")

    return "\n".join(lines)


def _md_escape(s: str) -> str:
    """Escape Markdown table separators so labels with pipes
    don't break the layout."""
    return (s or "").replace("|", "\\|")


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


CSV_FIELDS: Sequence[str] = (
    "index", "kind", "label",
    "uid", "catalog_source", "object_type",
    "bookmark_id", "search_query",
    "x_c4d", "y_c4d", "z_c4d",
    "x_pc", "y_pc", "z_pc",
    "epoch_jd",
    "duration_seconds", "pause_seconds", "roll_deg",
    "tags", "notes",
)


def mission_to_csv(mission: Mission) -> str:
    """Return ``mission`` as a CSV string with one row per
    waypoint. The header line is the v1.9 ``CSV_FIELDS``
    constant.

    All values are emitted as strings; missing values become
    empty cells. Tags are joined with semicolons (since CSV
    is comma-delimited)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_FIELDS)
    for i, w in enumerate(mission.waypoints):
        writer.writerow([
            i,
            w.kind,
            w.display_label(),
            w.uid or "",
            w.catalog_source or "",
            w.object_type or "",
            w.bookmark_id or "",
            w.search_query or "",
            "" if w.x_c4d is None else f"{w.x_c4d}",
            "" if w.y_c4d is None else f"{w.y_c4d}",
            "" if w.z_c4d is None else f"{w.z_c4d}",
            "" if w.x_pc is None else f"{w.x_pc}",
            "" if w.y_pc is None else f"{w.y_pc}",
            "" if w.z_pc is None else f"{w.z_pc}",
            "" if w.epoch_jd is None else f"{w.epoch_jd}",
            f"{w.duration_seconds}",
            f"{w.pause_seconds}",
            f"{w.roll_deg}",
            "; ".join(w.tags) if w.tags else "",
            (w.notes or "").replace("\n", " "),
        ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# JSON file (atomic)
# ---------------------------------------------------------------------------


def mission_to_json_file(mission: Mission, path: str) -> Optional[str]:
    """Atomic JSON write of ``mission``. Returns ``path`` on
    success or ``None`` on failure. Wraps the v1.7
    ``safe_write_json`` helper so a crash mid-write cannot
    truncate the destination."""
    from core.config import safe_write_json
    return safe_write_json(path, mission.to_json())


# ---------------------------------------------------------------------------
# File-writing convenience
# ---------------------------------------------------------------------------


def write_markdown(
    mission: Mission, path: str, *, include_route_analytics: bool = True,
) -> Optional[str]:
    """Write ``mission_to_markdown`` to ``path`` atomically."""
    from core.config import safe_write_json
    return safe_write_json(
        path,
        mission_to_markdown(
            mission, include_route_analytics=include_route_analytics,
        ),
    )


def write_csv(mission: Mission, path: str) -> Optional[str]:
    """Write ``mission_to_csv`` to ``path`` atomically."""
    from core.config import safe_write_json
    return safe_write_json(path, mission_to_csv(mission))
