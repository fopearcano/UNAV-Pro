"""Tests for the v1.0 binary visible-sector v2 format additions."""

from __future__ import annotations

import os

import pytest

from data.binary_export import (
    FORMAT_VERSION_V1,
    FORMAT_VERSION_V2,
    RENDERER_FLAG_BOUNDING_BOX_VALID,
    RENDERER_FLAG_BOUNDING_SPHERE_VALID,
    RENDERER_FLAG_DEBUG_DRAW,
    RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN,
    SUPPORTED_FORMAT_VERSIONS,
    V2_EXTRA_HEADER_SIZE,
    VISUAL_ENCODING_ID_NONE,
    BinaryExportError,
    BinaryHeader,
    BinaryV2Extras,
    UnavBinaryPoint,
    compute_aabb,
    compute_bounding_sphere,
    compute_uid_hash,
    export_objects,
    make_relative_points,
    make_v2_extras,
    read_visible_sector,
    write_visible_sector,
)
from data.schema import CatalogObject, compute_derived_fields


def _pt(x: float, y: float, z: float, **kw) -> UnavBinaryPoint:
    base = dict(
        x=x, y=y, z=z, size=1.0, r=0.5, g=0.5, b=0.5,
        uid_hash=1, source_id=1,
    )
    base.update(kw)
    return UnavBinaryPoint(**base)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_supported_versions_contains_both_v1_and_v2():
    assert FORMAT_VERSION_V1 in SUPPORTED_FORMAT_VERSIONS
    assert FORMAT_VERSION_V2 in SUPPORTED_FORMAT_VERSIONS


def test_v2_extra_header_size_is_112_bytes():
    assert V2_EXTRA_HEADER_SIZE == 112


def test_renderer_flag_bits_are_distinct_powers_of_two():
    flags = [
        RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN,
        RENDERER_FLAG_DEBUG_DRAW,
        RENDERER_FLAG_BOUNDING_SPHERE_VALID,
        RENDERER_FLAG_BOUNDING_BOX_VALID,
    ]
    for f in flags:
        assert f & (f - 1) == 0  # power of two
    # All distinct.
    assert len(set(flags)) == len(flags)


# ---------------------------------------------------------------------------
# compute_aabb / compute_bounding_sphere / make_v2_extras
# ---------------------------------------------------------------------------


def test_compute_aabb_returns_tight_box():
    pts = [_pt(-1, 0, 0), _pt(1, 5, -3), _pt(0, 0, 7)]
    mn, mx = compute_aabb(pts)
    assert mn == (-1, 0, -3)
    assert mx == (1, 5, 7)


def test_compute_aabb_handles_empty():
    mn, mx = compute_aabb([])
    assert mn == (0.0, 0.0, 0.0)
    assert mx == (0.0, 0.0, 0.0)


def test_compute_bounding_sphere_centroid_and_radius():
    # Three points at distance 3 from origin → centroid is the
    # origin (along axes that average out) and radius == 3.
    pts = [_pt(3, 0, 0), _pt(0, 3, 0), _pt(0, 0, 3)]
    cx, cy, cz, r = compute_bounding_sphere(pts)
    # Centroid = (1, 1, 1), distance from centroid to (3,0,0) is sqrt((3-1)^2+1+1) = sqrt(6).
    assert cx == pytest.approx(1.0)
    assert cy == pytest.approx(1.0)
    assert cz == pytest.approx(1.0)
    assert r == pytest.approx(6 ** 0.5)


def test_compute_bounding_sphere_handles_empty():
    out = compute_bounding_sphere([])
    assert out == (0.0, 0.0, 0.0, 0.0)


def test_make_v2_extras_sets_validity_flags_when_points_present():
    pts = [_pt(1, 2, 3), _pt(4, 5, 6)]
    extras = make_v2_extras(pts)
    assert extras.renderer_flags & RENDERER_FLAG_BOUNDING_SPHERE_VALID
    assert extras.renderer_flags & RENDERER_FLAG_BOUNDING_BOX_VALID


def test_make_v2_extras_uses_centroid_when_origin_unspecified():
    pts = [_pt(0, 0, 0), _pt(10, 0, 0)]
    extras = make_v2_extras(pts)
    # Centroid X = 5.
    assert extras.sector_origin[0] == pytest.approx(5.0)


def test_make_v2_extras_records_visual_encoding_id():
    extras = make_v2_extras([_pt(0, 0, 0)], visual_encoding_id=42)
    assert extras.visual_encoding_id == 42


# ---------------------------------------------------------------------------
# make_relative_points
# ---------------------------------------------------------------------------


def test_make_relative_points_subtracts_origin():
    pts = [_pt(10, 20, 30), _pt(11, 21, 31)]
    rel = make_relative_points(pts, sector_origin=(10.0, 20.0, 30.0))
    assert rel[0].x == 0 and rel[0].y == 0 and rel[0].z == 0
    assert rel[1].x == 1 and rel[1].y == 1 and rel[1].z == 1
    # Other fields preserved.
    assert rel[0].uid_hash == pts[0].uid_hash


