"""v1.9 voyage annotations.

Three layers of annotation that piggy-back on the existing
mission shape:

* **Waypoint annotations** — text attached to a specific
  ``MissionWaypoint``. Already supported in v1.4 via the
  ``notes`` field; this module adds a richer multi-line +
  metadata-derived helper layer on top.
* **Scene annotations** — free 3D points + label that the
  artist wants to remember at a coordinate (without making
  it a navigable waypoint). Stored in the mission's
  ``scene_annotations`` list (a v1.9 field on ``Mission``).
* **Mission annotations** — free text at the mission level.
  Already supported via ``Mission.description``.

This module's value is the **structured access layer**: it
consolidates the three sources into one ``MissionAnnotations``
report the dialog renders verbatim, plus a helper that
synthesises *metadata-derived* notes from a waypoint
(catalog source, distance method, redshift caveat).

Stdlib-only. Tested without Cinema 4D.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .mission import Mission, MissionWaypoint


# ---------------------------------------------------------------------------
# Scene annotation
# ---------------------------------------------------------------------------


@dataclass
class SceneAnnotation:
    """A free-floating 3D label the artist wants to remember
    at a specific scene coordinate.

    Distinct from a ``MissionWaypoint`` — scene annotations
    don't participate in the camera path, can't be focused,
    and have no duration. They only exist as documentation
    the dialog renders alongside the mission.
    """

    label: str
    x_c4d: float = 0.0
    y_c4d: float = 0.0
    z_c4d: float = 0.0
    notes: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("scene annotation requires a label")
        if self.tags:
            self.tags = [
                str(t).strip().lower() for t in self.tags
                if str(t).strip()
            ]

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "label": self.label,
            "x_c4d": float(self.x_c4d),
            "y_c4d": float(self.y_c4d),
            "z_c4d": float(self.z_c4d),
        }
        if self.notes:
            out["notes"] = self.notes
        if self.tags:
            out["tags"] = list(self.tags)
        return out

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SceneAnnotation":
        return cls(
            label=str(d.get("label") or ""),
            x_c4d=float(d.get("x_c4d") or 0.0),
            y_c4d=float(d.get("y_c4d") or 0.0),
            z_c4d=float(d.get("z_c4d") or 0.0),
            notes=str(d.get("notes") or ""),
            tags=[str(t) for t in (d.get("tags") or [])],
        )


# ---------------------------------------------------------------------------
# Mission-level annotations report
# ---------------------------------------------------------------------------


@dataclass
class WaypointAnnotation:
    """One waypoint's resolved annotation: explicit ``notes``
    plus any metadata-derived sentences."""

    index: int
    label: str
    kind: str
    notes: str = ""
    derived: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def render_text(self) -> str:
        parts: List[str] = [f"[{self.index}] {self.label} ({self.kind})"]
        if self.tags:
            parts.append("  tags: " + ", ".join(self.tags))
        if self.notes:
            parts.append("  note: " + self.notes)
        for d in self.derived:
            parts.append("  • " + d)
        return "\n".join(parts)


@dataclass
class MissionAnnotations:
    """Aggregate annotations for one mission."""

    title: str = ""
    description: str = ""
    waypoint_annotations: List[WaypointAnnotation] = field(default_factory=list)
    scene_annotations: List[SceneAnnotation] = field(default_factory=list)
    mission_tags: List[str] = field(default_factory=list)

    def render_text(self) -> str:
        lines: List[str] = []
        lines.append(f"=== Annotations: {self.title} ===")
        if self.description:
            lines.append(self.description)
        if self.mission_tags:
            lines.append("tags: " + ", ".join(self.mission_tags))
        if self.waypoint_annotations:
            lines.append("")
            lines.append("--- Waypoints ---")
            for wa in self.waypoint_annotations:
                lines.append(wa.render_text())
        if self.scene_annotations:
            lines.append("")
            lines.append("--- Scene Annotations ---")
            for sa in self.scene_annotations:
                lines.append(
                    f"  • {sa.label}  "
                    f"({sa.x_c4d:.3g}, {sa.y_c4d:.3g}, {sa.z_c4d:.3g})"
                )
                if sa.notes:
                    lines.append("    " + sa.notes)
        if not (
            self.description
            or self.waypoint_annotations
            or self.scene_annotations
        ):
            lines.append("(no annotations)")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Metadata-derived notes
# ---------------------------------------------------------------------------


def derive_notes(wp: MissionWaypoint) -> List[str]:
    """Synthesise plain-text notes from a waypoint's metadata.

    Examples:
        * ``catalog_source = "Gaia DR3"`` → "from Gaia DR3"
        * ``object_type = "quasar"`` → "object type: quasar"
        * ``epoch_jd = 2451545.0`` → "epoch: JD 2451545.000"
        * ``search_query = "Sirius"`` → "found via search: Sirius"

    Useful for the annotations panel and for the v1.9
    Markdown / CSV exporters."""
    out: List[str] = []
    if wp.catalog_source:
        out.append(f"from {wp.catalog_source}")
    if wp.object_type:
        out.append(f"object type: {wp.object_type}")
    if wp.uid and wp.kind in ("object", "search_result", "orbital"):
        out.append(f"uid: {wp.uid}")
    if wp.bookmark_id:
        out.append(f"bookmark: {wp.bookmark_id}")
    if wp.search_query:
        out.append(f"found via search: {wp.search_query}")
    if wp.epoch_jd is not None:
        out.append(f"epoch: JD {float(wp.epoch_jd):.3f}")
    if wp.has_pc_position():
        out.append(
            f"position (pc): "
            f"({float(wp.x_pc):.3g}, {float(wp.y_pc):.3g}, "
            f"{float(wp.z_pc):.3g})"
        )
    if wp.pause_seconds:
        out.append(f"dwell: {float(wp.pause_seconds):.2f} s")
    if wp.camera_offset is not None:
        ox, oy, oz = wp.camera_offset
        out.append(
            f"camera offset: ({ox:.3g}, {oy:.3g}, {oz:.3g})"
        )
    return out


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_mission_annotations(
    mission: Mission,
    *,
    scene_annotations: Optional[Iterable[SceneAnnotation]] = None,
    include_derived: bool = True,
) -> MissionAnnotations:
    """Build a ``MissionAnnotations`` report from ``mission``.

    Per-waypoint ``notes`` always appear; metadata-derived
    sentences are added when ``include_derived=True``
    (default). ``scene_annotations`` is the iterable of
    free 3D labels the artist has attached to coordinates;
    typically read from the v1.9 `scene_annotations` field on
    ``Mission`` (added below)."""
    rpt = MissionAnnotations(
        title=mission.title,
        description=mission.description,
        mission_tags=list(mission.tags),
        scene_annotations=list(scene_annotations or []),
    )
    for i, wp in enumerate(mission.waypoints):
        wa = WaypointAnnotation(
            index=i,
            label=wp.display_label(),
            kind=wp.kind,
            notes=wp.notes,
            tags=list(wp.tags),
            derived=derive_notes(wp) if include_derived else [],
        )
        rpt.waypoint_annotations.append(wa)
    return rpt


# ---------------------------------------------------------------------------
# Mission scene-annotation accessors (the field lives on
# ``Mission`` itself; the helpers here let the dialog stay
# import-clean).
# ---------------------------------------------------------------------------


def get_scene_annotations(mission: Mission) -> List[SceneAnnotation]:
    raw = getattr(mission, "scene_annotations", None) or []
    out: List[SceneAnnotation] = []
    for entry in raw:
        if isinstance(entry, SceneAnnotation):
            out.append(entry)
        elif isinstance(entry, dict):
            try:
                out.append(SceneAnnotation.from_dict(entry))
            except (TypeError, ValueError):
                continue
    return out


def add_scene_annotation(
    mission: Mission, annotation: SceneAnnotation,
) -> SceneAnnotation:
    if not hasattr(mission, "scene_annotations") or mission.scene_annotations is None:
        mission.scene_annotations = []  # type: ignore[attr-defined]
    mission.scene_annotations.append(annotation)
    mission._touch()  # noqa: SLF001 — manager owns the mtime stamp
    return annotation


def remove_scene_annotation_at(mission: Mission, index: int) -> bool:
    annotations = getattr(mission, "scene_annotations", None) or []
    if not (0 <= index < len(annotations)):
        return False
    annotations.pop(index)
    mission._touch()  # noqa: SLF001
    return True
