"""v3.3 presentation runtime-state tests."""

from __future__ import annotations

import pytest

from presentation import (
    PRESENTATION_FINISHED,
    PRESENTATION_IDLE,
    PRESENTATION_PAUSED,
    PRESENTATION_RUNNING,
    PresentationError,
    PresentationSequence,
    PresentationState,
    PresentationStep,
)


def _seq(n: int = 3) -> PresentationSequence:
    seq = PresentationSequence(title="Demo")
    for i in range(n):
        seq.add_step(PresentationStep(title=f"step {i}"))
    return seq


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_default_state_is_idle():
    s = PresentationState()
    assert s.status == PRESENTATION_IDLE
    assert s.is_active is False


def test_start_advances_to_step_zero():
    s = PresentationState()
    s.start(_seq(3))
    assert s.status == PRESENTATION_RUNNING
    assert s.step_index == 0


def test_start_empty_sequence_finishes_immediately():
    s = PresentationState()
    s.start(PresentationSequence())
    assert s.status == PRESENTATION_FINISHED
    assert s.step_index == -1


def test_start_validates_sequence_and_raises():
    """A sequence that fails validation cannot be
    started."""
    seq = PresentationSequence()
    a = PresentationStep()
    b = PresentationStep()
    b.step_id = a.step_id
    seq.steps = [a, b]
    s = PresentationState()
    with pytest.raises(PresentationError):
        s.start(seq)


def test_end_returns_to_idle():
    s = PresentationState()
    s.start(_seq(2))
    s.end()
    assert s.status == PRESENTATION_IDLE
    assert s.step_index == -1
    assert s.sequence is None


# ---------------------------------------------------------------------------
# Pause / resume
# ---------------------------------------------------------------------------


def test_pause_only_works_while_running():
    s = PresentationState()
    assert s.pause() is False
    s.start(_seq(2))
    assert s.pause() is True
    assert s.status == PRESENTATION_PAUSED


def test_resume_only_works_while_paused():
    s = PresentationState()
    s.start(_seq(2))
    assert s.resume() is False  # already running
    s.pause()
    assert s.resume() is True
    assert s.status == PRESENTATION_RUNNING


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def test_next_step_advances():
    s = PresentationState()
    s.start(_seq(3))
    assert s.next_step() is True
    assert s.step_index == 1


def test_next_step_at_end_finishes():
    s = PresentationState()
    s.start(_seq(2))
    s.next_step()
    assert s.next_step() is False
    assert s.status == PRESENTATION_FINISHED


def test_previous_step_rewinds():
    s = PresentationState()
    s.start(_seq(3))
    s.next_step()
    assert s.previous_step() is True
    assert s.step_index == 0


def test_previous_step_at_start_returns_false():
    s = PresentationState()
    s.start(_seq(2))
    assert s.previous_step() is False


def test_previous_step_after_finished_resumes_running():
    s = PresentationState()
    s.start(_seq(2))
    s.next_step()
    s.next_step()  # finishes
    assert s.is_finished
    assert s.previous_step() is True
    assert s.status == PRESENTATION_RUNNING


def test_next_step_resumes_paused():
    s = PresentationState()
    s.start(_seq(3))
    s.pause()
    s.next_step()
    assert s.status == PRESENTATION_RUNNING


def test_jump_to_index():
    s = PresentationState()
    s.start(_seq(5))
    assert s.jump_to(3) is True
    assert s.step_index == 3


def test_jump_to_same_index_returns_false():
    s = PresentationState()
    s.start(_seq(5))
    assert s.jump_to(0) is False


def test_jump_to_out_of_range_returns_false():
    s = PresentationState()
    s.start(_seq(3))
    assert s.jump_to(99) is False
    assert s.jump_to(-1) is False


def test_jump_to_step_id():
    s = PresentationState()
    seq = _seq(3)
    s.start(seq)
    target = seq.steps[2].step_id
    assert s.jump_to_step_id(target) is True
    assert s.step_index == 2


def test_jump_to_unknown_step_id_returns_false():
    s = PresentationState()
    s.start(_seq(2))
    assert s.jump_to_step_id("nope") is False


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------


def test_current_step_returns_active_step():
    s = PresentationState()
    seq = _seq(3)
    s.start(seq)
    assert s.current_step() is seq.steps[0]


def test_current_step_is_none_when_idle():
    s = PresentationState()
    assert s.current_step() is None


def test_current_resolved_returns_resolved_step():
    s = PresentationState()
    s.start(_seq(2))
    resolved = s.current_resolved()
    assert resolved is not None
    assert resolved.index == 0


# ---------------------------------------------------------------------------
# Locked navigation
# ---------------------------------------------------------------------------


def test_lock_and_unlock_navigation():
    s = PresentationState()
    s.lock_navigation({"camera_x": 10.0})
    assert s.locked_navigation_state == {"camera_x": 10.0}
    s.unlock_navigation()
    assert s.locked_navigation_state is None


def test_lock_navigation_none_clears():
    s = PresentationState()
    s.lock_navigation({"x": 1})
    s.lock_navigation(None)
    assert s.locked_navigation_state is None


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def test_snapshot_when_idle():
    s = PresentationState()
    snap = s.snapshot()
    assert snap.status == PRESENTATION_IDLE
    assert "(none active)" in snap.short_summary()


def test_snapshot_when_running():
    s = PresentationState()
    s.start(_seq(3))
    snap = s.snapshot()
    assert snap.status == PRESENTATION_RUNNING
    assert snap.step_total == 3
    assert snap.step_index == 0
    assert "step" in snap.short_summary().lower()


def test_snapshot_when_paused():
    s = PresentationState()
    s.start(_seq(2))
    s.pause()
    assert s.snapshot().status == PRESENTATION_PAUSED


def test_snapshot_when_finished():
    s = PresentationState()
    s.start(_seq(1))
    s.next_step()  # finishes
    snap = s.snapshot()
    assert snap.status == PRESENTATION_FINISHED
    assert "finished" in snap.short_summary()
