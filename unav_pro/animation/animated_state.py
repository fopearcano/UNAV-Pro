"""v2.2 animated UNAV state evaluator.

A pure-Python frame-aware evaluator that turns a mission +
its built ``CameraPath`` into the per-frame state Cinema 4D's
timeline needs:

* navigator position
* camera orientation (HPB radians)
* optional FOV
* optional epoch (Julian Date)
* active waypoint index
* sync markers — explicit frames at which the dialog should
  re-stream the visible sector

The evaluator is **side-effect-free** and **deterministic**:
same inputs → byte-identical output. It is the seam between
the v1.4 / v1.8 voyage stack and the v2.2 timeline-baking
pipeline. Tests drive this module directly without Cinema 4D.

Design notes:

* The evaluator does not advance any cursor. ``Playback`` is
  the cursor-bearing transport; this module is a pure
  "what does the mission look like at frame N" oracle.
* Sync markers are *explicit*: the artist (or a default
  policy) lists the frames where the visible-sector should
  refresh. v2.2 acceptance criteria forbid per-frame
  sector regeneration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from c4d_objects.timeline_keys import (
    DEFAULT_FPS,
    MAX_FRAMES_FOR_BAKE,
    MIN_FRAMES_FOR_BAKE,
    BakeRange,
    KeyframeRecord,
    quaternion_to_hpb,
)
from voyage.camera_path import CameraPath, CameraSample, Quaternion
from voyage.mission import Mission

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


Vec3 = Tuple[float, float, float]


@dataclass
class AnimatedSample:
    """One per-frame sample produced by the v2.2 animated-
    state evaluator.

    ``frame`` is the C4D frame number; ``progress`` is the
    underlying mission progress in ``[0, 1]``. Both are
    populated so a caller can report either in the dialog
    log without re-deriving.
    """

    frame: int
    progress: float
    seconds: float
    navigator_position: Vec3
    camera_position: Vec3
    camera_orientation_quat: Quaternion
    rotation_hpb: Tuple[float, float, float]
    fov_rad: Optional[float] = None
    epoch_jd: Optional[float] = None
    waypoint_index: int = 0
    is_sync_marker: bool = False


@dataclass
class AnimatedStateConfig:
    """Knobs the dialog exposes to the v2.2 evaluator.

    All optional. ``BakeRange`` from v1.8 stays the canonical
    frame-range / fps source — this config layers on the
    extras.

    * ``fov_rad`` — constant FOV in radians (None → leave
      ``AnimatedSample.fov_rad`` empty). v2.2 does *not*
      animate FOV across the path; the field exists so a
      single FOV value can be baked alongside the camera
      keyframes.
    * ``apply_camera_offset_to_navigator`` — when True (the
      default), the navigator's position equals the
      *waypoint anchor* position (without the camera offset)
      while the camera's position equals the *path sample*
      position (with the camera offset). When False, both
      receive the path sample directly.
    * ``sync_markers`` — explicit list of frame numbers at
      which the visible-sector should be re-streamed. The
      evaluator marks the sample at each frame with
      ``is_sync_marker = True`` so the dialog / SceneHook
      can fire ``sync_visible_sector`` at exactly those
      frames.
    * ``waypoint_arrival_markers`` — when True (default),
      the evaluator additionally marks the frame each
      waypoint's anchor lands on (one per waypoint, not just
      the explicit list).
    """

    fov_rad: Optional[float] = None
    apply_camera_offset_to_navigator: bool = True
    sync_markers: List[int] = field(default_factory=list)
    waypoint_arrival_markers: bool = True


@dataclass
class AnimatedTimeline:
    """Aggregate output of the v2.2 evaluator. Reuses the
    v1.8 ``BakeRange`` for the frame range and the v1.8
    ``KeyframeRecord`` for the keyframe-bake records, so the
    timeline-key applier consumes both without changes."""

    samples: List[AnimatedSample] = field(default_factory=list)
    keyframes: List[KeyframeRecord] = field(default_factory=list)
    waypoint_arrival_frames: List[int] = field(default_factory=list)
    sync_marker_frames: List[int] = field(default_factory=list)
    epoch_change_frames: List[int] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.samples


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def frame_to_seconds(frame: int, frame_range: BakeRange) -> float:
    """Convert a C4D frame into wall-clock seconds (relative
    to the bake's start frame)."""
    if frame_range.fps <= 0:
        return 0.0
    return (int(frame) - frame_range.start_frame) / float(frame_range.fps)


def seconds_to_frame(seconds: float, frame_range: BakeRange) -> int:
    """Inverse of ``frame_to_seconds``."""
    if frame_range.fps <= 0:
        return frame_range.start_frame
    return frame_range.start_frame + int(round(float(seconds) * frame_range.fps))


def frame_to_progress(frame: int, frame_range: BakeRange) -> float:
    """v2.2 mirror of v1.8 ``timeline_keys.frame_to_progress``;
    re-exposed here so the animated-state caller doesn't need
    a second import."""
    span = frame_range.end_frame - frame_range.start_frame
    if span <= 0:
        return 0.0
    raw = (int(frame) - frame_range.start_frame) / float(span)
    if raw < 0.0:
        return 0.0
    if raw > 1.0:
        return 1.0
    return raw


def _waypoint_arrival_frames_for_path(
    path: CameraPath,
    frame_range: BakeRange,
) -> List[int]:
    """Map each waypoint's cumulative-normalised anchor onto a
    C4D frame number. Used both for the explicit per-waypoint
    sample marker and as a fallback sync-marker policy."""
    if path.is_empty() or path.waypoint_count() < 1:
        return []
    span = frame_range.end_frame - frame_range.start_frame
    out: List[int] = []
    for cum in path.cumulative_normalised:
        out.append(frame_range.start_frame + int(round(cum * span)))
    return out


def _epoch_change_frames(
    samples: Sequence[AnimatedSample],
    path: CameraPath,
    waypoint_arrivals: Sequence[int],
) -> List[int]:
    """Return frames at which the *path's per-waypoint
    epoch* changes. We detect changes at the waypoint
    granularity, not on the per-frame interpolated value
    (which would fire every frame within a segment because
    of the linear epoch lerp).

    A frame is an epoch-change frame when the waypoint that
    "owns" it has a different epoch from the previous
    waypoint's epoch."""
    out: List[int] = []
    if not waypoint_arrivals or path.is_empty():
        return out
    last_epoch: Optional[float] = None
    for i, frame in enumerate(waypoint_arrivals):
        if i >= len(path.epochs):
            break
        ep = path.epochs[i]
        if ep is None:
            last_epoch = None
            continue
        if last_epoch is None or abs(float(ep) - float(last_epoch)) > 1e-9:
            out.append(int(frame))
            last_epoch = float(ep)
    return out


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


def evaluate_animated_state(
    mission: Mission,
    path: CameraPath,
    *,
    frame_range: Optional[BakeRange] = None,
    config: Optional[AnimatedStateConfig] = None,
) -> AnimatedTimeline:
    """Build an ``AnimatedTimeline`` from a mission + its
    built camera path.

    The mission is consulted for per-waypoint
    ``camera_offset`` (so the navigator position can differ
    from the camera position when requested). The path is
    consulted for everything else.
    """
    cfg = config or AnimatedStateConfig()
    fr = frame_range or BakeRange()
    timeline = AnimatedTimeline()

    if path.is_empty() or path.waypoint_count() < 2:
        timeline.warnings.append(
            "animated state: need ≥ 2 resolvable waypoints; "
            "the mission produced fewer."
        )
        return timeline

    # Pre-compute waypoint arrival frames (used both for the
    # sample-tagging step and for the marker output).
    waypoint_arrivals = _waypoint_arrival_frames_for_path(path, fr)
    timeline.waypoint_arrival_frames = list(waypoint_arrivals)

    # Sync markers: explicit list + (optionally) the waypoint
    # arrival frames. De-duplicated and sorted so the artist
    # never sees the same frame fire twice.
    sync_set = set(int(f) for f in cfg.sync_markers if isinstance(f, (int, float)))
    if cfg.waypoint_arrival_markers:
        sync_set.update(waypoint_arrivals)
    timeline.sync_marker_frames = sorted(sync_set)

    # Pre-compute the camera-offset for each waypoint so we
    # can re-derive the *anchor* position at evaluation time
    # (path.sample includes the offset).
    offsets: List[Vec3] = []
    for wp in mission.waypoints:
        if not wp.is_path_contributing():
            continue
        if wp.has_c4d_position():
            ox, oy, oz = (0.0, 0.0, 0.0)
            if wp.camera_offset is not None:
                ox = float(wp.camera_offset[0])
                oy = float(wp.camera_offset[1])
                oz = float(wp.camera_offset[2])
            offsets.append((ox, oy, oz))

    # Walk every frame in the range.
    span = fr.end_frame - fr.start_frame
    for i in range(fr.frame_count):
        frame = fr.start_frame + i
        progress = i / float(span) if span > 0 else 0.0
        sample = path.sample(progress)
        seconds = frame_to_seconds(frame, fr)

        # Navigator vs camera position split. The camera is
        # whatever the path sample produced (offset already
        # applied at build time). For the navigator we
        # subtract the per-waypoint offset, lerping linearly
        # within each segment.
        cam_pos = (sample.x, sample.y, sample.z)
        nav_pos = cam_pos
        if cfg.apply_camera_offset_to_navigator and offsets:
            seg = max(0, min(sample.waypoint_index, len(offsets) - 2))
            local_offset = _lerp_vec3(
                offsets[seg], offsets[min(seg + 1, len(offsets) - 1)],
                _segment_local_t(path, progress, seg),
            )
            nav_pos = (
                cam_pos[0] - local_offset[0],
                cam_pos[1] - local_offset[1],
                cam_pos[2] - local_offset[2],
            )

        h, p, b = quaternion_to_hpb(sample.orientation)
        is_sync = frame in sync_set
        timeline.samples.append(AnimatedSample(
            frame=frame,
            progress=progress,
            seconds=seconds,
            navigator_position=nav_pos,
            camera_position=cam_pos,
            camera_orientation_quat=sample.orientation,
            rotation_hpb=(h, p, b),
            fov_rad=cfg.fov_rad,
            epoch_jd=sample.epoch_jd,
            waypoint_index=sample.waypoint_index,
            is_sync_marker=is_sync,
        ))

        # Build a v1.8 ``KeyframeRecord`` for every frame so
        # the existing timeline_keys applier can consume it
        # verbatim.
        timeline.keyframes.append(KeyframeRecord(
            frame=frame,
            position=cam_pos,
            rotation_hpb=(h, p, b),
            fov_rad=cfg.fov_rad,
        ))

    timeline.epoch_change_frames = _epoch_change_frames(
        timeline.samples, path, waypoint_arrivals,
    )

    # Surface a warning if the artist has scheduled lots of
    # sync points (the visible sector pipeline is the
    # plugin's most expensive operation).
    if len(timeline.sync_marker_frames) > 32:
        timeline.warnings.append(
            f"animated state: {len(timeline.sync_marker_frames)} "
            "sync markers scheduled — the visible-sector "
            "pipeline will fire that many times during "
            "playback / bake. Consider trimming."
        )

    return timeline


def _lerp_vec3(a: Vec3, b: Vec3, t: float) -> Vec3:
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else float(t)
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _segment_local_t(
    path: CameraPath, progress: float, seg: int,
) -> float:
    """Local parameter within a segment for the camera-offset
    lerp. Mirrors ``CameraPath.sample``'s segment lookup."""
    n = path.waypoint_count()
    if n < 2:
        return 0.0
    cum = path.cumulative_normalised
    if seg < 0 or seg >= n - 1:
        return 0.0
    span = max(cum[seg + 1] - cum[seg], 1e-12)
    return max(0.0, min(1.0, (progress - cum[seg]) / span))


# ---------------------------------------------------------------------------
# Frame-level pure read API
# ---------------------------------------------------------------------------


def evaluate_at_frame(
    mission: Mission,
    path: CameraPath,
    frame: int,
    *,
    frame_range: Optional[BakeRange] = None,
    config: Optional[AnimatedStateConfig] = None,
) -> Optional[AnimatedSample]:
    """v2.2 *single-frame* read. The dialog's "Preview Frame"
    button uses this; tests can hit it without paying for the
    full timeline.

    Returns ``None`` for empty paths, frames outside the
    range (clamped), or paths with < 2 waypoints."""
    cfg = config or AnimatedStateConfig()
    fr = frame_range or BakeRange()
    if path.is_empty() or path.waypoint_count() < 2:
        return None
    f = max(fr.start_frame, min(int(frame), fr.end_frame))
    progress = frame_to_progress(f, fr)
    sample = path.sample(progress)
    h, p, b = quaternion_to_hpb(sample.orientation)
    cam_pos = (sample.x, sample.y, sample.z)
    nav_pos = cam_pos
    if cfg.apply_camera_offset_to_navigator:
        # We don't have the cached offsets here without a
        # second pass; the dialog's preview-frame button is
        # for visual confirmation only. Fall back to the
        # path sample for both.
        nav_pos = cam_pos
    return AnimatedSample(
        frame=f,
        progress=progress,
        seconds=frame_to_seconds(f, fr),
        navigator_position=nav_pos,
        camera_position=cam_pos,
        camera_orientation_quat=sample.orientation,
        rotation_hpb=(h, p, b),
        fov_rad=cfg.fov_rad,
        epoch_jd=sample.epoch_jd,
        waypoint_index=sample.waypoint_index,
        is_sync_marker=int(f) in set(cfg.sync_markers),
    )


def evaluate_at_seconds(
    mission: Mission,
    path: CameraPath,
    seconds: float,
    *,
    frame_range: Optional[BakeRange] = None,
    config: Optional[AnimatedStateConfig] = None,
) -> Optional[AnimatedSample]:
    """v2.2 second-precision read. Wraps ``evaluate_at_frame``
    via ``seconds_to_frame``. Returns ``None`` on empty
    paths."""
    fr = frame_range or BakeRange()
    return evaluate_at_frame(
        mission, path, seconds_to_frame(seconds, fr),
        frame_range=fr, config=config,
    )
