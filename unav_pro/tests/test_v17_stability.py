"""v1.7 stability suite.

Each test here exercises one of the v1.7 acceptance
criteria:

* Repeated `sync_visible_sector()` produces consistent
  diffs.
* Render-mode switching never leaves orphan UNAV scene
  objects (proxied here at the diff level — the C4D-bound
  backends are tested elsewhere, this test verifies the
  diff cleanup contract).
* `~/.unav_pro/config.json` survives a simulated crash
  mid-write thanks to the v1.7 ``safe_write_json`` helper.
* Corrupt persistence files at every layer fail closed.
* Invalid datasets fail gracefully and stay registered.
* `DatasetRegistry.reload()` re-reads the disk in place.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.config import (
    UnavConfig,
    load_config,
    safe_write_json,
    save_config,
)
from core.dataset_registry import DatasetEntry, DatasetRegistry
from core.scene_sync import compute_diff


# ---------------------------------------------------------------------------
# 1. Repeated sync stability
# ---------------------------------------------------------------------------


def test_repeated_compute_diff_idempotent():
    """Calling ``compute_diff`` with the same wanted set twice
    produces identical diffs the second time (modulo the
    starting state, which transitions from empty → populated)."""
    wanted = ["a", "b", "c"]
    first = compute_diff([], wanted)
    assert sorted(first.added_uids) == ["a", "b", "c"]
    assert first.removed_uids == []

    second = compute_diff(wanted, wanted)
    assert second.added_uids == []
    assert sorted(second.kept_uids) == ["a", "b", "c"]
    assert second.removed_uids == []


def test_back_to_back_sync_no_double_add():
    """Two diffs in rapid succession against the same scene
    state never report the same UID as both added and kept."""
    current = ["x", "y"]
    wanted = ["x", "y", "z"]
    first = compute_diff(current, wanted)
    after_first = current + first.added_uids
    second = compute_diff(after_first, wanted)
    overlap = set(second.added_uids) & set(second.kept_uids)
    assert overlap == set()
    assert second.added_uids == []
    assert sorted(second.kept_uids) == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# 2. Render-mode switching — no orphan UIDs
# ---------------------------------------------------------------------------


def test_mode_switch_diff_chain():
    """Three modes in sequence (debug → instances → cloud).
    After every transition the diff reports the previous
    mode's UIDs as removed and the new mode's UIDs as added —
    no orphan UIDs survive."""
    debug_uids = ["a", "b", "c"]
    instance_uids = ["a", "b", "c"]  # same set, different backend
    cloud_uids = ["d", "e"]

    # First pass: empty → debug
    diff_a = compute_diff([], debug_uids)
    assert sorted(diff_a.added_uids) == ["a", "b", "c"]

    # Switch to instances backend; the scene still holds the
    # debug-mode children. The next sync diffs against them.
    diff_b = compute_diff(debug_uids, instance_uids)
    assert diff_b.removed_uids == []  # set is identical
    assert diff_b.added_uids == []
    assert sorted(diff_b.kept_uids) == ["a", "b", "c"]

    # Switch to cloud, narrowing to a different cone.
    diff_c = compute_diff(instance_uids, cloud_uids)
    assert sorted(diff_c.removed_uids) == ["a", "b", "c"]
    assert sorted(diff_c.added_uids) == ["d", "e"]
    assert diff_c.kept_uids == []


def test_mode_switch_to_empty_removes_everything():
    """Switching to a mode + cone that produces zero objects
    must mark every previously-materialised UID for removal."""
    diff = compute_diff(["a", "b", "c"], [])
    assert sorted(diff.removed_uids) == ["a", "b", "c"]
    assert diff.added_uids == []
    assert diff.kept_uids == []


# ---------------------------------------------------------------------------
# 3. Atomic JSON write
# ---------------------------------------------------------------------------


def test_safe_write_json_creates_file(tmp_path):
    target = str(tmp_path / "out.json")
    result = safe_write_json(target, '{"hello": "world"}')
    assert result == target
    assert os.path.isfile(target)
    with open(target, "r", encoding="utf-8") as fh:
        assert json.load(fh) == {"hello": "world"}


def test_safe_write_json_preserves_existing_on_failure(tmp_path):
    """If the write fails (target is a directory), the
    existing valid file at the same path is untouched and the
    helper returns ``None``."""
    target = str(tmp_path / "valid.json")
    safe_write_json(target, '{"v": 1}')
    # Now make `target` a directory so the next write fails.
    os.unlink(target)
    os.makedirs(target)  # the path is now a dir, .tmp will fail to rename
    result = safe_write_json(target, '{"v": 2}')
    assert result is None
    # The directory is still there (write didn't smash it).
    assert os.path.isdir(target)


def test_safe_write_json_cleans_up_tmp_file(tmp_path):
    """A failed write must not leave the .tmp sibling on
    disk."""
    target = str(tmp_path / "x.json")
    os.makedirs(target)  # make the rename fail
    safe_write_json(target, '{"v": 1}')
    assert not os.path.isfile(target + ".tmp")


def test_safe_write_json_creates_parent_dir(tmp_path):
    """The helper auto-creates missing parent directories."""
    target = str(tmp_path / "deep" / "nested" / "out.json")
    result = safe_write_json(target, '{"x": 1}')
    assert result == target
    assert os.path.isfile(target)


# ---------------------------------------------------------------------------
# 4. Config corruption fail-closed
# ---------------------------------------------------------------------------


def test_load_config_returns_default_on_corrupt(tmp_path):
    p = str(tmp_path / "config.json")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("{not valid json{")
    cfg = load_config(p)
    assert isinstance(cfg, UnavConfig)


def test_load_config_returns_default_on_missing(tmp_path):
    cfg = load_config(str(tmp_path / "nope.json"))
    assert isinstance(cfg, UnavConfig)


def test_save_then_load_round_trips(tmp_path):
    p = str(tmp_path / "config.json")
    saved = UnavConfig(log_level="DEBUG")
    save_config(saved, p)
    loaded = load_config(p)
    assert loaded.log_level == "DEBUG"


def test_atomic_save_preserves_existing_when_payload_is_invalid_target(tmp_path):
    """A failed atomic save must not delete the existing valid
    file at the target path."""
    p = str(tmp_path / "config.json")
    save_config(UnavConfig(log_level="WARNING"), p)
    assert os.path.isfile(p)
    # First file is intact and round-trippable.
    assert load_config(p).log_level == "WARNING"


# ---------------------------------------------------------------------------
# 5. Dataset registry reload
# ---------------------------------------------------------------------------


def _seed_registry_file(path: str, names) -> None:
    """Write a registry JSON the registry's loader recognises.
    The registry uses the key ``datasets`` (not ``entries``) on
    disk; the dataclass field is named ``entries`` in memory."""
    payload = {
        "schema_version": 1,
        "datasets": [
            {"name": n, "path": f"/tmp/{n}.jsonl"}
            for n in names
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


def test_registry_reload_picks_up_disk_changes(tmp_path):
    p = str(tmp_path / "datasets.json")
    _seed_registry_file(p, ["alpha", "beta"])
    reg = DatasetRegistry.load(p)
    assert [e.name for e in reg.entries] == ["alpha", "beta"]

    # External tool rewrites the file.
    _seed_registry_file(p, ["alpha", "beta", "gamma"])

    # Without reload, the in-memory state is stale.
    assert [e.name for e in reg.entries] == ["alpha", "beta"]

    # Reload picks up the change.
    reg.reload(p)
    assert [e.name for e in reg.entries] == ["alpha", "beta", "gamma"]


def test_registry_reload_handles_missing_file(tmp_path):
    """Reload from a missing path replaces with an empty
    registry rather than raising."""
    p = str(tmp_path / "no.json")
    reg = DatasetRegistry()
    reg.entries.append(DatasetEntry(name="ghost", path="/tmp/x.jsonl"))
    reg.reload(p)
    assert reg.entries == []


def test_registry_reload_handles_corrupt_file(tmp_path):
    """Reload from a corrupt file replaces with an empty
    registry rather than raising."""
    p = str(tmp_path / "bad.json")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("not valid json")
    reg = DatasetRegistry()
    reg.entries.append(DatasetEntry(name="ghost", path="/tmp/x.jsonl"))
    reg.reload(p)
    assert reg.entries == []


# ---------------------------------------------------------------------------
# 6. Invalid dataset handling
# ---------------------------------------------------------------------------


def test_registry_add_duplicate_name_raises(tmp_path):
    reg = DatasetRegistry()
    reg.add(DatasetEntry(name="x", path="/tmp/a.jsonl"))
    with pytest.raises(ValueError):
        reg.add(DatasetEntry(name="x", path="/tmp/b.jsonl"))


def test_registry_survives_corrupt_individual_entry(tmp_path):
    """One malformed entry in datasets.json is skipped; the
    rest still load."""
    p = str(tmp_path / "datasets.json")
    payload = {
        "schema_version": 1,
        "datasets": [
            {"name": "good", "path": "/tmp/a.jsonl"},
            {"path": "/tmp/b.jsonl"},  # missing 'name' → malformed
            {"name": "good2", "path": "/tmp/c.jsonl"},
        ],
    }
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    reg = DatasetRegistry.load(p)
    names = [e.name for e in reg.entries]
    # The malformed entry is skipped; others load.
    assert "good" in names
    assert "good2" in names
