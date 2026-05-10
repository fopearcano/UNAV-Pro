"""v3.3 presentation runtime state.

The dialog's *Presentation* panel drives a
``PresentationState`` instance: which presentation is
active, which step is current, whether playback is
paused, what locked navigation pose is being held.

The state is **pure data**; the C4D builder reads from
it after each transition to materialise the active
step's overlay / science / annotation layout.

Pure stdlib; no Cinema 4D, no threading.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .presentation_sequence import (
    PresentationError,
    PresentationSequence,
    PresentationStep,
    ResolvedStep,
)


# ---------------------------------------------------------------------------
# Lifecycle status
# ---------------------------------------------------------------------------


PRESENTATION_IDLE: str = "idle"
PRESENTATION_RUNNING: str = "running"
PRESENTATION_PAUSED: str = "paused"
PRESENTATION_FINISHED: str = "finished"

PRESENTATION_STATUSES = (
    PRESENTATION_IDLE,
    PRESENTATION_RUNNING,
    PRESENTATION_PAUSED,
    PRESENTATION_FINISHED,
)


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


@dataclass
class PresentationSnapshot:
    """Snapshot the dialog renders into the presentation
    panel header. Pure data; safe to log + serialise."""

    presentation_id: str = ""
    presentation_title: str = ""
    status: str = PRESENTATION_IDLE
    step_index: int = -1
    step_total: int = 0
    step_id: str = ""
    step_title: str = ""
    presenter_notes: str = ""
    started_at_iso: str = ""

    def short_summary(self) -> str:
        if self.status == PRESENTATION_IDLE:
            return "Presentation: (none active)"
        prefix = f"Presentation '{self.presentation_title}'"
        if self.status == PRESENTATION_FINISHED:
            return f"{prefix} — finished"
        return (
            f"{prefix} — step {self.step_index + 1}/{self.step_total}"
            + (f" '{self.step_title}'" if self.step_title else "")
            + (f" [{self.status}]" if self.status != PRESENTATION_RUNNING else "")
        )


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class PresentationState:
    """Runtime tracker.

    Construct via ``PresentationState()`` to start in the
    idle state; call ``start(sequence)`` to load and
    advance to step 0; ``next_step`` / ``previous_step`` /
    ``jump_to`` to navigate; ``pause`` / ``resume`` /
    ``end`` for lifecycle.

    The state is **single-threaded**. The C4D dialog
    drives it from the main thread; the resolver is pure
    Python and never touches Cinema 4D itself.
    """

    sequence: Optional[PresentationSequence] = None
    status: str = PRESENTATION_IDLE
    step_index: int = -1
    started_at_iso: str = ""
    locked_navigation_state: Optional[Dict[str, Any]] = None
    _resolved_cache: List[ResolvedStep] = field(default_factory=list)

    # ---------------------------------------------------- predicates
    @property
    def is_active(self) -> bool:
        return self.status in (
            PRESENTATION_RUNNING, PRESENTATION_PAUSED,
        )

    @property
    def is_finished(self) -> bool:
        return self.status == PRESENTATION_FINISHED

    @property
    def is_paused(self) -> bool:
        return self.status == PRESENTATION_PAUSED

    @property
    def step_total(self) -> int:
        return self.sequence.step_count() if self.sequence else 0

    # ---------------------------------------------------- lifecycle
    def start(self, sequence: PresentationSequence) -> "PresentationState":
        """Load ``sequence`` and advance to step 0. The
        sequence is validated; an empty presentation
        transitions straight to ``finished``.

        Returns ``self`` so the caller can chain.
        """
        errs = sequence.validate()
        if errs:
            raise PresentationError(
                "presentation failed validation:\n  - "
                + "\n  - ".join(errs)
            )
        self.sequence = sequence
        self._resolved_cache = sequence.resolved_steps()
        self.started_at_iso = _utc_iso()
        self.locked_navigation_state = None
        if not self._resolved_cache:
            self.status = PRESENTATION_FINISHED
            self.step_index = -1
            return self
        self.status = PRESENTATION_RUNNING
        self.step_index = 0
        return self

    def end(self) -> None:
        """Stop the presentation. Returns to idle so the
        next ``start`` reloads cleanly. Idempotent."""
        self.status = PRESENTATION_IDLE
        self.step_index = -1
        self.sequence = None
        self._resolved_cache = []
        self.started_at_iso = ""
        self.locked_navigation_state = None

    def pause(self) -> bool:
        if self.status != PRESENTATION_RUNNING:
            return False
        self.status = PRESENTATION_PAUSED
        return True

    def resume(self) -> bool:
        if self.status != PRESENTATION_PAUSED:
            return False
        self.status = PRESENTATION_RUNNING
        return True

    # ---------------------------------------------------- navigation
    def next_step(self) -> bool:
        """Advance to the next step. Returns True iff a
        step was advanced; transitions to ``finished``
        when the last step rolls over."""
        if not self.is_active or self.sequence is None:
            return False
        if self.step_index + 1 >= self.step_total:
            self.status = PRESENTATION_FINISHED
            return False
        self.step_index += 1
        if self.status == PRESENTATION_PAUSED:
            self.status = PRESENTATION_RUNNING
        return True

    def previous_step(self) -> bool:
        """Walk back one step. Refuses to go below 0;
        returns True iff a step was rewound."""
        if self.sequence is None or self.step_total == 0:
            return False
        if self.step_index <= 0:
            return False
        self.step_index -= 1
        # Walking back from finished returns to running.
        if self.status in (PRESENTATION_FINISHED, PRESENTATION_PAUSED):
            self.status = PRESENTATION_RUNNING
        return True

    def jump_to(self, index: int) -> bool:
        """Seek to ``index`` (0-based). Refuses out-of-
        bounds; returns True iff the index changed."""
        if self.sequence is None or self.step_total == 0:
            return False
        if not 0 <= index < self.step_total:
            return False
        if index == self.step_index:
            return False
        self.step_index = int(index)
        if self.status in (PRESENTATION_FINISHED, PRESENTATION_PAUSED):
            self.status = PRESENTATION_RUNNING
        return True

    def jump_to_step_id(self, step_id: str) -> bool:
        """Seek by step id. Useful for the dialog's step-
        picker. Returns True iff the index changed."""
        if self.sequence is None:
            return False
        idx = self.sequence.find_step_index(step_id)
        if idx < 0:
            return False
        return self.jump_to(idx)

    # ---------------------------------------------------- accessors
    def current_step(self) -> Optional[PresentationStep]:
        if (
            self.sequence is None
            or self.step_index < 0
            or self.step_index >= self.step_total
        ):
            return None
        return self.sequence.steps[self.step_index]

    def current_resolved(self) -> Optional[ResolvedStep]:
        """Return the resolved (post-inheritance) view of
        the current step. The C4D builder uses this."""
        if (
            not self._resolved_cache
            or self.step_index < 0
            or self.step_index >= len(self._resolved_cache)
        ):
            return None
        return self._resolved_cache[self.step_index]

    def lock_navigation(self, state: Dict[str, Any]) -> None:
        """Store a snapshot of the navigator + dataset
        flags the artist wants the presentation to hold
        steady. The dialog passes this in via
        ``Project → Lock Navigation``.

        Pure data; the runtime layer does not interpret
        the dict — it's just round-tripped to / from the
        Cinema 4D builder."""
        self.locked_navigation_state = (
            None if state is None else dict(state)
        )

    def unlock_navigation(self) -> None:
        self.locked_navigation_state = None

    # ---------------------------------------------------- snapshot
    def snapshot(self) -> PresentationSnapshot:
        """Render a ``PresentationSnapshot`` for the
        dialog's panel header."""
        if self.sequence is None or self.status == PRESENTATION_IDLE:
            return PresentationSnapshot(status=PRESENTATION_IDLE)
        cur = self.current_step()
        return PresentationSnapshot(
            presentation_id=self.sequence.presentation_id,
            presentation_title=self.sequence.title,
            status=self.status,
            step_index=self.step_index,
            step_total=self.step_total,
            step_id=cur.step_id if cur is not None else "",
            step_title=cur.title if cur is not None else "",
            presenter_notes=cur.presenter_notes if cur is not None else "",
            started_at_iso=self.started_at_iso,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
