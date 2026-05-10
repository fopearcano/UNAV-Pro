"""v3.3 presentation panel-action tests.

Drive the pure-Python facade end-to-end without any UI
primitives.
"""

from __future__ import annotations

import pytest

from presentation import (
    PRESENTATION_FINISHED,
    PRESENTATION_PAUSED,
    PRESENTATION_RUNNING,
    PresentationManager,
    PresentationSequence,
    PresentationState,
    PresentationStep,
)
from ui.presentation_panel import (
    PresentationPanelError,
    end_presentation_action,
    jump_to_step_action,
    list_presentations_action,
    next_step_action,
    open_presentation_from_manager,
    pause_presentation_action,
    presenter_notes_action,
    previous_step_action,
    resume_presentation_action,
    start_presentation_action,
    step_narration_action,
)


def _seq() -> PresentationSequence:
    seq = PresentationSequence(title="Demo")
    seq.add_step(PresentationStep(
        title="A", narration="hello", presenter_notes="off-script note",
    ))
    seq.add_step(PresentationStep(title="B"))
    seq.add_step(PresentationStep(title="C"))
    return seq


# ---------------------------------------------------------------------------
# start / end / pause / resume
# ---------------------------------------------------------------------------


def test_start_returns_initial_snapshot():
    state = PresentationState()
    snap = start_presentation_action(state, _seq())
    assert snap.status == PRESENTATION_RUNNING
    assert snap.step_index == 0
    assert snap.step_total == 3


def test_start_rejects_none_state():
    with pytest.raises(PresentationPanelError):
        start_presentation_action(None, _seq())  # type: ignore[arg-type]


def test_start_rejects_none_sequence():
    with pytest.raises(PresentationPanelError):
        start_presentation_action(PresentationState(), None)  # type: ignore[arg-type]


def test_start_translates_validation_error():
    seq = PresentationSequence()
    a = PresentationStep()
    b = PresentationStep()
    b.step_id = a.step_id
    seq.steps = [a, b]
    with pytest.raises(PresentationPanelError):
        start_presentation_action(PresentationState(), seq)


def test_end_returns_idle_snapshot():
    state = PresentationState()
    start_presentation_action(state, _seq())
    snap = end_presentation_action(state)
    assert snap.status == "idle"


def test_pause_then_resume_cycle():
    state = PresentationState()
    start_presentation_action(state, _seq())
    paused = pause_presentation_action(state)
    assert paused.status == PRESENTATION_PAUSED
    resumed = resume_presentation_action(state)
    assert resumed.status == PRESENTATION_RUNNING


def test_pause_when_not_running_raises():
    with pytest.raises(PresentationPanelError):
        pause_presentation_action(PresentationState())


def test_resume_when_not_paused_raises():
    state = PresentationState()
    start_presentation_action(state, _seq())
    with pytest.raises(PresentationPanelError):
        resume_presentation_action(state)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def test_next_step_advances():
    state = PresentationState()
    start_presentation_action(state, _seq())
    snap = next_step_action(state)
    assert snap.step_index == 1


def test_previous_step_rewinds():
    state = PresentationState()
    start_presentation_action(state, _seq())
    next_step_action(state)
    snap = previous_step_action(state)
    assert snap.step_index == 0


def test_next_step_at_end_finishes():
    state = PresentationState()
    start_presentation_action(state, _seq())
    next_step_action(state)
    next_step_action(state)
    snap = next_step_action(state)  # rolls over
    assert snap.status == PRESENTATION_FINISHED


def test_jump_to_step_index():
    state = PresentationState()
    start_presentation_action(state, _seq())
    snap = jump_to_step_action(state, 2)
    assert snap.step_index == 2


def test_jump_to_step_rejects_out_of_range():
    state = PresentationState()
    start_presentation_action(state, _seq())
    with pytest.raises(PresentationPanelError):
        jump_to_step_action(state, 99)


def test_jump_to_step_rejects_non_integer():
    state = PresentationState()
    start_presentation_action(state, _seq())
    with pytest.raises(PresentationPanelError):
        jump_to_step_action(state, "two")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Notes / narration
# ---------------------------------------------------------------------------


def test_presenter_notes_returns_current_step_notes():
    state = PresentationState()
    start_presentation_action(state, _seq())
    assert "off-script note" in presenter_notes_action(state)


def test_presenter_notes_empty_when_no_step():
    assert presenter_notes_action(PresentationState()) == ""


def test_step_narration_returns_current_text():
    state = PresentationState()
    start_presentation_action(state, _seq())
    assert step_narration_action(state) == "hello"


def test_step_narration_empty_when_no_step():
    assert step_narration_action(PresentationState()) == ""


# ---------------------------------------------------------------------------
# Manager-backed
# ---------------------------------------------------------------------------


def test_open_from_manager_returns_sequence(tmp_path):
    pm = PresentationManager(str(tmp_path))
    seq = _seq()
    pm.create(seq)
    rt = open_presentation_from_manager(pm, seq.presentation_id)
    assert rt is seq


def test_open_from_manager_missing_raises(tmp_path):
    pm = PresentationManager(str(tmp_path))
    with pytest.raises(PresentationPanelError):
        open_presentation_from_manager(pm, "nope")


def test_open_from_manager_no_manager_raises():
    with pytest.raises(PresentationPanelError):
        open_presentation_from_manager(None, "x")  # type: ignore[arg-type]


def test_list_presentations_action(tmp_path):
    pm = PresentationManager(str(tmp_path))
    a = _seq()
    a.title = "Talk A"
    b = _seq()
    b.title = "Talk B"
    pm.create(a)
    pm.create(b)
    rows = list_presentations_action(pm)
    assert len(rows) == 2
    titles = {title for (_id, title) in rows}
    assert "Talk A" in titles
    assert "Talk B" in titles
