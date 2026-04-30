"""Tests for core.native_bridge (v0.9 Python ↔ C++ bridge protocol)."""

from __future__ import annotations

import json

import pytest

from core.native_bridge import (
    BRIDGE_SCHEMA_VERSION,
    DEFAULT_SIDECAR_FILENAME,
    DEFAULT_VISIBLE_SECTOR_FILENAME,
    NativeBridgeError,
    NativeRequest,
    NativeSelection,
    NativeStatus,
    default_bridge_dir,
    default_request_path,
    default_selection_path,
    default_sidecar_path,
    default_status_path,
    default_visible_sector_path,
    make_clear_request,
    make_load_request,
    read_request,
    read_selection,
    read_status,
    resolve_uid_from_hash,
    write_request,
    write_selection,
    write_status,
)
from data.binary_export import compute_uid_hash


# ---------------------------------------------------------------------------
# Defaults / paths
# ---------------------------------------------------------------------------


def test_bridge_filenames_are_known_strings():
    assert DEFAULT_VISIBLE_SECTOR_FILENAME == "visible_sector.bin"
    assert DEFAULT_SIDECAR_FILENAME == "visible_sector.jsonl"


def test_default_paths_live_under_the_bridge_dir():
    base = default_bridge_dir()
    assert default_visible_sector_path().startswith(base)
    assert default_sidecar_path().startswith(base)
    assert default_request_path().startswith(base)
    assert default_status_path().startswith(base)
    assert default_selection_path().startswith(base)


def test_schema_version_is_locked_at_one():
    assert BRIDGE_SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# NativeRequest validation + round-trip
# ---------------------------------------------------------------------------


def test_request_rejects_unknown_action():
    with pytest.raises(ValueError):
        NativeRequest(action="garbage")


def test_request_auto_assigns_id_and_timestamp():
    req = NativeRequest(action="load", binary_path="/tmp/x.unav")
    assert req.request_id
    assert req.requested_at_iso


def test_request_round_trip_through_disk(tmp_path):
    path = str(tmp_path / "req.json")
    out = make_load_request(
        "/tmp/visible.unav", sidecar_path="/tmp/visible.jsonl",
        max_points=42,
    )
    write_request(out, path=path)
    parsed = read_request(path=path)
    assert parsed is not None
    assert parsed.action == "load"
    assert parsed.binary_path == "/tmp/visible.unav"
    assert parsed.sidecar_path == "/tmp/visible.jsonl"
    assert parsed.max_points == 42
    assert parsed.request_id == out.request_id


def test_request_missing_file_returns_none(tmp_path):
    assert read_request(str(tmp_path / "absent.json")) is None


def test_request_rejects_unsupported_schema_version(tmp_path):
    path = str(tmp_path / "req.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": 99, "action": "load"}, fh)
    with pytest.raises(NativeBridgeError, match="schema_version"):
        read_request(path)


def test_make_clear_request_produces_clear_action():
    assert make_clear_request().action == "clear"


# ---------------------------------------------------------------------------
# NativeStatus
# ---------------------------------------------------------------------------


def test_status_round_trip(tmp_path):
    path = str(tmp_path / "status.json")
    s = NativeStatus(
        engine_available=True, engine_version="0.9.0",
        binary_path="/tmp/x.unav",
        point_count=12345, file_size_bytes=64218,
        load_seconds=0.087,
    )
    write_status(s, path=path)
    parsed = read_status(path=path)
    assert parsed is not None
    assert parsed.engine_available is True
    assert parsed.point_count == 12345


def test_status_short_summary_for_loaded_engine():
    s = NativeStatus(
        engine_available=True, engine_version="0.9.0",
        point_count=1000, file_size_bytes=52030, load_seconds=0.05,
    )
    out = s.short_summary()
    assert "0.9.0" in out
    assert "1000 points" in out


def test_status_short_summary_when_engine_unloaded():
    s = NativeStatus(engine_available=False)
    assert "fallback" in s.short_summary()


def test_status_short_summary_for_error():
    s = NativeStatus(error="bad CRC")
    assert "error" in s.short_summary()
    assert "bad CRC" in s.short_summary()


def test_status_missing_file_returns_none(tmp_path):
    assert read_status(str(tmp_path / "absent.json")) is None


# ---------------------------------------------------------------------------
# NativeSelection
# ---------------------------------------------------------------------------


def test_selection_round_trip(tmp_path):
    path = str(tmp_path / "sel.json")
    s = NativeSelection(
        uid_hash=0xDEADBEEFCAFEBABE,
        point_index=42,
        x=1.0, y=2.0, z=3.0,
        source_id=1,
    )
    write_selection(s, path=path)
    parsed = read_selection(path=path)
    assert parsed is not None
    assert parsed.uid_hash == 0xDEADBEEFCAFEBABE
    assert parsed.point_index == 42
    assert parsed.x == pytest.approx(1.0)
    assert parsed.timestamp_iso  # auto-assigned by writer


def test_selection_missing_returns_none(tmp_path):
    assert read_selection(str(tmp_path / "absent.json")) is None


# ---------------------------------------------------------------------------
# uid_hash → uid resolution
# ---------------------------------------------------------------------------


def test_resolve_uid_finds_match_by_hash():
    candidates = ["gaia:1", "sdss:9001", "desi:42", "jpl:Mars:2026-01-01"]
    target = compute_uid_hash("desi:42")
    assert resolve_uid_from_hash(target, candidates) == "desi:42"


def test_resolve_uid_returns_none_on_miss():
    candidates = ["gaia:1", "sdss:9001"]
    assert resolve_uid_from_hash(0x1234, candidates) is None


def test_resolve_uid_handles_uint64_overflow_safely():
    """Hash collisions are vanishingly unlikely at 2⁶⁴, but the
    resolver must still tolerate malformed (e.g. negative) ints."""
    assert resolve_uid_from_hash(-1, []) is None
