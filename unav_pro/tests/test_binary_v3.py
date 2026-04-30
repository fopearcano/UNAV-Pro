"""Tests for the v1.2 binary visible-sector v3 format additions.

The v3 layout extends v2's extra-header block by 16 bytes:

    float64 epoch_jd        — Julian Date the file was rendered for
    uint8   state_mode      — 0 static / 1 proper_motion / 2 ephemeris / 3 mixed
    bytes   pad[7]          — reserved

This test module verifies the round-trip, the cross-version
read/write matrix, and the explicit ``state_mode`` enum.
"""

from __future__ import annotations

import struct

import pytest

from core.time_model import J2016_JD
from data.binary_export import (
    FORMAT_VERSION_V1,
    FORMAT_VERSION_V2,
    FORMAT_VERSION_V3,
    HEADER_SIZE,
    STATE_MODE_EPHEMERIS,
    STATE_MODE_MIXED,
    STATE_MODE_PROPER_MOTION,
    STATE_MODE_STATIC,
    STATE_MODES,
    SUPPORTED_FORMAT_VERSIONS,
    V2_EXTRA_HEADER_SIZE,
    V3_EXTRA_HEADER_SIZE,
    V3_EXTRA_TAIL_SIZE,
    BinaryExportError,
    BinaryV2Extras,
    UnavBinaryPoint,
    export_objects,
    make_v2_extras,
    read_visible_sector,
    write_visible_sector,
)
from data.schema import CatalogObject, compute_derived_fields


