"""v1.8 Cinema 4D timeline-baking helpers.

Convert a v1.4 ``CameraPath`` into a sequence of frame data
the dialog can write to Cinema 4D's timeline as keyframes on
the navigator null and on a camera object.

The pure-Python frame generator (``generate_keyframes``) is
testable without Cinema 4D: it produces a list of
``KeyframeRecord`` rows that the c4d-bound applier
(``apply_keyframes``) feeds into ``c4d.CTrack`` /
``c4d.CCurve`` / ``c4d.CKey`` at runtime.

Determinism: same camera path + same frame range → byte-
identical keyframe records, every time. There is no
floating-point timing dependence.

The applier is the only function in this module that imports
``c4d``. Tests drive ``generate_keyframes`` directly; the
applier's c4d-bound path is exercised by the dialog at
runtime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from voyage.camera_path import CameraPath, CameraSample, Quaternion

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default Cinema 4D frame rate. The artist sets the project
#: FPS in the host; this is only the fallback the v1.8 dialog
#: uses when the project FPS isn't readable.
DEFAULT_FPS: int = 30

#: Hard floor on baked frame count. With < 2 frames the
#: timeline can't carry an animation curve, so the helper
#: refuses.
MIN_FRAMES_FOR_BAKE: int = 2

#: Hard cap on baked frame count. Above this the helper
#: refuses (10 minutes at 60 fps); the artist can split the
#: mission or lower the fps.
MAX_FRAMES_FOR_BAKE: int = 36_000


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass
class KeyframeRecord:
    """One row of baked timeline data.

    The c4d applier consumes this verbatim. ``frame`` is an
    integer C4D frame number; ``position`` is C4D world units;
    ``rotation_hpb`` is the Heading-Pitch-Bank triple in radians
    that C4D expects for a camera object's rotation; ``fov_rad``
    is the optional horizontal field-of-view (when the bake
    requested it).
    """

    frame: int
    position: Tuple[float, float, float]
    rotation_hpb: Tuple[float, float, float]
    fov_rad: Optional[float] = None


@dataclass
class BakeRange:
    """Frame range + fps the bake operates over.

    The mission's total runtime is mapped uniformly into
    ``[start_frame, end_frame]`` — no per-segment quantisation,
    no easing. Same input → same output.

    ``include_fov`` controls whether each record carries a
    constant ``fov_rad`` (the dialog's "lock FOV" hint). v1.8
    does **not** vary FOV across the path; that's reserved
    for a future cinematics milestone.
    """

    start_frame: int = 0
    end_frame: int = 240
    fps: int = DEFAULT_FPS
    include_fov: bool = False
    fov_rad: Optional[float] = None

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise ValueError("fps must be > 0")
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be > start_frame")
        span = self.end_frame - self.start_frame + 1
        if span < MIN_FRAMES_FOR_BAKE:
            raise ValueError(
                f"frame range too narrow for a bake "
                f"({span} frames; need >= {MIN_FRAMES_FOR_BAKE})"
            )
        if span > MAX_FRAMES_FOR_BAKE:
            raise ValueError(
                f"frame range too wide for a bake "
                f"({span} frames; cap is {MAX_FRAMES_FOR_BAKE})"
            )

    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame + 1

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / float(self.fps)


@dataclass
class BakeReport:
    """One-line summary the dialog writes to the log.

    Distinct from ``KeyframeRecord`` so the dialog can
    surface "baked N keys, range [a..b], fps X" without
    walking the records list."""

    record_count: int = 0
    start_frame: int = 0
    end_frame: int = 0
    fps: int = DEFAULT_FPS
    include_fov: bool = False

    def summary_line(self) -> str:
        parts = [
            f"baked {self.record_count} keyframe(s)",
            f"frames [{self.start_frame}..{self.end_frame}]",
            f"@ {self.fps} fps",
        ]
        if self.include_fov:
            parts.append("with FOV")
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Frame mapping
# ---------------------------------------------------------------------------


def frame_to_progress(frame: int, frame_range: BakeRange) -> float:
    """Map a C4D frame number into the camera path's
    normalised ``[0, 1]`` progress. Out-of-range frames
    clamp."""
    span = frame_range.end_frame - frame_range.start_frame
    if span <= 0:
        return 0.0
    raw = (int(frame) - frame_range.start_frame) / float(span)
    if raw < 0.0:
        return 0.0
    if raw > 1.0:
        return 1.0
    return raw


def progress_to_frame(progress: float, frame_range: BakeRange) -> int:
    """Inverse of ``frame_to_progress``. Used by the dialog
    when it wants to highlight the timeline cursor for a
    given playback progress."""
    p = 0.0 if progress < 0.0 else 1.0 if progress > 1.0 else float(progress)
    span = frame_range.end_frame - frame_range.start_frame
    return int(round(frame_range.start_frame + p * span))


# ---------------------------------------------------------------------------
# Quaternion → HPB
# ---------------------------------------------------------------------------


def quaternion_to_hpb(q: Quaternion) -> Tuple[float, float, float]:
    """Convert a UNAV-convention ``(w, x, y, z)`` unit
    quaternion into Cinema 4D Heading-Pitch-Bank radians.

    The order of operations is the C4D convention
    (Heading × Pitch × Bank applied right-to-left in the
    body frame). Singularity at |pitch| ≈ 90° degenerates
    gracefully — heading and bank fold into a single
    rotation about ±Y.
    """
    w, x, y, z = q
    # Normalise defensively. Empty / zero quat → identity.
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n < 1e-9:
        return (0.0, 0.0, 0.0)
    w, x, y, z = w / n, x / n, y / n, z / n

    # HPB derivation: rotate +Z by q, decompose. C4D's HPB is
    # (heading about Y, pitch about X, bank about Z) applied
    # in body order H→P→B. Standard tait-bryan ZYX:
    sin_pitch = 2.0 * (w * x - y * z)
    sin_pitch = max(-1.0, min(1.0, sin_pitch))
    pitch = math.asin(sin_pitch)
    if abs(sin_pitch) > 0.999_999:
        # Gimbal lock — collapse heading + bank into one axis.
        heading = math.atan2(-2.0 * (x * z - w * y), 1.0 - 2.0 * (x * x + y * y))
        bank = 0.0
    else:
        heading = math.atan2(2.0 * (w * y + x * z), 1.0 - 2.0 * (x * x + y * y))
        bank = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (x * x + z * z))
    return (heading, pitch, bank)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def generate_keyframes(
    path: CameraPath,
    frame_range: Optional[BakeRange] = None,
    *,
    samples: Optional[int] = None,
) -> List[KeyframeRecord]:
    """Build the list of ``KeyframeRecord`` rows that an
    applier will write into Cinema 4D's timeline.

    One record per frame in ``frame_range`` by default. The
    ``samples`` argument lets the caller force a specific
    number of records (clamped to ``[MIN_FRAMES_FOR_BAKE,
    MAX_FRAMES_FOR_BAKE]``); useful when the artist wants
    every-N-frames keys for a sparser bake.

    Empty paths return an empty list — the applier no-ops
    and the dialog logs "nothing to bake."
    """
    if path.is_empty():
        return []
    fr = frame_range or BakeRange()
    if samples is None:
        samples = fr.frame_count
    samples = max(MIN_FRAMES_FOR_BAKE, min(int(samples), MAX_FRAMES_FOR_BAKE))

    out: List[KeyframeRecord] = []
    span = fr.end_frame - fr.start_frame
    if samples == 1:
        # Degenerate: emit a single record at start_frame.
        sample = path.sample(0.0)
        out.append(_record_from_sample(sample, fr.start_frame, fr))
        return out

    for i in range(samples):
        progress = i / float(samples - 1)
        frame = fr.start_frame + int(round(progress * span))
        sample = path.sample(progress)
        out.append(_record_from_sample(sample, frame, fr))
    return out


def _record_from_sample(
    sample: CameraSample, frame: int, frame_range: BakeRange,
) -> KeyframeRecord:
    h, p, b = quaternion_to_hpb(sample.orientation)
    fov: Optional[float] = None
    if frame_range.include_fov and frame_range.fov_rad is not None:
        fov = float(frame_range.fov_rad)
    return KeyframeRecord(
        frame=int(frame),
        position=(float(sample.x), float(sample.y), float(sample.z)),
        rotation_hpb=(h, p, b),
        fov_rad=fov,
    )


def generate_bake_report(
    records: Sequence[KeyframeRecord],
    frame_range: BakeRange,
) -> BakeReport:
    """One-shot summary the dialog renders after a bake."""
    return BakeReport(
        record_count=len(records),
        start_frame=frame_range.start_frame,
        end_frame=frame_range.end_frame,
        fps=frame_range.fps,
        include_fov=frame_range.include_fov,
    )


# ---------------------------------------------------------------------------
# Cinema 4D applier
# ---------------------------------------------------------------------------


def apply_keyframes(
    records: Sequence[KeyframeRecord],
    *,
    navigator=None,
    camera=None,
    doc=None,
    apply_position_to_navigator: bool = True,
    apply_position_to_camera: bool = True,
    apply_rotation_to_camera: bool = True,
    apply_fov_to_camera: bool = False,
) -> int:
    """Cinema 4D-bound applier. Writes ``records`` into the
    host's timeline as CTrack / CCurve keys on ``navigator``
    and / or ``camera``. Returns the number of records
    actually written.

    The function is **only** for the c4d-bound path; tests
    drive ``generate_keyframes`` directly. ``apply_keyframes``
    silently no-ops when no ``c4d`` module is importable so
    importing this module from a non-C4D process is safe.

    The dialog calls this after generating records — there is
    no streaming variant; baking always mutates the timeline
    in one transactional pass.
    """
    try:
        import c4d  # type: ignore
    except ImportError:
        return 0
    if not records:
        return 0
    if doc is None:
        try:
            from c4d import documents  # type: ignore
            doc = documents.GetActiveDocument()
        except Exception:  # noqa: BLE001
            return 0
    if doc is None:
        return 0

    written = 0
    doc.StartUndo()
    try:
        for rec in records:
            if navigator is not None and apply_position_to_navigator:
                _set_position_key(doc, navigator, rec.frame, rec.position)
                written += 1
            if camera is not None:
                if apply_position_to_camera:
                    _set_position_key(doc, camera, rec.frame, rec.position)
                if apply_rotation_to_camera:
                    _set_rotation_key(doc, camera, rec.frame, rec.rotation_hpb)
                if apply_fov_to_camera and rec.fov_rad is not None:
                    _set_fov_key(doc, camera, rec.frame, rec.fov_rad)
                written += 1
    finally:
        doc.EndUndo()
        try:
            c4d.EventAdd()
        except Exception:  # noqa: BLE001
            pass
    return written


# ---------------------------------------------------------------------------
# C4D-bound key setters (extracted so the applier reads cleanly)
# ---------------------------------------------------------------------------


def _set_position_key(doc, obj, frame: int, position) -> None:
    """Stamp a position key on ``obj`` at ``frame``. Safe
    no-op outside Cinema 4D."""
    try:
        import c4d  # type: ignore
    except ImportError:
        return
    btime = c4d.BaseTime(int(frame), doc.GetFps())
    for axis, value, desc_id in (
        ("x", position[0], c4d.ID_BASEOBJECT_REL_POSITION),
        ("y", position[1], c4d.ID_BASEOBJECT_REL_POSITION),
        ("z", position[2], c4d.ID_BASEOBJECT_REL_POSITION),
    ):
        # Each axis is a sub-component on the same DescID.
        # The dialog's bake button is the only caller of this
        # helper — it's intentionally simple-minded; future
        # passes may switch to ``DescID(c4d.ID_BASEOBJECT_REL_POSITION,
        # c4d.VECTOR_X)`` etc. for finer control.
        pass
    # Set a vector value at the time on the object.
    obj[c4d.ID_BASEOBJECT_REL_POSITION] = c4d.Vector(
        float(position[0]), float(position[1]), float(position[2]),
    )
    _record_track_key(doc, obj, c4d.ID_BASEOBJECT_REL_POSITION, btime,
                      c4d.Vector(*[float(v) for v in position]))


def _set_rotation_key(doc, obj, frame: int, hpb) -> None:
    try:
        import c4d  # type: ignore
    except ImportError:
        return
    btime = c4d.BaseTime(int(frame), doc.GetFps())
    obj[c4d.ID_BASEOBJECT_REL_ROTATION] = c4d.Vector(
        float(hpb[0]), float(hpb[1]), float(hpb[2]),
    )
    _record_track_key(doc, obj, c4d.ID_BASEOBJECT_REL_ROTATION, btime,
                      c4d.Vector(*[float(v) for v in hpb]))


def _set_fov_key(doc, obj, frame: int, fov_rad: float) -> None:
    try:
        import c4d  # type: ignore
    except ImportError:
        return
    btime = c4d.BaseTime(int(frame), doc.GetFps())
    # CAMERA_FOV is the horizontal FOV in radians on a c4d.CameraObject.
    obj[c4d.CAMERA_FOV] = float(fov_rad)
    _record_track_key(doc, obj, c4d.CAMERA_FOV, btime, float(fov_rad))


def _record_track_key(doc, obj, desc_id, btime, value) -> None:
    """Find-or-create the CTrack on ``desc_id`` and stamp a
    key at ``btime``. Pure helper for the c4d-bound code path
    — no-ops outside Cinema 4D."""
    try:
        import c4d  # type: ignore
    except ImportError:
        return
    track = obj.FindCTrack(c4d.DescID(desc_id))
    if track is None:
        track = c4d.CTrack(obj, c4d.DescID(desc_id))
        obj.InsertTrackSorted(track)
    curve = track.GetCurve()
    key = curve.AddKey(btime)
    if key is None or key.get("key") is None:
        return
    k = key["key"]
    if isinstance(value, c4d.Vector):
        # vector write is per-component on the same desc; UNAV
        # uses scalar curves only via SetValue.
        k.SetValue(curve, value.x)
    else:
        k.SetValue(curve, float(value))


# ---------------------------------------------------------------------------
# v2.2 mission-to-timeline one-shot
# ---------------------------------------------------------------------------


def bake_mission_to_timeline(
    mission,
    path,
    *,
    frame_range: Optional[BakeRange] = None,
    config=None,
    navigator=None,
    camera=None,
    doc=None,
    apply_markers_to_doc: bool = True,
    science_layer_frames: Optional[Sequence[int]] = None,
    waypoint_labels: Optional[Sequence[str]] = None,
):
    """v2.2 high-level baker.

    Walks the v2.2 ``evaluate_animated_state`` over ``mission``
    + ``path``, then in one transactional step:

    * writes one keyframe per frame on ``navigator`` and
      ``camera`` (position / rotation; FOV optional);
    * inserts UNAV-tagged markers (waypoint / epoch / sync /
      science) onto the document timeline;
    * returns the (``timeline``, ``keyframes_written``,
      ``markers_written``) tuple so the dialog can log a
      summary.

    The visible-sector pipeline is **never** triggered by
    this function — the markers are *requests* that the
    dialog / SceneHook honours separately.

    Pure-Python fallback: when Cinema 4D isn't available, the
    function still builds the animated timeline + marker
    bundle and returns them with zero scene writes.
    """
    from animation.animated_state import (
        evaluate_animated_state,
    )
    from c4d_objects.timeline_markers import (
        apply_markers,
        build_marker_bundle,
    )
    fr = frame_range or BakeRange()
    timeline = evaluate_animated_state(
        mission, path, frame_range=fr, config=config,
    )
    if timeline.is_empty():
        return timeline, 0, 0

    # Keyframes — reuse the v1.8 applier verbatim.
    keys_written = apply_keyframes(
        timeline.keyframes,
        navigator=navigator,
        camera=camera,
        doc=doc,
        apply_position_to_navigator=True,
        apply_position_to_camera=True,
        apply_rotation_to_camera=True,
        apply_fov_to_camera=any(
            r.fov_rad is not None for r in timeline.keyframes
        ),
    )

    markers_written = 0
    if apply_markers_to_doc:
        bundle = build_marker_bundle(
            timeline,
            waypoint_labels=waypoint_labels,
            science_layer_frames=science_layer_frames,
        )
        markers_written = apply_markers(
            bundle, doc=doc, fps=fr.fps,
        )

    return timeline, keys_written, markers_written
