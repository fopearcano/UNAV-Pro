"""v3.4 internal-beta demo workspace tests.

The bundled `samples/internal_beta_demo/` workspace is
part of the release contract: every v3.4 release ships
it; the beta checklist walks through it; tests verify
its on-disk shape.
"""

from __future__ import annotations

import json
import os

import pytest


_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_DEMO = os.path.join(_REPO_ROOT, "samples", "internal_beta_demo")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def test_demo_dir_exists():
    assert os.path.isdir(_DEMO)


@pytest.mark.parametrize("relpath", [
    "project_manifest.json",
    "README.md",
    "datasets/gaia_demo.jsonl",
    "datasets/jpl_demo.jsonl",
    "missions/demo_tour.json",
    "routes/demo_route.json",
    "presentations/demo_talk.json",
    "notes/project.md",
])
def test_demo_required_file_present(relpath):
    path = os.path.join(_DEMO, relpath)
    assert os.path.isfile(path), f"missing {relpath}"


# ---------------------------------------------------------------------------
# Files are tiny
# ---------------------------------------------------------------------------


_MAX_FILE_BYTES = 32 * 1024


def test_every_demo_file_under_32kb():
    too_big = []
    for root, _dirs, files in os.walk(_DEMO):
        for f in files:
            path = os.path.join(root, f)
            size = os.path.getsize(path)
            if size > _MAX_FILE_BYTES:
                too_big.append((path, size))
    assert too_big == [], f"oversized: {too_big}"


# ---------------------------------------------------------------------------
# Manifest loads cleanly
# ---------------------------------------------------------------------------


def test_manifest_loads_via_workspace_layer():
    from project import open_workspace
    ws = open_workspace(_DEMO)
    assert ws.manifest.project_name == "UNAV Internal Beta Demo"
    assert ws.manifest.plugin_version == "3.4.0"
    assert len(ws.manifest.datasets) == 2
    assert len(ws.manifest.missions) == 1
    assert len(ws.manifest.routes) == 1


def test_manifest_passes_validation():
    from project import open_workspace
    ws = open_workspace(_DEMO)
    assert ws.manifest.validate() == []


def test_manifest_is_intact_on_disk():
    from project import open_workspace
    ws = open_workspace(_DEMO)
    assert ws.is_intact()


# ---------------------------------------------------------------------------
# Datasets load + carry provenance
# ---------------------------------------------------------------------------


def test_gaia_demo_loads_via_canonical_loader():
    from data.catalog_io import load_catalog
    rows = list(load_catalog(
        os.path.join(_DEMO, "datasets", "gaia_demo.jsonl"),
    ))
    assert len(rows) == 5
    sources = {r.catalog_source for r in rows}
    assert sources == {"Gaia DR3 (demo)"}


def test_gaia_demo_rows_carry_provenance():
    from data import read_provenance
    from data.catalog_io import load_catalog
    rows = list(load_catalog(
        os.path.join(_DEMO, "datasets", "gaia_demo.jsonl"),
    ))
    for r in rows:
        rec = read_provenance(r)
        assert rec is not None
        assert rec.connector == "gaia_connector"


def test_jpl_demo_loads_three_bodies():
    from data.catalog_io import load_catalog
    rows = list(load_catalog(
        os.path.join(_DEMO, "datasets", "jpl_demo.jsonl"),
    ))
    assert len(rows) == 3
    names = {r.name for r in rows}
    assert names == {"Mercury", "Earth", "Mars"}


def test_jpl_demo_rows_have_epoch():
    from data.catalog_io import load_catalog
    rows = list(load_catalog(
        os.path.join(_DEMO, "datasets", "jpl_demo.jsonl"),
    ))
    for r in rows:
        meta = json.loads(r.metadata_json or "{}")
        assert "epoch_jd" in meta


# ---------------------------------------------------------------------------
# Mission + route + presentation load cleanly
# ---------------------------------------------------------------------------


def test_mission_loads_and_validates():
    from voyage import Mission
    with open(os.path.join(_DEMO, "missions", "demo_tour.json"),
              encoding="utf-8") as fh:
        mission = Mission.from_json(fh.read())
    assert mission.title == "UNAV Internal Beta Tour"
    assert len(mission.waypoints) == 3


def test_route_loads():
    from core.route import Route
    with open(os.path.join(_DEMO, "routes", "demo_route.json"),
              encoding="utf-8") as fh:
        route = Route.from_json(fh.read())
    assert len(route) == 3


def test_presentation_loads():
    from presentation import PresentationSequence
    with open(os.path.join(_DEMO, "presentations", "demo_talk.json"),
              encoding="utf-8") as fh:
        seq = PresentationSequence.from_json(fh.read())
    assert seq.title == "UNAV Internal Beta Talk"
    assert seq.step_count() == 3
    assert seq.mission_ref == "beta-demo-tour"


def test_presentation_steps_are_resolvable():
    """Every step's resolved view must produce a complete
    record (no exceptions, every field populated by
    inheritance)."""
    from presentation import PresentationSequence
    with open(os.path.join(_DEMO, "presentations", "demo_talk.json"),
              encoding="utf-8") as fh:
        seq = PresentationSequence.from_json(fh.read())
    resolved = seq.resolved_steps()
    assert len(resolved) == seq.step_count()


def test_demo_validation_clean():
    """Run the v3.2 audit against the bundled Gaia demo
    rows: no errors expected (warnings ok)."""
    from data import validate_objects
    from data.catalog_io import load_catalog
    rows = list(load_catalog(
        os.path.join(_DEMO, "datasets", "gaia_demo.jsonl"),
    ))
    rep = validate_objects(rows, include_no_provenance_probe=False)
    error_count = rep.counts.by_severity.get("error", 0)
    assert error_count == 0


# ---------------------------------------------------------------------------
# README sanity
# ---------------------------------------------------------------------------


def test_readme_describes_layout():
    with open(os.path.join(_DEMO, "README.md"),
              encoding="utf-8") as fh:
        text = fh.read()
    for keyword in (
        "internal_beta_demo",
        "datasets",
        "missions",
        "presentations",
        "Open Workspace",
    ):
        assert keyword in text, f"README missing '{keyword}'"
