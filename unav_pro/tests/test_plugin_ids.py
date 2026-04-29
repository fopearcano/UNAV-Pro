"""Sanity checks for the plugin ID registry."""

from __future__ import annotations

from core import plugin_ids


def test_ids_are_unique():
    ids = plugin_ids.all_ids()
    assert len(ids) == len(set(ids)), "Plugin IDs must be unique"


def test_ids_are_in_dev_range():
    for pid in plugin_ids.all_ids():
        assert isinstance(pid, int)
        assert pid >= 1000000, "Plugin IDs must be >= 1,000,000"
