"""Tests for core.dataset_registry and the manager controller's
non-c4d code paths. Pure CPython, no Cinema 4D."""

from __future__ import annotations

import json
import math
import os

import pytest

from core import dataset_registry
from core.dataset_registry import (
    DatasetEntry,
    DatasetRegistry,
    DatasetStats,
    REGISTRY_SCHEMA_VERSION,
    bootstrap_with_sample,
    default_registry_path,
    render_registry,
    scan_dataset_stats,
)
from data.catalog_io import write_catalog
from data.schema import CatalogObject, compute_derived_fields


# ---------------------------------------------------------------------------
# Fixtures — small catalogs on disk
# ---------------------------------------------------------------------------


def _make_objects(prefix: str, n: int = 3, source: str = "unav_sample"):
    out = []
    for i in range(n):
        obj = CatalogObject(
            uid=f"{prefix}-{i}",
            catalog_source=source,
            object_type="star",
            ra_deg=10.0 + i,
            dec_deg=-20.0,
            distance_parsec=10.0 + i,
            apparent_magnitude=5.0 + i * 0.1,
            spectral_type="G2V",
        )
        compute_derived_fields(obj)
        out.append(obj)
    return out


@pytest.fixture
def small_catalog(tmp_path):
    path = str(tmp_path / "small.jsonl")
    write_catalog(_make_objects("a", n=4), path)
    return path


@pytest.fixture
def overlap_catalog(tmp_path):
    """Has the same uid prefix as small_catalog so collisions are
    guaranteed without namespacing."""
    path = str(tmp_path / "overlap.jsonl")
    write_catalog(_make_objects("a", n=3), path)
    return path


@pytest.fixture
def disjoint_catalog(tmp_path):
    path = str(tmp_path / "disjoint.jsonl")
    write_catalog(_make_objects("b", n=2, source="other"), path)
    return path


# ---------------------------------------------------------------------------
# DatasetEntry
# ---------------------------------------------------------------------------


def test_entry_validates_required_fields():
    with pytest.raises(ValueError):
        DatasetEntry(name="", path="/x")
    with pytest.raises(ValueError):
        DatasetEntry(name="x", path="")


def test_entry_to_dict_round_trip(small_catalog):
    e = DatasetEntry(name="x", path=small_catalog, enabled=False)
    e.stats = DatasetStats(object_count=4, bounding_radius_pc=12.0,
                           sources=["unav_sample"], available_fields=["uid"])
    out = DatasetEntry.from_dict(e.to_dict())
    assert out.name == "x"
    assert out.enabled is False
    assert out.stats is not None
    assert out.stats.object_count == 4


def test_entry_is_indexed_reflects_path(tmp_path, small_catalog):
    e = DatasetEntry(name="x", path=small_catalog)
    assert not e.is_indexed
    e.index_path = str(tmp_path)  # exists
    assert e.is_indexed
    e.index_path = str(tmp_path / "nope")  # missing
    assert not e.is_indexed


def test_entry_file_exists_predicate(small_catalog):
    e = DatasetEntry(name="x", path=small_catalog)
    assert e.file_exists is True
    e.path = "/path/that/does/not/exist.jsonl"
    assert e.file_exists is False


# ---------------------------------------------------------------------------
# scan_dataset_stats
# ---------------------------------------------------------------------------


def test_scan_dataset_stats_populates_counts(small_catalog):
    stats = scan_dataset_stats(small_catalog)
    assert stats.object_count == 4
    assert stats.bounding_radius_pc > 0
    assert "uid" in stats.available_fields
    assert "ra_deg" in stats.available_fields
    assert stats.sources == ["unav_sample"]
    assert stats.last_scanned_iso


def test_scan_dataset_stats_excludes_cosmetic_fields(small_catalog):
    stats = scan_dataset_stats(small_catalog)
    assert "display_color_rgb" not in stats.available_fields


def test_scan_dataset_stats_radius_matches_max_distance(small_catalog):
    stats = scan_dataset_stats(small_catalog)
    # max obj cartesian distance corresponds to obj 3 (distance_parsec=13)
    expected = 13.0
    assert math.isclose(stats.bounding_radius_pc, expected, rel_tol=1e-6)


