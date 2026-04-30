"""Tests for c4d_objects.native_viewer_backend (v0.9 backend)."""

from __future__ import annotations

import json
import os

import pytest

from c4d_objects.native_viewer_backend import (
    NATIVE_PLACEHOLDER_NAME,
    NativeViewerBackend,
)
from c4d_objects.render_backend import backend_for_mode
from core.native_bridge import (
    BRIDGE_SCHEMA_VERSION,
    NativeStatus,
    write_status,
)
from core.render_mode import (
    RENDER_MODE_NATIVE_VIEWER,
    capabilities_for,
    cap_for_mode,
)
from data.binary_export import (
    POINT_SIZE,
    compute_uid_hash,
    read_visible_sector,
)
from data.schema import CatalogObject, compute_derived_fields


def _obj(uid: str, **kw) -> CatalogObject:
    base = dict(
        uid=uid, catalog_source="Gaia DR3", object_type="star",
        ra_deg=10.0, dec_deg=20.0, distance_parsec=10.0,
    )
    base.update(kw)
    o = CatalogObject(**base)
    compute_derived_fields(o)
    return o


# ---------------------------------------------------------------------------
# Mode wiring + capabilities
# ---------------------------------------------------------------------------


def test_factory_builds_native_viewer_backend():
    b = backend_for_mode(RENDER_MODE_NATIVE_VIEWER)
    assert isinstance(b, NativeViewerBackend)
    assert b.mode == RENDER_MODE_NATIVE_VIEWER


def test_native_viewer_capabilities_match_v07_pattern():
    caps = capabilities_for(RENDER_MODE_NATIVE_VIEWER)
    # v0.9 contract: no per-object selection (the C++ side handles
    # picking via a separate selection file).
    assert caps.supports_per_object_selection is False
    assert caps.supports_per_instance_metadata is False
    assert caps.hard_cap == cap_for_mode(RENDER_MODE_NATIVE_VIEWER)


def test_native_viewer_supports_metadata_selection_returns_false():
    b = NativeViewerBackend()
    assert b.supports_metadata_selection() is False


# ---------------------------------------------------------------------------
# Build → file present
# ---------------------------------------------------------------------------


def test_build_writes_binary_and_sidecar(tmp_path):
    b = NativeViewerBackend(bridge_dir=str(tmp_path))
    objects = [_obj(f"gaia:{i}") for i in range(3)]
    result = b.build_visible_sector(doc=None, objects=objects)
    assert result.added == 3
    assert os.path.isfile(b.binary_path)
    assert os.path.isfile(b.sidecar_path)
    assert b.last_file_size_bytes > 0


def test_build_emits_load_request_with_correct_paths(tmp_path):
    b = NativeViewerBackend(bridge_dir=str(tmp_path))
    b.build_visible_sector(doc=None, objects=[_obj("a")])
    request_path = os.path.join(str(tmp_path), "native_request.json")
    assert os.path.isfile(request_path)
    with open(request_path, "r", encoding="utf-8") as fh:
        req = json.load(fh)
    assert req["schema_version"] == BRIDGE_SCHEMA_VERSION
    assert req["action"] == "load"
    assert req["binary_path"] == b.binary_path
    assert req["sidecar_path"] == b.sidecar_path


def test_binary_file_round_trip_via_python_reader(tmp_path):
    """Sanity: the file the backend writes parses cleanly using
    the same reference reader the v0.8 tests cover."""
    b = NativeViewerBackend(bridge_dir=str(tmp_path))
    objects = [_obj(f"gaia:{i}") for i in range(5)]
    b.build_visible_sector(doc=None, objects=objects)
    parsed = read_visible_sector(b.binary_path)
    assert parsed.header.point_count == 5
    assert parsed.header.source_count == 1
    expected_uid_hashes = {compute_uid_hash(o.uid) for o in objects}
    assert {p.uid_hash for p in parsed.points} == expected_uid_hashes


