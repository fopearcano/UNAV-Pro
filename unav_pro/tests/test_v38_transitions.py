"""v3.8 transition-sequencer tests."""

from __future__ import annotations

import math

import pytest

from presentation import (
    TRANSITION_KINDS,
    StepProjection,
    TransitionFrame,
    TransitionKind,
    TransitionSequence,
    TransitionSpec,
    build_transition_sequence,
    project_resolved_step,
    sequence_transition,
)


def _step(step_id, *, position=None, target=None, fov=None):
    return StepProjection(
        step_id=step_id,
        camera_position=position,
        camera_target=target,
        fov_deg=fov,
    )


# ---------------------------------------------------------------------------
# TransitionKind constant
# ---------------------------------------------------------------------------


def test_transition_kinds_complete():
    expected = {
        TransitionKind.HARD_CUT, TransitionKind.SMOOTH_CAMERA,
        TransitionKind.CROSSFADE_PLACEHOLDER,
        TransitionKind.WAYPOINT_PAUSE,
    }
    assert expected == set(TRANSITION_KINDS)


# ---------------------------------------------------------------------------
# TransitionSpec validation
# ---------------------------------------------------------------------------


def test_spec_default():
    spec = TransitionSpec()
    assert spec.kind is TransitionKind.HARD_CUT
    assert spec.frame_count == 12


def test_spec_negative_frame_count_raises():
    with pytest.raises(ValueError):
        TransitionSpec(frame_count=-1)


def test_spec_negative_pause_raises():
    with pytest.raises(ValueError):
        TransitionSpec(pause_seconds=-1.0)


# ---------------------------------------------------------------------------
# project_resolved_step
# ---------------------------------------------------------------------------


def test_project_resolved_step_extracts_fields():
    class Resolved:
        step_id = "x"
        camera_position = (1, 2, 3)
        camera_target = (4, 5, 6)
        camera_fov_deg = 36.0
    out = project_resolved_step(Resolved())
    assert out.step_id == "x"
    assert out.camera_position == (1, 2, 3)
    assert out.camera_target == (4, 5, 6)
    assert out.fov_deg == 36.0


def test_project_resolved_step_handles_missing_attrs():
    class Empty:
        pass
    out = project_resolved_step(Empty())
    assert out.step_id == ""
    assert out.camera_position is None


# ---------------------------------------------------------------------------
# Hard cut
# ---------------------------------------------------------------------------


def test_hard_cut_emits_no_frames():
    a = _step("a", position=(0, 0, 0), target=(0, 0, 0), fov=36.0)
    b = _step("b", position=(10, 0, 0), target=(0, 0, 0), fov=36.0)
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(kind=TransitionKind.HARD_CUT),
    )
    assert frames == []


# ---------------------------------------------------------------------------
# Smooth camera
# ---------------------------------------------------------------------------


def test_smooth_camera_emits_frame_count():
    a = _step("a", position=(0, 0, 0), target=(0, 0, 0))
    b = _step("b", position=(10, 0, 0), target=(0, 0, 0))
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.SMOOTH_CAMERA, frame_count=8,
        ),
    )
    assert len(frames) == 8


def test_smooth_camera_first_frame_is_source():
    a = _step("a", position=(0, 0, 0))
    b = _step("b", position=(10, 0, 0))
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.SMOOTH_CAMERA, frame_count=4,
        ),
    )
    assert frames[0].camera_position == (0.0, 0.0, 0.0)
    assert frames[0].t == 0.0


def test_smooth_camera_last_frame_is_destination():
    a = _step("a", position=(0, 0, 0))
    b = _step("b", position=(10, 0, 0))
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.SMOOTH_CAMERA, frame_count=4,
        ),
    )
    assert frames[-1].camera_position == (10.0, 0.0, 0.0)
    assert frames[-1].t == 1.0


def test_smooth_camera_interpolates_target():
    a = _step("a", target=(0, 0, 0))
    b = _step("b", target=(10, 0, 0))
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.SMOOTH_CAMERA, frame_count=3,
        ),
    )
    assert frames[1].camera_target == (5.0, 0.0, 0.0)


def test_smooth_camera_interpolates_fov():
    a = _step("a", fov=24.0)
    b = _step("b", fov=48.0)
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.SMOOTH_CAMERA, frame_count=3,
        ),
    )
    assert math.isclose(frames[1].fov_deg, 36.0)


def test_smooth_camera_handles_none_position():
    """If neither side has a position, the frames
    should carry None — no exceptions."""
    a = _step("a")
    b = _step("b")
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.SMOOTH_CAMERA, frame_count=2,
        ),
    )
    assert frames[0].camera_position is None
    assert frames[1].camera_position is None


def test_smooth_camera_zero_frames_returns_empty():
    a = _step("a", position=(0, 0, 0))
    b = _step("b", position=(10, 0, 0))
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.SMOOTH_CAMERA, frame_count=0,
        ),
    )
    assert frames == []