def test_scan_dataset_stats_raises_on_missing_file():
    from data.catalog_io import CatalogIOError

    with pytest.raises(CatalogIOError):
        scan_dataset_stats("/path/that/does/not/exist.jsonl")


# ---------------------------------------------------------------------------
# DatasetRegistry — CRUD
# ---------------------------------------------------------------------------


def test_registry_starts_empty():
    r = DatasetRegistry()
    assert len(r) == 0
    assert r.names() == []


def test_registry_add_path_scans_and_appends(small_catalog):
    r = DatasetRegistry()
    e = r.add_path(small_catalog)
    assert len(r) == 1
    assert e.stats is not None
    assert e.stats.object_count == 4


def test_registry_add_path_picks_unique_name(small_catalog, tmp_path):
    r = DatasetRegistry()
    a = r.add_path(small_catalog, name="dup")
    # Re-adding with the same explicit name should fail.
    with pytest.raises(ValueError):
        r.add_path(small_catalog, name="dup")
    # Auto-name picks a non-colliding suffix.
    other = str(tmp_path / "different.jsonl")
    write_catalog(_make_objects("c"), other)
    second = r.add_path(other, name=None)
    assert second.name not in (a.name,)


def test_registry_add_path_handles_missing_file_gracefully():
    r = DatasetRegistry()
    e = r.add_path(
        "/path/that/does/not/exist.jsonl",
        name="ghost",
        scan=True,
    )
    assert e in r.entries
    assert "scan failed" in (e.notes or "")
    assert e.stats is None
    assert not e.file_exists


def test_registry_remove_returns_entry(small_catalog):
    r = DatasetRegistry()
    e = r.add_path(small_catalog, name="a")
    out = r.remove("a")
    assert out is e
    assert len(r) == 0
    assert r.remove("missing") is None


def test_registry_set_enabled(small_catalog):
    r = DatasetRegistry()
    r.add_path(small_catalog, name="a")
    assert r.set_enabled("a", False) is True
    assert r.find("a").enabled is False
    assert r.set_enabled("missing", True) is False


def test_registry_set_index_path(small_catalog, tmp_path):
    r = DatasetRegistry()
    r.add_path(small_catalog, name="a")
    p = str(tmp_path / "index_dir")
    assert r.set_index_path("a", p) is True
    assert r.find("a").index_path == p


def test_registry_rescan_updates_stats(small_catalog):
    r = DatasetRegistry()
    e = r.add_path(small_catalog, name="a")
    # Wipe stats and re-scan.
    e.stats = None
    out = r.rescan("a")
    assert out is e
    assert e.stats is not None
    assert e.stats.object_count == 4


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_registry_save_load_round_trip(tmp_path, small_catalog):
    path = str(tmp_path / "registry.json")
    r = DatasetRegistry()
    r.add_path(small_catalog, name="a")
    r.add_path(small_catalog, name="b", enabled=False)
    saved = r.save(path)
    assert os.path.exists(saved)
    raw = json.loads(open(saved).read())
    assert raw["schema_version"] == REGISTRY_SCHEMA_VERSION
    loaded = DatasetRegistry.load(path)
    assert loaded.names() == ["a", "b"]
    assert loaded.find("b").enabled is False
    assert loaded.find("a").stats is not None


def test_registry_load_missing_returns_empty(tmp_path):
    out = DatasetRegistry.load(str(tmp_path / "no.json"))
    assert isinstance(out, DatasetRegistry)
    assert len(out) == 0


def test_registry_load_corrupt_returns_empty(tmp_path):
    p = str(tmp_path / "bad.json")
    with open(p, "w") as fh:
        fh.write("{not valid json")
    out = DatasetRegistry.load(p)
    assert len(out) == 0


def test_registry_load_skips_malformed_entry(tmp_path):
    p = str(tmp_path / "mixed.json")
    with open(p, "w") as fh:
        json.dump(
            {
                "schema_version": 1,
                "datasets": [
                    {"name": "ok", "path": "/x"},
                    {"name": "", "path": ""},  # invalid; should be skipped
                ],
            },
            fh,
        )
    out = DatasetRegistry.load(p)
    assert out.names() == ["ok"]


# ---------------------------------------------------------------------------
# Merge (the headline behaviour)
# ---------------------------------------------------------------------------


