"""v3.3 presentation export.

Helpers for emitting:

* a presentation summary as **Markdown** (the human
  reading text);
* a presentation **package** payload that integrates
  with the v2.3 export-package builder (so the
  presentation rides into the same ``UNAV_Export/``
  tree as the mission, route, timeline);
* a **presenter notes** plain-text dump.

Pure stdlib + JSON-serialisable. No Cinema 4D imports,
no rendering.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .presentation_sequence import (
    PresentationSequence,
    PresentationStep,
    ResolvedStep,
)


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------


def render_presentation_markdown(
    presentation: PresentationSequence,
    *,
    include_presenter_notes: bool = True,
    include_resolved: bool = False,
) -> str:
    """Render the presentation as a Markdown document.

    ``include_presenter_notes`` controls whether the
    private notes column is emitted. ``include_resolved``
    appends the post-inheritance resolved view (one
    section per step) so a reader can audit what the
    runtime engine will see.
    """
    lines: List[str] = []
    lines.append(f"# {presentation.title or 'Untitled Presentation'}")
    lines.append("")
    if presentation.description:
        lines.append(presentation.description)
        lines.append("")
    lines.append(f"- Steps: {presentation.step_count()}")
    lines.append(
        f"- Estimated duration: "
        f"{presentation.total_duration_seconds():.1f} s"
    )
    if presentation.mission_ref:
        lines.append(f"- Mission: `{presentation.mission_ref}`")
    if presentation.tags:
        lines.append("- Tags: " + ", ".join(f"`{t}`" for t in presentation.tags))
    lines.append("")
    if (
        include_presenter_notes
        and presentation.presenter_notes
    ):
        lines.append("## Presenter notes (overall)")
        lines.append("")
        lines.append(presentation.presenter_notes.strip())
        lines.append("")
    lines.append("## Steps")
    lines.append("")
    for i, step in enumerate(presentation.steps):
        title = step.title or step.step_id
        lines.append(f"### Step {i + 1}: {title}")
        if step.tags:
            lines.append("*Tags: " + ", ".join(step.tags) + "*")
        if step.waypoint_ref:
            lines.append(f"- Waypoint: `{step.waypoint_ref}`")
        if step.epoch_jd is not None:
            lines.append(f"- Epoch (JD): {step.epoch_jd:.4f}")
        if step.pause_seconds:
            lines.append(f"- Pause: {step.pause_seconds:.2f} s")
        if step.overlay_flags:
            on = sorted(k for k, v in step.overlay_flags.items() if v)
            off = sorted(k for k, v in step.overlay_flags.items() if not v)
            if on:
                lines.append("- Overlays on: " + ", ".join(f"`{k}`" for k in on))
            if off:
                lines.append("- Overlays off: " + ", ".join(f"`{k}`" for k in off))
        if step.science_flags:
            on = sorted(k for k, v in step.science_flags.items() if v)
            off = sorted(k for k, v in step.science_flags.items() if not v)
            if on:
                lines.append("- Science layers on: " + ", ".join(f"`{k}`" for k in on))
            if off:
                lines.append("- Science layers off: " + ", ".join(f"`{k}`" for k in off))
        if step.visible_annotation_indices:
            lines.append(
                "- Visible annotations: "
                + ", ".join(str(i) for i in step.visible_annotation_indices),
            )
        if step.highlighted_annotation_indices:
            lines.append(
                "- Highlighted annotations: "
                + ", ".join(str(i) for i in step.highlighted_annotation_indices),
            )
        if step.narration:
            lines.append("")
            lines.append(step.narration.strip())
        if include_presenter_notes and step.presenter_notes:
            lines.append("")
            lines.append("> Presenter notes:")
            for note_line in step.presenter_notes.splitlines():
                lines.append(f"> {note_line}")
        lines.append("")
    if include_resolved:
        lines.append("## Resolved steps (post-inheritance)")
        lines.append("")
        for resolved in presentation.resolved_steps():
            lines.append(
                f"- Step {resolved.index + 1} `{resolved.step_id}` "
                f"camera={_fmt_vec(resolved.camera_position)} "
                f"target={_fmt_vec(resolved.camera_target)} "
                f"epoch={resolved.epoch_jd}",
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _fmt_vec(v):
    if v is None:
        return "(inherited)"
    return f"({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f})"


# ---------------------------------------------------------------------------
# Presenter notes export
# ---------------------------------------------------------------------------


def render_presenter_notes(presentation: PresentationSequence) -> str:
    """Plain-text dump of every step's presenter notes,
    plus the overall presenter notes if any. Suitable
    for printing or piping into a teleprompter."""
    out: List[str] = []
    out.append(f"Presenter notes — {presentation.title or 'Untitled'}")
    out.append("=" * 60)
    if presentation.presenter_notes:
        out.append(presentation.presenter_notes.strip())
        out.append("")
    for i, step in enumerate(presentation.steps):
        out.append(f"[Step {i + 1}] {step.title or step.step_id}")
        if step.narration:
            out.append("  Narration:")
            for line in step.narration.splitlines():
                out.append(f"    {line}")
        if step.presenter_notes:
            out.append("  Presenter notes:")
            for line in step.presenter_notes.splitlines():
                out.append(f"    {line}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Package integration
# ---------------------------------------------------------------------------


@dataclass
class PresentationPackagePayload:
    """Bag of presentation files for the v2.3 export
    builder. The dialog hands the items in this dict
    straight into ``PackagePayload.docs`` (or a new
    ``presentations`` subdir if the export builder
    grows one)."""

    presentations: Dict[str, str] = field(default_factory=dict)
    summaries: Dict[str, str] = field(default_factory=dict)
    presenter_notes: Dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (
            self.presentations or self.summaries
            or self.presenter_notes
        )

    def file_count(self) -> int:
        return (
            len(self.presentations)
            + len(self.summaries)
            + len(self.presenter_notes)
        )

    def merged(self) -> Dict[str, str]:
        """Flatten every payload into a single dict keyed
        by relative path; the v2.3 export builder picks
        these up via ``PackagePayload.docs``."""
        out: Dict[str, str] = {}
        for name, body in self.presentations.items():
            out[f"presentations/{name}"] = body
        for name, body in self.summaries.items():
            out[f"presentations/{name}"] = body
        for name, body in self.presenter_notes.items():
            out[f"presentations/{name}"] = body
        return out


def build_presentation_payload(
    presentation: PresentationSequence,
    *,
    include_presenter_notes: bool = True,
    include_resolved: bool = False,
) -> PresentationPackagePayload:
    """Assemble the standard set of presentation files for
    one presentation.

    Files emitted (relative names inside ``presentations/``):

    * ``<presentation_id>.json`` — the full presentation
      JSON.
    * ``<presentation_id>.md`` — the Markdown summary.
    * ``<presentation_id>.notes.txt`` — presenter notes.
    """
    payload = PresentationPackagePayload()
    base = (
        presentation.presentation_id
        or "untitled-presentation"
    )
    payload.presentations[f"{base}.json"] = presentation.to_json()
    payload.summaries[f"{base}.md"] = render_presentation_markdown(
        presentation,
        include_presenter_notes=include_presenter_notes,
        include_resolved=include_resolved,
    )
    if include_presenter_notes:
        payload.presenter_notes[f"{base}.notes.txt"] = (
            render_presenter_notes(presentation)
        )
    return payload


def write_presentation_files(
    presentation: PresentationSequence,
    output_dir: str,
    *,
    include_presenter_notes: bool = True,
    include_resolved: bool = False,
) -> List[str]:
    """Write the presentation payload to ``output_dir``.

    Returns the list of absolute paths written. Atomic
    writes via temp + rename. Used by the dialog's
    *Project → Export Presentation* button when the
    artist wants a presentation directory outside the
    full export package.
    """
    os.makedirs(output_dir, exist_ok=True)
    payload = build_presentation_payload(
        presentation,
        include_presenter_notes=include_presenter_notes,
        include_resolved=include_resolved,
    )
    written: List[str] = []
    for relname, body in payload.merged().items():
        # Strip the "presentations/" prefix when writing
        # to a flat directory so the artist gets clean
        # filenames in the destination.
        leaf = relname.split("/", 1)[-1]
        path = os.path.join(output_dir, leaf)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
            if not body.endswith("\n"):
                fh.write("\n")
        os.replace(tmp, path)
        written.append(path)
    return written
