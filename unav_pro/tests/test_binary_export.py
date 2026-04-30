"""Tests for data.binary_export (v0.8 visible-sector binary format)."""

from __future__ import annotations

import os
import struct
import zlib

import pytest

from data.binary_export import (
    FOOTER_SIZE,
    FORMAT_VERSION,
    HEADER_SIZE,
    MAGIC,
    MAGIC_END,
    POINT_SIZE,
    SOURCE_HEADER_SIZE,
    BinaryExportError,
    BinaryHeader,
    UnavBinaryPoint,
    build_source_table,
    compute_uid_hash,
    export_objects,
    object_to_binary_point,
    read_visible_sector,
    write_visible_sector,
)
from data.schema import CatalogObject, compute_derived_fields


# ---------------------------------------------------------------------------
# Constants / sanity
# ---------------------------------------------------------------------------


def test_point_record_is_52_bytes():
    """The on-disk point matches the documented C++ struct layout."""
    assert POINT_SIZE == 52


def test_header_size_matches_struct():
    # Sanity: size matches the doc.
    # 4 (magic) + 2 (ver) + 2 (flags) + 8 (scale) + 4*3 (counts) + 2 (sidecar_len) = 30
    assert HEADER_SIZE == 30


def test_footer_size_is_eight_bytes():
    assert FOOTER_SIZE == 8


def test_magic_constants_are_uppercase_ascii():
    assert MAGIC == b"UNAV"
    assert MAGIC_END == b"UEND"


# ---------------------------------------------------------------------------
# UnavBinaryPoint pack/unpack
# ---------------------------------------------------------------------------


def test_point_round_trips_bytes():
    p = UnavBinaryPoint(
        x=1.5, y=-2.0, z=3.0,
        size=2.0, r=0.1, g=0.5, b=0.9,
        uid_hash=0xDEADBEEFCAFEBABE,
        source_id=42,
    )
    raw = p.pack()
    assert len(raw) == POINT_SIZE
    p2 = UnavBinaryPoint.unpack(raw)
    assert p2.x == pytest.approx(1.5)
    assert p2.y == pytest.approx(-2.0)
    assert p2.z == pytest.approx(3.0)
    assert p2.size == pytest.approx(2.0)
    assert p2.uid_hash == 0xDEADBEEFCAFEBABE
    assert p2.source_id == 42


def test_point_unpack_rejects_wrong_size():
    with pytest.raises(BinaryExportError):
        UnavBinaryPoint.unpack(b"\x00" * (POINT_SIZE - 1))
    with pytest.raises(BinaryExportError):
        UnavBinaryPoint.unpack(b"\x00" * (POINT_SIZE + 1))


def test_point_clamps_color_into_packed_floats():
    p = UnavBinaryPoint(
        x=0.0, y=0.0, z=0.0, size=1.0,
        r=2.5, g=-0.3, b=0.5,
        uid_hash=1, source_id=1,
    )
    # The dataclass itself doesn't clamp (object_to_binary_point does).
    # Round-trip is loss-tolerant up to float32 precision.
    p2 = UnavBinaryPoint.unpack(p.pack())
    assert p2.r == pytest.approx(2.5)
    assert p2.g == pytest.approx(-0.3)


# ---------------------------------------------------------------------------
# compute_uid_hash
# ---------------------------------------------------------------------------


def test_uid_hash_is_stable_across_calls():
    a = compute_uid_hash("gaia:1234567890")
    b = compute_uid_hash("gaia:1234567890")
    assert a == b


def test_uid_hash_distinguishes_distinct_uids():
    a = compute_uid_hash("gaia:1")
    b = compute_uid_hash("sdss:1")
    assert a != b


def test_uid_hash_handles_empty_string():
    # Stable, non-raising.
    assert compute_uid_hash("") == compute_uid_hash("")


def test_uid_hash_fits_in_uint64():
    h = compute_uid_hash("very long uid that is unlikely to overflow")
    assert 0 <= h < (1 << 64)


# ---------------------------------------------------------------------------
# build_source_table
# ---------------------------------------------------------------------------


def _obj(uid: str, source: str, **kw) -> CatalogObject:
    base = dict(
        uid=uid, catalog_source=source, object_type="star",
        ra_deg=10.0, dec_deg=20.0, distance_parsec=10.0,
    )
    base.update(kw)
    o = CatalogObject(**base)
    compute_derived_fields(o)
    return o


def test_source_table_assigns_ids_starting_at_one():
    objects = [
        _obj("a", "Gaia DR3"),
        _obj("b", "Gaia DR3"),
        _obj("c", "SDSS"),
    ]
    table, name_to_id = build_source_table(objects)
    assert name_to_id == {"Gaia DR3": 1, "SDSS": 2}
    assert table == [(1, "Gaia DR3"), (2, "SDSS")]


def test_source_table_preserves_first_seen_order():
    objects = [
        _obj("a", "DESI"),
        _obj("b", "Gaia DR3"),
        _obj("c", "DESI"),
    ]
    table, name_to_id = build_source_table(objects)
    assert table == [(1, "DESI"), (2, "Gaia DR3")]


