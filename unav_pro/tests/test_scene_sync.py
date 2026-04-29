"""Tests for core.scene_sync. Covers the pure diff and the c4d guard."""

from __future__ import annotations

import pytest

from core import scene_sync
from core.scene_sync import SyncDiff, compute_diff


# ---------------------------------------------------------------------------
# compute_diff — basic
# ---------------------------------------------------------------------------


def test_compute_diff_basic_overlap():
    diff = compute_diff(
        current_uids=["a", "b", "c"],
        wanted_uids=["b", "c", "d"],
    )
    assert diff.added_uids == ["d"]
    assert diff.kept_uids == ["b", "c"]
    assert diff.removed_uids == ["a"]
    assert diff.capped_uids == 0
    assert diff.total_visible == 3


def test_compute_diff_disjoint_sets():
    diff = compute_diff(["a", "b"], ["x", "y"])
    assert diff.added_uids == ["x", "y"]
    assert diff.kept_uids == []
    assert diff.removed_uids == ["a", "b"]


def test_compute_diff_full_overlap_only_kept():
    diff = compute_diff(["a", "b"], ["a", "b"])
    assert diff.added_uids == []
    assert diff.removed_uids == []
    assert diff.kept_uids == ["a", "b"]


def test_compute_diff_empty_current_all_added():
    diff = compute_diff([], ["a", "b", "c"])
    assert diff.added_uids == ["a", "b", "c"]
    assert diff.kept_uids == []
    assert diff.removed_uids == []


def test_compute_diff_empty_wanted_all_removed():
    diff = compute_diff(["a", "b"], [])
    assert diff.added_uids == []
    assert diff.kept_uids == []
    assert diff.removed_uids == ["a", "b"]


def test_compute_diff_both_empty():
    diff = compute_diff([], [])
    assert diff.added_uids == []
    assert diff.kept_uids == []
    assert diff.removed_uids == []


# ---------------------------------------------------------------------------
# compute_diff — ordering and dedup
# ---------------------------------------------------------------------------


def test_compute_diff_added_preserves_input_order():
    """Filter-ordered uids stay in order — this is what makes
    'closest first' or 'brightest first' meaningful when downstream
    code consumes the added list as a sequence."""
    diff = compute_diff(
        current_uids=[],
        wanted_uids=["c", "a", "b"],
    )
    assert diff.added_uids == ["c", "a", "b"]


def test_compute_diff_dedups_wanted_uids():
    diff = compute_diff([], ["a", "b", "a", "c"])
    assert diff.added_uids == ["a", "b", "c"]


def test_compute_diff_skips_falsy_uids():
    diff = compute_diff(["", "a"], ["", "b"])
    assert "" not in diff.added_uids
    assert "" not in diff.kept_uids
    assert "" not in diff.removed_uids


# ---------------------------------------------------------------------------
# compute_diff — max_visible cap
# ---------------------------------------------------------------------------


def test_compute_diff_cap_truncates_after_dedup():
    diff = compute_diff(
        current_uids=[],
        wanted_uids=["a", "b", "c", "d", "e"],
        max_visible=3,
    )
    assert diff.added_uids == ["a", "b", "c"]
    assert diff.capped_uids == 2


def test_compute_diff_cap_zero_keeps_nothing():
    diff = compute_diff(["a"], ["a", "b"], max_visible=0)
    assert diff.added_uids == []
    assert diff.kept_uids == []
    assert diff.removed_uids == ["a"]
    assert diff.capped_uids == 2


def test_compute_diff_cap_above_size_is_noop():
    diff = compute_diff([], ["a", "b"], max_visible=99)
    assert diff.added_uids == ["a", "b"]
    assert diff.capped_uids == 0


def test_compute_diff_cap_drops_currently_visible_when_no_longer_wanted():
    """When max_visible truncates the wanted list, anything already
    materialized that falls past the cut must be removed."""
    diff = compute_diff(
        current_uids=["a", "b", "c"],
        wanted_uids=["a", "b", "c", "d", "e"],
        max_visible=2,
    )
    # Only the first two of wanted survive.
    assert diff.kept_uids == ["a", "b"]
    assert diff.removed_uids == ["c"]
    assert diff.added_uids == []
    assert diff.capped_uids == 3


def test_compute_diff_negative_cap_treated_as_no_cap():
    diff = compute_diff([], ["a", "b"], max_visible=-1)
    # The implementation skips the cap branch for negative values that
    # would otherwise produce a nonsensical empty slice. We document
    # this behavior.
    assert diff.added_uids == ["a", "b"]
    assert diff.capped_uids == 0


# ---------------------------------------------------------------------------
# SyncDiff helpers
# ---------------------------------------------------------------------------


def test_sync_diff_short_summary_with_capped():
    diff = SyncDiff(
        added_uids=["a"], kept_uids=["b", "c"], removed_uids=["d"],
        capped_uids=5,
    )
    text = diff.short_summary()
    assert "+1 added" in text
    assert "=2 kept" in text
    assert "-1 removed" in text
    assert "5 capped" in text


def test_sync_diff_short_summary_omits_zero_cap():
    diff = SyncDiff(
        added_uids=[], kept_uids=[], removed_uids=[],
        capped_uids=0,
    )
    text = diff.short_summary()
    assert "capped" not in text


def test_sync_diff_total_visible_excludes_removed():
    diff = SyncDiff(
        added_uids=["a", "b"], kept_uids=["c"], removed_uids=["d", "e"],
    )
    assert diff.total_visible == 3


# ---------------------------------------------------------------------------
# C4D guard
# ---------------------------------------------------------------------------


def test_sync_visible_sector_outside_c4d_raises_runtime_error():
    with pytest.raises(RuntimeError, match="requires Cinema 4D"):
        scene_sync.sync_visible_sector(None, [])


def test_update_debug_cone_outside_c4d_raises_runtime_error():
    with pytest.raises(RuntimeError, match="requires Cinema 4D"):
        scene_sync.update_debug_cone(None, show=True)