def test_merge_active_combines_enabled_only(small_catalog, disjoint_catalog):
    r = DatasetRegistry()
    r.add_path(small_catalog, name="A")
    r.add_path(disjoint_catalog, name="B", enabled=False)
    result = r.merge_active()
    assert result.total_objects == 4
    assert result.per_dataset_counts == {"A": 4}


def test_merge_active_namespaces_uids_and_avoids_collision(
    small_catalog, overlap_catalog,
):
    r = DatasetRegistry()
    r.add_path(small_catalog, name="A")
    r.add_path(overlap_catalog, name="B")
    result = r.merge_active()
    # Both files use uid prefix "a-" with 4 and 3 rows respectively.
    # Without namespacing they'd collide on "a-0", "a-1", "a-2".
    # With namespacing on (default), both flow through.
    assert result.total_objects == 7
    uids = {o.uid for o in result.objects}
    assert "A:a-0" in uids
    assert "B:a-0" in uids
    assert result.duplicates_skipped == 0
    assert result.per_dataset_counts == {"A": 4, "B": 3}


def test_merge_active_disabling_namespace_exposes_collisions(
    small_catalog, overlap_catalog,
):
    r = DatasetRegistry()
    r.add_path(small_catalog, name="A", namespace=False)
    r.add_path(overlap_catalog, name="B", namespace=False)
    result = r.merge_active()
    # Collisions: a-0..a-2 appear in both files. The first dataset
    # wins; later duplicates are counted.
    assert result.total_objects == 4
    assert result.duplicates_skipped == 3
    assert result.per_dataset_counts == {"A": 4, "B": 0}


def test_merge_active_records_per_entry_errors(tmp_path, small_catalog):
    r = DatasetRegistry()
    r.add_path(small_catalog, name="ok")
    # Manually attach a broken entry — bypasses add_path's scan.
    r.entries.append(
        DatasetEntry(name="broken", path="/path/does/not/exist.jsonl"),
    )
    result = r.merge_active()
    assert "broken" in result.errors
    assert result.per_dataset_counts == {"ok": 4}
    assert result.total_objects == 4


def test_merge_active_raise_propagates_when_requested(small_catalog):
    from data.catalog_io import CatalogIOError

    r = DatasetRegistry()
    r.entries.append(
        DatasetEntry(name="broken", path="/path/does/not/exist.jsonl"),
    )
    with pytest.raises(CatalogIOError):
        r.merge_active(on_error="raise")


def test_merge_short_summary_includes_dupes_and_errors(
    small_catalog, overlap_catalog,
):
    r = DatasetRegistry()
    r.add_path(small_catalog, name="A", namespace=False)
    r.add_path(overlap_catalog, name="B", namespace=False)
    text = r.merge_active().short_summary()
    assert "duplicate uid(s) skipped" in text


# ---------------------------------------------------------------------------
# Pretty rendering
# ---------------------------------------------------------------------------


def test_render_registry_empty_friendly():
    text = render_registry(DatasetRegistry())
    assert "No datasets registered" in text


def test_render_registry_lists_names_and_flags(small_catalog):
    r = DatasetRegistry()
    r.add_path(small_catalog, name="A", enabled=True)
    r.add_path(small_catalog, name="B", enabled=False)
    text = render_registry(r)
    assert "[0] ON " in text
    assert "[1] off" in text
    assert "A" in text and "B" in text


def test_render_registry_marks_missing_file_and_index(tmp_path, small_catalog):
    r = DatasetRegistry()
    e = r.add_path(small_catalog, name="exists")
    e.index_path = str(tmp_path)
    bad = DatasetEntry(name="ghost", path="/nope.jsonl")
    r.entries.append(bad)
    text = render_registry(r)
    assert "[missing file]" in text
    assert "idx" in text  # index marker for "exists"


# ---------------------------------------------------------------------------
# Bootstrap helper
# ---------------------------------------------------------------------------


def test_bootstrap_with_sample_includes_bundled_catalog():
    r = bootstrap_with_sample()
    # The bundled sample is shipped with the plugin.
    names = r.names()
    assert any("UNAV Sample" in n for n in names)
    sample = r.find(names[0])
    assert sample.stats is not None
    assert sample.stats.object_count == 100


# ---------------------------------------------------------------------------
# default_registry_path
# ---------------------------------------------------------------------------


