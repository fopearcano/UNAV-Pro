"""Time-navigator state for the v1.2 dialog.

Holds the artist's current epoch + step preferences so the dialog
panel can step backward / forward without recomputing from
scratch on every click. Stays separate from the navigation null
(which deals with *spatial* pose) — this module is the *temporal*
pose.

Stdlib-only. The values round-trip through the project-state
sidecar so reopening a `.c4d` restores the artist's preferred
epoch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from core.time_model import (
    DAYS_PER_JULIAN_YEAR,
    DEFAULT_REFERENCE_EPOCH_JD,
    Epoch,
    coerce_epoch,
    julian_date_to_iso,
    julian_date_to_jyear,
)


#: Default step size for the dialog's backward / forward buttons.
#: One day is fine for solar-system fly-throughs (a planet moves
#: visibly day-over-day on the screen) but slow for long sweeps.
DEFAULT_STEP_DAYS: float = 1.0

#: Hard caps so a runaway step button can't overflow.
MAX_STEP_DAYS: float = 365.25 * 1000.0      # 1 millennium per click
MAX_TOTAL_DAYS_FROM_J2000: float = 365.25 * 10_000.0  # ± 10 ky from J2000


@dataclass
class TimeNavigatorState:
    """One-of state object the dialog mutates.

    The artist's Time Navigator panel reads / writes this; the
    rest of the codebase (sector streaming, binary export, native
    bridge) consumes ``current_epoch_jd`` only.
    """

    current_epoch_jd: float = DEFAULT_REFERENCE_EPOCH_JD
    step_days: float = DEFAULT_STEP_DAYS
    is_playing: bool = False
    last_label: str = ""

    def __post_init__(self) -> None:
        if self.step_days <= 0:
            raise ValueError("step_days must be > 0")
        if self.step_days > MAX_STEP_DAYS:
            self.step_days = MAX_STEP_DAYS

    # ------------------------------------------------ accessors
    @property
    def current_epoch(self) -> Epoch:
        return Epoch.from_jd(self.current_epoch_jd, label=self.last_label)

    @property
    def current_iso(self) -> str:
        return julian_date_to_iso(self.current_epoch_jd)

    @property
    def current_jyear(self) -> float:
        return julian_date_to_jyear(self.current_epoch_jd)

    # ------------------------------------------------ mutators
    def set_epoch(
        self, value: Union[None, "Epoch", str, float],
    ) -> Epoch:
        """Set the navigator's current epoch from any input
        ``coerce_epoch`` understands. Returns the resolved
        ``Epoch`` so the caller can update its UI label."""
        ep = coerce_epoch(value)
        if ep is None:
            raise ValueError("epoch is None; pass an explicit value")
        self.current_epoch_jd = float(ep.jd)
        self.last_label = ep.label
        return ep

    def step_forward(self, *, steps: int = 1) -> Epoch:
        """Advance ``steps`` × ``step_days`` and return the new
        ``Epoch``. Negative ``steps`` are valid (mirrors of
        ``step_backward``)."""
        return self._step(int(steps))

    def step_backward(self, *, steps: int = 1) -> Epoch:
        return self._step(-int(steps))

    def _step(self, n: int) -> Epoch:
        delta = n * float(self.step_days)
        new_jd = float(self.current_epoch_jd) + delta
        # Defensive bound vs absurd "step a million years" inputs.
        from core.time_model import J2000_JD
        if abs(new_jd - J2000_JD) > MAX_TOTAL_DAYS_FROM_J2000:
            raise ValueError(
                f"refused to step beyond ±{MAX_TOTAL_DAYS_FROM_J2000:.0f} "
                f"days from J2000; tighten step_days or set epoch directly"
            )
        self.current_epoch_jd = new_jd
        self.last_label = julian_date_to_iso(new_jd)
        return Epoch.from_jd(new_jd, label=self.last_label)

    def set_step_days(self, days: float) -> None:
        if days <= 0:
            raise ValueError("step_days must be > 0")
        if days > MAX_STEP_DAYS:
            days = MAX_STEP_DAYS
        self.step_days = float(days)

    def toggle_play(self) -> bool:
        """Flip the play / pause flag. v1.2 is a placeholder —
        the dialog wires this to a status line; per-frame stepping
        lands when the v1.x SceneHook + Auto-Sync pipeline arrives.
        Returns the new value."""
        self.is_playing = not self.is_playing
        return self.is_playing

    # ------------------------------------------------ rendering
    def short_summary(self) -> str:
        return (
            f"epoch {self.current_iso} (JD {self.current_epoch_jd:.3f}, "
            f"{self.current_jyear:.3f}J), step {self.step_days:g}d"
            + (" [playing]" if self.is_playing else "")
        )


# ---------------------------------------------------------------------------
# Process-wide singleton — the dialog mutates this directly.
# ---------------------------------------------------------------------------


_default_state: Optional[TimeNavigatorState] = None


def default_state(*, reload: bool = False) -> TimeNavigatorState:
    """Return the process-wide singleton, lazily initialised at the
    Gaia DR3 reference epoch (J2016.0). Mutating the returned object
    is observable by every caller — the dialog's Time Navigator
    panel relies on this.

    With ``reload=True`` the existing singleton is replaced with a
    fresh instance at the default epoch. Mirrors
    ``metadata_lookup.default_lookup``'s reload semantics so the
    v1.7 ``state_manager`` facade can offer a uniform API across
    every singleton it tracks (see V1_7_ARCHITECTURE_AUDIT §2)."""
    global _default_state
    if reload or _default_state is None:
        _default_state = TimeNavigatorState()
    return _default_state


def set_default_state(state: Optional[TimeNavigatorState]) -> None:
    """Replace (or clear) the singleton. Useful for tests and for
    code paths that load a different epoch from saved state."""
    global _default_state
    _default_state = state
