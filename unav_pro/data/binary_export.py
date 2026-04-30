"""Binary visible-sector exporter (v0.8 native bridge format).

Writes a small, mmap-friendly binary file the future C++ point
renderer will read. The format is documented in
``docs/BINARY_VISIBLE_SECTOR_FORMAT.md``; this module is the
reference implementation.

Design notes
------------

* **Stdlib-only.** ``struct`` for packing, ``hashlib`` for the
  ``uid_hash``, ``zlib`` for the trailing CRC32. No numpy at
  runtime.
* **No C++ coupling today.** The exporter writes a file; the
  native plugin (when it lands) reads the same file. There is no
  embedded Python ↔ C++ ABI in v0.8 — the file is the only
  contract.
* **Round-trippable.** ``read_visible_sector(path)`` consumes a
  file produced by ``write_visible_sector(...)`` and produces a
  ``BinaryVisibleSector`` matching the input. Tests assert this.

The on-disk layout is little-endian throughout. Both endianness
and struct padding are pinned by ``<`` in the format strings;
reading on a big-endian host or with a different alignment
discipline still produces the same bytes.
"""

from __future__ import annotations

import hashlib
import os
import struct
import zlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core.logging_util import get_logger
from data.schema import (
    DEFAULT_SCALE_MODE,
    SCALE_MODES,
    CatalogObject,
    compute_derived_fields,
    display_color_for,
    render_radius_from_magnitude,
)

_log = get_logger("data.binary_export")


# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------

#: Header magic. 4 ASCII bytes. ``b"UNAV"``.
MAGIC: bytes = b"UNAV"

#: End-of-file magic. 4 ASCII bytes. ``b"UEND"``.
MAGIC_END: bytes = b"UEND"

#: On-disk format version. Bumped when a backwards-incompatible
#: change lands. Today: 1.
FORMAT_VERSION: int = 1

#: Header struct format (excluding the optional metadata-sidecar
#: path appended after the fixed header). Little-endian, packed.
#:
#:   magic[4]:                 b"UNAV"
#:   version:                  uint16
#:   flags:                    uint16   (reserved; 0 today)
#:   coordinate_scale_factor:  float64  (C4D units per parsec)
#:   point_count:              uint32
#:   source_count:              uint32
#:   header_extra_bytes:       uint32   (reserved future header growth, 0 today)
#:   sidecar_path_len:         uint16   (UTF-8 byte length, 0 if no sidecar)
_HEADER_FMT = "<4sHHdIIIH"
HEADER_SIZE: int = struct.calcsize(_HEADER_FMT)

#: Per-point record. Mirrors the C++ ``UnavPoint`` struct in
#: ``native/include/unav_point_buffer.h``. 52 bytes per point;
#: explicit little-endian + packed (no struct padding) so the
#: format is portable across compilers and platforms.
#:
#:   double x, y, z         (3 × 8 = 24 bytes)
#:   float  size            (4 bytes)
#:   float  r, g, b         (3 × 4 = 12 bytes)
#:   uint64 uid_hash        (8 bytes)
#:   uint32 source_id       (4 bytes)
_POINT_FMT = "<dddffffQI"
POINT_SIZE: int = struct.calcsize(_POINT_FMT)

#: Per-source-table-entry record (variable; the name byte length
#: is in the entry itself).
#:
#:   uint32 source_id
#:   uint16 name_len
#:   bytes  name (name_len UTF-8 bytes)
_SOURCE_HEADER_FMT = "<IH"
SOURCE_HEADER_SIZE: int = struct.calcsize(_SOURCE_HEADER_FMT)

