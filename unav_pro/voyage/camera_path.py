"""Cinematic camera path for the v1.4 voyage system.

Given a sequence of resolved waypoint poses (position +
optional orientation + optional epoch), this module produces
the **per-segment interpolation table** the playback engine
samples.

The contract is intentionally minimal:

* **Position** — Catmull-Rom spline through the waypoint
  positions, evaluated in C4D world units. Endpoints are
  duplicated so the spline begins and ends at the first /
  last waypoint exactly. With < 2 control points the path
  degenerates to a single static pose.
* **Orientation** — slerp between the per-waypoint
  ``orientation_quat`` values. Waypoints that don't carry an
  explicit quaternion get a synthesised "look toward the next
  waypoint" pose at build time; the build helper documents
  the convention.
* **Epoch** — linear interpolation in JD. Waypoints without
  an explicit epoch are treated as "carry the previous
  epoch"; if no waypoint carries one, the path is non-temporal.

Determinism: same inputs → byte-identical output. There is no
floating-point timing dependence and no per-frame variability.
v1.4 explicitly does not implement an easing curve catalogue
or a real-time keyframe engine — the path is a parameterised
table the playback module samples.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .mission import Mission, MissionWaypoint

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

#: Quaternion as ``(w, x, y, z)``. UNAV uses w-first to match
#: Cinema 4D's ``c4d.Quaternion`` constructor.
Quaternion = Tuple[float, float, float, float]

#: Identity orientation — no rotation.
IDENTITY_QUAT: Quaternion = (1.0, 0.0, 0.0, 0.0)

#: v1.8 interpolation modes. ``smooth`` is the v1.4 default
#: (Catmull-Rom). ``linear`` swaps in straight-line position
#: interpolation per segment — useful for "constant-velocity
#: between waypoints" cinematics where Catmull-Rom's overshoot
#: at corners is undesirable. The slerp orientation path and
#: the epoch lerp path are unchanged across modes.
INTERP_SMOOTH: str = "smooth"
INTERP_LINEAR: str = "linear"
INTERP_MODES: Tuple[str, ...] = (INTERP_SMOOTH, INTERP_LINEAR)


@dataclass
class CameraSample:
    """One sampled pose along the camera path.

    ``t`` is the path parameter in ``[0.0, 1.0]``. The
    playback module clamps to this range so callers never
    have to worry about extrapolation.
    """

    t: float
    x: float
    y: float
    z: float
    orientation: Quaternion = IDENTITY_QUAT
    epoch_jd: Optional[float] = None
    waypoint_index: int = 0


@dataclass
class CameraPath:
    """A built, evaluable camera path.

    The path is sampled by ``sample(t)`` (parametric ``t`` in
    ``[0, 1]``) or ``sample_at_step(i, total_steps)`` (integer
    step in ``[0, total_steps]``). Both produce a
    ``CameraSample``.

    The path is built by ``build_camera_path(...)`` from a
    mission + a ``CameraPathConfig``; building it directly is
    not supported (the dataclass fields are an implementation
    detail of the sampler).
    """

    positions: List[Tuple[float, float, float]] = field(default_factory=list)
    orientations: List[Quaternion] = field(default_factory=list)
    epochs: List[Optional[float]] = field(default_factory=list)
    durations: List[float] = field(default_factory=list)
    cumulative_normalised: List[float] = field(default_factory=list)
    # v1.8 fields. Defaults preserve the v1.4 behaviour when
    # they aren't populated, so old paths keep working.
    interp_mode: str = INTERP_SMOOTH
    pause_durations: List[float] = field(default_factory=list)  # per-waypoint dwell, seconds
    rolls_deg: List[float] = field(default_factory=list)  # per-waypoint roll, degrees

    # ------------------------------------------------------------- predicates
    def is_empty(self) -> bool:
        return len(self.positions) == 0

    def waypoint_count(self) -> int:
        return len(self.positions)

    def total_duration_seconds(self) -> float:
        return float(sum(self.durations))

    # --------------------------------------------------------------- sampling
    def sample(self, t: float) -> CameraSample:
        """Return the pose at parameter ``t`` (clamped to
        ``[0, 1]``). Empty paths return a zero pose."""
        if self.is_empty():
            return CameraSample(t=0.0, x=0.0, y=0.0, z=0.0)
        t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else float(t)

        n = len(self.positions)
        if n == 1:
            x, y, z = self.positions[0]
            return CameraSample(
                t=t, x=x, y=y, z=z,
                orientation=self.orientations[0],
                epoch_jd=self.epochs[0],
                waypoint_index=0,
            )

        # Locate the segment ``[i, i+1]`` that contains t.
        # cumulative_normalised has n entries and starts at 0.0,
        # ends at 1.0.
        cum = self.cumulative_normalised
        # Linear scan is fine — n is at most MAX_WAYPOINTS_PER_MISSION.
        seg = 0
        for i in range(n - 1):
            if t <= cum[i + 1] + 1e-12:
                seg = i
                break
        else:
            seg = n - 2

        seg_t0 = cum[seg]
        seg_t1 = cum[seg + 1]
        seg_span = max(seg_t1 - seg_t0, 1e-12)
        local = (t - seg_t0) / seg_span
        clamped = max(0.0, min(1.0, local))

        if self.interp_mode == INTERP_LINEAR:
            pos = _linear_segment(self.positions, seg, clamped)
        else:
            pos = _catmull_rom_segment(self.positions, seg, clamped)
        ori = _slerp(
            self.orientations[seg], self.orientations[seg + 1], local,
        )
        # v1.8: roll about the local forward axis (interp linearly
        # between waypoints). Applied as a quaternion composition
        # so the slerp output stays a unit quaternion.
        if self.rolls_deg:
            roll = _interpolate_scalar(
                self.rolls_deg[seg], self.rolls_deg[seg + 1], local,
            )
            if roll:
                ori = _apply_roll(ori, roll)
        ep = _interpolate_epoch(
            self.epochs[seg], self.epochs[seg + 1], local,
        )
        return CameraSample(
            t=t,
            x=pos[0], y=pos[1], z=pos[2],
            orientation=ori,
            epoch_jd=ep,
            waypoint_index=seg,
        )

    def sample_at_step(self, step: int, total_steps: int) -> CameraSample:
        """Convenience: sample uniformly in ``[0, total_steps]``.
        Returns the first/last pose for the boundary cases."""
        if total_steps <= 0:
            return self.sample(0.0)
        step = max(0, min(step, total_steps))
        return self.sample(step / float(total_steps))


# ---------------------------------------------------------------------------
# Path config
# ---------------------------------------------------------------------------


@dataclass
class CameraPathConfig:
    """Knobs the build helper exposes to the dialog.

    * ``speed_multiplier`` scales every waypoint's duration
      uniformly. ``2.0`` halves total runtime; ``0.5`` doubles
      it. Bounded to ``[0.1, 10.0]``.
    * ``include_epoch`` decides whether the path interpolates
      the epoch field. Off → all samples have ``epoch_jd =
      None`` regardless of waypoint epochs.
    * ``orient_toward_next`` decides whether waypoints without
      an explicit ``orientation_quat`` get a synthesised "look
      at next" orientation. Off → such waypoints get the
      identity quaternion.
    * v1.8: ``interp_mode`` selects between Catmull-Rom
      smoothing (``smooth``, the default) and per-segment
      linear interpolation (``linear``).
    * v1.8: ``honour_pause_seconds`` — when True (default),
      ``MissionWaypoint.pause_seconds`` extends the cumulative
      duration so the cursor *dwells* at the waypoint. When
      False, pauses are ignored (the v1.4 behaviour).
    * v1.8: ``honour_look_at`` — when True (default), a
      waypoint's ``look_at_uid`` / ``look_at_position`` is
      honoured (overrides the orient-toward-next default).
    """

    speed_multiplier: float = 1.0
    include_epoch: bool = True
    orient_toward_next: bool = True
    interp_mode: str = INTERP_SMOOTH
    honour_pause_seconds: bool = True
    honour_look_at: bool = True

    def __post_init__(self) -> None:
        if self.speed_multiplier <= 0:
            raise ValueError("speed_multiplier must be > 0")
        if self.speed_multiplier < 0.1:
            self.speed_multiplier = 0.1
        if self.speed_multiplier > 10.0:
            self.speed_multiplier = 10.0
        if self.interp_mode not in INTERP_MODES:
            raise ValueError(
                f"interp_mode must be one of {INTERP_MODES}; "
                f"got {self.interp_mode!r}"
            )


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------


def _resolve_position(wp: MissionWaypoint) -> Optional[Tuple[float, float, float]]:
    if wp.has_c4d_position():
        # v1.9: ``camera_offset`` shifts the camera's sample
        # position away from the waypoint's anchor by a fixed
        # (dx, dy, dz). Useful for "look at Mars from a few
        # units behind" — the navigator still anchors at the
        # waypoint, but the camera path samples the offset.
        x = float(wp.x_c4d)
        y = float(wp.y_c4d)
        z = float(wp.z_c4d)
        if wp.camera_offset is not None:
            x += float(wp.camera_offset[0])
            y += float(wp.camera_offset[1])
            z += float(wp.camera_offset[2])
        return (x, y, z)
    return None


def _orient_toward(
    here: Tuple[float, float, float],
    target: Tuple[float, float, float],
) -> Quaternion:
    """Build a quaternion that rotates +Z onto the unit vector
    from ``here`` to ``target``. Used when a waypoint doesn't
    carry an explicit orientation."""
    dx = target[0] - here[0]
    dy = target[1] - here[1]
    dz = target[2] - here[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-9:
        return IDENTITY_QUAT
    dx /= length
    dy /= length
    dz /= length
    # Quaternion that maps (0,0,1) → (dx,dy,dz).
    # axis = z × dir;  cos(θ) = z · dir = dz.
    cos_theta = dz
    if cos_theta > 0.999_999:
        return IDENTITY_QUAT
    if cos_theta < -0.999_999:
        # 180° flip; pick any axis perpendicular to z.
        return (0.0, 1.0, 0.0, 0.0)
    # axis = (0,0,1) × (dx,dy,dz) = (-dy, dx, 0)
    ax = -dy
    ay = dx
    az = 0.0
    axis_len = math.sqrt(ax * ax + ay * ay)
    if axis_len < 1e-9:
        return IDENTITY_QUAT
    ax /= axis_len
    ay /= axis_len
    half = math.acos(max(-1.0, min(1.0, cos_theta))) * 0.5
    s = math.sin(half)
    return (math.cos(half), ax * s, ay * s, az * s)


def build_camera_path(
    mission: Mission,
    config: Optional[CameraPathConfig] = None,
    *,
    on_unresolved=None,
) -> CameraPath:
    """Build a sampled ``CameraPath`` from a mission.

    ``on_unresolved`` is an optional callback invoked once per
    waypoint whose position cannot be resolved (no c4d coords
    cached). It receives the index + waypoint and the path
    drops the waypoint silently. The dialog uses it to surface
    "X waypoints could not be resolved" to the artist.

    Waypoints without an explicit ``epoch_jd`` inherit the
    previous waypoint's epoch (fall-through). Waypoints
    without an explicit ``orientation_quat`` get a synthesised
    look-toward-next orientation (or the identity, depending
    on ``config.orient_toward_next``).
    """
    cfg = config or CameraPathConfig()
    resolved: List[Tuple[int, MissionWaypoint, Tuple[float, float, float]]] = []
    for idx, wp in enumerate(mission.waypoints):
        # v1.9: annotation waypoints are pure metadata; they
        # never participate in the camera path. They are also
        # not surfaced via ``on_unresolved`` because they have
        # no resolution to attempt.
        if not wp.is_path_contributing():
            continue
        pos = _resolve_position(wp)
        if pos is None:
            if on_unresolved is not None:
                on_unresolved(idx, wp)
            continue
        resolved.append((idx, wp, pos))

    path = CameraPath()
    path.interp_mode = cfg.interp_mode
    if not resolved:
        return path

    # --- Positions / durations / epochs / pauses / rolls ---
    last_epoch: Optional[float] = None
    for _, wp, pos in resolved:
        path.positions.append(pos)
        # v1.8: travel duration + optional dwell pause are summed
        # into the segment duration so the cursor visibly stops at
        # the waypoint. Pauses are *additive* — they don't shorten
        # travel time.
        travel = float(wp.duration_seconds) / float(cfg.speed_multiplier)
        pause = 0.0
        if cfg.honour_pause_seconds and wp.pause_seconds:
            pause = float(wp.pause_seconds) / float(cfg.speed_multiplier)
        path.durations.append(travel + pause)
        path.pause_durations.append(pause)
        path.rolls_deg.append(float(wp.roll_deg or 0.0))
        if cfg.include_epoch and wp.epoch_jd is not None:
            last_epoch = float(wp.epoch_jd)
        path.epochs.append(last_epoch if cfg.include_epoch else None)

    # --- Cumulative normalised ---
    total = sum(path.durations)
    if total <= 0:
        # Should not happen — durations are validated > 0 in
        # MissionWaypoint — but stay defensive.
        path.cumulative_normalised = [
            i / max(len(path.positions) - 1, 1)
            for i in range(len(path.positions))
        ]
    else:
        running = 0.0
        cum = [0.0]
        for d in path.durations[1:]:
            running += d
            cum.append(running / total)
        # The last entry must be exactly 1.0 (avoid float drift).
        cum[-1] = 1.0
        path.cumulative_normalised = cum

    # --- Orientations ---
    for i, (_, wp, pos) in enumerate(resolved):
        # 1. Explicit quaternion always wins.
        if wp.orientation_quat is not None:
            path.orientations.append(_normalise_quat(wp.orientation_quat))
            continue
        # 2. v1.8: explicit look-at target wins over orient-toward-next.
        look_target = None
        if cfg.honour_look_at and wp.look_at_position is not None:
            look_target = (
                float(wp.look_at_position[0]),
                float(wp.look_at_position[1]),
                float(wp.look_at_position[2]),
            )
        if look_target is not None:
            path.orientations.append(_orient_toward(pos, look_target))
            continue
        # 3. Fall back to orient-toward-next (the v1.4 behaviour).
        if cfg.orient_toward_next and i < len(resolved) - 1:
            target_pos = resolved[i + 1][2]
            path.orientations.append(_orient_toward(pos, target_pos))
        elif cfg.orient_toward_next and i > 0 and len(resolved) >= 2:
            # Last waypoint inherits the previous orientation.
            path.orientations.append(path.orientations[-1])
        else:
            path.orientations.append(IDENTITY_QUAT)

    return path


def build_route_from_mission(mission: Mission):
    """Convert a mission into a v0.6 ``Route`` (so the
    existing route-spline rendering path can draw a preview).
    Mission waypoints without a cached position are silently
    dropped — exactly the same convention ``build_camera_path``
    uses."""
    from core.route import Route, Waypoint

    route = Route(name=mission.title or "Mission")
    for wp in mission.waypoints:
        if not wp.has_c4d_position():
            continue
        if wp.kind in ("object", "named"):
            try:
                route.add(Waypoint(
                    kind="object" if wp.kind == "object" else "named",
                    label=wp.display_label(),
                    uid=wp.uid,
                    catalog_source=wp.catalog_source,
                    object_type=wp.object_type,
                    x_c4d=wp.x_c4d, y_c4d=wp.y_c4d, z_c4d=wp.z_c4d,
                    x_pc=wp.x_pc, y_pc=wp.y_pc, z_pc=wp.z_pc,
                ))
            except ValueError:
                continue
        elif wp.kind in ("coordinate", "bookmark"):
            try:
                route.add(Waypoint(
                    kind="coordinate",
                    label=wp.display_label(),
                    x_c4d=wp.x_c4d, y_c4d=wp.y_c4d, z_c4d=wp.z_c4d,
                    x_pc=wp.x_pc, y_pc=wp.y_pc, z_pc=wp.z_pc,
                ))
            except ValueError:
                continue
    return route


# ---------------------------------------------------------------------------
# Math helpers — Catmull-Rom + slerp + epoch lerp
# ---------------------------------------------------------------------------


def _linear_segment(
    pts: Sequence[Tuple[float, float, float]],
    seg: int,
    t: float,
) -> Tuple[float, float, float]:
    """v1.8 ``INTERP_LINEAR`` evaluator. Straight line between
    ``pts[seg]`` and ``pts[seg+1]`` at parameter ``t`` in
    ``[0, 1]``. Used when the artist wants constant-velocity
    travel between waypoints with no Catmull-Rom overshoot."""
    p1 = pts[seg]
    p2 = pts[min(seg + 1, len(pts) - 1)]
    return (
        p1[0] + (p2[0] - p1[0]) * t,
        p1[1] + (p2[1] - p1[1]) * t,
        p1[2] + (p2[2] - p1[2]) * t,
    )


def _interpolate_scalar(a: float, b: float, t: float) -> float:
    """Linear lerp between two floats. v1.8 helper for the
    per-waypoint roll channel."""
    return float(a) + (float(b) - float(a)) * float(t)


def _apply_roll(q: Quaternion, roll_deg: float) -> Quaternion:
    """Compose ``q`` with a roll rotation about the camera's
    local forward axis (the body-frame +Z used by every
    orientation in the camera path). v1.8 helper."""
    if not roll_deg:
        return q
    half = math.radians(roll_deg) * 0.5
    s = math.sin(half)
    c = math.cos(half)
    # Roll quat about local +Z, in body frame.
    rq = (c, 0.0, 0.0, s)
    return _quat_multiply(q, rq)


def _quat_multiply(a: Quaternion, b: Quaternion) -> Quaternion:
    """Hamilton product of two unit quaternions. ``(w, x, y, z)``
    convention."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def _catmull_rom_segment(
    pts: Sequence[Tuple[float, float, float]],
    seg: int,
    t: float,
) -> Tuple[float, float, float]:
    """Evaluate a centripetal-feeling Catmull-Rom segment at
    parameter ``t`` in ``[0, 1]``. The endpoints are mirrored so
    the curve passes through ``pts[seg]`` and ``pts[seg+1]``
    exactly."""
    n = len(pts)
    p0 = pts[max(seg - 1, 0)]
    p1 = pts[seg]
    p2 = pts[min(seg + 1, n - 1)]
    p3 = pts[min(seg + 2, n - 1)]
    t2 = t * t
    t3 = t2 * t
    out = []
    for k in range(3):
        a = -0.5 * p0[k] + 1.5 * p1[k] - 1.5 * p2[k] + 0.5 * p3[k]
        b = p0[k] - 2.5 * p1[k] + 2.0 * p2[k] - 0.5 * p3[k]
        c = -0.5 * p0[k] + 0.5 * p2[k]
        d = p1[k]
        out.append(a * t3 + b * t2 + c * t + d)
    return (out[0], out[1], out[2])


