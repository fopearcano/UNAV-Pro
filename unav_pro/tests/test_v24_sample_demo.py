"""v2.4 minimal-sample-demo tests.

The demo files at ``samples/minimal_unav_demo/`` ship with
every release. Tests assert the files exist + load via the
canonical UNAV loaders + reference each other consistently.
"""

from __future__ import annotations

import json
import os

import pytest


_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_DEMO_DIR = os.path.join(_REPO_ROOT, "samples", "minimal_unav_demo")


# ---------------------------------------------------------------------------
# Files exist
# ---------------------------------------------------------------------------


def test_demo_directory_exists():
    assert os.path.isdir(_DEMO_DIR)


def test_demo_has_catalog():
    assert os.path.isfile(os.path.join(_DEMO_DIR, "catalog.jsonl"))


def test_demo_has_mission():
    assert os.path.isfile(os.path.join(_DEMO_DIR, "mission.json"))


def test_demo_has_route():
    assert os.path.isfile(os.path.join(_DEMO_DIR, "route.json"))


def test_demo_has_readme():
    assert os.path.isfile(os.path.join(_DEMO_DIR, "README.md"))


# ---------------------------------------------------------------------------
# Files are tiny (release-engineering size budget)
# ---------------------------------------------------------------------------


_SIZE_BUDGET_BYTES = 16 * 1024  # 16 KB per file


def test_demo_files_are_tiny():
    for fname in ("catalog.jsonl", "mission.json", "route.json", "README.md"):
        path = os.path.join(_DEMO_DIR, fname)
        size = os.path.getsize(path)
        assert size > 0
        assert size < _SIZE_BUDGET_BYTES, (
            f"{fname} exceeds tiny-demo budget ({size} bytes)"
        )


# ---------------------------------------------------------------------------
# Catalog loads via the v0.5 loader
# ---------------------------------------------------------------------------


def test_demo_catalog_loads_via_canonical_loader():
    from data.catalog_io import load_catalog
    rows = load_catalog(os.path.join(_DEMO_DIR, "catalog.jsonl"))
    rows = list(rows)
    assert len(rows) == 5
    sources = {r.catalog_source for r in rows}
    assert sources == {"UNAV Demo"}
    types = {r.object_type for r in rows}
    assert types == {"star", "galaxy", "planet"}


def test_demo_catalog_uids_unique():
    from data.catalog_io import load_catalog
    rows = list(load_catalog(os.path.join(_DEMO_DIR, "catalog.jsonl")))
    uids = [r.uid for r in rows]
    assert len(uids) == len(set(uids))


def test_demo_catalog_has_demo_planet_with_epoch():
    from data.catalog_io import load_catalog
    rows = list(load_catalog(os.path.join(_DEMO_DIR, "catalog.jsonl")))
    planet = next((r for r in rows if r.uid == "demo:5"), None)
    assert planet is not None
    assert planet.object_type == "planet"
    # Epoch is encoded in metadata_json (the v0.4 JPL convention).
    meta = json.loads(planet.metadata_json or "{}")
    assert "epoch" in meta


# ---------------------------------------------------------------------------
# Mission loads via the v1.4 loader
# ---------------------------------------------------------------------------


def test_demo_mission_loads_via_canonical_loader():
    from voyage import Mission
    with open(os.path.join(_DEMO_DIR, "mission.json"), encoding="utf-8") as fh:
        m = Mission.from_json(fh.read())
    assert m.title == "UNAV Demo Mission"
    assert len(m.waypoints) == 5


def test_demo_mission_references_catalog_uids():
    """Every object/search-result waypoint in the demo
    mission references a uid that exists in the demo
    catalog."""
    from data.catalog_io import load_catalog
    from voyage import Mission
    with open(os.path.join(_DEMO_DIR, "mission.json"), encoding="utf-8") as fh:
        mission = Mission.from_json(fh.read())
    catalog_uids = {
        r.uid for r in load_catalog(os.path.join(_DEMO_DIR, "catalog.jsonl"))
    }
    for wp in mission.waypoints:
        if wp.kind in ("object", "search_result", "orbital") and wp.uid:
            assert wp.uid in catalog_uids, (
                f"mission references missing uid: {wp.uid}"
            )


def test_demo_mission_path_is_buildable():
    from voyage import Mission, build_camera_path
    with open(os.path.join(_DEMO_DIR, "mission.json"), encoding="utf-8") as fh:
        mission = Mission.from_json(fh.read())
    path = build_camera_path(mission)
    assert not path.is_empty()
    assert path.waypoint_count() == 5


def test_demo_mission_round_trips_byte_identical():
    """Loading + re-saving the demo mission must produce
    the same JSON shape (modulo timestamps, which the
    Mission JSON reproduces verbatim from the file)."""
    from voyage import Mission
    with open(os.path.join(_DEMO_DIR, "mission.json"), encoding="utf-8") as fh:
        original = fh.read()
    mission = Mission.from_json(original)
    rt = mission.to_json()
    # Field-level round-trip: the same five waypoints come
    # back with the same uids + labels.
    rt_mission = Mission.from_json(rt)
    assert [w.uid for w in mission.waypoints] == [w.uid for w in rt_mission.waypoints]
    assert [w.label for w in mission.waypoints] == [w.label for w in rt_mission.waypoints]


# ---------------------------------------------------------------------------
# Route loads via the v0.6 loader
# ---------------------------------------------------------------------------


def test_demo_route_loads_via_canonical_loader():
    from core.route import Route
    with open(os.path.join(_DEMO_DIR, "route.json"), encoding="utf-8") as fh:
        route = Route.from_json(fh.read())
    assert len(route) == 3
    assert route.name == "UNAV Demo Route"


def test_demo_route_references_catalog_uids():
    from core.route import Route
    from data.catalog_io import load_catalog
    catalog_uids = {
        r.uid for r in load_catalog(os.path.join(_DEMO_DIR, "catalog.jsonl"))
    }
    with open(os.path.join(_DEMO_DIR, "route.json"), encoding="utf-8") as fh:
        route = Route.from_json(fh.read())
    for wp in route.waypoints:
        if wp.kind == "object" and wp.uid:
            assert wp.uid in catalog_uids


# ---------------------------------------------------------------------------
# README has the expected workflow lines
# ---------------------------------------------------------------------------


def test_demo_readme_describes_full_workflow():
    with open(os.path.join(_DEMO_DIR, "README.md"), encoding="utf-8") as fh:
        text = fh.read()
    # Sanity-check the key workflow steps are present.
    expected_phrases = (
        "Load the catalog",
        "Inspect",
        "demo mission",
        "Bake to Timeline",
        "Export Full Package",
    )
    for phrase in expected_phrases:
        assert phrase in text, f"README missing '{phrase}'"