def test_smooth_camera_single_frame_uses_t1():
    a = _step("a", position=(0, 0, 0))
    b = _step("b", position=(10, 0, 0))
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.SMOOTH_CAMERA, frame_count=1,
        ),
    )
    assert len(frames) == 1
    assert frames[0].t == 1.0


# ---------------------------------------------------------------------------
# Crossfade placeholder
# ---------------------------------------------------------------------------


def test_crossfade_placeholder_emits_fraction():
    a = _step("a", position=(0, 0, 0))
    b = _step("b", position=(10, 0, 0))
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.CROSSFADE_PLACEHOLDER, frame_count=4,
        ),
    )
    assert all(f.crossfade_fraction is not None for f in frames)
    assert frames[0].crossfade_fraction == 0.0
    assert frames[-1].crossfade_fraction == 1.0


def test_crossfade_first_frame_carries_disclaimer_note():
    a = _step("a")
    b = _step("b")
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.CROSSFADE_PLACEHOLDER, frame_count=2,
        ),
    )
    assert "placeholder" in frames[0].notes.lower()


# ---------------------------------------------------------------------------
# Waypoint pause
# ---------------------------------------------------------------------------


def test_waypoint_pause_holds_source():
    a = _step("a", position=(1, 2, 3))
    b = _step("b", position=(99, 99, 99))
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.WAYPOINT_PAUSE,
            frame_count=4, pause_seconds=2.0,
        ),
    )
    assert all(f.holds_source for f in frames)
    assert all(f.camera_position == (1, 2, 3) for f in frames)


def test_waypoint_pause_zero_frames_emits_one_hold():
    a = _step("a", position=(1, 2, 3))
    b = _step("b", position=(99, 99, 99))
    frames = sequence_transition(
        source=a, destination=b,
        spec=TransitionSpec(
            kind=TransitionKind.WAYPOINT_PAUSE,
            frame_count=0, pause_seconds=2.0,
        ),
    )
    assert len(frames) == 1
    assert frames[0].holds_source


# ---------------------------------------------------------------------------
# Multi-step sequence
# ---------------------------------------------------------------------------


def test_build_transition_sequence_chains_frames():
    steps = [
        _step("a", position=(0, 0, 0)),
        _step("b", position=(10, 0, 0)),
        _step("c", position=(20, 0, 0)),
    ]
    specs = [
        TransitionSpec(kind=TransitionKind.SMOOTH_CAMERA, frame_count=4),
        TransitionSpec(kind=TransitionKind.HARD_CUT),
    ]
    out = build_transition_sequence(steps=steps, specs=specs)
    # 4 frames for a→b + 0 for b→c.
    assert out.total_frames == 4
    assert [f.index for f in out.frames] == [0, 1, 2, 3]


def test_build_transition_sequence_emits_notes_for_pauses():
    steps = [_step("a", position=(0, 0, 0)), _step("b", position=(10, 0, 0))]
    specs = [TransitionSpec(
        kind=TransitionKind.WAYPOINT_PAUSE, frame_count=2, pause_seconds=2.0,
    )]
    out = build_transition_sequence(steps=steps, specs=specs)
    assert any("pause" in n.lower() for n in out.notes)


def test_build_transition_sequence_emits_notes_for_crossfade():
    steps = [_step("a"), _step("b")]
    specs = [TransitionSpec(
        kind=TransitionKind.CROSSFADE_PLACEHOLDER, frame_count=2,
    )]
    out = build_transition_sequence(steps=steps, specs=specs)
    assert any("crossfade" in n.lower() for n in out.notes)


def test_build_transition_sequence_rejects_wrong_spec_count():
    steps = [_step("a"), _step("b"), _step("c")]
    specs = [TransitionSpec()]
    with pytest.raises(ValueError):
        build_transition_sequence(steps=steps, specs=specs)


def test_build_transition_sequence_empty_steps():
    out = build_transition_sequence(steps=[], specs=[])
    assert out.total_frames == 0


def test_build_transition_sequence_short_summary():
    steps = [_step("a", position=(0, 0, 0)), _step("b", position=(10, 0, 0))]
    specs = [TransitionSpec(
        kind=TransitionKind.SMOOTH_CAMERA, frame_count=4,
    )]
    out = build_transition_sequence(steps=steps, specs=specs)
    assert "4 frame" in out.short_summary()


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_sequencer_deterministic():
    steps = [
        _step("a", position=(0, 0, 0)),
        _step("b", position=(10, 0, 0)),
    ]
    specs = [TransitionSpec(
        kind=TransitionKind.SMOOTH_CAMERA, frame_count=8,
    )]
    a = build_transition_sequence(steps=steps, specs=specs)
    b = build_transition_sequence(steps=steps, specs=specs)
    assert [f.camera_position for f in a.frames] == \
           [f.camera_position for f in b.frames]
