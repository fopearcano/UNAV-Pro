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

#: On-disk format versions supported.
#:
#:   v1 — v0.8 / v0.9 layout. Header, sources, points, footer.
#:   v2 — v1.0 layout. Same prefix as v1 plus a fixed-size extra
#:        header block (`header_extra_bytes = V2_EXTRA_HEADER_SIZE`)
#:        carrying renderer flags, visual-encoding id, sector
#:        origin, bounding sphere + AABB. The points block layout
#:        is unchanged.
FORMAT_VERSION_V1: int = 1
FORMAT_VERSION_V2: int = 2
#: v1.2 — adds an explicit ``epoch_jd`` and ``state_mode`` field
#: at the tail of the v2 extra-header block. The native loader
#: parses the extra 16 bytes after the v2 fields when
#: ``version == 3``.
FORMAT_VERSION_V3: int = 3

#: Format version emitted by ``write_visible_sector(...)`` when the
#: caller does not request a specific version. v1.0 keeps the
#: default at v1 so existing callers (the v0.8 CLI, v0.9 native
#: viewer) get bit-for-bit identical output. New callers that
#: want the v2 / v3 features pass ``format_version=FORMAT_VERSION_V2``
#: or ``FORMAT_VERSION_V3`` explicitly.
FORMAT_VERSION: int = FORMAT_VERSION_V1
SUPPORTED_FORMAT_VERSIONS: Tuple[int, ...] = (
    FORMAT_VERSION_V1, FORMAT_VERSION_V2, FORMAT_VERSION_V3,
)

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
# v2 extra-header block
# ---------------------------------------------------------------------------

#: v2 extra-header layout. Sits immediately after the optional
#: sidecar path string (``sidecar_path_len`` bytes) and before the
#: source table. Locked at 96 bytes so the v0.8 ``header_extra_bytes``
#: forward-compat slot exactly carries it.
#:
#:   uint32 renderer_flags
#:   uint32 visual_encoding_id
#:   float64 sector_origin_x, y, z              (parsec)
#:   float64 bounding_sphere_x, y, z, radius    (parsec)
#:   float64 aabb_min_x, y, z                   (parsec)
#:   float64 aabb_max_x, y, z                   (parsec)
_V2_EXTRA_HEADER_FMT = "<II3d4d3d3d"
V2_EXTRA_HEADER_SIZE: int = struct.calcsize(_V2_EXTRA_HEADER_FMT)

#: v3 extras append to the v2 layout:
#:
#:   float64 epoch_jd        — Julian Date the file was rendered for
#:   uint8   state_mode      — 0=static, 1=proper_motion, 2=ephemeris,
#:                              3=mixed (the default for the resolver)
#:   bytes   pad[7]          — reserved for forward-compatibility
_V3_EXTRA_TAIL_FMT = "<dB7s"
V3_EXTRA_TAIL_SIZE: int = struct.calcsize(_V3_EXTRA_TAIL_FMT)
V3_EXTRA_HEADER_SIZE: int = V2_EXTRA_HEADER_SIZE + V3_EXTRA_TAIL_SIZE  # 128

#: ``state_mode`` values stable since v1.2.
STATE_MODE_STATIC = 0
STATE_MODE_PROPER_MOTION = 1
STATE_MODE_EPHEMERIS = 2
STATE_MODE_MIXED = 3
STATE_MODES = (
    STATE_MODE_STATIC, STATE_MODE_PROPER_MOTION,
    STATE_MODE_EPHEMERIS, STATE_MODE_MIXED,
)

#: ``renderer_flags`` bit values. Stable since v1.0.
RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN = 1 << 0  # camera-rel coords
RENDERER_FLAG_DISABLE_DISTANCE_FADE = 1 << 1            # solid alpha at all distances
RENDERER_FLAG_DEBUG_DRAW = 1 << 2                       # GPU debug visualization
RENDERER_FLAG_PREFER_BILLBOARD = 1 << 3                 # billboard fallback if AA points unavailable
RENDERER_FLAG_BOUNDING_SPHERE_VALID = 1 << 4
RENDERER_FLAG_BOUNDING_BOX_VALID = 1 << 5