def _normalise_quat(q: Quaternion) -> Quaternion:
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n < 1e-12:
        return IDENTITY_QUAT
    return (w / n, x / n, y / n, z / n)


def _slerp(a: Quaternion, b: Quaternion, t: float) -> Quaternion:
    """Spherical linear interpolation between two unit quats."""
    a = _normalise_quat(a)
    b = _normalise_quat(b)
    dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
    if dot < 0.0:
        b = (-b[0], -b[1], -b[2], -b[3])
        dot = -dot
    if dot > 0.9995:
        # Quats are very close; lerp + renormalise.
        out = (
            a[0] + t * (b[0] - a[0]),
            a[1] + t * (b[1] - a[1]),
            a[2] + t * (b[2] - a[2]),
            a[3] + t * (b[3] - a[3]),
        )
        return _normalise_quat(out)
    theta_0 = math.acos(max(-1.0, min(1.0, dot)))
    theta = theta_0 * t
    sin_theta_0 = math.sin(theta_0)
    s_a = math.sin(theta_0 - theta) / sin_theta_0
    s_b = math.sin(theta) / sin_theta_0
    return (
        a[0] * s_a + b[0] * s_b,
        a[1] * s_a + b[1] * s_b,
        a[2] * s_a + b[2] * s_b,
        a[3] * s_a + b[3] * s_b,
    )


