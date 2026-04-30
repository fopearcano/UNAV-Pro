"""Tests for c4d_objects.render_backend (v0.7 backend interface).

The c4d-bound paths live behind a guard so these tests target only
the pure-Python contract: the abstract base, the stats dataclass,
the factory, and the per-backend metadata-selection contract.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import pytest

from c4d_objects.render_backend import (
    BackendStats,
    BackendUpdateResult,
    DebugObjectsBackend,
    PointCloudBackend,
    RenderBackend,
    backend_for_mode,
)
from core.render_mode import (
    DEFAULT_RENDER_MODE,
    RENDER_MODE_DEBUG_OBJECTS,
    RENDER_MODE_INSTANCES,
    RENDER_MODE_POINT_CLOUD,
)
from data.schema import CatalogObject


def _obj(uid: str, **kw) -> CatalogObject:
    base = dict(
        uid=uid, catalog_source="Gaia DR3", object_type="star",
        ra_deg=10.0, dec_deg=20.0,
    )
    base.update(kw)
    return CatalogObject(**base)


# ---------------------------------------------------------------------------
# BackendStats
# ---------------------------------------------------------------------------


def test_backend_stats_default_state():
    s = BackendStats()
    assert s.mode == DEFAULT_RENDER_MODE
    assert s.last_build_seconds == 0.0
    assert s.visible_count == 0
    assert s.generated_count == 0
    assert s.estimated_scene_objects == 0


def test_backend_stats_short_summary_is_compact_one_liner():
    s = BackendStats(
        mode="instances", last_build_seconds=0.123,
        visible_count=10, generated_count=5,
        estimated_scene_objects=15,
    )
    out = s.short_summary()
    assert "instances" in out
    assert "visible=10" in out
    assert "generated=5" in out
    assert "scene≈15" in out
    assert "ms" in out


def test_backend_update_result_default_zeroed():
    r = BackendUpdateResult()
    assert r.added == r.removed == r.kept == r.skipped == 0
    assert r.warnings == []


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_builds_debug_backend_for_default_mode():
    b = backend_for_mode(DEFAULT_RENDER_MODE)
    assert isinstance(b, DebugObjectsBackend)
    assert b.mode == RENDER_MODE_DEBUG_OBJECTS


def test_factory_builds_point_cloud_backend():
    b = backend_for_mode(RENDER_MODE_POINT_CLOUD)
    assert isinstance(b, PointCloudBackend)
    assert b.mode == RENDER_MODE_POINT_CLOUD


def test_factory_builds_instance_backend_for_instances_mode():
    """``InstanceBackend`` lives in instance_builder.py; the factory
    imports it lazily so this is the only test that pulls it in."""
    from c4d_objects.instance_builder import InstanceBackend
    b = backend_for_mode(RENDER_MODE_INSTANCES)
    assert isinstance(b, InstanceBackend)
    assert b.mode == RENDER_MODE_INSTANCES


def test_factory_falls_back_for_unknown_mode():
    b = backend_for_mode("garbage")
    assert isinstance(b, DebugObjectsBackend)


# ---------------------------------------------------------------------------
# Per-backend metadata-selection contract
# ---------------------------------------------------------------------------


def test_debug_backend_supports_metadata_selection():
    b = DebugObjectsBackend()
    assert b.supports_metadata_selection() is True


def test_point_cloud_backend_does_not_support_per_object_selection():
    b = PointCloudBackend()
    assert b.supports_metadata_selection() is False


def test_instance_backend_supports_per_object_selection_via_uid_marker():
    from c4d_objects.instance_builder import InstanceBackend
    b = InstanceBackend()
    assert b.supports_metadata_selection() is True


# ---------------------------------------------------------------------------
# Point Cloud Mode without c4d (offline path)
# ---------------------------------------------------------------------------


def test_point_cloud_build_records_uids_without_c4d():
    """In a c4d-free environment, build_visible_sector still records
    the visible-uid map so the search-based fallback works."""
    backend = PointCloudBackend()
    objects = [_obj("a"), _obj("b"), _obj("c")]
    result = backend.build_visible_sector(
        doc=None, objects=objects, max_visible=None,
    )
    # No c4d → no scene objects generated, but the bookkeeping is intact.
    assert result.added == 3
    assert backend.remembered_uids() == ["a", "b", "c"]
    for o in objects:
        assert backend.remembered_object(o.uid) is o


def test_point_cloud_max_visible_truncates_and_skips():
    backend = PointCloudBackend()
    objects = [_obj(f"x:{i}") for i in range(50)]
    result = backend.build_visible_sector(
        doc=None, objects=objects, max_visible=10,
    )
    assert result.added == 10
    assert result.skipped == 40
    assert len(backend.remembered_uids()) == 10


def test_point_cloud_update_adds_and_removes_in_uid_map():
    backend = PointCloudBackend()
    backend.build_visible_sector(
        doc=None, objects=[_obj("a"), _obj("b"), _obj("c")],
        max_visible=None,
    )
    result = backend.update_visible_sector(
        doc=None,
        added=[_obj("d")],
        removed_uids=["a"],
        kept_uids=["b", "c"],
    )
    assert result.added == 1
    assert result.removed == 1
    assert result.kept == 2
    assert set(backend.remembered_uids()) == {"b", "c", "d"}


def test_point_cloud_records_stats_after_build():
    backend = PointCloudBackend()
    backend.build_visible_sector(
        doc=None, objects=[_obj("a"), _obj("b")],
    )
    stats = backend.get_stats()
    assert stats.mode == RENDER_MODE_POINT_CLOUD
    assert stats.visible_count == 2


def test_point_cloud_get_object_uid_from_selection_returns_none():
    """Cloud mode never yields per-object selection."""
    backend = PointCloudBackend()
    assert backend.get_object_uid_from_selection(doc=None, c4d_object=None) is None


# ---------------------------------------------------------------------------
# Debug backend stats path (c4d-free)
# ---------------------------------------------------------------------------


def test_debug_backend_clear_returns_zero_without_c4d():
    backend = DebugObjectsBackend()
    assert backend.clear(doc=None) == 0


def test_debug_backend_get_uid_from_none_selection_returns_none():
    backend = DebugObjectsBackend()
    assert backend.get_object_uid_from_selection(doc=None, c4d_object=None) is None


# ---------------------------------------------------------------------------
# Mode-switch safety: backends share no state
# ---------------------------------------------------------------------------


def test_backends_each_have_independent_uid_maps():
    a = backend_for_mode(RENDER_MODE_POINT_CLOUD)
    b = backend_for_mode(RENDER_MODE_POINT_CLOUD)
    a.build_visible_sector(doc=None, objects=[_obj("only_in_a")])
    assert b.remembered_uids() == []


# ---------------------------------------------------------------------------
# Encoding gets handed to backend without duplication
# ---------------------------------------------------------------------------


class _FakeBackend(RenderBackend):
    """In-memory fake the scene_sync test below uses to assert the
    diff is forwarded faithfully without c4d."""

    mode = RENDER_MODE_DEBUG_OBJECTS

    def __init__(self) -> None:
        super().__init__()
        self.cleared = 0
        self.last_build = None  # type: ignore[assignment]
        self.last_update = None  # type: ignore[assignment]
        self.last_encoding = None

    def clear(self, doc) -> int:
        self.cleared += 1
        return 0

    def build_visible_sector(
        self, doc, objects, *, encoding=None, scale_mode="pc", max_visible=None,
    ) -> BackendUpdateResult:
        self.last_build = list(objects)
        self.last_encoding = encoding
        return BackendUpdateResult(added=len(self.last_build))

    def update_visible_sector(
        self, doc, *, added, removed_uids, kept_uids,
        encoding=None, scale_mode="pc",
    ) -> BackendUpdateResult:
        self.last_update = {
            "added": list(added),
            "removed": list(removed_uids),
            "kept": list(kept_uids),
        }
        self.last_encoding = encoding
        return BackendUpdateResult(
            added=len(added), removed=len(removed_uids),
            kept=len(kept_uids),
        )


def test_fake_backend_records_encoding_passed_in():
    """Sanity: a backend implementation can capture the
    VisualEncodingParams the dialog hands it. v0.7 contract: the
    backend must NOT duplicate visual-encoding logic — it consumes
    what it's given."""
    from core.visual_encoding import VisualEncodingParams
    fake = _FakeBackend()
    params = VisualEncodingParams(color_mode="redshift")
    fake.build_visible_sector(
        doc=None, objects=[_obj("a")], encoding=params,
    )
    assert fake.last_encoding is params
