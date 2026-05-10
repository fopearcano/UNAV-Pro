"""v3.8 exhibition export.

Three artefacts the v3.8 *Exhibition* panel
emits:

* an **exhibition package** — JSON bundle
  describing the chaptered tour + every preset
  cue + presenter notes;
* a **chapter summary** Markdown — printable
  reference for the presenter;
* a **presentation cue sheet** Markdown — table
  of cues with timestamps, narration, presenter
  notes.

Pure stdlib; no Cinema 4D imports. Atomic file
writes. Deterministic output (modulo timestamp).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .chapters import Chapter, ChapteredPresentation


EXHIBITION_PACKAGE_SCHEMA_VERSION: int = 1


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Exhibition package payload
# ---------------------------------------------------------------------------


@dataclass
class ExhibitionPackagePayload:
    """Bag of files an exhibition export produces.

    The dialog hands the dict's items into the v2.3
    export-package builder, dropped under a
    ``presentations/`` subdir."""

    files: Dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.files

    def file_count(self) -> int:
        return len(self.files)


def build_exhibition_package(
    *,
    chaptered: ChapteredPresentation,
    presentation_json: str = "",
    include_presenter_notes: bool = True,
) -> ExhibitionPackagePayload:
    """Compose the exhibition export's files.

    Always emits:

    * ``<presentation_id>.exhibition.json`` — the
      v3.8 chaptered-presentation document.
    * ``<presentation_id>.chapter_summary.md`` —
      Markdown chapter table.
    * ``<presentation_id>.cue_sheet.md`` — Markdown
      cue sheet.

    Optionally embeds the v3.3 presentation JSON
    when ``presentation_json`` is non-empty (used
    when the dialog wants a single bundle the
    audience can't lose).
    """
    payload = ExhibitionPackagePayload()
    base = chaptered.presentation_id or "exhibition"
    payload.files[f"{base}.exhibition.json"] = chaptered.to_json()
    payload.files[f"{base}.chapter_summary.md"] = render_chapter_summary(
        chaptered, include_presenter_notes=include_presenter_notes,
    )
    payload.files[f"{base}.cue_sheet.md"] = render_cue_sheet(
        chaptered, include_presenter_notes=include_presenter_notes,
    )
    if presentation_json:
        payload.files[f"{base}.presentation.json"] = presentation_json
    return payload


# ---------------------------------------------------------------------------
# Chapter summary
# ---------------------------------------------------------------------------


def render_chapter_summary(
    chaptered: ChapteredPresentation,
    *,
    include_presenter_notes: bool = True,
) -> str:
    """Render the chapter list as a clean Markdown
    document. Used as a printable cue card the
    presenter can carry into the gallery."""
    lines: List[str] = []
    lines.append(f"# {chaptered.title or 'Untitled Tour'}")
    lines.append("")
    lines.append(f"*Generated: {_utc_iso()}*")
    if chaptered.description:
        lines.append("")
        lines.append(chaptered.description.strip())
    lines.append("")
    total = chaptered.total_estimated_duration_seconds()
    if total:
        lines.append(
            f"**Estimated total runtime:** "
            f"{total:.0f} seconds (~{total / 60.0:.1f} min)"
        )
    lines.append(
        f"**Chapters:** {chaptered.chapter_count()}"
    )
    lines.append("")
    lines.append("## Chapters")
    lines.append("")
    if not chaptered.chapters:
        lines.append("(no chapters defined)")
        lines.append("")
    else:
        for i, chapter in enumerate(chaptered.chapters, start=1):
            lines.append(
                f"### Chapter {i}: {chapter.title or chapter.chapter_id}"
            )
            lines.append("")
            lines.append(
                f"- Steps: {chapter.step_count()}"
            )
            if chapter.estimated_duration_seconds:
                lines.append(
                    f"- Estimated duration: "
                    f"{chapter.estimated_duration_seconds:.0f} s"
                )
            if chapter.tags:
                lines.append("- Tags: " + ", ".join(
                    f"`{t}`" for t in chapter.tags
                ))
            on_overlays = sorted(
                k for k, v in chapter.overlay_flags.items() if v
            )
            if on_overlays:
                lines.append(
                    "- Overlays on: "
                    + ", ".join(f"`{k}`" for k in on_overlays)
                )
            on_science = sorted(
                k for k, v in chapter.science_flags.items() if v
            )
            if on_science:
                lines.append(
                    "- Science layers on: "
                    + ", ".join(f"`{k}`" for k in on_science)
                )
            if chapter.narration:
                lines.append("")
                lines.append(chapter.narration.strip())
            if include_presenter_notes and chapter.presenter_notes:
                lines.append("")
                lines.append("> **Presenter notes:**")
                for raw in chapter.presenter_notes.splitlines():
                    lines.append(f"> {raw}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Cue sheet
# ---------------------------------------------------------------------------


def render_cue_sheet(
    chaptered: ChapteredPresentation,
    *,
    include_presenter_notes: bool = True,
) -> str:
    """Render the cue sheet as a flat table the
    presenter follows live. Each chapter contributes
    one row per step (with an estimated cumulative
    timecode where durations are known)."""
    lines: List[str] = []
    lines.append(f"# Cue Sheet — {chaptered.title or 'Untitled Tour'}")
    lines.append("")
    lines.append(f"*Generated: {_utc_iso()}*")
    lines.append("")
    if not chaptered.chapters:
        lines.append("(no chapters defined)")
        return "\n".join(lines) + "\n"
    lines.append("| # | chapter | step_id | est. duration | narration / notes |")
    lines.append("| --: | --- | --- | --: | --- |")
    cumulative = 0.0
    cue_index = 0
    for chapter in chaptered.chapters:
        per_step = (
            chapter.estimated_duration_seconds / max(1, chapter.step_count())
            if chapter.step_count() > 0 else 0.0
        )
        for step_id in chapter.step_ids:
            cue_index += 1
            cumulative += per_step
            narration = (chapter.narration or "").strip()
            note_field = narration.replace("|", "\\|").replace("\n", "<br>")
            if include_presenter_notes and chapter.presenter_notes:
                note_field = (
                    note_field
                    + f" — *(notes: {chapter.presenter_notes.strip()[:60]})*"
                ).strip()
            duration_field = (
                f"{per_step:.1f} s" if per_step else ""
            )
            lines.append(
                f"| {cue_index} | "
                f"{chapter.title or chapter.chapter_id} | "
                f"`{step_id}` | "
                f"{duration_field} | "
                f"{note_field} |"
            )
    lines.append("")
    if cumulative > 0:
        lines.append(
            f"**Total estimated runtime:** {cumulative:.0f} s "
            f"(~{cumulative / 60.0:.1f} min)"
        )
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


def write_exhibition_package(
    payload: ExhibitionPackagePayload,
    output_dir: str,
) -> List[str]:
    """Write every file in ``payload`` to
    ``output_dir``. Returns the list of absolute
    paths written. Atomic writes via temp + rename;
    no leftover ``.tmp`` files."""
    if payload is None:
        raise ValueError("payload is required")
    os.makedirs(output_dir, exist_ok=True)
    written: List[str] = []
    for relname, body in payload.files.items():
        path = os.path.join(output_dir, relname)
        _safe_write(path, body)
        written.append(os.path.abspath(path))
    return written
