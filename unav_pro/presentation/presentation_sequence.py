"""v3.3 presentation sequences.

A *presentation* is an **ordered list of steps** the
artist guides an audience through. Each step owns the
camera pose, the active waypoint reference, the visible
overlay / science-layer set, the active epoch, and the
narration text the presenter reads aloud.

This module defines the **declarative shape** of a
presentation:

* ``PresentationStep`` — one step, fully self-describing.
* ``PresentationSequence`` — title + ordered list of
  steps + presenter notes.

Pure stdlib + JSON-serialisable. No Cinema 4D imports.
The runtime state (current step index, paused flag) is
tracked separately by ``presentation_state.py``.

Schema policy
-------------

* ``schema_version`` bumps when the on-disk shape
  changes incompatibly. v3.3 ships ``v=1``.
* Loaders accept missing fields (defaulted) but reject
  unknown ``schema_version`` values fail-closed.
* Steps are addressed by zero-based index. Every step
  carries an immutable ``step_id`` so external state
  (presenter notes, marker bindings) can survive
  reorder.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


PRESENTATION_SCHEMA_VERSION: int = 1

#: Hard cap on steps per presentation. Aligned with the
#: v1.4 ``MAX_WAYPOINTS_PER_MISSION`` so mission-driven
#: presentations don't blow past the existing safety
#: budget.
MAX_STEPS_PER_PRESENTATION: int = 200

DEFAULT_STEP_PAUSE_SECONDS: float = 4.0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PresentationError(ValueError):
    """Raised on presentation schema / I/O failures."""


# ---------------------------------------------------------------------------
# PresentationStep
# ---------------------------------------------------------------------------


def _new_step_id() -> str:
    return f"step-{uuid.uuid4().hex[:12]}"


@dataclass
class PresentationStep:
    """One step in a presentation.

    Optional fields are ``None`` when the step doesn't
    care about that surface. The runtime resolver
    inherits "previous step's value" for any field that
    is ``None``, so a step that only changes the active
    annotation doesn't need to re-spell the camera pose.
    """

    step_id: str = field(default_factory=_new_step_id)
    title: str = ""
    narration: str = ""
    presenter_notes: str = ""
    pause_seconds: float = DEFAULT_STEP_PAUSE_SECONDS

    # Reference to a v1.4 mission waypoint by id (the
    # mission's ``waypoint_id`` if one exists, else its
    # ``label``). The runtime resolver looks this up
    # against the active mission.
    waypoint_ref: Optional[str] = None

    # Camera pose snapshot. ``None`` ⇒ inherit from the
    # mission's resolved camera path at this step's
    # waypoint.
    camera_position: Optional[Tuple[float, float, float]] = None
    camera_target: Optional[Tuple[float, float, float]] = None
    camera_fov_deg: Optional[float] = None

    # Active epoch (Julian date). ``None`` ⇒ inherit
    # from the previous step.
    epoch_jd: Optional[float] = None

    # Per-step overlay / science-layer flags. Each is a
    # dict mapping ``show_*`` field name → bool. Empty
    # ⇒ inherit from the previous step.
    overlay_flags: Dict[str, bool] = field(default_factory=dict)
    science_flags: Dict[str, bool] = field(default_factory=dict)

    # Annotation visibility + highlight. Two parallel
    # lists keyed by annotation index in the active
    # mission's ``scene_annotations``. Empty ⇒ inherit.
    visible_annotation_indices: List[int] = field(default_factory=list)
    highlighted_annotation_indices: List[int] = field(default_factory=list)

    # Free-form tags (e.g. ``["intro", "act-2"]``) the
    # dialog can use to filter step views.
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.pause_seconds < 0:
            raise PresentationError(
                f"pause_seconds must be >= 0, got {self.pause_seconds}"
            )
        if self.camera_fov_deg is not None and self.camera_fov_deg <= 0:
            raise PresentationError(
                f"camera_fov_deg must be > 0, got {self.camera_fov_deg}"
            )
        if self.tags:
            self.tags = [
                str(t).strip().lower() for t in self.tags
                if str(t).strip()
            ]

    # ---------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "step_id": self.step_id,
            "title": self.title,
            "narration": self.narration,
            "presenter_notes": self.presenter_notes,
            "pause_seconds": float(self.pause_seconds),
            "waypoint_ref": self.waypoint_ref,
            "camera_position": (
                list(self.camera_position)
                if self.camera_position is not None else None
            ),
            "camera_target": (
                list(self.camera_target)
                if self.camera_target is not None else None
            ),
            "camera_fov_deg": self.camera_fov_deg,
            "epoch_jd": self.epoch_jd,
            "overlay_flags": dict(self.overlay_flags),
            "science_flags": dict(self.science_flags),
            "visible_annotation_indices": list(self.visible_annotation_indices),
            "highlighted_annotation_indices": list(self.highlighted_annotation_indices),
            "tags": list(self.tags),
        }
        return out

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "PresentationStep":
        if not isinstance(d, dict):
            raise PresentationError("step payload is not an object")
        cam_pos = d.get("camera_position")
        cam_tgt = d.get("camera_target")
        return cls(
            step_id=str(d.get("step_id") or _new_step_id()),
            title=str(d.get("title") or ""),
            narration=str(d.get("narration") or ""),
            presenter_notes=str(d.get("presenter_notes") or ""),
            pause_seconds=float(
                d.get("pause_seconds", DEFAULT_STEP_PAUSE_SECONDS)
                or DEFAULT_STEP_PAUSE_SECONDS,
            ),
            waypoint_ref=(
                str(d["waypoint_ref"])
                if d.get("waypoint_ref") not in (None, "")
                else None
            ),
            camera_position=(
                tuple(float(x) for x in cam_pos)  # type: ignore[arg-type]
                if isinstance(cam_pos, (list, tuple)) and len(cam_pos) == 3
                else None
            ),
            camera_target=(
                tuple(float(x) for x in cam_tgt)  # type: ignore[arg-type]
                if isinstance(cam_tgt, (list, tuple)) and len(cam_tgt) == 3
                else None
            ),
            camera_fov_deg=(
                float(d["camera_fov_deg"])
                if d.get("camera_fov_deg") is not None else None
            ),
            epoch_jd=(
                float(d["epoch_jd"])
                if d.get("epoch_jd") is not None else None
            ),
            overlay_flags={
                str(k): bool(v)
                for k, v in (d.get("overlay_flags") or {}).items()
            },
            science_flags={
                str(k): bool(v)
                for k, v in (d.get("science_flags") or {}).items()
            },
            visible_annotation_indices=[
                int(i) for i in (d.get("visible_annotation_indices") or [])
            ],
            highlighted_annotation_indices=[
                int(i) for i in (d.get("highlighted_annotation_indices") or [])
            ],
            tags=[str(t) for t in (d.get("tags") or [])],
        )

    def short_summary(self) -> str:
        bits: List[str] = []
        if self.title:
            bits.append(self.title)
        if self.waypoint_ref:
            bits.append(f"@{self.waypoint_ref}")
        if self.epoch_jd is not None:
            bits.append(f"epoch={self.epoch_jd:.1f}")
        if self.pause_seconds:
            bits.append(f"{self.pause_seconds:.1f}s")
        return " · ".join(bits) or self.step_id


# ---------------------------------------------------------------------------
# Resolved step (post-inheritance)
# ---------------------------------------------------------------------------


@dataclass
class ResolvedStep:
    """A step with every inheritance chain folded in. The
    runtime resolver produces these in order; the C4D
    builder reads them to drive the scene without having
    to walk back to the previous step."""

    step_id: str
    index: int
    title: str
    narration: str
    presenter_notes: str
    pause_seconds: float
    waypoint_ref: Optional[str]
    camera_position: Optional[Tuple[float, float, float]]
    camera_target: Optional[Tuple[float, float, float]]
    camera_fov_deg: Optional[float]
    epoch_jd: Optional[float]
    overlay_flags: Dict[str, bool]
    science_flags: Dict[str, bool]
    visible_annotation_indices: List[int]
    highlighted_annotation_indices: List[int]
    tags: List[str]


# ---------------------------------------------------------------------------
# PresentationSequence
# ---------------------------------------------------------------------------


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_presentation_id() -> str:
    return f"pres-{uuid.uuid4().hex[:12]}"


@dataclass
class PresentationSequence:
    """Top-level presentation document.

    ``mission_ref`` is the optional mission_id this
    presentation drives. When set, waypoint refs in the
    steps are resolved against the named mission.
    """

    presentation_id: str = field(default_factory=_new_presentation_id)
    title: str = "Untitled Presentation"
    description: str = ""
    presenter_notes: str = ""
    mission_ref: Optional[str] = None
    steps: List[PresentationStep] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at_iso: str = ""
    updated_at_iso: str = ""
    schema_version: int = PRESENTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.tags:
            self.tags = [
                str(t).strip().lower() for t in self.tags
                if str(t).strip()
            ]

    # ---------------------------------------------------- size + lookup
    def __len__(self) -> int:
        return len(self.steps)

    def step_count(self) -> int:
        return len(self.steps)

    def find_step(self, step_id: str) -> Optional[PresentationStep]:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def find_step_index(self, step_id: str) -> int:
        for i, s in enumerate(self.steps):
            if s.step_id == step_id:
                return i
        return -1

    # ---------------------------------------------------- timestamps
    def touch(self) -> None:
        self.updated_at_iso = _utc_iso()

    # ---------------------------------------------------- (de)ser
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "presentation_id": self.presentation_id,
            "title": self.title,
            "description": self.description,
            "presenter_notes": self.presenter_notes,
            "mission_ref": self.mission_ref,
            "steps": [s.to_dict() for s in self.steps],
            "tags": list(self.tags),
            "created_at_iso": self.created_at_iso,
            "updated_at_iso": self.updated_at_iso,
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "PresentationSequence":
        if not isinstance(d, dict):
            raise PresentationError("presentation payload is not an object")
        version = d.get("schema_version", PRESENTATION_SCHEMA_VERSION)
        try:
            version_i = int(version)
        except (TypeError, ValueError) as exc:
            raise PresentationError(
                f"presentation schema_version not an integer: {version!r}",
            ) from exc
        if version_i > PRESENTATION_SCHEMA_VERSION:
            raise PresentationError(
                f"presentation schema_version {version_i} is newer "
                f"than this build understands "
                f"({PRESENTATION_SCHEMA_VERSION})."
            )
        steps_in = d.get("steps") or []
        if not isinstance(steps_in, list):
            raise PresentationError("steps must be a list")
        steps = [PresentationStep.from_dict(s) for s in steps_in if isinstance(s, dict)]
        return cls(
            schema_version=version_i,
            presentation_id=str(d.get("presentation_id") or _new_presentation_id()),
            title=str(d.get("title") or "Untitled Presentation"),
            description=str(d.get("description") or ""),
            presenter_notes=str(d.get("presenter_notes") or ""),
            mission_ref=(
                str(d["mission_ref"])
                if d.get("mission_ref") not in (None, "")
                else None
            ),
            steps=steps,
            tags=[str(t) for t in (d.get("tags") or [])],
            created_at_iso=str(d.get("created_at_iso") or ""),
            updated_at_iso=str(d.get("updated_at_iso") or ""),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(), indent=indent, ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, text: str) -> "PresentationSequence":
        try:
            d = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PresentationError(
                f"presentation JSON parse failed: {exc}",
            ) from exc
        return cls.from_dict(d)

    # ---------------------------------------------------- mutation
    def add_step(self, step: PresentationStep) -> PresentationStep:
        if len(self.steps) >= MAX_STEPS_PER_PRESENTATION:
            raise PresentationError(
                f"step cap exceeded "
                f"({MAX_STEPS_PER_PRESENTATION})"
            )
        if any(s.step_id == step.step_id for s in self.steps):
            raise PresentationError(
                f"duplicate step_id: {step.step_id}"
            )
        self.steps.append(step)
        return step

    def remove_step(self, step_id: str) -> bool:
        before = len(self.steps)
        self.steps = [s for s in self.steps if s.step_id != step_id]
        return len(self.steps) != before

    def move_step(self, step_id: str, new_index: int) -> bool:
        idx = self.find_step_index(step_id)
        if idx < 0:
            return False
        new_index = max(0, min(len(self.steps) - 1, int(new_index)))
        if idx == new_index:
            return False
        step = self.steps.pop(idx)
        self.steps.insert(new_index, step)
        return True

    # ---------------------------------------------------- validation
    def validate(self) -> List[str]:
        errs: List[str] = []
        if self.schema_version != PRESENTATION_SCHEMA_VERSION:
            errs.append(
                f"schema_version is {self.schema_version}; this build "
                f"writes {PRESENTATION_SCHEMA_VERSION}."
            )
        seen: set = set()
        for i, step in enumerate(self.steps):
            if not step.step_id:
                errs.append(f"step #{i}: step_id is empty")
            if step.step_id in seen:
                errs.append(
                    f"step #{i}: duplicate step_id '{step.step_id}'"
                )
            seen.add(step.step_id)
            if step.pause_seconds < 0:
                errs.append(
                    f"step #{i}: pause_seconds must be >= 0"
                )
        if len(self.steps) > MAX_STEPS_PER_PRESENTATION:
            errs.append(
                f"step count {len(self.steps)} exceeds cap "
                f"({MAX_STEPS_PER_PRESENTATION})"
            )
        return errs

    # ---------------------------------------------------- resolution
    def resolved_steps(self) -> List[ResolvedStep]:
        """Walk the steps front-to-back, applying inheritance
        for any field a step left blank.

        Determinism: same input → same output, byte for
        byte. The C4D playback engine reads this list and
        does not need to peek at adjacent steps.
        """
        out: List[ResolvedStep] = []
        prev_camera: Optional[Tuple[float, float, float]] = None
        prev_target: Optional[Tuple[float, float, float]] = None
        prev_fov: Optional[float] = None
        prev_epoch: Optional[float] = None
        prev_overlay: Dict[str, bool] = {}
        prev_science: Dict[str, bool] = {}
        prev_visible: List[int] = []
        prev_highlighted: List[int] = []
        for i, step in enumerate(self.steps):
            cam_pos = (
                step.camera_position if step.camera_position is not None
                else prev_camera
            )
            cam_tgt = (
                step.camera_target if step.camera_target is not None
                else prev_target
            )
            fov = (
                step.camera_fov_deg if step.camera_fov_deg is not None
                else prev_fov
            )
            epoch = (
                step.epoch_jd if step.epoch_jd is not None
                else prev_epoch
            )
            overlay = (
                dict(step.overlay_flags) if step.overlay_flags
                else dict(prev_overlay)
            )
            science = (
                dict(step.science_flags) if step.science_flags
                else dict(prev_science)
            )
            visible = (
                list(step.visible_annotation_indices)
                if step.visible_annotation_indices
                else list(prev_visible)
            )
            highlighted = (
                list(step.highlighted_annotation_indices)
                if step.highlighted_annotation_indices
                else list(prev_highlighted)
            )
            out.append(ResolvedStep(
                step_id=step.step_id,
                index=i,
                title=step.title,
                narration=step.narration,
                presenter_notes=step.presenter_notes,
                pause_seconds=step.pause_seconds,
                waypoint_ref=step.waypoint_ref,
                camera_position=cam_pos,
                camera_target=cam_tgt,
                camera_fov_deg=fov,
                epoch_jd=epoch,
                overlay_flags=overlay,
                science_flags=science,
                visible_annotation_indices=visible,
                highlighted_annotation_indices=highlighted,
                tags=list(step.tags),
            ))
            prev_camera = cam_pos
            prev_target = cam_tgt
            prev_fov = fov
            prev_epoch = epoch
            prev_overlay = overlay
            prev_science = science
            prev_visible = visible
            prev_highlighted = highlighted
        return out

    def total_duration_seconds(self) -> float:
        """Sum of every step's pause duration. Used by the
        dialog status bar."""
        return sum(s.pause_seconds for s in self.steps)
