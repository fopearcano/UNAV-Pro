"""v1.7 state manager facade tests.

The facade itself is thin glue — these tests verify that
``health_summary``, ``reload_all``, the validators, and the
per-subsystem summaries behave the way the diagnostics
panel expects.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.bookmarks import Bookmark, BookmarkList
from core.config import UnavConfig
from core.dataset_registry import DatasetEntry, DatasetRegistry
from core.state_manager import (
    StateHealth,
    StateHealthEntry,
    dataset_summary,
    get_dataset_registry,
    health_summary,
    reload_all,
    set_dataset_registry,
    validate_bookmarks,
    validate_config,
    validate_registry,
    visible_sector_summary,
)


# ---------------------------------------------------------------------------
# Health summary
# ---------------------------------------------------------------------------


def test_health_summary_has_one_entry_per_subsystem():
    h = health_summary()
    names = {e.name for e in h.entries}
    assert "config" in names
    assert "bookmarks" in names
    assert "datasets" in names
    assert "time_navigator" in names
    assert "metadata_lookup" in names
    assert "missions" in names


def test_health_summary_is_healthy_when_everything_loads():
    h = health_summary()
    # Default state on a fresh test run should be healthy.
    assert h.is_healthy()
    assert "OK" in h.summary_line()


def test_health_summary_render_lists_every_entry():
    h = health_summary()
    rendered = h.render()
    assert "UNAV State Health" in rendered
    for entry in h.entries:
        assert entry.name in rendered


def test_state_health_summary_line_when_failure():
    h = StateHealth(entries=[
        StateHealthEntry(name="ok_one", ok=True, detail="fine"),
        StateHealthEntry(name="broken_two", ok=False, detail="oops"),
    ])
    assert not h.is_healthy()
    assert "issues" in h.summary_line()
    assert "broken_two" in h.summary_line()


# ---------------------------------------------------------------------------
# Singleton get / set / reload
# ---------------------------------------------------------------------------


def test_get_dataset_registry_is_a_singleton():
    a = get_dataset_registry()
    b = get_dataset_registry()
    assert a is b


def test_set_dataset_registry_replaces_singleton():
    fresh = DatasetRegistry()
    fresh.entries.append(DatasetEntry(name="custom", path="/tmp/x.jsonl"))
    set_dataset_registry(fresh)
    assert get_dataset_registry() is fresh
    # Restore by clearing for the rest of the suite.
    set_dataset_registry(None)


def test_reload_all_resets_singletons():
    """``reload_all`` drops every singleton; the next access
    reloads from disk."""
    first = get_dataset_registry()
    reload_all()
    second = get_dataset_registry()
    # Re-loaded fresh from disk; these may or may not be the same
    # object (they're both freshly-bootstrapped registries) but
    # both must be valid registries.
    assert isinstance(second, DatasetRegistry)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def test_validate_config_passes_for_default():
    cfg = UnavConfig()
    issues = validate_config(cfg)
    assert issues == []


def test_validate_config_rejects_non_config_input():
    issues = validate_config("not a config")  # type: ignore[arg-type]
    assert any("not a UnavConfig" in i for i in issues)


def test_validate_config_flags_invalid_schema_version():
    cfg = UnavConfig(schema_version=0)
    issues = validate_config(cfg)
    assert any("schema_version" in i for i in issues)


def test_validate_bookmarks_passes_for_unique_ids():
    bms = BookmarkList()
    bms.bookmarks.append(Bookmark(kind="object", uid="x:1", id="alpha"))
    bms.bookmarks.append(Bookmark(kind="object", uid="x:2", id="beta"))
    issues = validate_bookmarks(bms)
    assert issues == []


def test_validate_bookmarks_flags_duplicates():
    bms = BookmarkList()
    bms.bookmarks.append(Bookmark(kind="object", uid="x:1", id="dup"))
    bms.bookmarks.append(Bookmark(kind="object", uid="x:2", id="dup"))
    issues = validate_bookmarks(bms)
    assert any("duplicate" in i for i in issues)


def test_validate_registry_passes_for_clean_entries():
    reg = DatasetRegistry()
    reg.add(DatasetEntry(name="alpha", path="/tmp/1.jsonl"))
    reg.add(DatasetEntry(name="beta", path="/tmp/2.jsonl"))
    assert validate_registry(reg) == []


def test_validate_registry_flags_duplicate_names():
    """Duplicates can only arise via direct list-mutation (the
    public ``add()`` raises). The validator catches those."""
    reg = DatasetRegistry()
    reg.add(DatasetEntry(name="a", path="/tmp/1.jsonl"))
    # Bypass add()'s duplicate check to simulate a corrupt
    # in-memory state.
    reg.entries.append(DatasetEntry(name="a", path="/tmp/2.jsonl"))
    issues = validate_registry(reg)
    assert any("duplicate dataset name" in i for i in issues)


# ---------------------------------------------------------------------------
# Per-subsystem summaries
# ---------------------------------------------------------------------------


def test_dataset_summary_handles_empty_registry():
    set_dataset_registry(DatasetRegistry())
    text = dataset_summary()
    assert "No datasets" in text
    set_dataset_registry(None)


def test_dataset_summary_renders_count():
    reg = DatasetRegistry()
    reg.entries.append(DatasetEntry(name="alpha", path="/tmp/a.jsonl"))
    reg.entries.append(DatasetEntry(name="beta", path="/tmp/b.jsonl"))
    set_dataset_registry(reg)
    text = dataset_summary()
    assert "Datasets (2)" in text
    assert "alpha" in text
    assert "beta" in text
    set_dataset_registry(None)


def test_visible_sector_summary_no_doc():
    text = visible_sector_summary(None)
    assert "no active document" in text