def test_source_table_skips_empty_source_label():
    objects = [
        _obj("a", "Gaia DR3"),
        _obj("b", ""),
        _obj("c", "Gaia DR3"),
    ]
    table, _ = build_source_table(objects)
    assert table == [(1, "Gaia DR3")]


# ---------------------------------------------------------------------------
# object_to_binary_point
# ---------------------------------------------------------------------------


def test_object_to_binary_point_uses_natural_color_when_encoding_none():
    obj = _obj("gaia:1", "Gaia DR3")
    pt = object_to_binary_point(obj, source_id=1)
    # Natural path produces a non-zero radius and a colour in [0, 1].
    assert pt.size > 0
    assert 0.0 <= pt.r <= 1.0
    assert 0.0 <= pt.g <= 1.0
    assert 0.0 <= pt.b <= 1.0
    assert pt.uid_hash == compute_uid_hash("gaia:1")
    assert pt.source_id == 1


def test_object_to_binary_point_uses_encoder_when_supplied():
    from core.visual_encoding import VisualEncodingParams
    obj = _obj("desi:1", "DESI", redshift=0.05, object_type="galaxy")
    enc = VisualEncodingParams(color_mode="redshift", redshift_min=0.0, redshift_max=3.0)
    pt = object_to_binary_point(obj, source_id=1, encoding=enc)
    assert 0.0 <= pt.r <= 1.0
    assert 0.0 <= pt.g <= 1.0
    assert 0.0 <= pt.b <= 1.0