def _interpolate_epoch(
    a: Optional[float], b: Optional[float], t: float,
) -> Optional[float]:
    """Linear interpolation between two optional JD floats. The
    result is ``None`` only when both endpoints are ``None``;
    otherwise the missing endpoint is treated as equal to the
    populated one."""
    if a is None and b is None:
        return None
    if a is None:
        return float(b)
    if b is None:
        return float(a)
    return float(a) + (float(b) - float(a)) * float(t)


# ---------------------------------------------------------------------------
# v1.8: tessellation + C4D preview spline
# ---------------------------------------------------------------------------


def tessellate_path(
    path: CameraPath,
    *,
    samples_per_segment: int = 16,
) -> List[Tuple[float, float, float]]:
    """Sample the camera path into a list of (x, y, z) points
    suitable for a Cinema 4D ``SplineObject``.

    For ``INTERP_LINEAR`` paths this returns each waypoint
    plus interior points along the straight segments; for
    ``INTERP_SMOOTH`` paths it tessellates the Catmull-Rom
    curve at ``samples_per_segment`` points per segment so the
    preview spline visibly follows the cinematic curve. Empty
    paths return an empty list.

    The returned list is a *visual approximation* — it is
    suitable for the path-preview spline the dialog shows the
    artist before Bake. It is **not** the data the playback
    engine uses; that path samples the analytic curve directly.
    """
    if path.is_empty():
        return []
    if path.waypoint_count() == 1:
        return [path.positions[0]]

    samples_per_segment = max(2, int(samples_per_segment))
    out: List[Tuple[float, float, float]] = []
    n = path.waypoint_count()
    cum = path.cumulative_normalised
    for seg in range(n - 1):
        for j in range(samples_per_segment):
            local = j / float(samples_per_segment)
            t = cum[seg] + (cum[seg + 1] - cum[seg]) * local
            sample = path.sample(t)
            out.append((sample.x, sample.y, sample.z))
    # Always include the final endpoint exactly.
    last = path.sample(1.0)
    out.append((last.x, last.y, last.z))
    return out


#: Default name for the C4D preview spline the dialog drops
#: into the active document. Pinning the name (instead of
#: keying off a marker container) keeps the helper trivially
#: identifiable in the OM and lets the artist find / delete
#: it manually if anything goes wrong.
PREVIEW_SPLINE_NAME: str = "UNAV_Mission_Preview"


def build_preview_spline_data(
    path: CameraPath,
    *,
    samples_per_segment: int = 16,
) -> List[Tuple[float, float, float]]:
    """Wrapper for the dialog's "Preview Path" button. Returns
    the list of (x, y, z) points the dialog passes to its
    Cinema 4D builder. The c4d-bound ``apply_preview_spline``
    helper in ``c4d_objects/path_preview.py`` (when present)
    consumes this list.

    Kept separate from ``tessellate_path`` to give a stable
    callsite for the v1.8 dialog wiring even if the
    tessellation algorithm is replaced later."""
    return tessellate_path(path, samples_per_segment=samples_per_segment)
