"""v3.8 chapter tests."""

from __future__ import annotations

import pytest

from presentation import (
    CHAPTER_SCHEMA_VERSION,
    MAX_CHAPTERS_PER_PRESENTATION,
    Chapter,
    ChapterError,
    ChapteredPresentation,
    chapters_from_step_groups,
)


# ---------------------------------------------------------------------------
# Chapter
# ---------------------------------------------------------------------------


def test_chapter_default_has_unique_id():
    a = Chapter()
    b = Chapter()
    assert a.chapter_id and b.chapter_id
    assert a.chapter_id != b.chapter_id


def test_chapter_round_trip():
    c = Chapter(
        title="Saturn",
        narration="Saturn approach narration.",
        presenter_notes="Mention Encke gap.",
        step_ids=["s1", "s2", "s3"],
        estimated_duration_seconds=60.0,
        overlay_flags={"show_distance_rings": True},
        science_flags={"show_motion_vectors": True},
        highlighted_annotation_indices=[1, 3],
        tags=["outer", "saturn"],
    )
    rt = Chapter.from_dict(c.to_dict())
    assert rt.title == "Saturn"
    assert rt.narration == "Saturn approach narration."
    assert rt.presenter_notes == "Mention Encke gap."
    assert rt.step_ids == ["s1", "s2", "s3"]
    assert rt.estimated_duration_seconds == 60.0
    assert rt.overlay_flags == {"show_distance_rings": True}
    assert rt.science_flags == {"show_motion_vectors": True}
    assert rt.highlighted_annotation_indices == [1, 3]
    assert rt.tags == ["outer", "saturn"]


def test_chapter_rejects_negative_duration():
    with pytest.raises(ChapterError):
        Chapter(estimated_duration_seconds=-1.0)


def test_chapter_normalises_tags_lowercase():
    c = Chapter(tags=["Intro", "Outer"])
    assert c.tags == ["intro", "outer"]


def test_chapter_step_count():
    c = Chapter(step_ids=["s1", "s2"])
    assert c.step_count() == 2
    assert not c.is_empty()


def test_chapter_short_summary():
    c = Chapter(title="Saturn", step_ids=["s1", "s2"], estimated_duration_seconds=10.0)
    s = c.short_summary()
    assert "Saturn" in s
    assert "2 step" in s
    assert "10s" in s


def test_chapter_from_non_dict_raises():
    with pytest.raises(ChapterError):
        Chapter.from_dict([])  # type: ignore[arg-type]


def test_chapter_from_dict_handles_missing_fields():
    c = Chapter.from_dict({"chapter_id": "x"})
    assert c.chapter_id == "x"
    assert c.step_ids == []


# ---------------------------------------------------------------------------
# ChapteredPresentation
# ---------------------------------------------------------------------------


def test_chaptered_default_is_valid():
    cp = ChapteredPresentation()
    assert cp.validate() == []
    assert cp.chapter_count() == 0
    assert cp.schema_version == CHAPTER_SCHEMA_VERSION


def test_chaptered_round_trip():
    cp = ChapteredPresentation(
        presentation_id="pres-x",
        title="Voyager Tour",
        description="d",
    )
    cp.add_chapter(Chapter(title="Intro", step_ids=["s1"]))
    cp.add_chapter(Chapter(title="Saturn", step_ids=["s2", "s3"]))
    rt = ChapteredPresentation.from_json(cp.to_json())
    assert rt.title == "Voyager Tour"
    assert rt.description == "d"
    assert rt.presentation_id == "pres-x"
    assert rt.chapter_count() == 2


def test_chaptered_rejects_newer_schema():
    with pytest.raises(ChapterError):
        ChapteredPresentation.from_dict({"schema_version": 999})


def test_chaptered_rejects_non_object_payload():
    with pytest.raises(ChapterError):
        ChapteredPresentation.from_dict([])  # type: ignore[arg-type]


def test_chaptered_from_json_bad_input():
    with pytest.raises(ChapterError):
        ChapteredPresentation.from_json("not json")


def test_chaptered_add_chapter_enforces_cap():
    cp = ChapteredPresentation()
    for _ in range(MAX_CHAPTERS_PER_PRESENTATION):
        cp.add_chapter(Chapter())
    with pytest.raises(ChapterError):
        cp.add_chapter(Chapter())


def test_chaptered_add_chapter_rejects_duplicate_id():
    cp = ChapteredPresentation()
    c = Chapter()
    cp.add_chapter(c)
    with pytest.raises(ChapterError):
        cp.add_chapter(c)


def test_chaptered_remove_chapter():
    cp = ChapteredPresentation()
    c = Chapter()
    cp.add_chapter(c)
    assert cp.remove_chapter(c.chapter_id) is True
    assert cp.chapter_count() == 0


def test_chaptered_remove_unknown_returns_false():
    cp = ChapteredPresentation()
    assert cp.remove_chapter("missing") is False


def test_chaptered_find_chapter():
    cp = ChapteredPresentation()
    c = Chapter(title="X")
    cp.add_chapter(c)
    assert cp.find_chapter(c.chapter_id) is c
    assert cp.find_chapter("missing") is None


