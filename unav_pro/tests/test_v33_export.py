"""v3.3 presentation-export tests."""

from __future__ import annotations

import json
import os

import pytest

from presentation import (
    PresentationPackagePayload,
    PresentationSequence,
    PresentationStep,
    build_presentation_payload,
    render_presentation_markdown,
    render_presenter_notes,
    write_presentation_files,
)


def _seq() -> PresentationSequence:
    seq = PresentationSequence(
        title="Voyager Talk",
        description="Outer-system tour.",
        presenter_notes="Overall presenter notes.",
        mission_ref="voyager-arrival",
        tags=["lecture"],
    )
    seq.add_step(PresentationStep(
        title="Saturn",
        narration="Saturn fills the frame.",
        presenter_notes="Mention Encke gap.",
        waypoint_ref="saturn",
        pause_seconds=8.0,
        epoch_jd=2461041.5,
        overlay_flags={"show_distance_rings": True},
        science_flags={"show_motion_vectors": False},
        visible_annotation_indices=[0, 1],
        highlighted_annotation_indices=[1],
        tags=["outer"],
    ))
    seq.add_step(PresentationStep(
        title="Uranus",
        narration="Now to Uranus.",
        waypoint_ref="uranus",
        pause_seconds=6.0,
    ))
    return seq


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------


def test_markdown_includes_title_and_description():
    md = render_presentation_markdown(_seq())
    assert "# Voyager Talk" in md
    assert "Outer-system tour." in md


def test_markdown_includes_step_titles():
    md = render_presentation_markdown(_seq())
    assert "Step 1: Saturn" in md
    assert "Step 2: Uranus" in md


def test_markdown_includes_overlay_flags_on():
    md = render_presentation_markdown(_seq())
    assert "show_distance_rings" in md


def test_markdown_includes_narration():
    md = render_presentation_markdown(_seq())
    assert "Saturn fills the frame" in md


def test_markdown_includes_presenter_notes_when_enabled():
    md = render_presentation_markdown(
        _seq(), include_presenter_notes=True,
    )
    assert "Encke gap" in md
    assert "> Presenter notes" in md


def test_markdown_excludes_presenter_notes_when_disabled():
    md = render_presentation_markdown(
        _seq(), include_presenter_notes=False,
    )
    assert "Encke gap" not in md


def test_markdown_with_resolved_steps_appended():
    md = render_presentation_markdown(
        _seq(), include_resolved=True,
    )
    assert "Resolved steps" in md


def test_markdown_handles_empty_presentation():
    md = render_presentation_markdown(PresentationSequence())
    assert "Untitled Presentation" in md


def test_markdown_handles_step_without_title():
    seq = PresentationSequence(title="X")
    s = PresentationStep()
    seq.add_step(s)
    md = render_presentation_markdown(seq)
    # Falls back to the step_id when title is empty.
    assert s.step_id in md


def test_markdown_includes_estimated_duration():
    md = render_presentation_markdown(_seq())
    assert "Estimated duration" in md


def test_markdown_includes_mission_ref():
    md = render_presentation_markdown(_seq())
    assert "voyager-arrival" in md


# ---------------------------------------------------------------------------
# Presenter notes export
# ---------------------------------------------------------------------------


def test_presenter_notes_dump_includes_overall():
    text = render_presenter_notes(_seq())
    assert "Overall presenter notes" in text


def test_presenter_notes_dump_includes_steps():
    text = render_presenter_notes(_seq())
    assert "[Step 1] Saturn" in text
    assert "Mention Encke gap" in text


def test_presenter_notes_dump_includes_narration():
    text = render_presenter_notes(_seq())
    assert "Saturn fills the frame" in text


def test_presenter_notes_dump_handles_empty():
    text = render_presenter_notes(PresentationSequence())
    assert text  # at least the header


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------


def test_payload_includes_three_files():
    payload = build_presentation_payload(_seq())
    assert payload.file_count() == 3
    merged = payload.merged()
    # All files live under presentations/.
    for k in merged:
        assert k.startswith("presentations/")


def test_payload_strips_presenter_notes_when_disabled():
    payload = build_presentation_payload(
        _seq(), include_presenter_notes=False,
    )
    assert not payload.presenter_notes
    # Markdown still emitted.
    assert payload.summaries


def test_payload_filenames_use_presentation_id():
    seq = _seq()
    payload = build_presentation_payload(seq)
    keys = list(payload.presentations.keys())
    assert any(seq.presentation_id in k for k in keys)


def test_payload_handles_empty_id():
    seq = _seq()
    seq.presentation_id = ""
    payload = build_presentation_payload(seq)
    keys = list(payload.presentations.keys())
    assert any("untitled-presentation" in k for k in keys)


def test_payload_is_empty_predicate():
    p = PresentationPackagePayload()
    assert p.is_empty()


# ---------------------------------------------------------------------------
# Disk write
# ---------------------------------------------------------------------------


def test_write_files_creates_outputs(tmp_path):
    seq = _seq()
    paths = write_presentation_files(seq, str(tmp_path))
    assert len(paths) == 3
    for p in paths:
        assert os.path.isfile(p)


def test_write_files_emits_clean_filenames(tmp_path):
    seq = _seq()
    write_presentation_files(seq, str(tmp_path))
    files = sorted(os.listdir(tmp_path))
    # No "presentations/" prefix in flat output.
    assert all("/" not in f for f in files)


def test_write_files_excludes_notes_when_flag_off(tmp_path):
    seq = _seq()
    write_presentation_files(
        seq, str(tmp_path), include_presenter_notes=False,
    )
    files = os.listdir(tmp_path)
    assert not any(f.endswith(".notes.txt") for f in files)


def test_write_files_atomic_no_tmp_left(tmp_path):
    seq = _seq()
    write_presentation_files(seq, str(tmp_path))
    files = os.listdir(tmp_path)
    assert not any(f.endswith(".tmp") for f in files)


def test_written_json_round_trips_back(tmp_path):
    seq = _seq()
    paths = write_presentation_files(seq, str(tmp_path))
    json_path = next(p for p in paths if p.endswith(".json"))
    with open(json_path, encoding="utf-8") as fh:
        text = fh.read()
    rt = PresentationSequence.from_json(text)
    assert rt.title == "Voyager Talk"
    assert rt.step_count() == 2
