"""v3.3 presentation-sequence tests."""

from __future__ import annotations

import json

import pytest

from presentation import (
    DEFAULT_STEP_PAUSE_SECONDS,
    MAX_STEPS_PER_PRESENTATION,
    PRESENTATION_SCHEMA_VERSION,
    PresentationError,
    PresentationSequence,
    PresentationStep,
    ResolvedStep,
)


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


def test_step_default_has_unique_id():
    a = PresentationStep()
    b = PresentationStep()
    assert a.step_id and b.step_id
    assert a.step_id != b.step_id


def test_step_round_trip():
    s = PresentationStep(
        title="Saturn",
        narration="Saturn here.",
        presenter_notes="Encke gap",
        pause_seconds=12.0,
        waypoint_ref="saturn",
        camera_position=(1.0, 2.0, 3.0),
        camera_target=(4.0, 5.0, 6.0),
        camera_fov_deg=45.0,
        epoch_jd=2461041.5,
        overlay_flags={"show_distance_rings": True},
        science_flags={"show_motion_vectors": False},
        visible_annotation_indices=[0, 2],
        highlighted_annotation_indices=[2],
        tags=["intro", "outer"],
    )
    rt = PresentationStep.from_dict(s.to_dict())
    assert rt.title == "Saturn"
    assert rt.narration == "Saturn here."
    assert rt.camera_position == (1.0, 2.0, 3.0)
    assert rt.epoch_jd == 2461041.5
    assert rt.overlay_flags == {"show_distance_rings": True}
    assert rt.visible_annotation_indices == [0, 2]
    assert rt.tags == ["intro", "outer"]


def test_step_rejects_negative_pause():
    with pytest.raises(PresentationError):
        PresentationStep(pause_seconds=-1.0)


def test_step_rejects_zero_fov():
    with pytest.raises(PresentationError):
        PresentationStep(camera_fov_deg=0.0)


def test_step_default_pause_is_documented():
    s = PresentationStep()
    assert s.pause_seconds == DEFAULT_STEP_PAUSE_SECONDS


def test_step_normalises_tags_lowercase():
    s = PresentationStep(tags=["Intro", "Outer"])
    assert s.tags == ["intro", "outer"]


def test_step_short_summary_includes_known_fields():
    s = PresentationStep(
        title="Saturn", waypoint_ref="saturn",
        epoch_jd=2461041.5, pause_seconds=4.0,
    )
    summary = s.short_summary()
    assert "Saturn" in summary
    assert "saturn" in summary


def test_step_from_dict_rejects_non_dict():
    with pytest.raises(PresentationError):
        PresentationStep.from_dict([])  # type: ignore[arg-type]


def test_step_from_dict_handles_missing_optionals():
    s = PresentationStep.from_dict({"step_id": "x"})
    assert s.step_id == "x"
    assert s.camera_position is None


def test_step_from_dict_rejects_malformed_camera_position():
    """A 2-tuple should be rejected (camera_position must
    be 3 floats)."""
    s = PresentationStep.from_dict({
        "step_id": "x",
        "camera_position": [1.0, 2.0],  # malformed
    })
    assert s.camera_position is None  # silently dropped


# ---------------------------------------------------------------------------
# Sequence
# ---------------------------------------------------------------------------


def test_sequence_default_is_valid():
    seq = PresentationSequence()
    assert seq.validate() == []
    assert seq.step_count() == 0


def test_sequence_round_trip_via_json():
    seq = PresentationSequence(
        title="Demo", description="d",
        presenter_notes="overall", mission_ref="m1",
        tags=["demo"],
    )
    seq.add_step(PresentationStep(title="A"))
    seq.add_step(PresentationStep(title="B"))
    rt = PresentationSequence.from_json(seq.to_json())
    assert rt.title == "Demo"
    assert rt.description == "d"
    assert rt.presenter_notes == "overall"
    assert rt.mission_ref == "m1"
    assert rt.tags == ["demo"]
    assert rt.step_count() == 2
    assert rt.steps[0].title == "A"


def test_sequence_rejects_newer_schema():
    with pytest.raises(PresentationError):
        PresentationSequence.from_dict({"schema_version": 999})


def test_sequence_rejects_non_object_payload():
    with pytest.raises(PresentationError):
        PresentationSequence.from_dict([])  # type: ignore[arg-type]


def test_sequence_from_json_bad_input():
    with pytest.raises(PresentationError):
        PresentationSequence.from_json("not json")


def test_sequence_add_step_enforces_cap():
    seq = PresentationSequence()
    for _ in range(MAX_STEPS_PER_PRESENTATION):
        seq.add_step(PresentationStep())
    with pytest.raises(PresentationError):
        seq.add_step(PresentationStep())


def test_sequence_add_step_rejects_duplicate_id():
    seq = PresentationSequence()
    s = PresentationStep()
    seq.add_step(s)
    with pytest.raises(PresentationError):
        seq.add_step(s)