def test_chaptered_find_chapter_index():
    cp = ChapteredPresentation()
    cp.add_chapter(Chapter())
    target = Chapter()
    cp.add_chapter(target)
    assert cp.find_chapter_index(target.chapter_id) == 1
    assert cp.find_chapter_index("missing") == -1


def test_chaptered_move_chapter():
    cp = ChapteredPresentation()
    a, b, c = Chapter(title="a"), Chapter(title="b"), Chapter(title="c")
    cp.add_chapter(a)
    cp.add_chapter(b)
    cp.add_chapter(c)
    assert cp.move_chapter(c.chapter_id, 0) is True
    assert cp.chapters[0] is c


def test_chaptered_move_chapter_clamps_index():
    cp = ChapteredPresentation()
    a = Chapter(title="a")
    b = Chapter(title="b")
    cp.add_chapter(a)
    cp.add_chapter(b)
    cp.move_chapter(a.chapter_id, 99)
    assert cp.chapters[-1] is a


def test_chaptered_total_estimated_duration():
    cp = ChapteredPresentation()
    cp.add_chapter(Chapter(estimated_duration_seconds=30.0))
    cp.add_chapter(Chapter(estimated_duration_seconds=20.0))
    assert cp.total_estimated_duration_seconds() == 50.0


def test_chaptered_step_id_to_chapter_map():
    cp = ChapteredPresentation()
    a = Chapter(step_ids=["s1", "s2"])
    b = Chapter(step_ids=["s3"])
    cp.add_chapter(a)
    cp.add_chapter(b)
    mapping = cp.step_id_to_chapter()
    assert mapping["s1"] == a.chapter_id
    assert mapping["s2"] == a.chapter_id
    assert mapping["s3"] == b.chapter_id


def test_chaptered_chapter_for_step_returns_first_match():
    cp = ChapteredPresentation()
    a = Chapter(step_ids=["s1"])
    b = Chapter(step_ids=["s2"])
    cp.add_chapter(a)
    cp.add_chapter(b)
    assert cp.chapter_for_step("s1") is a
    assert cp.chapter_for_step("s2") is b
    assert cp.chapter_for_step("missing") is None


def test_chaptered_validate_flags_duplicate_ids():
    cp = ChapteredPresentation()
    a = Chapter()
    b = Chapter()
    cp.chapters = [a, b]
    b.chapter_id = a.chapter_id
    errs = cp.validate()
    assert any("duplicate chapter_id" in e for e in errs)


def test_chaptered_touch_updates_timestamp():
    cp = ChapteredPresentation()
    cp.touch()
    assert cp.updated_at_iso


# ---------------------------------------------------------------------------
# Coverage check
# ---------------------------------------------------------------------------


def test_coverage_full():
    cp = ChapteredPresentation()
    cp.add_chapter(Chapter(step_ids=["s1", "s2", "s3"]))
    rep = cp.coverage_against_sequence(step_ids=["s1", "s2", "s3"])
    assert rep["fully_covered"] is True
    assert rep["uncovered"] == []
    assert rep["unknown"] == []


def test_coverage_partial():
    cp = ChapteredPresentation()
    cp.add_chapter(Chapter(step_ids=["s1", "s2"]))
    rep = cp.coverage_against_sequence(step_ids=["s1", "s2", "s3"])
    assert rep["fully_covered"] is False
    assert rep["uncovered"] == ["s3"]
    assert rep["unknown"] == []


def test_coverage_unknown_step_in_chapter():
    cp = ChapteredPresentation()
    cp.add_chapter(Chapter(step_ids=["s1", "s_typo"]))
    rep = cp.coverage_against_sequence(step_ids=["s1", "s2"])
    assert "s_typo" in rep["unknown"]
    assert "s2" in rep["uncovered"]


def test_coverage_handles_empty_inputs():
    cp = ChapteredPresentation()
    rep = cp.coverage_against_sequence(step_ids=[])
    assert rep["covered"] == []
    assert rep["uncovered"] == []
    assert rep["unknown"] == []
    assert rep["fully_covered"] is True


# ---------------------------------------------------------------------------
# chapters_from_step_groups
# ---------------------------------------------------------------------------


def test_factory_builds_correct_chapters():
    cp = chapters_from_step_groups(
        presentation_id="p",
        title="Tour",
        groups=[
            ("Intro", ["s1", "s2"]),
            ("Outro", ["s3"]),
        ],
        durations=[10.0, 5.0],
    )
    assert cp.title == "Tour"
    assert cp.presentation_id == "p"
    assert cp.chapter_count() == 2
    assert cp.chapters[0].title == "Intro"
    assert cp.chapters[0].step_ids == ["s1", "s2"]
    assert cp.chapters[0].estimated_duration_seconds == 10.0
    assert cp.chapters[1].estimated_duration_seconds == 5.0


def test_factory_with_missing_durations_uses_zero():
    cp = chapters_from_step_groups(
        presentation_id="p",
        groups=[
            ("Intro", ["s1"]),
            ("Outro", ["s2"]),
        ],
    )
    assert cp.chapters[0].estimated_duration_seconds == 0.0
    assert cp.chapters[1].estimated_duration_seconds == 0.0