#: Footer:
#:
#:   bytes  magic_end[4]    (b"UEND")
#:   uint32 crc32           (over: file bytes from header[4:] up to but not including the footer)
_FOOTER_FMT = "<4sI"
FOOTER_SIZE: int = struct.calcsize(_FOOTER_FMT)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BinaryExportError(Exception):
    """Raised for unrecoverable binary-export / parse errors."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class UnavBinaryPoint:
    """One record in the visible-sector binary file.

    Mirrors the C++ ``UnavPoint`` struct documented in the
    ``native/`` skeleton. ``uid_hash`` is a 64-bit BLAKE2b digest
    of the original ``CatalogObject.uid`` (computed by
    ``compute_uid_hash``); the original string lives only in the
    optional metadata sidecar.
    """

    x: float
    y: float
    z: float
    size: float
    r: float
    g: float
    b: float
    uid_hash: int
    source_id: int

    def pack(self) -> bytes:
        return struct.pack(
            _POINT_FMT,
            float(self.x), float(self.y), float(self.z),
            float(self.size),
            float(self.r), float(self.g), float(self.b),
            int(self.uid_hash) & 0xFFFFFFFFFFFFFFFF,
            int(self.source_id) & 0xFFFFFFFF,
        )

    @classmethod
    def unpack(cls, raw: bytes) -> "UnavBinaryPoint":
        if len(raw) != POINT_SIZE:
            raise BinaryExportError(
                f"point record size {len(raw)} != expected {POINT_SIZE}"
            )
        (
            x, y, z, size, r, g, b, uid_hash, source_id,
        ) = struct.unpack(_POINT_FMT, raw)
        return cls(
            x=float(x), y=float(y), z=float(z),
            size=float(size), r=float(r), g=float(g), b=float(b),
            uid_hash=int(uid_hash), source_id=int(source_id),
        )


@dataclass
class BinaryHeader:
    """Header fields read from / written to disk."""

    magic: bytes = MAGIC
    version: int = FORMAT_VERSION
    flags: int = 0
    coordinate_scale_factor: float = 1.0
    point_count: int = 0
    source_count: int = 0
    header_extra_bytes: int = 0
    sidecar_path: str = ""


@dataclass
class BinaryVisibleSector:
    """In-memory view of a parsed visible-sector binary file."""

    header: BinaryHeader = field(default_factory=BinaryHeader)
    sources: List[Tuple[int, str]] = field(default_factory=list)
    points: List[UnavBinaryPoint] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_uid_hash(uid: str) -> int:
    """Stable 64-bit BLAKE2b digest of a UNAV uid.

    The native plugin uses this to key its in-engine metadata
    side-car: the C++ buffer carries hashes only; the Python side
    keeps the (uid_hash → uid) reverse table in the metadata
    sidecar."""
    digest = hashlib.blake2b(
        (uid or "").encode("utf-8"), digest_size=8,
    ).digest()
    return int.from_bytes(digest, "little", signed=False)


def _safe_clamp_color(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def object_to_binary_point(
    obj: CatalogObject,
    *,
    source_id: int,
    scale_mode: str = DEFAULT_SCALE_MODE,
    encoding=None,
) -> UnavBinaryPoint:
    """Convert one ``CatalogObject`` into a ``UnavBinaryPoint``.

    The colour and radius come from ``core.visual_encoding.encode``
    via the same path the v0.7 backends use, so the binary file
    matches what Instance Mode would produce in the viewport.
    """
    if (
        obj.c4d_x is None or obj.c4d_y is None or obj.c4d_z is None
        or scale_mode != DEFAULT_SCALE_MODE
    ):
        compute_derived_fields(obj, scale_mode=scale_mode)

    if encoding is None:
        rgb_int = obj.display_color_rgb or display_color_for(
            obj.object_type, obj.spectral_type,
        )
        radius = obj.render_radius
        if radius is None:
            radius = render_radius_from_magnitude(obj.apparent_magnitude)
    else:
        from core.visual_encoding import encode as encode_visuals
        rgb_int, radius = encode_visuals(obj, encoding)

    r, g, b = rgb_int
    return UnavBinaryPoint(
        x=float(obj.c4d_x),
        y=float(obj.c4d_y),
        z=float(obj.c4d_z),
        size=float(radius),
        r=_safe_clamp_color(r / 255.0),
        g=_safe_clamp_color(g / 255.0),
        b=_safe_clamp_color(b / 255.0),
        uid_hash=compute_uid_hash(obj.uid),
        source_id=int(source_id),
    )


def build_source_table(
    objects: Sequence[CatalogObject],
) -> Tuple[List[Tuple[int, str]], Dict[str, int]]:
    """Walk ``objects`` and produce ``(source_table, name_to_id)``.

    Source IDs are assigned in first-seen order starting at 1
    (``0`` is reserved for "unknown / no source"). The returned
    ``name_to_id`` map keys by the catalog source label (`"Gaia
    DR3"`, `"SDSS"`, `"DESI"`, `"JPL Horizons"`, …).
    """
    table: List[Tuple[int, str]] = []
    name_to_id: Dict[str, int] = {}
    next_id = 1
    for obj in objects:
        name = (obj.catalog_source or "").strip() or ""
        if not name:
            continue
        if name not in name_to_id:
            name_to_id[name] = next_id
            table.append((next_id, name))
            next_id += 1
    return table, name_to_id


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def _pack_header(header: BinaryHeader) -> bytes:
    sidecar_bytes = (header.sidecar_path or "").encode("utf-8")
    fixed = struct.pack(
        _HEADER_FMT,
        MAGIC,
        int(header.version) & 0xFFFF,
        int(header.flags) & 0xFFFF,
        float(header.coordinate_scale_factor),
        int(header.point_count) & 0xFFFFFFFF,
        int(header.source_count) & 0xFFFFFFFF,
        int(header.header_extra_bytes) & 0xFFFFFFFF,
        len(sidecar_bytes) & 0xFFFF,
    )
    return fixed + sidecar_bytes


def _pack_source_table(sources: Sequence[Tuple[int, str]]) -> bytes:
    parts: List[bytes] = []
    for source_id, name in sources:
        name_bytes = (name or "").encode("utf-8")
        parts.append(struct.pack(
            _SOURCE_HEADER_FMT,
            int(source_id) & 0xFFFFFFFF,
            len(name_bytes) & 0xFFFF,
        ))
        parts.append(name_bytes)
    return b"".join(parts)


def write_visible_sector(
    path: str,
    points: Sequence[UnavBinaryPoint],
    *,
    sources: Sequence[Tuple[int, str]] = (),
    coordinate_scale_factor: float = 1.0,
    sidecar_path: str = "",
) -> int:
    """Write the visible sector to ``path``. Returns total bytes
    written. Parent directories are created as needed.

    ``coordinate_scale_factor`` records the C4D-units-per-parsec
    used when the points were packed (default ``1.0`` for
    ``scale_mode='pc'``). ``sidecar_path`` is an optional relative
    path to a UTF-8 metadata sidecar (the JSONL produced by the
    rest of the plugin); ``""`` (default) means no sidecar.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    header = BinaryHeader(
        magic=MAGIC,
        version=FORMAT_VERSION,
        flags=0,
        coordinate_scale_factor=float(coordinate_scale_factor),
        point_count=len(points),
        source_count=len(sources),
        header_extra_bytes=0,
        sidecar_path=sidecar_path or "",
    )

    header_bytes = _pack_header(header)
    sources_bytes = _pack_source_table(sources)
    points_bytes_chunks: List[bytes] = [pt.pack() for pt in points]
    points_bytes = b"".join(points_bytes_chunks)

    payload = header_bytes[len(MAGIC):] + sources_bytes + points_bytes
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    footer_bytes = struct.pack(_FOOTER_FMT, MAGIC_END, crc)

    total = 0
    with open(path, "wb") as fh:
        for blob in (header_bytes, sources_bytes, points_bytes, footer_bytes):
            fh.write(blob)
            total += len(blob)
    _log.info(
        "Wrote %d points (%d sources) to %s (%d bytes).",
        len(points), len(sources), path, total,
    )
    return total


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


