"""v3.3 Presentation panel — pure-Python facade.

The dialog's *Presentation* panel surfaces eight
buttons:

* **Start Presentation** — load + start a sequence.
* **Next Step** — advance one step.
* **Previous Step** — rewind one step.
* **Jump To Step** — seek to an arbitrary index.
* **Pause** — stop advancing.
* **Resume** — un-pause.
* **End Presentation** — return to idle.
* **Presenter Notes** — read the current step's
  notes for display in the host editor.

Each function takes plain inputs (state, indices,
sequences) and returns plain outputs (snapshots, str,
bool). The dialog handles file pickers + status logging.

Pure stdlib; no Cinema 4D imports. Tested without any
UI primitives.
"""

from __future__ import annotations

from typing import Optional

from presentation import (
    PresentationError,
    PresentationManager,
    PresentationSequence,
    PresentationSnapshot,
    PresentationState,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PresentationPanelError(RuntimeError):
    """Raised on panel-action failures. Carries a short
    human message the dialog renders in the status
    line."""


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start_presentation_action(
    state: PresentationState,
    sequence: PresentationSequence,
) -> PresentationSnapshot:
    """Load ``sequence`` into ``state`` and return the
    starting snapshot."""
    if state is None:
        raise PresentationPanelError("no active presentation state")
    if sequence is None:
        raise PresentationPanelError("no presentation sequence")
    try:
        state.start(sequence)
    except PresentationError as exc:
        raise PresentationPanelError(f"start failed: {exc}") from exc
    return state.snapshot()


def end_presentation_action(
    state: PresentationState,
) -> PresentationSnapshot:
    if state is None:
        raise PresentationPanelError("no active presentation state")
    state.end()
    return state.snapshot()


def pause_presentation_action(
    state: PresentationState,
) -> PresentationSnapshot:
    if state is None:
        raise PresentationPanelError("no active presentation state")
    if not state.pause():
        raise PresentationPanelError(
            "presentation not running; nothing to pause",
        )
    return state.snapshot()


def resume_presentation_action(
    state: PresentationState,
) -> PresentationSnapshot:
    if state is None:
        raise PresentationPanelError("no active presentation state")
    if not state.resume():
        raise PresentationPanelError(
            "presentation not paused; nothing to resume",
        )
    return state.snapshot()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def next_step_action(
    state: PresentationState,
) -> PresentationSnapshot:
    if state is None:
        raise PresentationPanelError("no active presentation state")
    if not state.is_active and not state.is_finished:
        raise PresentationPanelError("no active presentation")
    state.next_step()
    return state.snapshot()


def previous_step_action(
    state: PresentationState,
) -> PresentationSnapshot:
    if state is None:
        raise PresentationPanelError("no active presentation state")
    state.previous_step()
    return state.snapshot()


def jump_to_step_action(
    state: PresentationState,
    index: int,
) -> PresentationSnapshot:
    if state is None:
        raise PresentationPanelError("no active presentation state")
    try:
        idx = int(index)
    except (TypeError, ValueError) as exc:
        raise PresentationPanelError(
            f"jump_to: index must be an integer (got {index!r})"
        ) from exc
    if not state.jump_to(idx):
        raise PresentationPanelError(
            f"jump_to: index {idx} out of range "
            f"(0..{state.step_total - 1})"
        )
    return state.snapshot()


# ---------------------------------------------------------------------------
# Presenter notes
# ---------------------------------------------------------------------------


def presenter_notes_action(
    state: PresentationState,
) -> str:
    """Return the current step's presenter notes, or an
    empty string when no step is current."""
    if state is None:
        raise PresentationPanelError("no active presentation state")
    cur = state.current_step()
    if cur is None:
        return ""
    return cur.presenter_notes or ""


def step_narration_action(
    state: PresentationState,
) -> str:
    """Return the current step's narration text. Used by
    the dialog's narration display."""
    if state is None:
        raise PresentationPanelError("no active presentation state")
    cur = state.current_step()
    if cur is None:
        return ""
    return cur.narration or ""


# ---------------------------------------------------------------------------
# Manager-backed helpers
# ---------------------------------------------------------------------------


def open_presentation_from_manager(
    manager: PresentationManager,
    presentation_id: str,
) -> PresentationSequence:
    """Look up ``presentation_id`` in the manager's
    in-memory store. Raises ``PresentationPanelError`` on
    misses so the dialog can surface a friendly status
    line."""
    if manager is None:
        raise PresentationPanelError("no presentation manager")
    pres = manager.get(presentation_id)
    if pres is None:
        raise PresentationPanelError(
            f"presentation not found: {presentation_id}"
        )
    return pres


def list_presentations_action(
    manager: PresentationManager,
) -> list:
    """Return a list of (presentation_id, title) tuples
    for the dialog's *Open Presentation…* picker."""
    if manager is None:
        raise PresentationPanelError("no presentation manager")
    return [
        (p.presentation_id, p.title)
        for p in manager.list_all()
    ]