#: Reserved sentinel for "no visual encoding id" — the renderer
#: should fall back to the colour/size baked into the points.
VISUAL_ENCODING_ID_NONE: int = 0


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
class BinaryV2Extras:
    """v2 / v3 extra-header block.

    The first 112 bytes are the v2 layout (renderer flags +
    visual encoding id + sector origin + bounding sphere + AABB).
    v3 appends 16 more bytes (``epoch_jd`` + ``state_mode`` + 7
    reserved bytes) — those fields are populated only when the
    file is v3.
    """

    renderer_flags: int = 0
    visual_encoding_id: int = VISUAL_ENCODING_ID_NONE
    sector_origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounding_sphere: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    aabb_min: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    aabb_max: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    # v1.2 / v3 additions.
    epoch_jd: float = 0.0
    state_mode: int = STATE_MODE_STATIC


@dataclass
class BinaryHeader:
    """Header fields read from / written to disk.

    The ``v2_extras`` field is populated only when the file is v2
    (``version == FORMAT_VERSION_V2``); v1 files leave it at the
    default. ``has_v2_extras()`` is the canonical predicate.
    """

    magic: bytes = MAGIC
    version: int = FORMAT_VERSION
    flags: int = 0
    coordinate_scale_factor: float = 1.0
    point_count: int = 0
    source_count: int = 0
    header_extra_bytes: int = 0
    sidecar_path: str = ""
    v2_extras: Optional[BinaryV2Extras] = None

    def has_v2_extras(self) -> bool:
        return (
            self.version in (FORMAT_VERSION_V2, FORMAT_VERSION_V3)
            and self.v2_extras is not None
        )

    def has_v3_extras(self) -> bool:
        return (
            self.version == FORMAT_VERSION_V3
            and self.v2_extras is not None
        )


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


def _pack_v2_extras(extras: BinaryV2Extras, *, with_v3_tail: bool = False) -> bytes:
    head = struct.pack(
        _V2_EXTRA_HEADER_FMT,
        int(extras.renderer_flags) & 0xFFFFFFFF,
        int(extras.visual_encoding_id) & 0xFFFFFFFF,
        float(extras.sector_origin[0]),
        float(extras.sector_origin[1]),
        float(extras.sector_origin[2]),
        float(extras.bounding_sphere[0]),
        float(extras.bounding_sphere[1]),
        float(extras.bounding_sphere[2]),
        float(extras.bounding_sphere[3]),
        float(extras.aabb_min[0]),
        float(extras.aabb_min[1]),
        float(extras.aabb_min[2]),
        float(extras.aabb_max[0]),
        float(extras.aabb_max[1]),
        float(extras.aabb_max[2]),
    )
    if not with_v3_tail:
        return head
    tail = struct.pack(
        _V3_EXTRA_TAIL_FMT,
        float(extras.epoch_jd),
        int(extras.state_mode) & 0xFF,
        b"\x00" * 7,
    )
    return head + tail


def _unpack_v2_extras(raw: bytes, *, with_v3_tail: bool = False) -> BinaryV2Extras:
    expected = V3_EXTRA_HEADER_SIZE if with_v3_tail else V2_EXTRA_HEADER_SIZE
    if len(raw) != expected:
        raise BinaryExportError(
            f"v2/v3 extras block size {len(raw)} != "
            f"expected {expected}"
        )
    head_fields = struct.unpack(_V2_EXTRA_HEADER_FMT, raw[:V2_EXTRA_HEADER_SIZE])
    extras = BinaryV2Extras(
        renderer_flags=int(head_fields[0]),
        visual_encoding_id=int(head_fields[1]),
        sector_origin=(float(head_fields[2]), float(head_fields[3]), float(head_fields[4])),
        bounding_sphere=(
            float(head_fields[5]), float(head_fields[6]),
            float(head_fields[7]), float(head_fields[8]),
        ),
        aabb_min=(float(head_fields[9]), float(head_fields[10]), float(head_fields[11])),
        aabb_max=(float(head_fields[12]), float(head_fields[13]), float(head_fields[14])),
    )
    if with_v3_tail:
        epoch_jd, state_mode, _pad = struct.unpack(
            _V3_EXTRA_TAIL_FMT, raw[V2_EXTRA_HEADER_SIZE:],
        )
        extras.epoch_jd = float(epoch_jd)
        extras.state_mode = int(state_mode)
    return extras