def _unpack_header(raw: bytes) -> Tuple[BinaryHeader, int]:
    """Parse the fixed header (and, if present, the trailing
    sidecar-path UTF-8). Returns ``(header, total_header_bytes)``."""
    if len(raw) < HEADER_SIZE:
        raise BinaryExportError(
            f"file too small to hold header: {len(raw)} < {HEADER_SIZE}"
        )
    (
        magic, version, flags, scale, point_count, source_count,
        header_extra_bytes, sidecar_path_len,
    ) = struct.unpack(_HEADER_FMT, raw[:HEADER_SIZE])
    if magic != MAGIC:
        raise BinaryExportError(
            f"bad magic {magic!r}; expected {MAGIC!r}"
        )
    if version != FORMAT_VERSION:
        raise BinaryExportError(
            f"unsupported format version {version}; "
            f"this build understands {FORMAT_VERSION}"
        )
    sidecar_end = HEADER_SIZE + int(sidecar_path_len)
    if sidecar_end > len(raw):
        raise BinaryExportError(
            "sidecar_path_len overruns file"
        )
    sidecar = raw[HEADER_SIZE:sidecar_end].decode("utf-8") if sidecar_path_len else ""
    return (
        BinaryHeader(
            magic=magic,
            version=int(version),
            flags=int(flags),
            coordinate_scale_factor=float(scale),
            point_count=int(point_count),
            source_count=int(source_count),
            header_extra_bytes=int(header_extra_bytes),
            sidecar_path=sidecar,
        ),
        sidecar_end,
    )