def _pt(x: float, y: float, z: float) -> UnavBinaryPoint:
    return UnavBinaryPoint(
        x=x, y=y, z=z, size=1.0, r=0.4, g=0.6, b=0.9,
        uid_hash=42, source_id=1,
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_v3_in_supported_versions():
    assert FORMAT_VERSION_V3 in SUPPORTED_FORMAT_VERSIONS
    # All three versions co-exist.
    assert FORMAT_VERSION_V1 in SUPPORTED_FORMAT_VERSIONS
    assert FORMAT_VERSION_V2 in SUPPORTED_FORMAT_VERSIONS


def test_v3_extra_tail_is_16_bytes():
    assert V3_EXTRA_TAIL_SIZE == 16


def test_v3_extra_header_is_v2_plus_tail():
    assert V3_EXTRA_HEADER_SIZE == V2_EXTRA_HEADER_SIZE + V3_EXTRA_TAIL_SIZE
    assert V3_EXTRA_HEADER_SIZE == 128


def test_state_modes_are_distinct_and_compact():
    assert STATE_MODE_STATIC == 0
    assert STATE_MODE_PROPER_MOTION == 1
    assert STATE_MODE_EPHEMERIS == 2
    assert STATE_MODE_MIXED == 3
    assert set(STATE_MODES) == {0, 1, 2, 3}


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_v3_round_trip_preserves_epoch_and_state_mode(tmp_path):
    extras = make_v2_extras([_pt(1.0, 2.0, 3.0)])
    extras.epoch_jd = J2016_JD + 100.0
    extras.state_mode = STATE_MODE_EPHEMERIS

    path = str(tmp_path / "v3.bin")
    write_visible_sector(
        path, [_pt(1.0, 2.0, 3.0)],
        sources=[(1, "Gaia DR3")],
        format_version=FORMAT_VERSION_V3,
        v2_extras=extras,
    )

    parsed = read_visible_sector(path)
    assert parsed.header.version == FORMAT_VERSION_V3
    assert parsed.header.has_v2_extras()
    assert parsed.header.has_v3_extras()
    assert parsed.header.header_extra_bytes == V3_EXTRA_HEADER_SIZE

    rt = parsed.header.v2_extras
    assert rt is not None
    assert rt.epoch_jd == pytest.approx(J2016_JD + 100.0)
    assert rt.state_mode == STATE_MODE_EPHEMERIS
    # v2 fields survive too.
    assert rt.aabb_min == (1.0, 2.0, 3.0)
    assert rt.aabb_max == (1.0, 2.0, 3.0)


def test_v3_round_trip_with_zero_defaults(tmp_path):
    """Caller passes ``format_version=V3`` without populating the v3
    fields → file is well-formed, defaults round-trip."""
    path = str(tmp_path / "v3_default.bin")
    write_visible_sector(
        path, [_pt(0.0, 0.0, 0.0)],
        sources=[],
        format_version=FORMAT_VERSION_V3,
    )
    parsed = read_visible_sector(path)
    assert parsed.header.version == FORMAT_VERSION_V3
    assert parsed.header.v2_extras is not None
    assert parsed.header.v2_extras.epoch_jd == 0.0
    assert parsed.header.v2_extras.state_mode == STATE_MODE_STATIC


# ---------------------------------------------------------------------------
# v1 / v2 stay backward-compatible
# ---------------------------------------------------------------------------


def test_v1_round_trip_still_works(tmp_path):
    path = str(tmp_path / "v1.bin")
    write_visible_sector(
        path, [_pt(1.0, 2.0, 3.0)],
        format_version=FORMAT_VERSION_V1,
    )
    parsed = read_visible_sector(path)
    assert parsed.header.version == FORMAT_VERSION_V1
    assert not parsed.header.has_v2_extras()
    assert not parsed.header.has_v3_extras()
    assert parsed.header.v2_extras is None


def test_v2_round_trip_still_works(tmp_path):
    extras = make_v2_extras([_pt(0.0, 0.0, 0.0)])
    path = str(tmp_path / "v2.bin")
    write_visible_sector(
        path, [_pt(0.0, 0.0, 0.0)],
        format_version=FORMAT_VERSION_V2,
        v2_extras=extras,
    )
    parsed = read_visible_sector(path)
    assert parsed.header.version == FORMAT_VERSION_V2
    assert parsed.header.has_v2_extras()
    assert not parsed.header.has_v3_extras()
    # v2 readers should not surface the v3 fields as populated values.
    assert parsed.header.v2_extras.epoch_jd == 0.0
    assert parsed.header.v2_extras.state_mode == STATE_MODE_STATIC


# ---------------------------------------------------------------------------
# Cross-version safety
# ---------------------------------------------------------------------------


def _patch_version_field(raw: bytes, new_version: int) -> bytes:
    """Rewrite the version field of a binary file's header (for
    fault-injection tests). The field is at byte offset 4."""
    return raw[:4] + struct.pack("<H", new_version) + raw[6:]


def test_v3_reader_rejects_wrong_header_extra_bytes(tmp_path):
    """A file claiming version=3 but carrying the 112-byte v2 extras
    block must fail closed (the parser sanity-checks the field)."""
    extras = make_v2_extras([_pt(0.0, 0.0, 0.0)])
    path = str(tmp_path / "v2.bin")
    write_visible_sector(
        path, [_pt(0.0, 0.0, 0.0)],
        format_version=FORMAT_VERSION_V2,
        v2_extras=extras,
    )
    with open(path, "rb") as fh:
        raw = fh.read()
    bad = _patch_version_field(raw, FORMAT_VERSION_V3)
    bad_path = str(tmp_path / "fake_v3.bin")
    with open(bad_path, "wb") as fh:
        fh.write(bad)
    with pytest.raises(BinaryExportError):
        read_visible_sector(bad_path)


def test_unsupported_version_rejected(tmp_path):
    path = str(tmp_path / "fake.bin")
    write_visible_sector(
        path, [_pt(0.0, 0.0, 0.0)],
        format_version=FORMAT_VERSION_V1,
    )
    with open(path, "rb") as fh:
        raw = fh.read()
    bad = _patch_version_field(raw, 99)
    bad_path = str(tmp_path / "fake_99.bin")
    with open(bad_path, "wb") as fh:
        fh.write(bad)
    with pytest.raises(BinaryExportError):
        read_visible_sector(bad_path)


def test_write_unknown_format_version_rejected(tmp_path):
    with pytest.raises(BinaryExportError):
        write_visible_sector(
            str(tmp_path / "x.bin"),
            [_pt(0.0, 0.0, 0.0)],
            format_version=42,
        )


# ---------------------------------------------------------------------------
# export_objects integration
# ---------------------------------------------------------------------------


def _star(uid: str, ra: float, dec: float, dist: float) -> CatalogObject:
    obj = CatalogObject(
        uid=uid, catalog_source="Gaia DR3",
        object_type="star",
        ra_deg=ra, dec_deg=dec,
        distance_parsec=dist,
    )
    compute_derived_fields(obj)
    return obj


def test_export_objects_v3_threads_epoch_and_state_mode(tmp_path):
    objs = [_star(f"gaia:{i}", 0.0, float(i), 10.0 + i) for i in range(3)]
    path = str(tmp_path / "exp_v3.bin")
    written, header, sources = export_objects(
        path, objs,
        format_version=FORMAT_VERSION_V3,
        epoch_jd=J2016_JD + 365.25,
        state_mode=STATE_MODE_PROPER_MOTION,
    )
    assert written > 0
    assert header.version == FORMAT_VERSION_V3
    assert header.v2_extras is not None
    assert header.v2_extras.epoch_jd == pytest.approx(J2016_JD + 365.25)
    assert header.v2_extras.state_mode == STATE_MODE_PROPER_MOTION

    parsed = read_visible_sector(path)
    assert parsed.header.version == FORMAT_VERSION_V3
    assert parsed.header.v2_extras.epoch_jd == pytest.approx(J2016_JD + 365.25)
    assert parsed.header.v2_extras.state_mode == STATE_MODE_PROPER_MOTION
    assert len(parsed.points) == 3


def test_export_objects_v3_with_mixed_state_mode(tmp_path):
    objs = [_star("gaia:0", 0.0, 0.0, 10.0)]
    path = str(tmp_path / "exp_mixed.bin")
    _, header, _ = export_objects(
        path, objs,
        format_version=FORMAT_VERSION_V3,
        epoch_jd=J2016_JD,
        state_mode=STATE_MODE_MIXED,
    )
    assert header.v2_extras.state_mode == STATE_MODE_MIXED
    parsed = read_visible_sector(path)
    assert parsed.header.v2_extras.state_mode == STATE_MODE_MIXED


def test_export_objects_v1_ignores_epoch_args(tmp_path):
    """Caller passes ``epoch_jd`` to a v1 export — silently dropped
    (v1 has no place to store it). The file is still v1."""
    objs = [_star("gaia:0", 0.0, 0.0, 10.0)]
    path = str(tmp_path / "exp_v1.bin")
    _, header, _ = export_objects(
        path, objs,
        format_version=FORMAT_VERSION_V1,
        epoch_jd=J2016_JD,
        state_mode=STATE_MODE_EPHEMERIS,
    )
    assert header.version == FORMAT_VERSION_V1
    assert header.v2_extras is None
    parsed = read_visible_sector(path)
    assert parsed.header.version == FORMAT_VERSION_V1