def _pack_header(header: BinaryHeader) -> bytes:
    sidecar_bytes = (header.sidecar_path or "").encode("utf-8")
    extras_bytes = b""
    extra_len = int(header.header_extra_bytes) & 0xFFFFFFFF
    if header.version == FORMAT_VERSION_V2:
        extras = header.v2_extras or BinaryV2Extras()
        extras_bytes = _pack_v2_extras(extras, with_v3_tail=False)
        extra_len = len(extras_bytes)
    elif header.version == FORMAT_VERSION_V3:
        extras = header.v2_extras or BinaryV2Extras()
        extras_bytes = _pack_v2_extras(extras, with_v3_tail=True)
        extra_len = len(extras_bytes)
    fixed = struct.pack(
        _HEADER_FMT,
        MAGIC,
        int(header.version) & 0xFFFF,
        int(header.flags) & 0xFFFF,
        float(header.coordinate_scale_factor),
        int(header.point_count) & 0xFFFFFFFF,
        int(header.source_count) & 0xFFFFFFFF,
        extra_len,
        len(sidecar_bytes) & 0xFFFF,
    )
    # v1 layout: header (30B) + sidecar.
    # v2 layout: header (30B) + sidecar + extras_bytes.
    return fixed + sidecar_bytes + extras_bytes


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
    format_version: int = FORMAT_VERSION_V1,
    v2_extras: Optional[BinaryV2Extras] = None,
) -> int:
    """Write the visible sector to ``path``. Returns total bytes
    written. Parent directories are created as needed.

    ``coordinate_scale_factor`` records the C4D-units-per-parsec
    used when the points were packed (default ``1.0`` for
    ``scale_mode='pc'``). ``sidecar_path`` is an optional relative
    path to a UTF-8 metadata sidecar (the JSONL produced by the
    rest of the plugin); ``""`` (default) means no sidecar.

    ``format_version`` (v1.0+) selects the on-disk layout. v1 keeps
    bit-for-bit parity with v0.8 / v0.9. v2 emits the extra header
    block declared in
    ``docs/BINARY_VISIBLE_SECTOR_FORMAT.md`` §4 carrying
    ``renderer_flags``, ``visual_encoding_id``, ``sector_origin``,
    ``bounding_sphere``, and the AABB. ``v2_extras`` is required
    when ``format_version == FORMAT_VERSION_V2`` and ignored
    otherwise.
    """
    if format_version not in SUPPORTED_FORMAT_VERSIONS:
        raise BinaryExportError(
            f"unsupported format_version {format_version}; "
            f"supported: {SUPPORTED_FORMAT_VERSIONS}"
        )
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    extras = v2_extras
    if format_version in (FORMAT_VERSION_V2, FORMAT_VERSION_V3) and extras is None:
        # Caller asked for v2/v3 without giving us extras — fill
        # with zeros so the file is still well-formed.
        extras = BinaryV2Extras()

    if format_version == FORMAT_VERSION_V3:
        header_extra_bytes = V3_EXTRA_HEADER_SIZE
    elif format_version == FORMAT_VERSION_V2:
        header_extra_bytes = V2_EXTRA_HEADER_SIZE
    else:
        header_extra_bytes = 0

    header = BinaryHeader(
        magic=MAGIC,
        version=format_version,
        flags=0,
        coordinate_scale_factor=float(coordinate_scale_factor),
        point_count=len(points),
        source_count=len(sources),
        header_extra_bytes=header_extra_bytes,
        sidecar_path=sidecar_path or "",
        v2_extras=extras,
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
    """Parse the fixed header, the optional sidecar path, and (for
    v2 files) the extra-header block. Returns
    ``(header, total_header_bytes)``."""
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
    if int(version) not in SUPPORTED_FORMAT_VERSIONS:
        raise BinaryExportError(
            f"unsupported format version {version}; "
            f"this build understands {SUPPORTED_FORMAT_VERSIONS}"
        )
    sidecar_end = HEADER_SIZE + int(sidecar_path_len)
    if sidecar_end > len(raw):
        raise BinaryExportError(
            "sidecar_path_len overruns file"
        )
    sidecar = raw[HEADER_SIZE:sidecar_end].decode("utf-8") if sidecar_path_len else ""

    extras: Optional[BinaryV2Extras] = None
    extras_end = sidecar_end
    if int(version) == FORMAT_VERSION_V3:
        if int(header_extra_bytes) != V3_EXTRA_HEADER_SIZE:
            raise BinaryExportError(
                f"v3 header_extra_bytes is {header_extra_bytes}; "
                f"expected {V3_EXTRA_HEADER_SIZE}"
            )
        extras_end = sidecar_end + V3_EXTRA_HEADER_SIZE
        if extras_end > len(raw):
            raise BinaryExportError("v3 extras block overruns file")
        extras = _unpack_v2_extras(
            raw[sidecar_end:extras_end], with_v3_tail=True,
        )
    elif int(version) == FORMAT_VERSION_V2:
        if int(header_extra_bytes) != V2_EXTRA_HEADER_SIZE:
            raise BinaryExportError(
                f"v2 header_extra_bytes is {header_extra_bytes}; "
                f"expected {V2_EXTRA_HEADER_SIZE}"
            )
        extras_end = sidecar_end + V2_EXTRA_HEADER_SIZE
        if extras_end > len(raw):
            raise BinaryExportError("v2 extras block overruns file")
        extras = _unpack_v2_extras(raw[sidecar_end:extras_end])
    elif int(version) == FORMAT_VERSION_V1:
        if int(header_extra_bytes) != 0:
            # v1 readers fail closed on a non-zero forward-compat
            # slot — see BINARY_VISIBLE_SECTOR_FORMAT.md §3.3.
            raise BinaryExportError(
                "v1 header has non-zero header_extra_bytes; "
                "use the v2/v3 reader for that file"
            )
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
            v2_extras=extras,
        ),
        extras_end,
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
# v2 helpers — bounding sphere / AABB / sector origin
# ---------------------------------------------------------------------------