def _unpack_source_table(
    raw: bytes, offset: int, count: int,
) -> Tuple[List[Tuple[int, str]], int]:
    out: List[Tuple[int, str]] = []
    cursor = offset
    for _ in range(count):
        if cursor + SOURCE_HEADER_SIZE > len(raw):
            raise BinaryExportError("source table overruns file")
        (source_id, name_len) = struct.unpack(
            _SOURCE_HEADER_FMT, raw[cursor:cursor + SOURCE_HEADER_SIZE],
        )
        cursor += SOURCE_HEADER_SIZE
        if cursor + int(name_len) > len(raw):
            raise BinaryExportError("source name overruns file")
        name = raw[cursor:cursor + int(name_len)].decode("utf-8")
        cursor += int(name_len)
        out.append((int(source_id), name))
    return out, cursor


def read_visible_sector(path: str) -> BinaryVisibleSector:
    """Parse a visible-sector binary file produced by
    ``write_visible_sector``. Raises ``BinaryExportError`` on any
    malformed / truncated / mis-CRCed input.

    Note: missing files raise ``FileNotFoundError`` (Python's
    natural ``OSError`` subclass), not ``BinaryExportError`` —
    callers that want a uniform error type should wrap the call
    site themselves."""
    with open(path, "rb") as fh:
        raw = fh.read()

    if len(raw) < HEADER_SIZE + FOOTER_SIZE:
        raise BinaryExportError("file truncated; missing header / footer")

    header, header_end = _unpack_header(raw)
    sources, src_end = _unpack_source_table(
        raw, header_end, header.source_count,
    )

    points_bytes_needed = header.point_count * POINT_SIZE
    if src_end + points_bytes_needed + FOOTER_SIZE > len(raw):
        raise BinaryExportError("point block overruns file")

    points: List[UnavBinaryPoint] = []
    cursor = src_end
    for _ in range(header.point_count):
        points.append(UnavBinaryPoint.unpack(
            raw[cursor:cursor + POINT_SIZE],
        ))
        cursor += POINT_SIZE

    footer_start = cursor
    if footer_start + FOOTER_SIZE != len(raw):
        # Allow harmless trailing whitespace / extra bytes only
        # if a future version uses them; today the file ends at
        # the footer. Anything else is corrupt.
        raise BinaryExportError(
            "trailing bytes after footer: file is malformed"
        )
    magic_end, stored_crc = struct.unpack(
        _FOOTER_FMT, raw[footer_start:footer_start + FOOTER_SIZE],
    )
    if magic_end != MAGIC_END:
        raise BinaryExportError(
            f"bad end magic {magic_end!r}; expected {MAGIC_END!r}"
        )
    payload = raw[len(MAGIC):footer_start]
    actual_crc = zlib.crc32(payload) & 0xFFFFFFFF
    if int(stored_crc) != int(actual_crc):
        raise BinaryExportError(
            f"CRC mismatch: stored {stored_crc:#x}, computed {actual_crc:#x}"
        )

    return BinaryVisibleSector(
        header=header, sources=sources, points=points,
    )


# ---------------------------------------------------------------------------
# CatalogObject → file end-to-end
# ---------------------------------------------------------------------------


def export_objects(
    path: str,
    objects: Sequence[CatalogObject],
    *,
    encoding=None,
    scale_mode: str = DEFAULT_SCALE_MODE,
    sidecar_path: str = "",
) -> Tuple[int, BinaryHeader, List[Tuple[int, str]]]:
    """Convenience: convert a sequence of ``CatalogObject`` into
    binary points and write them. Returns
    ``(bytes_written, header, source_table)``.

    The source IDs are assigned in first-seen order starting at 1;
    the C++ side reads them straight off the file's source table.
    """
    sources, name_to_id = build_source_table(objects)
    points: List[UnavBinaryPoint] = []
    for obj in objects:
        if not getattr(obj, "uid", None):
            continue
        sid = name_to_id.get((obj.catalog_source or "").strip(), 0)
        try:
            points.append(object_to_binary_point(
                obj, source_id=sid,
                scale_mode=scale_mode, encoding=encoding,
            ))
        except Exception:  # noqa: BLE001 — never let one bad row stop the export
            _log.exception("Skipping bad object during export: %r", obj.uid)
            continue

    scale_factor = SCALE_MODES.get(scale_mode, 1.0)
    bytes_written = write_visible_sector(
        path, points,
        sources=sources,
        coordinate_scale_factor=scale_factor,
        sidecar_path=sidecar_path,
    )
    header = BinaryHeader(
        version=FORMAT_VERSION,
        flags=0,
        coordinate_scale_factor=float(scale_factor),
        point_count=len(points),
        source_count=len(sources),
        sidecar_path=sidecar_path or "",
    )
    return bytes_written, header, sources