def test_sequence_remove_step():
    seq = PresentationSequence()
    s = PresentationStep()
    seq.add_step(s)
    assert seq.remove_step(s.step_id) is True
    assert seq.step_count() == 0


def test_sequence_remove_unknown_step_returns_false():
    seq = PresentationSequence()
    assert seq.remove_step("does-not-exist") is False


def test_sequence_move_step():
    seq = PresentationSequence()
    a, b, c = PresentationStep(title="a"), PresentationStep(title="b"), PresentationStep(title="c")
    seq.add_step(a)
    seq.add_step(b)
    seq.add_step(c)
    assert seq.move_step(c.step_id, 0) is True
    assert seq.steps[0] is c


def test_sequence_move_step_clamps_out_of_bounds():
    seq = PresentationSequence()
    a = PresentationStep(title="a")
    b = PresentationStep(title="b")
    seq.add_step(a)
    seq.add_step(b)
    seq.move_step(a.step_id, 99)  # clamps to last
    assert seq.steps[-1] is a


def test_sequence_find_step():
    seq = PresentationSequence()
    s = PresentationStep(title="x")
    seq.add_step(s)
    assert seq.find_step(s.step_id) is s
    assert seq.find_step("nope") is None


def test_sequence_find_step_index():
    seq = PresentationSequence()
    a = PresentationStep()
    seq.add_step(a)
    assert seq.find_step_index(a.step_id) == 0
    assert seq.find_step_index("missing") == -1


def test_sequence_total_duration_sums_pauses():
    seq = PresentationSequence()
    seq.add_step(PresentationStep(pause_seconds=3.0))
    seq.add_step(PresentationStep(pause_seconds=5.0))
    assert seq.total_duration_seconds() == 8.0


def test_sequence_validate_flags_duplicate_step_ids():
    """A sequence whose internal state has somehow
    duplicated ids should fail validation."""
    seq = PresentationSequence()
    s1 = PresentationStep()
    s2 = PresentationStep()
    seq.steps = [s1, s2]
    s2.step_id = s1.step_id
    errs = seq.validate()
    assert any("duplicate step_id" in e for e in errs)


def test_sequence_touch_updates_timestamp():
    seq = PresentationSequence()
    seq.touch()
    assert seq.updated_at_iso


def test_schema_version_constant():
    assert PRESENTATION_SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# Resolved steps (post-inheritance)
# ---------------------------------------------------------------------------


def test_resolved_steps_inherits_camera_position():
    seq = PresentationSequence()
    seq.add_step(PresentationStep(camera_position=(1.0, 2.0, 3.0)))
    seq.add_step(PresentationStep(camera_position=None))
    seq.add_step(PresentationStep(camera_position=(10.0, 0.0, 0.0)))
    seq.add_step(PresentationStep(camera_position=None))
    resolved = seq.resolved_steps()
    assert resolved[0].camera_position == (1.0, 2.0, 3.0)
    assert resolved[1].camera_position == (1.0, 2.0, 3.0)
    assert resolved[2].camera_position == (10.0, 0.0, 0.0)
    assert resolved[3].camera_position == (10.0, 0.0, 0.0)


def test_resolved_steps_inherits_overlay_flags():
    seq = PresentationSequence()
    seq.add_step(PresentationStep(
        overlay_flags={"show_grid": True},
    ))
    seq.add_step(PresentationStep())
    resolved = seq.resolved_steps()
    assert resolved[1].overlay_flags == {"show_grid": True}


def test_resolved_steps_inherits_epoch_jd():
    seq = PresentationSequence()
    seq.add_step(PresentationStep(epoch_jd=2461041.5))
    seq.add_step(PresentationStep())
    resolved = seq.resolved_steps()
    assert resolved[1].epoch_jd == 2461041.5


def test_resolved_steps_inherits_annotation_visibility():
    seq = PresentationSequence()
    seq.add_step(PresentationStep(visible_annotation_indices=[0, 1]))
    seq.add_step(PresentationStep())
    resolved = seq.resolved_steps()
    assert resolved[1].visible_annotation_indices == [0, 1]


def test_resolved_steps_index_is_zero_based():
    seq = PresentationSequence()
    seq.add_step(PresentationStep())
    seq.add_step(PresentationStep())
    resolved = seq.resolved_steps()
    assert [r.index for r in resolved] == [0, 1]


def test_resolved_steps_deterministic_with_same_input():
    """Same input → same output, byte for byte."""
    seq = PresentationSequence()
    seq.add_step(PresentationStep(camera_position=(1, 2, 3)))
    seq.add_step(PresentationStep(camera_target=(4, 5, 6)))
    a = [r.__dict__ for r in seq.resolved_steps()]
    b = [r.__dict__ for r in seq.resolved_steps()]
    assert a == b


def test_resolved_returns_resolved_step_instances():
    seq = PresentationSequence()
    seq.add_step(PresentationStep())
    resolved = seq.resolved_steps()
    assert isinstance(resolved[0], ResolvedStep)


def test_empty_sequence_resolves_to_empty_list():
    seq = PresentationSequence()
    assert seq.resolved_steps() == []