def compute_aabb(
    points: Sequence[UnavBinaryPoint],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Tight axis-aligned bounding box over ``points``. Returns
    ``((min_x, min_y, min_z), (max_x, max_y, max_z))``. An empty
    sequence yields the zero-volume box at the origin so the
    on-disk fields stay valid."""
    if not points:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def compute_bounding_sphere(
    points: Sequence[UnavBinaryPoint],
) -> Tuple[float, float, float, float]:
    """Centroid-centred bounding sphere over ``points``. Not the
    minimum-enclosing sphere (Welzl's algorithm) — the centroid
    sphere is good enough for the renderer's frustum-culling and
    has a closed-form, fast computation. Returns
    ``(cx, cy, cz, radius)``. Empty input yields a zero-radius
    sphere at the origin."""
    if not points:
        return (0.0, 0.0, 0.0, 0.0)
    n = float(len(points))
    cx = sum(p.x for p in points) / n
    cy = sum(p.y for p in points) / n
    cz = sum(p.z for p in points) / n
    radius_sq = 0.0
    for p in points:
        dx = p.x - cx
        dy = p.y - cy
        dz = p.z - cz
        d2 = dx * dx + dy * dy + dz * dz
        if d2 > radius_sq:
            radius_sq = d2
    return (cx, cy, cz, radius_sq ** 0.5)


def make_v2_extras(
    points: Sequence[UnavBinaryPoint],
    *,
    visual_encoding_id: int = VISUAL_ENCODING_ID_NONE,
    renderer_flags: int = 0,
    sector_origin: Optional[Tuple[float, float, float]] = None,
) -> BinaryV2Extras:
    """Compute a populated ``BinaryV2Extras`` for ``points``.

    By default ``sector_origin`` is the centroid of the points;
    callers passing camera-relative-rendering can override with
    the active navigator's pose. The bounding-sphere /
    bounding-box flags are turned on automatically when there is
    at least one point. ``visual_encoding_id`` is the caller's
    cache key (``0`` means "renderer falls back to baked colour /
    size")."""
    sphere = compute_bounding_sphere(points)
    aabb_min, aabb_max = compute_aabb(points)
    if sector_origin is None:
        sector_origin = (sphere[0], sphere[1], sphere[2])
    flags = int(renderer_flags)
    if points:
        flags |= RENDERER_FLAG_BOUNDING_SPHERE_VALID
        flags |= RENDERER_FLAG_BOUNDING_BOX_VALID
    return BinaryV2Extras(
        renderer_flags=flags,
        visual_encoding_id=int(visual_encoding_id),
        sector_origin=sector_origin,
        bounding_sphere=sphere,
        aabb_min=aabb_min,
        aabb_max=aabb_max,
    )


def make_relative_points(
    points: Sequence[UnavBinaryPoint],
    sector_origin: Tuple[float, float, float],
) -> List[UnavBinaryPoint]:
    """Return a new list with every point's xyz expressed relative
    to ``sector_origin``. Used by the camera-relative rendering
    path: the binary file then carries small floats (point
    distances from the cluster centroid) regardless of how far
    the absolute coordinates are from the C4D origin."""
    out: List[UnavBinaryPoint] = []
    ox, oy, oz = sector_origin
    for p in points:
        out.append(UnavBinaryPoint(
            x=p.x - ox, y=p.y - oy, z=p.z - oz,
            size=p.size, r=p.r, g=p.g, b=p.b,
            uid_hash=p.uid_hash, source_id=p.source_id,
        ))
    return out


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
    format_version: int = FORMAT_VERSION_V1,
    visual_encoding_id: int = VISUAL_ENCODING_ID_NONE,
    sector_origin: Optional[Tuple[float, float, float]] = None,
    camera_relative: bool = False,
    renderer_flags: int = 0,
    epoch_jd: float = 0.0,
    state_mode: int = STATE_MODE_STATIC,
) -> Tuple[int, BinaryHeader, List[Tuple[int, str]]]:
    """Convenience: convert a sequence of ``CatalogObject`` into
    binary points and write them. Returns
    ``(bytes_written, header, source_table)``.

    The source IDs are assigned in first-seen order starting at 1;
    the C++ side reads them straight off the file's source table.

    v1.0 additions (only used when ``format_version=FORMAT_VERSION_V2``):

    * ``visual_encoding_id`` — caller's cache key (e.g. a hash of
      the ``VisualEncodingParams``); ``0`` defers to baked colour.
    * ``sector_origin`` — explicit C4D-units sector origin for the
      camera-relative-rendering path. ``None`` falls back to the
      bounding-sphere centre when ``camera_relative=True``.
    * ``camera_relative`` — when True, the points are rewritten as
      offsets from ``sector_origin`` and the
      ``RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN`` bit is
      set in the header. v2 readers re-add the origin at draw time.
    * ``renderer_flags`` — extra flags ORed into the v2 header.
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

    extras: Optional[BinaryV2Extras] = None
    points_to_write = list(points)
    if format_version in (FORMAT_VERSION_V2, FORMAT_VERSION_V3):
        extras = make_v2_extras(
            points,
            visual_encoding_id=visual_encoding_id,
            renderer_flags=renderer_flags,
            sector_origin=sector_origin,
        )
        if camera_relative:
            extras.renderer_flags |= (
                RENDERER_FLAG_POINTS_RELATIVE_TO_SECTOR_ORIGIN
            )
            points_to_write = make_relative_points(
                points, extras.sector_origin,
            )
        if format_version == FORMAT_VERSION_V3:
            extras.epoch_jd = float(epoch_jd)
            extras.state_mode = int(state_mode)

    bytes_written = write_visible_sector(
        path, points_to_write,
        sources=sources,
        coordinate_scale_factor=scale_factor,
        sidecar_path=sidecar_path,
        format_version=format_version,
        v2_extras=extras,
    )
    if format_version == FORMAT_VERSION_V3:
        header_extra = V3_EXTRA_HEADER_SIZE
    elif format_version == FORMAT_VERSION_V2:
        header_extra = V2_EXTRA_HEADER_SIZE
    else:
        header_extra = 0
    header = BinaryHeader(
        version=format_version,
        flags=0,
        coordinate_scale_factor=float(scale_factor),
        point_count=len(points_to_write),
        source_count=len(sources),
        header_extra_bytes=header_extra,
        sidecar_path=sidecar_path or "",
        v2_extras=extras,
    )
    return bytes_written, header, sources
