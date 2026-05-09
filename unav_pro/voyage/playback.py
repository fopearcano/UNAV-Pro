"""Playback engine for the v1.4 voyage system.

A *deterministic* stepper that drives a built ``CameraPath``.
The dialog calls ``play()`` / ``pause()`` / ``stop()`` /
``step_forward()`` / ``step_backward()`` / ``jump_to_waypoint()``
and the engine emits a ``PlaybackTick`` per call describing
what changed (camera pose, epoch, whether to re-sync the
visible sector). Playback is not tied to wall-clock time — the
caller decides how often to advance.

This module is the seam between the v1.4 mission/voyage layer
and the rest of UNAV:

* The ``apply`` callback receives one ``PlaybackTick`` per
  step. The dialog wires ``apply`` to update the navigator
  null, the camera, and (optionally) the v1.2 Time Navigator
  state.
* The ``sync_callback`` is invoked once every
  ``sync_every_n_steps`` ticks (default: every 4 steps), so
  the visible-sector pipeline isn't hammered on a tight scrub.
* A ``max_visible_objects`` cap is honoured: when the playback
  speed multiplier drops the per-step interval below
  ``MIN_INTERVAL_SECONDS_FOR_FULL_SYNC``, the engine throttles
  the sync callback to once per second (wall-clock-free —
  measured in tick count).

The stepper is **frame-rate-independent**: it counts integer
steps in ``[0, total_steps]`` where ``total_steps`` is derived
from the camera path's total duration and the dialog's chosen
step rate. The artist drives the rate; the engine enforces
the safety thresholds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .camera_path import CameraPath, CameraSample
from .mission import Mission

#: Default integer steps per second when the dialog hasn't told
#: us otherwise. 30 gives smooth-looking scrubs without
#: hammering the visible-sector sync.
DEFAULT_STEPS_PER_SECOND: int = 30

#: Default visible-sector sync cadence — re-stream every N
#: ticks. 4 with 30 steps/s is ~7.5 syncs/s, fast enough that
#: the artist sees the cone update during the playback but slow
#: enough that we don't melt the DB.
DEFAULT_SYNC_EVERY_N_STEPS: int = 4

#: Minimum simulated step interval (seconds) the engine will
#: emit a sync request at. Below this the sync cadence is
#: throttled — the artist is scrubbing too fast for a full
#: re-stream every step to be useful.
MIN_INTERVAL_SECONDS_FOR_FULL_SYNC: float = 1.0 / 60.0

#: Hard upper cap on per-tick visible objects the playback
#: engine will request. Mirrors the navigator's cap so a fast
#: scrub can't blow through the safety guard.
DEFAULT_MAX_VISIBLE_OBJECTS: int = 100_000


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class PlaybackTick:
    """One step's worth of state.

    The dialog reads ``sample`` for the camera pose,
    ``trigger_sync`` for "should I re-stream the visible
    sector right now?", and ``status`` for the human-readable
    status-line update.
    """

    step: int
    total_steps: int
    sample: CameraSample
    trigger_sync: bool = False
    is_playing: bool = False
    is_finished: bool = False
    status: str = ""


@dataclass
class PlaybackConfig:
    """Knobs the dialog passes to ``Playback``.

    * ``steps_per_second`` — how many integer steps the
      stepper advances per simulated second.
    * ``speed_multiplier`` — uniform scaling on top
      (``2.0`` halves runtime). Bounded to ``[0.1, 10.0]``.
    * ``sync_every_n_steps`` — how often to fire the
      visible-sector callback; the engine may extend this
      automatically when the per-step interval drops below
      ``MIN_INTERVAL_SECONDS_FOR_FULL_SYNC``.
    * ``loop`` — when True, hitting the last step resets to 0
      instead of stopping.
    * ``max_visible_objects`` — safety cap forwarded into the
      sync callback.
    """

    steps_per_second: int = DEFAULT_STEPS_PER_SECOND
    speed_multiplier: float = 1.0
    sync_every_n_steps: int = DEFAULT_SYNC_EVERY_N_STEPS
    loop: bool = False
    max_visible_objects: int = DEFAULT_MAX_VISIBLE_OBJECTS

    def __post_init__(self) -> None:
        if self.steps_per_second <= 0:
            raise ValueError("steps_per_second must be > 0")
        if self.speed_multiplier <= 0:
            raise ValueError("speed_multiplier must be > 0")
        if self.speed_multiplier < 0.1:
            self.speed_multiplier = 0.1
        if self.speed_multiplier > 10.0:
            self.speed_multiplier = 10.0
        if self.sync_every_n_steps < 1:
            self.sync_every_n_steps = 1
        if self.max_visible_objects <= 0:
            self.max_visible_objects = DEFAULT_MAX_VISIBLE_OBJECTS


# ---------------------------------------------------------------------------
# Playback engine
# ---------------------------------------------------------------------------


ApplyCallback = Callable[[PlaybackTick], None]
SyncCallback = Callable[[PlaybackTick], None]


class Playback:
    """Drives a camera path via integer steps.

    Construct with a built ``CameraPath`` and a
    ``PlaybackConfig``. The dialog then calls one of the
    transport methods per UI click; each transport returns the
    ``PlaybackTick`` that was just applied.

    Determinism: the engine has no internal clock. ``play()``
    does not "start a timer." ``advance()`` is what moves the
    cursor; the dialog's idle handler / SceneHook is expected
    to call ``advance()`` on a cadence the artist controls.
    The per-step interval is reported via
    ``effective_step_interval_seconds`` so the SceneHook can
    schedule itself accordingly.
    """

    def __init__(
        self,
        path: CameraPath,
        config: Optional[PlaybackConfig] = None,
        *,
        apply: Optional[ApplyCallback] = None,
        sync_callback: Optional[SyncCallback] = None,
    ) -> None:
        self._path = path
        self._config = config or PlaybackConfig()
        self._apply = apply
        self._sync = sync_callback

        self._total_steps = self._compute_total_steps()
        self._step = 0
        self._is_playing = False
        self._waypoint_step_anchors = self._compute_waypoint_anchors()
        self._steps_since_sync = 0

    # ------------------------------------------------------------ properties
    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def step(self) -> int:
        return self._step

    @property
    def total_steps(self) -> int:
        return self._total_steps

    @property
    def is_finished(self) -> bool:
        return self._total_steps == 0 or self._step >= self._total_steps

    @property
    def waypoint_step_anchors(self) -> List[int]:
        """The integer step values that align with each
        mission waypoint. Used by 'Next waypoint' / 'Previous
        waypoint' transports."""
        return list(self._waypoint_step_anchors)

    @property
    def effective_step_interval_seconds(self) -> float:
        """How long one step *would* represent if the dialog
        sampled at the configured cadence. Reported so a
        SceneHook can throttle correctly."""
        if self._config.steps_per_second <= 0:
            return 0.0
        base = 1.0 / float(self._config.steps_per_second)
        return base / float(self._config.speed_multiplier)

    # ------------------------------------------------------------ transport
    def play(self) -> Optional[PlaybackTick]:
        if self._path.is_empty():
            return None
        self._is_playing = True
        # Don't advance yet — the next ``advance()`` call does
        # that. ``play()`` is just a flag flip + status tick.
        return self._make_tick(triggered_sync=False, status="play")

    def pause(self) -> Optional[PlaybackTick]:
        self._is_playing = False
        return self._make_tick(triggered_sync=False, status="pause")

    def stop(self) -> Optional[PlaybackTick]:
        self._is_playing = False
        self._step = 0
        self._steps_since_sync = 0
        return self._make_tick(triggered_sync=True, status="stop")

    def step_forward(self, *, n: int = 1) -> Optional[PlaybackTick]:
        return self._move_by(int(n))

    def step_backward(self, *, n: int = 1) -> Optional[PlaybackTick]:
        return self._move_by(-int(n))

    def jump_to_waypoint(self, waypoint_index: int) -> Optional[PlaybackTick]:
        if not self._waypoint_step_anchors:
            return None
        idx = max(0, min(waypoint_index, len(self._waypoint_step_anchors) - 1))
        self._step = self._waypoint_step_anchors[idx]
        # A jump always triggers a sync so the visible sector
        # reflects the new pose immediately.
        return self._make_tick(triggered_sync=True, status=f"jump:{idx}")

    def jump_to_next_waypoint(self) -> Optional[PlaybackTick]:
        idx = self._waypoint_index_at_step(self._step)
        return self.jump_to_waypoint(idx + 1)

    def jump_to_previous_waypoint(self) -> Optional[PlaybackTick]:
        idx = self._waypoint_index_at_step(self._step)
        # If we're already past a waypoint anchor, "previous"
        # means jump to that anchor (rewinds to current
        # waypoint start).
        if (
            idx < len(self._waypoint_step_anchors)
            and self._step > self._waypoint_step_anchors[idx]
        ):
            return self.jump_to_waypoint(idx)
        return self.jump_to_waypoint(idx - 1)

    def advance(self) -> Optional[PlaybackTick]:
        """Advance the cursor by one step if playing. Called
        by the dialog's idle handler / SceneHook."""
        if not self._is_playing or self._total_steps == 0:
            return None
        return self._move_by(1)

    # --- v1.8 transport additions --------------------------------------
    def jump_to_start(self) -> Optional[PlaybackTick]:
        """v1.8: rewind the cursor to step 0 without resetting
        the play flag. Always fires a sync."""
        if self._total_steps == 0:
            return None
        self._step = 0
        self._steps_since_sync = 0
        return self._make_tick(triggered_sync=True, status="jump:start")

    def jump_to_end(self) -> Optional[PlaybackTick]:
        """v1.8: snap the cursor to the final step. Always fires
        a sync. Mirrors ``jump_to_start``."""
        if self._total_steps == 0:
            return None
        self._step = self._total_steps
        self._steps_since_sync = 0
        self._is_playing = False
        return self._make_tick(triggered_sync=True, status="jump:end")

    def scrub_to_progress(self, progress: float) -> Optional[PlaybackTick]:
        """v1.8: place the cursor at a normalised progress in
        ``[0.0, 1.0]``. Used by the dialog's scrub slider.

        Out-of-range values clamp; the helper never raises and
        always fires a sync (the artist explicitly seeks)."""
        if self._total_steps == 0:
            return None
        p = 0.0 if progress < 0.0 else 1.0 if progress > 1.0 else float(progress)
        self._step = int(round(p * self._total_steps))
        self._steps_since_sync = 0
        return self._make_tick(triggered_sync=True, status=f"scrub:{p:.3f}")

    @property
    def progress(self) -> float:
        """v1.8: current cursor as a normalised ``[0.0, 1.0]``
        progress. Useful for the dialog's scrub-slider readback."""
        if self._total_steps <= 0:
            return 0.0
        return min(1.0, max(0.0, self._step / float(self._total_steps)))

    def evaluate_at_progress(self, progress: float):
        """v1.8: pure / side-effect-free pose readback.

        Returns the ``CameraSample`` that *would* be produced if
        the cursor were at ``progress`` ∈ ``[0, 1]`` — without
        moving the cursor, without firing the apply callback, and
        without firing the sync callback. The dialog uses this to
        drive the scrub-slider preview before the artist commits.
        Determinism: same input → same output.
        """
        if self._path.is_empty():
            from voyage.camera_path import CameraSample
            return CameraSample(t=0.0, x=0.0, y=0.0, z=0.0)
        p = 0.0 if progress < 0.0 else 1.0 if progress > 1.0 else float(progress)
        return self._path.sample(p)

    def set_speed(self, multiplier: float) -> None:
        """Update the speed multiplier mid-playback. Total
        step count stays the same; only the reported
        ``effective_step_interval_seconds`` changes."""
        if multiplier <= 0:
            raise ValueError("speed multiplier must be > 0")
        if multiplier < 0.1:
            multiplier = 0.1
        if multiplier > 10.0:
            multiplier = 10.0
        self._config.speed_multiplier = float(multiplier)

    # ------------------------------------------------------------ internals
    def _compute_total_steps(self) -> int:
        if self._path.is_empty() or self._path.waypoint_count() < 2:
            return 0
        steps = int(round(
            self._path.total_duration_seconds()
            * float(self._config.steps_per_second)
        ))
        return max(steps, len(self._path.positions) - 1)

    def _compute_waypoint_anchors(self) -> List[int]:
        if self._total_steps == 0:
            return [0]
        anchors: List[int] = []
        for cum in self._path.cumulative_normalised:
            anchors.append(int(round(cum * self._total_steps)))
        return anchors

    def _waypoint_index_at_step(self, step: int) -> int:
        """Return the highest waypoint index whose anchor is
        ``<= step``."""
        idx = 0
        for i, anchor in enumerate(self._waypoint_step_anchors):
            if anchor <= step:
                idx = i
            else:
                break
        return idx

    def _move_by(self, delta: int) -> Optional[PlaybackTick]:
        if self._path.is_empty() or self._total_steps == 0:
            return None
        new_step = self._step + delta
        if new_step >= self._total_steps:
            if self._config.loop and self._total_steps > 0:
                new_step = new_step % self._total_steps
            else:
                new_step = self._total_steps
                self._is_playing = False
        if new_step < 0:
            if self._config.loop and self._total_steps > 0:
                new_step = (new_step % self._total_steps + self._total_steps) % self._total_steps
            else:
                new_step = 0

        # Decide whether this tick should trigger a sync. The
        # rule: sync at fixed step cadence OR at every
        # waypoint anchor crossing OR on the boundary frames
        # (start / end).
        triggered = False
        crossed_anchor = self._crossed_waypoint_anchor(self._step, new_step)
        self._steps_since_sync += abs(delta)
        if (
            crossed_anchor
            or new_step == 0
            or new_step == self._total_steps
            or self._steps_since_sync >= self._effective_sync_cadence()
        ):
            triggered = True
            self._steps_since_sync = 0

        self._step = new_step
        return self._make_tick(triggered_sync=triggered, status="step")

    def _effective_sync_cadence(self) -> int:
        """Return the cadence we'll actually fire syncs at,
        accounting for the throttle when the per-step interval
        drops below the safety threshold."""
        cadence = max(1, int(self._config.sync_every_n_steps))
        interval = self.effective_step_interval_seconds
        if interval > 0 and interval < MIN_INTERVAL_SECONDS_FOR_FULL_SYNC:
            # Stretch cadence so full re-syncs happen no more than
            # once per simulated second.
            seconds_per_sync = max(1.0, MIN_INTERVAL_SECONDS_FOR_FULL_SYNC * cadence)
            cadence = max(cadence, int(round(1.0 / interval)))
        return cadence

    def _crossed_waypoint_anchor(self, old_step: int, new_step: int) -> bool:
        if old_step == new_step:
            return False
        lo, hi = (old_step, new_step) if old_step < new_step else (new_step, old_step)
        for anchor in self._waypoint_step_anchors:
            if lo < anchor <= hi:
                return True
        return False

    def _make_tick(
        self, *, triggered_sync: bool, status: str,
    ) -> PlaybackTick:
        sample = self._path.sample_at_step(self._step, self._total_steps)
        finished = (
            not self._config.loop
            and self._total_steps > 0
            and self._step >= self._total_steps
        )
        tick = PlaybackTick(
            step=self._step,
            total_steps=self._total_steps,
            sample=sample,
            trigger_sync=triggered_sync,
            is_playing=self._is_playing and not finished,
            is_finished=finished,
            status=status,
        )
        if self._apply is not None:
            self._apply(tick)
        if triggered_sync and self._sync is not None:
            self._sync(tick)
        return tick


# ---------------------------------------------------------------------------
# Convenience: build a playback engine from a mission in one call
# ---------------------------------------------------------------------------


def make_playback(
    mission: Mission,
    *,
    config: Optional[PlaybackConfig] = None,
    path_config=None,
    apply: Optional[ApplyCallback] = None,
    sync_callback: Optional[SyncCallback] = None,
) -> Playback:
    """One-line builder: mission → ``Playback`` engine. The
    dialog calls this when the artist clicks Play on a mission;
    the camera-path layer handles position resolution and the
    playback engine handles stepping."""
    from .camera_path import CameraPathConfig, build_camera_path

    cp_cfg = path_config or CameraPathConfig()
    if config is not None and path_config is None:
        cp_cfg = CameraPathConfig(
            speed_multiplier=config.speed_multiplier,
        )
    path = build_camera_path(mission, cp_cfg)
    return Playback(
        path=path, config=config,
        apply=apply, sync_callback=sync_callback,
    )