def test_sidecar_jsonl_carries_one_row_per_uid(tmp_path):
    b = NativeViewerBackend(bridge_dir=str(tmp_path))
    objects = [_obj("a"), _obj("b"), _obj("c")]
    b.build_visible_sector(doc=None, objects=objects)
    rows = []
    with open(b.sidecar_path, "r", encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
    assert {r["uid"] for r in rows} == {"a", "b", "c"}


def test_build_skips_objects_without_uid(tmp_path):
    b = NativeViewerBackend(bridge_dir=str(tmp_path))
    bad = _obj("a"); bad.uid = ""
    good = _obj("b")
    b.build_visible_sector(doc=None, objects=[bad, good])
    parsed = read_visible_sector(b.binary_path)
    # The exporter and the sidecar both filter empty uids.
    assert parsed.header.point_count == 1


# ---------------------------------------------------------------------------
# Update path
# ---------------------------------------------------------------------------


def test_update_re_exports_full_snapshot(tmp_path):
    """The native side rebuilds from the file, so updates write a
    full snapshot, not just the delta."""
    b = NativeViewerBackend(bridge_dir=str(tmp_path))
    b.build_visible_sector(doc=None, objects=[_obj("a"), _obj("b")])
    result = b.update_visible_sector(
        doc=None, added=[_obj("c")],
        removed_uids=["a"], kept_uids=["b"],
    )
    assert result.added == 1
    assert result.removed == 1
    assert result.kept == 1
    parsed = read_visible_sector(b.binary_path)
    assert parsed.header.point_count == 2
    expected = {compute_uid_hash("b"), compute_uid_hash("c")}
    assert {p.uid_hash for p in parsed.points} == expected


# ---------------------------------------------------------------------------
# Cap enforcement
# ---------------------------------------------------------------------------


def test_max_visible_caps_export(tmp_path):
    b = NativeViewerBackend(bridge_dir=str(tmp_path))
    objects = [_obj(f"x:{i}") for i in range(50)]
    result = b.build_visible_sector(
        doc=None, objects=objects, max_visible=10,
    )
    assert result.added == 10
    assert result.skipped == 40
    parsed = read_visible_sector(b.binary_path)
    assert parsed.header.point_count == 10


# ---------------------------------------------------------------------------
# Clear path
# ---------------------------------------------------------------------------


def test_clear_removes_files_and_writes_clear_request(tmp_path):
    b = NativeViewerBackend(bridge_dir=str(tmp_path))
    b.build_visible_sector(doc=None, objects=[_obj("a"), _obj("b")])
    assert os.path.isfile(b.binary_path)
    b.clear(doc=None)
    assert not os.path.isfile(b.binary_path)
    assert not os.path.isfile(b.sidecar_path)
    request_path = os.path.join(str(tmp_path), "native_request.json")
    with open(request_path, "r", encoding="utf-8") as fh:
        req = json.load(fh)
    assert req["action"] == "clear"


# ---------------------------------------------------------------------------
# Status integration
# ---------------------------------------------------------------------------


def test_native_status_summary_falls_back_when_no_status(tmp_path):
    b = NativeViewerBackend(bridge_dir=str(tmp_path))
    b.build_visible_sector(doc=None, objects=[_obj("a")])
    # No status file yet → summary stays None.
    assert b.last_native_status_summary is None


def test_native_status_summary_picks_up_native_status(tmp_path):
    b = NativeViewerBackend(bridge_dir=str(tmp_path))
    # Pre-populate a status file as if the native plugin had loaded.
    write_status(
        NativeStatus(
            engine_available=True, engine_version="0.9.0",
            point_count=42, file_size_bytes=2222, load_seconds=0.01,
        ),
        path=os.path.join(str(tmp_path), "native_status.json"),
    )
    b.build_visible_sector(doc=None, objects=[_obj("a")])
    summary = b.last_native_status_summary
    assert summary is not None
    assert "0.9.0" in summary
    assert "42 points" in summary
