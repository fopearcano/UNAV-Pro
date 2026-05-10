"""v3.6 cinematic route beautification.

Pure-Python helpers that take a v1.4 ``Mission`` (or
v0.6 ``Route``) and return **a new** route / mission
with the path smoothed for a more cinematic camera
glide.

Two algorithms:

* **Chaikin smoothing** — corner cutting; each
  iteration replaces every interior point with two
  fractional cuts (typically at the 1/4 + 3/4
  points). Converges to a B-spline-like curve.
* **Gaussian-window averaging** — each interior
  point is replaced with a weighted average of its
  ``window`` neighbours. Lighter touch than Chaikin;
  preserves the gross shape.

Both algorithms **preserve the original mission
data** — they return new ``Route`` / ``Mission``
instances and never mutate the input. Pure stdlib;
no Cinema 4D, no NumPy.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional, Sequence, Tuple


Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Smoothing modes
# ---------------------------------------------------------------------------


class SmoothingMode(str, Enum):
    """Two cinematic-friendly smoothing algorithms."""

    NONE = "none"
    CHAIKIN = "chaikin"
    GAUSSIAN = "gaussian"


SMOOTHING_MODES = tuple(SmoothingMode)


@dataclass(frozen=True)
class SmoothingParameters:
    """Tunables for the smoothing algorithms.

    * ``iterations`` — number of Chaikin passes
      (each doubles the polyline density).
    * ``cut_ratio`` — Chaikin cut ratio in
      ``(0, 0.5)``; the classical value is 0.25.
    * ``window`` — Gaussian window radius in
      vertices (1 ⇒ 3-tap; 2 ⇒ 5-tap).
    * ``sigma`` — Gaussian σ; controls the
      smoothness vs. fidelity trade-off.
    * ``tension`` — placeholder for future spline
      tension control. v3.6 stores it on the result
      so a future Catmull-Rom integration can read
      it without a schema bump.
    """

    iterations: int = 2
    cut_ratio: float = 0.25
    window: int = 1
    sigma: float = 0.7
    tension: float = 0.5

    def __post_init__(self) -> None:
        if self.iterations < 0:
            raise ValueError("iterations must be >= 0")
        if not 0.0 < self.cut_ratio < 0.5:
            raise ValueError(
                "cut_ratio must be in (0, 0.5); 0.25 is classical"
            )
        if self.window < 0:
            raise ValueError("window must be >= 0")
        if self.sigma <= 0:
            raise ValueError("sigma must be > 0")
        if not 0.0 <= self.tension <= 1.0:
            raise ValueError("tension must be in [0, 1]")


# ---------------------------------------------------------------------------
# Chaikin smoothing
# ---------------------------------------------------------------------------


def chaikin_smooth(
    points: Sequence[Vec3],
    *,
    iterations: int = 2,
    cut_ratio: float = 0.25,
) -> List[Vec3]:
    """Apply ``iterations`` rounds of Chaikin corner
    cutting to ``points``.

    With < 3 points the polyline is too short to
    smooth — returned verbatim.
    Endpoints are preserved (the smoothing only
    cuts interior corners) so the route still
    starts + ends at the original waypoints.
    """
    if iterations <= 0 or len(points) < 3:
        return [tuple(p) for p in points]
    if not 0.0 < cut_ratio < 0.5:
        raise ValueError(
            "cut_ratio must be in (0, 0.5); 0.25 is classical"
        )
    pts: List[Vec3] = [tuple(p) for p in points]
    for _ in range(iterations):
        new_pts: List[Vec3] = [pts[0]]
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            q = (
                a[0] + cut_ratio * (b[0] - a[0]),
                a[1] + cut_ratio * (b[1] - a[1]),
                a[2] + cut_ratio * (b[2] - a[2]),
            )
            r = (
                a[0] + (1.0 - cut_ratio) * (b[0] - a[0]),
                a[1] + (1.0 - cut_ratio) * (b[1] - a[1]),
                a[2] + (1.0 - cut_ratio) * (b[2] - a[2]),
            )
            # Keep both Q and R; this doubles the
            # polyline density. The endpoints survive
            # because the loop appends pts[0] +
            # pts[-1] outside.
            new_pts.append(q)
            new_pts.append(r)
        new_pts.append(pts[-1])
        pts = new_pts
    return pts


# ---------------------------------------------------------------------------
# Gaussian-window smoothing
# ---------------------------------------------------------------------------


def gaussian_smooth(
    points: Sequence[Vec3],
    *,
    window: int = 1,
    sigma: float = 0.7,
) -> List[Vec3]:
    """Replace each interior vertex with a weighted
    average of its ``window`` neighbours on each
    side. Endpoints are preserved.

    For ``window = 1, sigma = 0.7`` this is a tight
    3-tap blur — perfect for taking the edge off a
    short sharp corner without changing the route's
    shape.
    """
    if len(points) < 3 or window <= 0:
        return [tuple(p) for p in points]
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    pts: List[Vec3] = [tuple(p) for p in points]
    out: List[Vec3] = [pts[0]]
    weights = []
    for k in range(-window, window + 1):
        weights.append(math.exp(-(k * k) / (2.0 * sigma * sigma)))
    weight_sum = sum(weights)
    for i in range(1, len(pts) - 1):
        sx = sy = sz = 0.0
        for k, w in zip(range(-window, window + 1), weights):
            j = i + k
            if j < 0:
                j = 0
            elif j >= len(pts):
                j = len(pts) - 1
            sx += w * pts[j][0]
            sy += w * pts[j][1]
            sz += w * pts[j][2]
        out.append((sx / weight_sum, sy / weight_sum, sz / weight_sum))
    out.append(pts[-1])
    return out


# ---------------------------------------------------------------------------
# Cinematic interpolation between waypoints
# ---------------------------------------------------------------------------


def interpolate_waypoints(
    points: Sequence[Vec3],
    *,
    samples_per_segment: int = 8,
) -> List[Vec3]:
    """Densify ``points`` by inserting
    ``samples_per_segment`` linearly-spaced points
    between each consecutive pair. Pure helper used
    before Chaikin / Gaussian smoothing on a route
    with very few waypoints.

    Endpoints are preserved; each interior original
    waypoint appears exactly once in the output.
    """
    if samples_per_segment <= 1 or len(points) < 2:
        return [tuple(p) for p in points]
    out: List[Vec3] = [tuple(points[0])]
    for i in range(len(points) - 1):
        a = points[i]
        b = points[i + 1]
        for k in range(1, samples_per_segment):
            t = k / float(samples_per_segment)
            out.append((
                a[0] + t * (b[0] - a[0]),
                a[1] + t * (b[1] - a[1]),
                a[2] + t * (b[2] - a[2]),
            ))
        out.append(tuple(b))
    return out


# ---------------------------------------------------------------------------
# Beautification report
# ---------------------------------------------------------------------------


@dataclass
class BeautificationReport:
    """Pure-data outcome of one beautification pass."""

    mode: SmoothingMode
    input_point_count: int
    output_point_count: int
    parameters: SmoothingParameters
    points: List[Vec3] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def short_summary(self) -> str:
        return (
            f"beautify[{self.mode.value}]: "
            f"{self.input_point_count} → {self.output_point_count} "
            f"point(s)"
        )


def beautify_polyline(
    points: Sequence[Vec3],
    *,
    mode: SmoothingMode = SmoothingMode.CHAIKIN,
    parameters: Optional[SmoothingParameters] = None,
    densify_segments: int = 0,
) -> BeautificationReport:
    """Top-level entry: densify (optionally), then
    apply the chosen smoothing mode.

    ``densify_segments > 0`` runs ``interpolate_waypoints``
    first, which is useful when the input is just a
    handful of waypoints and Chaikin would otherwise
    have too little to smooth.
    """
    params = parameters or SmoothingParameters()
    src = list(points)
    work = src
    if densify_segments > 1:
        work = interpolate_waypoints(
            work, samples_per_segment=densify_segments,
        )
    if mode is SmoothingMode.NONE:
        out = [tuple(p) for p in work]
    elif mode is SmoothingMode.CHAIKIN:
        out = chaikin_smooth(
            work,
            iterations=params.iterations,
            cut_ratio=params.cut_ratio,
        )
    elif mode is SmoothingMode.GAUSSIAN:
        out = gaussian_smooth(
            work,
            window=params.window,
            sigma=params.sigma,
        )
    else:  # pragma: no cover — defensive
        raise ValueError(f"unknown smoothing mode: {mode!r}")
    rep = BeautificationReport(
        mode=mode,
        input_point_count=len(src),
        output_point_count=len(out),
        parameters=params,
        points=list(out),
    )
    if densify_segments > 1:
        rep.notes.append(
            f"densified {len(src)} → {len(work)} before smoothing"
        )
    return rep


# ---------------------------------------------------------------------------
# Mission / Route facades
# ---------------------------------------------------------------------------


def beautify_mission_path(
    mission,
    *,
    mode: SmoothingMode = SmoothingMode.CHAIKIN,
    parameters: Optional[SmoothingParameters] = None,
    densify_segments: int = 0,
) -> BeautificationReport:
    """Run the smoother over the C4D-coordinate
    waypoints inside a v1.4 ``Mission``.

    The original mission is **not** mutated. The
    report's ``points`` field carries the smoothed
    polyline; the caller decides what to do with it
    (drop a preview spline, hand to the bake helper,
    etc.).
    """
    points: List[Vec3] = []
    for wp in getattr(mission, "waypoints", ()) or ():
        x = getattr(wp, "x_c4d", None)
        y = getattr(wp, "y_c4d", None)
        z = getattr(wp, "z_c4d", None)
        if x is None or y is None or z is None:
            continue
        points.append((float(x), float(y), float(z)))
    return beautify_polyline(
        points,
        mode=mode,
        parameters=parameters,
        densify_segments=densify_segments,
    )


def beautify_route_path(
    route,
    *,
    mode: SmoothingMode = SmoothingMode.CHAIKIN,
    parameters: Optional[SmoothingParameters] = None,
    densify_segments: int = 0,
) -> BeautificationReport:
    """Same shape as :func:`beautify_mission_path` but
    for v0.6 ``Route`` objects."""
    points: List[Vec3] = []
    for wp in getattr(route, "waypoints", ()) or ():
        x = getattr(wp, "x_c4d", None)
        y = getattr(wp, "y_c4d", None)
        z = getattr(wp, "z_c4d", None)
        if x is None or y is None or z is None:
            continue
        points.append((float(x), float(y), float(z)))
    return beautify_polyline(
        points,
        mode=mode,
        parameters=parameters,
        densify_segments=densify_segments,
    )


# ---------------------------------------------------------------------------
# Sharp-angle detection
# ---------------------------------------------------------------------------


def detect_sharp_angles(
    points: Sequence[Vec3],
    *,
    angle_threshold_deg: float = 60.0,
) -> List[int]:
    """Return the indices of interior points whose
    interior angle is **sharper** than
    ``angle_threshold_deg`` (i.e. the camera would
    "elbow" through them).

    Pure helper; useful for the cinematic panel's
    *Apply Cinematic Smoothing* button to highlight
    which corners would benefit from smoothing.
    """
    if len(points) < 3:
        return []
    out: List[int] = []
    cos_threshold = math.cos(math.radians(angle_threshold_deg))
    for i in range(1, len(points) - 1):
        a = points[i - 1]
        b = points[i]
        c = points[i + 1]
        ax, ay, az = a[0] - b[0], a[1] - b[1], a[2] - b[2]
        cx, cy, cz = c[0] - b[0], c[1] - b[1], c[2] - b[2]
        an = math.sqrt(ax * ax + ay * ay + az * az)
        cn = math.sqrt(cx * cx + cy * cy + cz * cz)
        if an == 0.0 or cn == 0.0:
            continue
        cos_angle = (ax * cx + ay * cy + az * cz) / (an * cn)
        # Interior angle = π − angle between the edge
        # vectors. A sharp interior angle means the
        # edges form a wide angle when seen from b's
        # side, i.e. cos(edges) > -cos(threshold).
        if cos_angle > -cos_threshold:
            out.append(i)
    return out