# ---------------------------------------------------------------------------
# v2 round-trip
# ---------------------------------------------------------------------------


def test_v2_write_read_round_trip_preserves_extras(tmp_path):
    out = tmp_path / "v2.unav"
    pts = [_pt(1, 2, 3), _pt(4, 5, 6), _pt(-1, -2, -3)]
    extras = make_v2_extras(pts, visual_encoding_id=0xDEADBEEF)
    extras.renderer_flags |= RENDERER_FLAG_DEBUG_DRAW
    write_visible_sector(
        str(out), pts,
        sources=[(1, "Gaia DR3")],
        format_version=FORMAT_VERSION_V2,
        v2_extras=extras,
    )
    parsed = read_visible_sector(str(out))
    assert parsed.header.version == FORMAT_VERSION_V2
    assert parsed.header.has_v2_extras()
    assert parsed.header.v2_extras.visual_encoding_id == 0xDEADBEEF
    assert parsed.header.v2_extras.renderer_flags & RENDERER_FLAG_DEBUG_DRAW
    assert parsed.header.v2_extras.bounding_sphere[3] == pytest.approx(
        extras.bounding_sphere[3]
    )


def test_v2_camera_relative_round_trip_via_export_objects(tmp_path):
    """``export_objects(format_version=V2, camera_relative=True)`` rewrites
    the points as offsets from the sector origin. The on-disk
    point xyz is small even when the absolute scene is far away."""
    out = tmp_path / "rel.unav"
    objs = []
    for i in range(3):
        o = CatalogObject(
            uid=f"gaia:{i}", catalog_source="Gaia DR3", object_type="star",
            ra_deg=0.0, dec_deg=0.0, distance_parsec=100.0 + i,
        )
        compute_derived_fields(o)
        objs.append(o)
    bytes_written, header, _ = export_objects(
        str(out), objs,
        format_version=FORMAT_VERSION_V2,
        camera_relative=True,
        sector_origin=(100.0, 0.0, 0.0),
    )
    parsed = read_visible_sector(str(out))
    assert parsed.header.version == FORMAT_VERSION_V2
    assert parsed.header.v2_extras.renderer_flags & (
        RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN
    )
    # Stored xyz are small (within ~few pc of origin).
    for p in parsed.points:
        assert abs(p.x) < 50.0
    # Sector origin matches what we asked for.
    assert parsed.header.v2_extras.sector_origin[0] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Backward compatibility — v1 callers still work
# ---------------------------------------------------------------------------


def test_v1_writer_default_emits_v1_file(tmp_path):
    """Default ``write_visible_sector(...)`` keeps v1 layout for
    bit-for-bit parity with v0.8 / v0.9."""
    out = tmp_path / "v1.unav"
    write_visible_sector(str(out), [_pt(0, 0, 0)], sources=[(1, "X")])
    parsed = read_visible_sector(str(out))
    assert parsed.header.version == FORMAT_VERSION_V1
    assert parsed.header.v2_extras is None
    assert parsed.header.has_v2_extras() is False


def test_v1_reader_rejects_v2_file_with_extras_flag_off(tmp_path):
    """Robustness check: a v2 file is identified by version=2; any
    file claiming version=1 with non-zero header_extra_bytes is
    malformed and rejected."""
    # We can't easily craft this via the library (the writer is
    # honest about the version). We construct it from raw bytes
    # instead, mirroring the C++ test.
    import struct
    raw = b""
    raw += b"UNAV"
    raw += struct.pack("<HHdIIIH", 1, 0, 1.0, 0, 0, 112, 0)
    raw += b"UEND"
    raw += struct.pack("<I", 0)  # bogus CRC; we'll fail-closed earlier
    p = tmp_path / "broken.unav"
    p.write_bytes(raw)
    with pytest.raises(BinaryExportError, match="header_extra_bytes"):
        read_visible_sector(str(p))


# ---------------------------------------------------------------------------
# Safety — unsupported version, absurd extras
# ---------------------------------------------------------------------------


def test_writer_rejects_unsupported_format_version(tmp_path):
    with pytest.raises(BinaryExportError, match="unsupported format_version"):
        write_visible_sector(str(tmp_path / "x.unav"), [], format_version=99)


def test_v2_writer_emits_zero_extras_when_none_passed(tmp_path):
    out = tmp_path / "zero.unav"
    write_visible_sector(
        str(out), [],
        format_version=FORMAT_VERSION_V2,
    )
    parsed = read_visible_sector(str(out))
    assert parsed.header.has_v2_extras()
    # Zero extras are still well-formed: visual_encoding_id == 0,
    # bounding sphere radius == 0, etc.
    assert parsed.header.v2_extras.visual_encoding_id == VISUAL_ENCODING_ID_NONE
    assert parsed.header.v2_extras.bounding_sphere[3] == 0.0