def test_default_registry_path_is_per_user():
    p = default_registry_path()
    assert p.endswith("datasets.json")
    assert ".unav_pro" in p


# ---------------------------------------------------------------------------
# DatasetManagerController (non-c4d code paths)
# ---------------------------------------------------------------------------


def test_controller_persists_changes(tmp_path, small_catalog, monkeypatch):
    from ui.dataset_manager import DatasetManagerController

    reg_path = str(tmp_path / "datasets.json")
    ctrl = DatasetManagerController(
        registry=DatasetRegistry(),
        registry_path=reg_path,
    )
    msg = ctrl.add_dataset(small_catalog)
    assert "registered" in msg
    # Persisted to disk.
    assert os.path.exists(reg_path)
    reloaded = DatasetRegistry.load(reg_path)
    assert len(reloaded) == 1


def test_controller_remove_and_toggle(tmp_path, small_catalog):
    from ui.dataset_manager import DatasetManagerController

    ctrl = DatasetManagerController(
        registry=DatasetRegistry(),
        registry_path=str(tmp_path / "r.json"),
    )
    ctrl.add_dataset(small_catalog)
    name = ctrl.registry.names()[0]
    out = ctrl.toggle_enabled(name)
    assert "disabled" in out
    out = ctrl.toggle_enabled(name)
    assert "enabled" in out
    out = ctrl.remove_dataset(name)
    assert "removed" in out
    assert ctrl.remove_dataset(name).startswith("Remove Dataset:")


def test_controller_load_active_sets_default_lookup(tmp_path, small_catalog):
    from core.metadata_lookup import default_lookup, set_default_lookup
    from ui.dataset_manager import DatasetManagerController

    set_default_lookup(None)
    ctrl = DatasetManagerController(
        registry=DatasetRegistry(),
        registry_path=str(tmp_path / "r.json"),
    )
    ctrl.add_dataset(small_catalog)
    msg = ctrl.load_active()
    assert "Load Active" in msg
    lk = default_lookup()
    # Lookup contains the namespaced uids.
    assert any(uid.split(":", 1)[0] for uid in lk.uids())
    assert len(lk) == 4


def test_controller_handles_no_enabled_datasets(tmp_path):
    from ui.dataset_manager import DatasetManagerController

    ctrl = DatasetManagerController(
        registry=DatasetRegistry(),
        registry_path=str(tmp_path / "r.json"),
    )
    msg = ctrl.load_active()
    assert "no enabled datasets" in msg


def test_controller_build_index_creates_index(tmp_path, small_catalog):
    from ui.dataset_manager import DatasetManagerController

    ctrl = DatasetManagerController(
        registry=DatasetRegistry(),
        registry_path=str(tmp_path / "r.json"),
    )
    ctrl.add_dataset(small_catalog)
    name = ctrl.registry.names()[0]
    msg = ctrl.build_index(name)
    assert "Build Index" in msg
    entry = ctrl.registry.find(name)
    assert entry.is_indexed


def test_controller_build_index_reports_missing_file(tmp_path):
    from ui.dataset_manager import DatasetManagerController

    reg = DatasetRegistry()
    reg.entries.append(DatasetEntry(name="ghost", path="/nope.jsonl"))
    ctrl = DatasetManagerController(
        registry=reg, registry_path=str(tmp_path / "r.json"),
    )
    msg = ctrl.build_index("ghost")
    assert "missing" in msg


def test_controller_refresh_stats(tmp_path, small_catalog):
    from ui.dataset_manager import DatasetManagerController

    ctrl = DatasetManagerController(
        registry=DatasetRegistry(),
        registry_path=str(tmp_path / "r.json"),
    )
    ctrl.add_dataset(small_catalog)
    name = ctrl.registry.names()[0]
    msg = ctrl.refresh_stats(name)
    assert "objects" in msg


def test_controller_remembers_path_across_instances(tmp_path, small_catalog):
    from ui.dataset_manager import DatasetManagerController

    reg_path = str(tmp_path / "r.json")
    a = DatasetManagerController(
        registry=DatasetRegistry(), registry_path=reg_path,
    )
    a.add_dataset(small_catalog)
    b = DatasetManagerController(registry_path=reg_path)
    assert b.registry.names() == a.registry.names()
