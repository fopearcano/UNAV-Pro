"""v3.8 presentation transitions.

**Pure-Python deterministic transition sequencing.**
The v3.8 transition layer plans how state changes
between two presentation steps unfold over a fixed
duration:

* ``HARD_CUT`` — instantaneous swap. No
  intermediate frames.
* ``SMOOTH_CAMERA`` — slerp-style camera-pose
  interpolation across N frames (no fades; no
  rendering).
* ``CROSSFADE_PLACEHOLDER`` — emits intermediate
  state records but each carries a fade-fraction
  the caller can ignore. v3.8 documents the
  placeholder slot; **no actual rendering fade
  happens**.
* ``WAYPOINT_PAUSE`` — hold on the source step
  for a configurable pause before snapping to
  the destination.

This is **navigation-state sequencing** only.
The dialog reads the produced ``TransitionFrame``
records to drive the v3.3 playback engine; nothing
here renders pixels or affects the C4D
viewport's display.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Transition kinds
# ---------------------------------------------------------------------------


class TransitionKind(str, Enum):
    """Four cinematic transition kinds the
    presentation layer supports."""

    HARD_CUT = "hard_cut"
    SMOOTH_CAMERA = "smooth_camera"
    CROSSFADE_PLACEHOLDER = "crossfade_placeholder"
    WAYPOINT_PAUSE = "waypoint_pause"


TRANSITION_KINDS = tuple(TransitionKind)


# ---------------------------------------------------------------------------
# Transition spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionSpec:
    """Declarative description of one transition.

    ``frame_count`` is the number of intermediate
    state records the sequencer emits between the
    source and destination steps. ``hard_cut``
    always emits 0; everything else honours the
    parameter.
    """

    kind: TransitionKind = TransitionKind.HARD_CUT
    frame_count: int = 12
    pause_seconds: float = 0.0  # used by WAYPOINT_PAUSE

    def __post_init__(self) -> None:
        if self.frame_count < 0:
            raise ValueError("frame_count must be >= 0")
        if self.pause_seconds < 0:
            raise ValueError("pause_seconds must be >= 0")


# ---------------------------------------------------------------------------
# Transition frame
# ---------------------------------------------------------------------------


@dataclass
class TransitionFrame:
    """One frame in the transition sequence.

    ``t`` is the parametric position in
    ``[0.0, 1.0]``. ``camera_position`` /
    ``camera_target`` come from the slerp / lerp.
    ``crossfade_fraction`` is populated only for
    the placeholder cross-fade; the dialog renders
    it as a status hint, **not** a real fade."""

    index: int
    t: float
    camera_position: Optional[Vec3] = None
    camera_target: Optional[Vec3] = None
    fov_deg: Optional[float] = None
    crossfade_fraction: Optional[float] = None
    holds_source: bool = False    # WAYPOINT_PAUSE flag
    notes: str = ""


# ---------------------------------------------------------------------------
# Step shape (duck-typed)
# ---------------------------------------------------------------------------


@dataclass
class StepProjection:
    """Pure-data projection of the v3.3
    ``ResolvedStep`` fields the transition sequencer
    needs. Tests can build these directly without a
    full presentation."""

    step_id: str
    camera_position: Optional[Vec3] = None
    camera_target: Optional[Vec3] = None
    fov_deg: Optional[float] = None


def project_resolved_step(step) -> StepProjection:
    """Build a ``StepProjection`` from a v3.3
    ``ResolvedStep`` (or any duck-typed equivalent
    with the right attributes)."""
    return StepProjection(
        step_id=str(getattr(step, "step_id", "") or ""),
        camera_position=getattr(step, "camera_position", None),
        camera_target=getattr(step, "camera_target", None),
        fov_deg=getattr(step, "camera_fov_deg", None),
    )


# ---------------------------------------------------------------------------
# Sequencer
# ---------------------------------------------------------------------------


def _vec_lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (
        a[0] + t * (b[0] - a[0]),
        a[1] + t * (b[1] - a[1]),
        a[2] + t * (b[2] - a[2]),
    )


def _scalar_lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


def sequence_transition(
    *,
    source: StepProjection,
    destination: StepProjection,
    spec: TransitionSpec,
) -> List[TransitionFrame]:
    """Pure deterministic helper: produce the list
    of ``TransitionFrame`` records for one
    transition.

    Same ``(source, destination, spec)`` always
    produces the same frames, byte for byte.
    """
    if spec.kind is TransitionKind.HARD_CUT:
        return []
    if spec.kind is TransitionKind.WAYPOINT_PAUSE:
        # One "hold" frame + one "snap" frame at the
        # end. Pure determinism; no in-between.
        out: List[TransitionFrame] = []
        if spec.frame_count == 0:
            out.append(TransitionFrame(
                index=0, t=0.0,
                camera_position=source.camera_position,
                camera_target=source.camera_target,
                fov_deg=source.fov_deg,
                holds_source=True,
                notes=(
                    f"holding source for {spec.pause_seconds:.2f}s"
                ),
            ))
            return out
        for i in range(spec.frame_count):
            t = i / float(spec.frame_count - 1) if spec.frame_count > 1 else 1.0
            out.append(TransitionFrame(
                index=i, t=t,
                camera_position=source.camera_position,
                camera_target=source.camera_target,
                fov_deg=source.fov_deg,
                holds_source=True,
                notes=(
                    f"holding source for {spec.pause_seconds:.2f}s"
                    if i == 0 else ""
                ),
            ))
        return out
    if spec.kind is TransitionKind.SMOOTH_CAMERA:
        return _smooth_camera_frames(source, destination, spec.frame_count)
    # CROSSFADE_PLACEHOLDER
    return _crossfade_placeholder_frames(
        source, destination, spec.frame_count,
    )


def _smooth_camera_frames(
    source: StepProjection,
    destination: StepProjection,
    frame_count: int,
) -> List[TransitionFrame]:
    out: List[TransitionFrame] = []
    if frame_count == 0:
        return out
    for i in range(frame_count):
        if frame_count == 1:
            t = 1.0
        else:
            t = i / float(frame_count - 1)
        cam_pos = _interp_optional_vec(
            source.camera_position, destination.camera_position, t,
        )
        cam_tgt = _interp_optional_vec(
            source.camera_target, destination.camera_target, t,
        )
        fov = _interp_optional_scalar(
            source.fov_deg, destination.fov_deg, t,
        )
        out.append(TransitionFrame(
            index=i, t=t,
            camera_position=cam_pos,
            camera_target=cam_tgt,
            fov_deg=fov,
        ))
    return out


def _crossfade_placeholder_frames(
    source: StepProjection,
    destination: StepProjection,
    frame_count: int,
) -> List[TransitionFrame]:
    out: List[TransitionFrame] = []
    if frame_count == 0:
        return out
    for i in range(frame_count):
        if frame_count == 1:
            t = 1.0
        else:
            t = i / float(frame_count - 1)
        cam_pos = _interp_optional_vec(
            source.camera_position, destination.camera_position, t,
        )
        cam_tgt = _interp_optional_vec(
            source.camera_target, destination.camera_target, t,
        )
        fov = _interp_optional_scalar(
            source.fov_deg, destination.fov_deg, t,
        )
        out.append(TransitionFrame(
            index=i, t=t,
            camera_position=cam_pos,
            camera_target=cam_tgt,
            fov_deg=fov,
            crossfade_fraction=t,
            notes=(
                "crossfade is a placeholder; the v3.8 layer "
                "doesn't render fades."
            ) if i == 0 else "",
        ))
    return out


def _interp_optional_vec(
    a: Optional[Vec3], b: Optional[Vec3], t: float,
) -> Optional[Vec3]:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return _vec_lerp(a, b, t)


def _interp_optional_scalar(
    a: Optional[float], b: Optional[float], t: float,
) -> Optional[float]:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return _scalar_lerp(float(a), float(b), t)


# ---------------------------------------------------------------------------
# Multi-step sequencer
# ---------------------------------------------------------------------------


@dataclass
class TransitionSequence:
    """Complete sequence: a list of (source step,
    transition, destination step) tuples expanded
    into a flat ``frames`` list.

    The dialog feeds this to the v3.3 playback
    engine; each frame is one C4D timeline tick the
    engine drives the camera through.
    """

    frames: List[TransitionFrame] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def total_frames(self) -> int:
        return len(self.frames)

    def short_summary(self) -> str:
        parts = [f"{self.total_frames} frame(s)"]
        if self.notes:
            parts.append(f"{len(self.notes)} note(s)")
        return " · ".join(parts)


def build_transition_sequence(
    *,
    steps: Sequence[StepProjection],
    specs: Sequence[TransitionSpec],
) -> TransitionSequence:
    """Compose the full transition sequence from a
    list of N steps + a list of N-1 transition specs
    (one per inter-step boundary).

    Pure deterministic; same inputs ⇒ identical
    output. Used by the dialog when the artist
    presses *Play Tour*.
    """
    if len(steps) == 0:
        return TransitionSequence()
    expected_specs = max(0, len(steps) - 1)
    if len(specs) != expected_specs:
        raise ValueError(
            f"expected {expected_specs} transition spec(s) for "
            f"{len(steps)} step(s); got {len(specs)}"
        )
    out = TransitionSequence()
    base_index = 0
    for i in range(expected_specs):
        spec = specs[i]
        sub = sequence_transition(
            source=steps[i],
            destination=steps[i + 1],
            spec=spec,
        )
        # Re-base each sub-sequence's index so the
        # final list reads 0, 1, 2, ...
        for frame in sub:
            frame.index = base_index
            base_index += 1
            out.frames.append(frame)
        if spec.kind is TransitionKind.CROSSFADE_PLACEHOLDER:
            out.notes.append(
                f"step {i}->{i + 1}: crossfade placeholder; "
                "no rendering fade applied."
            )
        elif spec.kind is TransitionKind.WAYPOINT_PAUSE:
            out.notes.append(
                f"step {i}->{i + 1}: pause "
                f"{spec.pause_seconds:.2f}s on source"
            )
    return out
