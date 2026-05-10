"""v3.8 exhibition-export tests."""

from __future__ import annotations

import json
import os

import pytest

from presentation import (
    EXHIBITION_PACKAGE_SCHEMA_VERSION,
    Chapter,
    ChapteredPresentation,
    ExhibitionPackagePayload,
    build_exhibition_package,
    render_chapter_summary,
    render_cue_sheet,
    write_exhibition_package,
)


def _chaptered() -> ChapteredPresentation:
    cp = ChapteredPresentation(
        presentation_id="voyager-tour",
        title="Voyager Tour",
        description="Three-act demo",
    )
    cp.add_chapter(Chapter(
        title="Intro",
        narration="Welcome to the tour.",
        presenter_notes="Check audience first.",
        step_ids=["step-a", "step-b"],
        estimated_duration_seconds=60.0,
    ))
    cp.add_chapter(Chapter(
        title="Saturn",
        narration="Saturn here.",
        presenter_notes="Encke gap.",
        step_ids=["step-c"],
        estimated_duration_seconds=120.0,
        overlay_flags={"show_distance_rings": True},
    ))
    cp.add_chapter(Chapter(
        title="Outro",
        step_ids=["step-d"],
        estimated_duration_seconds=30.0,
    ))
    return cp


# ---------------------------------------------------------------------------
# Schema version constant
# ---------------------------------------------------------------------------


def test_exhibition_package_schema_version_documented():
    assert EXHIBITION_PACKAGE_SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# build_exhibition_package
# ---------------------------------------------------------------------------


def test_build_package_includes_three_files_by_default():
    payload = build_exhibition_package(chaptered=_chaptered())
    assert isinstance(payload, ExhibitionPackagePayload)
    assert payload.file_count() == 3
    keys = sorted(payload.files)
    assert any(k.endswith(".exhibition.json") for k in keys)
    assert any(k.endswith(".chapter_summary.md") for k in keys)
    assert any(k.endswith(".cue_sheet.md") for k in keys)


def test_build_package_embeds_presentation_json_when_supplied():
    payload = build_exhibition_package(
        chaptered=_chaptered(),
        presentation_json="{\"title\": \"x\"}",
    )
    assert any(k.endswith(".presentation.json") for k in payload.files)


def test_build_package_uses_presentation_id_as_filename_prefix():
    payload = build_exhibition_package(chaptered=_chaptered())
    keys = list(payload.files)
    assert all(k.startswith("voyager-tour.") for k in keys)


def test_build_package_falls_back_to_default_prefix():
    cp = _chaptered()
    cp.presentation_id = ""
    payload = build_exhibition_package(chaptered=cp)
    keys = list(payload.files)
    assert all(k.startswith("exhibition.") for k in keys)


def test_build_package_omits_presenter_notes_when_disabled():
    cp = _chaptered()
    payload = build_exhibition_package(
        chaptered=cp, include_presenter_notes=False,
    )
    summary = next(
        v for k, v in payload.files.items()
        if k.endswith(".chapter_summary.md")
    )
    assert "Encke" not in summary
    assert "Presenter notes" not in summary


def test_build_package_includes_presenter_notes_when_enabled():
    cp = _chaptered()
    payload = build_exhibition_package(
        chaptered=cp, include_presenter_notes=True,
    )
    summary = next(
        v for k, v in payload.files.items()
        if k.endswith(".chapter_summary.md")
    )
    assert "Encke" in summary


def test_payload_is_empty_predicate():
    assert ExhibitionPackagePayload().is_empty()
    assert ExhibitionPackagePayload(files={"x.json": "x"}).is_empty() is False


# ---------------------------------------------------------------------------
# render_chapter_summary
# ---------------------------------------------------------------------------


def test_chapter_summary_includes_title():
    cp = _chaptered()
    md = render_chapter_summary(cp)
    assert "# Voyager Tour" in md


def test_chapter_summary_includes_chapters():
    cp = _chaptered()
    md = render_chapter_summary(cp)
    assert "Chapter 1: Intro" in md
    assert "Chapter 2: Saturn" in md
    assert "Chapter 3: Outro" in md


def test_chapter_summary_total_runtime():
    cp = _chaptered()
    md = render_chapter_summary(cp)
    # 60 + 120 + 30 = 210 seconds (~3.5 min)
    assert "210" in md
    assert "3.5 min" in md


def test_chapter_summary_handles_empty_chapters():
    md = render_chapter_summary(ChapteredPresentation(title="Empty"))
    assert "no chapters defined" in md


def test_chapter_summary_renders_overlay_flags():
    cp = _chaptered()
    md = render_chapter_summary(cp)
    assert "show_distance_rings" in md


# ---------------------------------------------------------------------------
# render_cue_sheet
# ---------------------------------------------------------------------------


def test_cue_sheet_includes_each_step():
    cp = _chaptered()
    md = render_cue_sheet(cp)
    for step in ("step-a", "step-b", "step-c", "step-d"):
        assert step in md


def test_cue_sheet_table_header():
    md = render_cue_sheet(_chaptered())
    assert "| # | chapter |" in md


def test_cue_sheet_has_total_runtime():
    cp = _chaptered()
    md = render_cue_sheet(cp)
    assert "Total estimated runtime" in md


def test_cue_sheet_handles_empty_chapters():
    md = render_cue_sheet(ChapteredPresentation())
    assert "no chapters defined" in md


def test_cue_sheet_omits_presenter_notes_when_disabled():
    cp = _chaptered()
    md = render_cue_sheet(cp, include_presenter_notes=False)
    assert "Encke" not in md


# ---------------------------------------------------------------------------
# write_exhibition_package
# ---------------------------------------------------------------------------


def test_write_exhibition_package_creates_files(tmp_path):
    payload = build_exhibition_package(chaptered=_chaptered())
    out = write_exhibition_package(payload, str(tmp_path / "exh"))
    assert len(out) == 3
    for path in out:
        assert os.path.isfile(path)


def test_write_exhibition_package_atomic_no_tmp(tmp_path):
    payload = build_exhibition_package(chaptered=_chaptered())
    write_exhibition_package(payload, str(tmp_path / "exh"))
    leftovers = []
    for root, _dirs, files in os.walk(str(tmp_path / "exh")):
        leftovers.extend(f for f in files if f.endswith(".tmp"))
    assert leftovers == []


def test_write_rejects_none_payload(tmp_path):
    with pytest.raises(ValueError):
        write_exhibition_package(None, str(tmp_path / "out"))  # type: ignore[arg-type]


def test_written_json_round_trips():
    payload = build_exhibition_package(chaptered=_chaptered())
    json_body = next(
        v for k, v in payload.files.items()
        if k.endswith(".exhibition.json")
    )
    decoded = json.loads(json_body)
    assert decoded["title"] == "Voyager Tour"
    assert len(decoded["chapters"]) == 3


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_chapter_summary_deterministic_modulo_timestamp():
    cp = _chaptered()
    a = render_chapter_summary(cp)
    b = render_chapter_summary(cp)
    def strip(text):
        return "\n".join(
            line for line in text.splitlines()
            if not line.startswith("*Generated:")
        )
    assert strip(a) == strip(b)


def test_cue_sheet_deterministic_modulo_timestamp():
    cp = _chaptered()
    a = render_cue_sheet(cp)
    b = render_cue_sheet(cp)
    def strip(text):
        return "\n".join(
            line for line in text.splitlines()
            if not line.startswith("*Generated:")
        )
    assert strip(a) == strip(b)
