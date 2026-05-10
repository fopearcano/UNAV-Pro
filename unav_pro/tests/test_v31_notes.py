"""v3.1 notes-system tests."""

from __future__ import annotations

import os

import pytest

from project import (
    NOTE_KIND_DATASET,
    NOTE_KIND_MISSION,
    NOTE_KIND_PROJECT,
    NotesStore,
    relative_path_for_note,
)


# ---------------------------------------------------------------------------
# relative_path_for_note
# ---------------------------------------------------------------------------


def test_project_note_path_is_fixed():
    assert relative_path_for_note(NOTE_KIND_PROJECT) == "notes/project.md"


def test_mission_note_path_uses_id():
    p = relative_path_for_note(NOTE_KIND_MISSION, "voyager-arrival")
    assert p == "notes/missions/voyager-arrival.md"


def test_dataset_note_path_uses_name():
    p = relative_path_for_note(NOTE_KIND_DATASET, "Gaia DR3")
    # Spaces normalised to underscores.
    assert p == "notes/datasets/Gaia_DR3.md"


def test_relative_path_sanitises_special_chars():
    p = relative_path_for_note(NOTE_KIND_MISSION, "weird/id:with*chars")
    # Slashes are filename-illegal; collapsed to underscores.
    assert "/" in p  # the separator chars in "notes/missions/"
    assert p.endswith(".md")
    assert "weird_id_with_chars" in p


def test_relative_path_rejects_unknown_kind():
    with pytest.raises(ValueError):
        relative_path_for_note("frobnicator")


def test_relative_path_requires_scope_id_for_mission():
    with pytest.raises(ValueError):
        relative_path_for_note(NOTE_KIND_MISSION)


# ---------------------------------------------------------------------------
# NotesStore: write / read / delete
# ---------------------------------------------------------------------------


def test_write_and_read_project_note(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_project_note("# Hello\n\nbody.")
    entry = store.read_project_note()
    assert entry is not None
    assert "Hello" in entry.body
    assert entry.kind == NOTE_KIND_PROJECT


def test_write_appends_trailing_newline(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_project_note("no trailing newline")
    body = store.read_project_note().body
    assert body.endswith("\n")


def test_write_mission_note_creates_subdir(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_mission_note("m1", "mission body")
    p = store.mission_note_path("m1")
    assert os.path.isfile(p)


def test_write_dataset_note_creates_subdir(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_dataset_note("Gaia DR3", "dataset body")
    p = store.dataset_note_path("Gaia DR3")
    assert os.path.isfile(p)


def test_read_missing_returns_none(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    assert store.read_project_note() is None
    assert store.read_mission_note("nope") is None
    assert store.read_dataset_note("nope") is None


def test_delete_returns_false_when_missing(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    assert store.delete_project_note() is False
    assert store.delete_mission_note("x") is False


def test_delete_returns_true_when_present(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_mission_note("m", "body")
    assert store.delete_mission_note("m") is True
    assert store.read_mission_note("m") is None


def test_write_with_empty_id_raises(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    with pytest.raises(ValueError):
        store.write_mission_note("", "body")
    with pytest.raises(ValueError):
        store.write_dataset_note("", "body")


# ---------------------------------------------------------------------------
# Filename safety: same input → same path
# ---------------------------------------------------------------------------


def test_safe_filename_is_deterministic(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    p1 = store.mission_note_path("Mission/With:Slashes")
    p2 = store.mission_note_path("Mission/With:Slashes")
    assert p1 == p2


def test_safe_filename_round_trip_writes_and_reads(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_mission_note("Tour: Beat 1", "body")
    entry = store.read_mission_note("Tour: Beat 1")
    assert entry is not None
    assert entry.body.strip() == "body"


# ---------------------------------------------------------------------------
# list_notes / count
# ---------------------------------------------------------------------------


def test_list_notes_orders_project_first(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_dataset_note("ds", "x")
    store.write_mission_note("m", "y")
    store.write_project_note("p")
    entries = store.list_notes()
    kinds = [e.kind for e in entries]
    assert kinds[0] == NOTE_KIND_PROJECT


def test_list_notes_returns_empty_for_blank_store(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    assert store.list_notes() == []


def test_count_matches_list_length(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_project_note("a")
    store.write_mission_note("m1", "b")
    store.write_dataset_note("d1", "c")
    assert store.count() == 3
    assert len(store.list_notes()) == 3


# ---------------------------------------------------------------------------
# annotation_summary
# ---------------------------------------------------------------------------


def test_annotation_summary_blank_store(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    assert "no notes" in store.annotation_summary().lower()


def test_annotation_summary_includes_each_note(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_project_note("project body")
    store.write_mission_note("m1", "mission body")
    text = store.annotation_summary()
    assert "project body" in text
    assert "mission body" in text
    assert "[mission] m1" in text


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_no_tmp_file_left_after_write(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_project_note("hello")
    notes_root = tmp_path / "notes"
    leftovers = [p for p in notes_root.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


# ---------------------------------------------------------------------------
# NoteEntry summary
# ---------------------------------------------------------------------------


def test_note_entry_short_summary_includes_first_line(tmp_path):
    store = NotesStore(str(tmp_path / "notes"))
    store.write_mission_note("m1", "First line\nsecond line\n")
    e = store.read_mission_note("m1")
    assert e is not None
    s = e.short_summary()
    assert "First line" in s
    assert "[mission:m1]" in s
