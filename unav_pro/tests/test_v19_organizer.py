"""v1.9 mission organizer tests — duplicate / rename / tag /
search / sort / package import-export."""

from __future__ import annotations

import json
import os

import pytest

from voyage import Mission, MissionWaypoint
from voyage.mission_manager import MissionManager


def _make_mission(title: str, **kwargs) -> Mission:
    return Mission(
        title=title,
        waypoints=[
            MissionWaypoint(kind="object", uid="x:1"),
        ],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Duplicate
# ---------------------------------------------------------------------------


def test_duplicate_creates_independent_copy(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    src = _make_mission("Alpha")
    mgr.create(src)
    clone = mgr.duplicate(src.mission_id)
    assert clone is not None
    assert clone.mission_id != src.mission_id
    assert "Copy of Alpha" in clone.title


def test_duplicate_with_explicit_title(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    src = _make_mission("Alpha")
    mgr.create(src)
    clone = mgr.duplicate(src.mission_id, new_title="Beta")
    assert clone.title == "Beta"


def test_duplicate_unknown_id_returns_none(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    assert mgr.duplicate("nope") is None


def test_duplicate_does_not_share_waypoints(tmp_path):
    """Mutating the clone's waypoints must not bleed into the
    source — the round-trip-through-JSON copy guarantees this."""
    mgr = MissionManager(missions_dir=str(tmp_path))
    src = _make_mission("Alpha")
    mgr.create(src)
    clone = mgr.duplicate(src.mission_id)
    clone.waypoints[0].label = "MUTATED"
    assert src.waypoints[0].label != "MUTATED"


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


def test_rename_updates_title_and_persists(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    m = _make_mission("Old")
    mgr.create(m)
    assert mgr.rename(m.mission_id, "New") is True
    assert mgr.get(m.mission_id).title == "New"
    # And the on-disk file reflects the rename.
    fresh = MissionManager(missions_dir=str(tmp_path))
    assert fresh.get(m.mission_id).title == "New"


def test_rename_rejects_empty_title(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    m = _make_mission("Old")
    mgr.create(m)
    assert mgr.rename(m.mission_id, "") is False
    assert mgr.rename(m.mission_id, "   ") is False


def test_rename_unknown_id_returns_false(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    assert mgr.rename("nope", "Title") is False


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_add_tags_dedup_lowercase(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    m = _make_mission("M")
    mgr.create(m)
    assert mgr.add_tags(m.mission_id, ["Solar", "STAR"]) is True
    assert m.tags == ["solar", "star"]
    # Adding existing returns False (nothing changed).
    assert mgr.add_tags(m.mission_id, ["solar"]) is False


def test_remove_tag(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    m = _make_mission("M", tags=["solar", "demo"])
    mgr.create(m)
    assert mgr.remove_tag(m.mission_id, "solar") is True
    assert "solar" not in m.tags
    assert mgr.remove_tag(m.mission_id, "missing") is False


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_by_title(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    mgr.create(_make_mission("Alpha trip"))
    mgr.create(_make_mission("Beta flight"))
    results = mgr.search("alpha")
    assert len(results) == 1
    assert "Alpha" in results[0].title


def test_search_by_tag(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    mgr.create(_make_mission("A", tags=["solar"]))
    mgr.create(_make_mission("B", tags=["extragalactic"]))
    assert len(mgr.search(tag="solar")) == 1
    assert len(mgr.search(tag="extragalactic")) == 1
    assert mgr.search(tag="missing") == []


def test_search_combines_query_and_tag(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    mgr.create(_make_mission("Alpha", tags=["solar"]))
    mgr.create(_make_mission("Alpha-2", tags=["extragalactic"]))
    results = mgr.search("alpha", tag="solar")
    assert len(results) == 1
    assert results[0].title == "Alpha"


def test_search_empty_query_returns_all(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    mgr.create(_make_mission("X"))
    mgr.create(_make_mission("Y"))
    assert len(mgr.search("")) == 2


# ---------------------------------------------------------------------------
# Sort
# ---------------------------------------------------------------------------


def test_sort_by_title(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    mgr.create(_make_mission("Charlie"))
    mgr.create(_make_mission("Alpha"))
    mgr.create(_make_mission("Bravo"))
    mgr.sort(by="title")
    assert [m.title for m in mgr.list_all()] == ["Alpha", "Bravo", "Charlie"]


def test_sort_by_waypoints(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    a = _make_mission("A")
    b = _make_mission("B")
    b.waypoints.append(MissionWaypoint(kind="object", uid="x:2"))
    mgr.create(a)
    mgr.create(b)
    mgr.sort(by="waypoints")
    assert [m.title for m in mgr.list_all()] == ["A", "B"]


def test_sort_unknown_key_raises(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    with pytest.raises(ValueError):
        mgr.sort(by="bogus")


# ---------------------------------------------------------------------------
# Packages
# ---------------------------------------------------------------------------


def test_export_then_import_package(tmp_path):
    src = MissionManager(missions_dir=str(tmp_path / "src"))
    src.create(_make_mission("A"))
    src.create(_make_mission("B"))
    pkg_path = str(tmp_path / "package.json")
    assert src.export_package(pkg_path) == 2

    dst = MissionManager(missions_dir=str(tmp_path / "dst"))
    n = dst.import_package(pkg_path)
    assert n == 2
    titles = [m.title for m in dst.list_all()]
    assert sorted(titles) == ["A", "B"]


def test_import_package_handles_missing_file(tmp_path):
    mgr = MissionManager(missions_dir=str(tmp_path))
    assert mgr.import_package(str(tmp_path / "no.json")) == 0


def test_import_package_handles_corrupt_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json", encoding="utf-8")
    mgr = MissionManager(missions_dir=str(tmp_path))
    assert mgr.import_package(str(bad)) == 0


def test_import_package_skips_malformed_entries(tmp_path):
    pkg = tmp_path / "pkg.json"
    pkg.write_text(json.dumps({
        "schema_version": 1,
        "missions": [
            {"title": "Good", "waypoints": []},
            "not a dict",  # malformed
            {"title": "Also Good", "waypoints": []},
        ],
    }), encoding="utf-8")
    mgr = MissionManager(missions_dir=str(tmp_path))
    assert mgr.import_package(str(pkg)) == 2


def test_import_package_collision_assigns_fresh_id(tmp_path):
    src = MissionManager(missions_dir=str(tmp_path / "src"))
    a = _make_mission("A")
    src.create(a)
    pkg_path = str(tmp_path / "pkg.json")
    src.export_package(pkg_path)
    # Re-importing into the same manager should collide and
    # assign a fresh id rather than overwriting.
    src.import_package(pkg_path)
    assert len(src) == 2
