"""Tests for core.bookmarks (v0.6 bookmarks system)."""

from __future__ import annotations

import json

import pytest

from core.bookmarks import (
    BOOKMARK_KINDS,
    Bookmark,
    BookmarkList,
    bookmark_from_coordinate,
    bookmark_from_search_result,
    bookmark_from_target_lock,
    load_bookmarks,
    render_bookmarks,
    save_bookmarks,
)
from core.search import SearchResult
from core.target_lock import TargetLock


# ---------------------------------------------------------------------------
# Bookmark validation
# ---------------------------------------------------------------------------


def test_object_bookmark_requires_uid():
    with pytest.raises(ValueError):
        Bookmark(kind="object")


def test_coordinate_bookmark_requires_position():
    with pytest.raises(ValueError):
        Bookmark(kind="coordinate", label="x")


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        Bookmark(kind="quasi", uid="g:1")


def test_object_bookmark_auto_assigns_id_and_timestamp():
    bm = Bookmark(kind="object", uid="g:1")
    assert bm.id  # not empty
    assert len(bm.id) >= 6
    assert bm.created_iso  # ISO timestamp


def test_coordinate_bookmark_accepts_position():
    bm = Bookmark(
        kind="coordinate", label="here",
        x_c4d=1.0, y_c4d=2.0, z_c4d=3.0,
    )
    assert bm.has_c4d_position()
    assert bm.display_label() == "here"


def test_object_bookmark_display_label_falls_back_to_uid():
    assert Bookmark(kind="object", uid="g:1").display_label() == "g:1"


# ---------------------------------------------------------------------------
# BookmarkList CRUD
# ---------------------------------------------------------------------------


def test_add_appends_and_assigns_unique_ids():
    lst = BookmarkList()
    a = Bookmark(kind="object", uid="g:1")
    b = Bookmark(kind="object", uid="g:2")
    ok_a, _ = lst.add(a)
    ok_b, _ = lst.add(b)
    assert ok_a and ok_b
    assert len(lst) == 2
    assert a.id != b.id


def test_add_rejects_duplicate_object_uid():
    lst = BookmarkList()
    lst.add(Bookmark(kind="object", uid="g:1"))
    ok, returned = lst.add(Bookmark(kind="object", uid="g:1"))
    assert ok is False
    assert returned.uid == "g:1"
    assert len(lst) == 1


def test_add_rejects_duplicate_coordinate_position():
    lst = BookmarkList()
    lst.add(Bookmark(
        kind="coordinate", label="A", x_c4d=1.0, y_c4d=2.0, z_c4d=3.0,
    ))
    ok, _ = lst.add(Bookmark(
        kind="coordinate", label="B", x_c4d=1.0, y_c4d=2.0, z_c4d=3.0,
    ))
    assert ok is False


def test_remove_by_id():
    lst = BookmarkList()
    a = Bookmark(kind="object", uid="g:1")
    lst.add(a)
    removed = lst.remove(a.id)
    assert removed is a
    assert len(lst) == 0


def test_remove_unknown_returns_none():
    lst = BookmarkList()
    assert lst.remove("nope") is None


def test_move_reorders_entry():
    lst = BookmarkList()
    a = Bookmark(kind="object", uid="g:1", label="A")
    b = Bookmark(kind="object", uid="g:2", label="B")
    c = Bookmark(kind="object", uid="g:3", label="C")
    for x in (a, b, c):
        lst.add(x)
    assert lst.move(a.id, 2)
    assert [bm.uid for bm in lst.bookmarks] == ["g:2", "g:3", "g:1"]


def test_move_clamps_out_of_range_index():
    lst = BookmarkList()
    a = Bookmark(kind="object", uid="g:1")
    b = Bookmark(kind="object", uid="g:2")
    lst.add(a)
    lst.add(b)
    assert lst.move(a.id, 999)
    assert lst.bookmarks[-1] is a
    assert lst.move(b.id, -10)
    assert lst.bookmarks[0] is b


def test_rename_updates_label():
    lst = BookmarkList()
    a = Bookmark(kind="object", uid="g:1", label="A")
    lst.add(a)
    assert lst.rename(a.id, "Renamed") is True
    assert a.label == "Renamed"


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_to_json_and_from_json_round_trip():
    lst = BookmarkList()
    lst.add(Bookmark(kind="object", uid="g:1", label="A"))
    lst.add(Bookmark(kind="coordinate", label="here",
                     x_c4d=1.0, y_c4d=2.0, z_c4d=3.0))
    s = lst.to_json()
    parsed = BookmarkList.from_json(s)
    assert len(parsed) == 2
    assert parsed.bookmarks[0].uid == "g:1"
    assert parsed.bookmarks[1].kind == "coordinate"


def test_from_json_handles_corrupt_input():
    assert len(BookmarkList.from_json("{ broken")) == 0
    assert len(BookmarkList.from_json("")) == 0


# ---------------------------------------------------------------------------
# save / load
# ---------------------------------------------------------------------------


def test_save_then_load_round_trip(tmp_path):
    p = str(tmp_path / "bookmarks.json")
    lst = BookmarkList()
    a = Bookmark(kind="object", uid="g:1", label="Sirius")
    lst.add(a)
    saved = save_bookmarks(lst, p)
    assert saved == p
    loaded = load_bookmarks(p)
    assert len(loaded) == 1
    assert loaded.bookmarks[0].uid == "g:1"
    assert loaded.bookmarks[0].label == "Sirius"


def test_load_missing_file_returns_empty(tmp_path):
    assert len(load_bookmarks(str(tmp_path / "absent.json"))) == 0


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------


def test_from_search_result_keeps_uid_label_source_type():
    r = SearchResult(
        uid="sdss:9001", name="PHOTO", common_name="Friendly",
        catalog_source="SDSS", object_type="galaxy",
    )
    bm = bookmark_from_search_result(r)
    assert bm.kind == "object"
    assert bm.uid == "sdss:9001"
    assert bm.label == "Friendly"
    assert bm.catalog_source == "SDSS"
    assert bm.object_type == "galaxy"


def test_from_target_lock_keeps_position_triple():
    lock = TargetLock(
        uid="g:1", catalog_source="Gaia DR3", label="x",
        position_c4d=(1.0, 2.0, 3.0), position_pc=(1.0, 2.0, 3.0),
    )
    bm = bookmark_from_target_lock(lock)
    assert bm.kind == "object"
    assert bm.has_c4d_position()
    assert bm.has_pc_position()


def test_from_coordinate_builds_coordinate_bookmark():
    bm = bookmark_from_coordinate((1.0, 2.0, 3.0), "Anchor")
    assert bm.kind == "coordinate"
    assert bm.label == "Anchor"
    assert bm.x_c4d == 1.0


# ---------------------------------------------------------------------------
# Pretty rendering
# ---------------------------------------------------------------------------


def test_render_empty_bookmarks_message():
    out = render_bookmarks(BookmarkList())
    assert "No bookmarks" in out


def test_render_bookmarks_lists_each():
    lst = BookmarkList()
    lst.add(Bookmark(kind="object", uid="g:1", label="Sirius",
                     catalog_source="Gaia DR3"))
    lst.add(Bookmark(kind="coordinate", label="Anchor",
                     x_c4d=1.0, y_c4d=2.0, z_c4d=3.0))
    out = render_bookmarks(lst)
    assert "Sirius" in out
    assert "Anchor" in out
    assert "Gaia DR3" in out


def test_kind_constants_are_object_and_coordinate():
    assert "object" in BOOKMARK_KINDS
    assert "coordinate" in BOOKMARK_KINDS