def test_object_to_binary_point_recomputes_when_c4d_missing():
    obj = CatalogObject(
        uid="a", catalog_source="X", object_type="star",
        ra_deg=0.0, dec_deg=0.0, distance_parsec=10.0,
    )
    pt = object_to_binary_point(obj, source_id=1)
    # ra=0, dec=0, d=10 → x=10, y=0, z=0 in pc.
    assert pt.x == pytest.approx(10.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Write / read round-trip
# ---------------------------------------------------------------------------


def test_round_trip_three_points(tmp_path):
    out = tmp_path / "rt.unav"
    points = [
        UnavBinaryPoint(
            x=float(i), y=float(-i), z=float(i * i),
            size=1.0, r=0.5, g=0.5, b=0.5,
            uid_hash=i + 1, source_id=1,
        )
        for i in range(3)
    ]
    sources = [(1, "Gaia DR3")]
    n_bytes = write_visible_sector(
        str(out), points, sources=sources,
        coordinate_scale_factor=1.0, sidecar_path="some/sidecar.jsonl",
    )
    assert n_bytes == os.path.getsize(out)

    parsed = read_visible_sector(str(out))
    assert parsed.header.magic == MAGIC
    assert parsed.header.version == FORMAT_VERSION
    assert parsed.header.point_count == 3
    assert parsed.header.source_count == 1
    assert parsed.header.coordinate_scale_factor == pytest.approx(1.0)
    assert parsed.header.sidecar_path == "some/sidecar.jsonl"
    assert parsed.sources == [(1, "Gaia DR3")]
    assert len(parsed.points) == 3
    for orig, reread in zip(points, parsed.points):
        assert reread.x == pytest.approx(orig.x)
        assert reread.uid_hash == orig.uid_hash
        assert reread.source_id == orig.source_id


def test_round_trip_empty_points(tmp_path):
    out = tmp_path / "empty.unav"
    write_visible_sector(str(out), points=[], sources=[])
    parsed = read_visible_sector(str(out))
    assert parsed.header.point_count == 0
    assert parsed.header.source_count == 0
    assert parsed.points == []
    assert parsed.sources == []


def test_round_trip_omits_sidecar_when_empty(tmp_path):
    out = tmp_path / "nosidecar.unav"
    write_visible_sector(str(out), points=[], sources=[])
    parsed = read_visible_sector(str(out))
    assert parsed.header.sidecar_path == ""


def test_round_trip_unicode_source_name(tmp_path):
    out = tmp_path / "unicode.unav"
    sources = [(1, "Survey Δ⃗ Æ"), (2, "DESI")]
    write_visible_sector(str(out), points=[], sources=sources)
    parsed = read_visible_sector(str(out))
    assert parsed.sources == sources


# ---------------------------------------------------------------------------
# Corruption detection
# ---------------------------------------------------------------------------


def test_corrupt_magic_rejected(tmp_path):
    out = tmp_path / "bad.unav"
    write_visible_sector(str(out), points=[], sources=[])
    raw = bytearray(out.read_bytes())
    raw[0:4] = b"XXXX"
    out.write_bytes(bytes(raw))
    with pytest.raises(BinaryExportError, match="bad magic"):
        read_visible_sector(str(out))


def test_corrupt_end_magic_rejected(tmp_path):
    out = tmp_path / "bad_end.unav"
    write_visible_sector(str(out), points=[], sources=[])
    raw = bytearray(out.read_bytes())
    raw[-FOOTER_SIZE:-FOOTER_SIZE + 4] = b"XXXX"
    out.write_bytes(bytes(raw))
    with pytest.raises(BinaryExportError, match="bad end magic"):
        read_visible_sector(str(out))


def test_unsupported_version_rejected(tmp_path):
    out = tmp_path / "bad_ver.unav"
    write_visible_sector(str(out), points=[], sources=[])
    raw = bytearray(out.read_bytes())
    # Version field starts at offset 4 (after magic), 2 bytes LE.
    raw[4:6] = (FORMAT_VERSION + 9).to_bytes(2, "little")
    out.write_bytes(bytes(raw))
    with pytest.raises(BinaryExportError, match="unsupported format version"):
        read_visible_sector(str(out))


def test_truncated_file_rejected(tmp_path):
    out = tmp_path / "trunc.unav"
    write_visible_sector(str(out), points=[], sources=[])
    raw = out.read_bytes()
    out.write_bytes(raw[:-1])
    with pytest.raises(BinaryExportError):
        read_visible_sector(str(out))


def test_crc_mismatch_rejected(tmp_path):
    """Tweak a point byte but leave the footer CRC intact → CRC mismatch."""
    out = tmp_path / "bad_crc.unav"
    points = [UnavBinaryPoint(
        x=1.0, y=2.0, z=3.0, size=1.0,
        r=0.5, g=0.5, b=0.5, uid_hash=42, source_id=1,
    )]
    write_visible_sector(str(out), points, sources=[(1, "Gaia DR3")])
    raw = bytearray(out.read_bytes())
    # Flip a byte inside the point block (just before the footer).
    raw[-FOOTER_SIZE - 1] ^= 0xFF
    out.write_bytes(bytes(raw))
    with pytest.raises(BinaryExportError, match="CRC"):
        read_visible_sector(str(out))


def test_point_count_mismatch_overruns_file(tmp_path):
    """Header claims a point count larger than the bytes can hold."""
    out = tmp_path / "lying_count.unav"
    write_visible_sector(str(out), points=[], sources=[])
    raw = bytearray(out.read_bytes())
    # point_count field is at offset 16 (4 magic + 2 ver + 2 flags + 8 scale).
    pc_offset = 4 + 2 + 2 + 8
    raw[pc_offset:pc_offset + 4] = (999).to_bytes(4, "little")
    out.write_bytes(bytes(raw))
    with pytest.raises(BinaryExportError, match="overruns"):
        read_visible_sector(str(out))


# ---------------------------------------------------------------------------
# export_objects end-to-end
# ---------------------------------------------------------------------------


def test_export_objects_writes_file_with_correct_counts(tmp_path):
    out = tmp_path / "objs.unav"
    objects = [
        _obj("gaia:1", "Gaia DR3"),
        _obj("gaia:2", "Gaia DR3"),
        _obj("sdss:9001", "SDSS", object_type="galaxy"),
    ]
    n_bytes, header, sources = export_objects(str(out), objects)
    assert n_bytes == os.path.getsize(out)
    assert header.point_count == 3
    assert header.source_count == 2
    assert {name for _id, name in sources} == {"Gaia DR3", "SDSS"}

    parsed = read_visible_sector(str(out))
    assert parsed.header.point_count == 3
    assert {name for _id, name in parsed.sources} == {"Gaia DR3", "SDSS"}


def test_export_objects_skips_objects_without_uid(tmp_path):
    out = tmp_path / "skipuid.unav"
    bad = _obj("a", "X")
    bad.uid = ""
    good = _obj("b", "X")
    n_bytes, header, _ = export_objects(str(out), [bad, good])
    assert header.point_count == 1


def test_export_objects_records_scale_factor_per_mode(tmp_path):
    """Header carries the C4D-units-per-pc scale used by the
    exporter so the C++ side doesn't have to guess."""
    from data.schema import SCALE_MODES
    out = tmp_path / "scale.unav"
    objects = [_obj("a", "X")]
    _bytes, header, _ = export_objects(
        str(out), objects, scale_mode="kpc",
    )
    assert header.coordinate_scale_factor == pytest.approx(SCALE_MODES["kpc"])


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_cli_exit_code_for_missing_input(tmp_path):
    from tools import export_visible_sector_binary
    rc = export_visible_sector_binary.main([
        "--input", str(tmp_path / "missing.jsonl"),
        "--output", str(tmp_path / "out.unav"),
        "--quiet",
    ])
    assert rc == 2


def test_cli_writes_file_for_valid_input(tmp_path):
    """End-to-end: write a JSONL, run the CLI, parse the output."""
    from tools import export_visible_sector_binary
    from data.catalog_io import write_catalog
    src = tmp_path / "in.jsonl"
    objects = [_obj(f"gaia:{i}", "Gaia DR3") for i in range(3)]
    write_catalog(objects, str(src))
    out = tmp_path / "out.unav"
    rc = export_visible_sector_binary.main([
        "--input", str(src), "--output", str(out), "--quiet",
    ])
    assert rc == 0
    parsed = read_visible_sector(str(out))
    assert parsed.header.point_count == 3
