# Binary Visible-Sector Format

The on-disk format the v0.8 Python exporter writes and the v0.9+
native plugin reads. Stable since v0.8 (format version 1).
Reference implementations:

* Writer / reader (Python): `unav_pro/data/binary_export.py`
* Writer CLI: `tools/export_visible_sector_binary.py`
* C++ reader (placeholder): `native/include/unav_point_buffer.h` /
  `native/src/unav_point_buffer.cpp` (loader stub; v0.9 implements
  it).

For the broader v0.8 spike see
[`V0_8_NATIVE_CPP_FEASIBILITY.md`](V0_8_NATIVE_CPP_FEASIBILITY.md).

---

## 1. Goals

* **Tiny.** Per-point overhead is 52 bytes flat; no JSON, no
  CSV, no schema-version-per-row.
* **mmap-friendly.** Fixed header + flat array layout means a
  C++ reader can `mmap` the file and treat the points block as
  a `std::span<UnavPoint>`.
* **CRC-protected.** A 32-bit CRC over the payload catches
  truncation and bit rot.
* **Endianness-pinned.** Little-endian throughout. Big-endian
  hosts (rare in 2026) read field-by-field via `struct.unpack`
  on the Python side.
* **Forward-compatible header.** A `header_extra_bytes` slot
  reserved for future header growth without breaking the
  point-block alignment.

---

## 2. File layout

```
+------------------------------------------+
| Header (HEADER_SIZE = 30 bytes, fixed)   |
+------------------------------------------+
| Optional sidecar path (UTF-8, sidecar_path_len bytes) |
+------------------------------------------+
| Source table (source_count entries)      |
|   Each: uint32 source_id + uint16 name_len + UTF-8 name |
+------------------------------------------+
| Point block (point_count entries × 52 bytes) |
+------------------------------------------+
| Footer (FOOTER_SIZE = 8 bytes)           |
+------------------------------------------+
```

Total file size:
```
30  +  sidecar_path_len
   +  Σ (6 + name_len_i)      for source entries i = 0..source_count-1
   +  52 * point_count
   +   8
```

---

## 3. Header (30 bytes, packed little-endian)

| Offset | Field                       | Type     | Size | Notes                                              |
|-------:|------------------------------|---------:|-----:|----------------------------------------------------|
|      0 | `magic`                     | char[4]  |    4 | ASCII `"UNAV"`. Mismatch → fail closed.            |
|      4 | `version`                   | uint16   |    2 | Format version. `1` today.                         |
|      6 | `flags`                     | uint16   |    2 | Reserved; `0` today.                               |
|      8 | `coordinate_scale_factor`   | float64  |    8 | C4D units per parsec (matches `data.schema.SCALE_MODES`). |
|     16 | `point_count`               | uint32   |    4 | Number of point records in the point block.       |
|     20 | `source_count`              | uint32   |    4 | Number of entries in the source table.            |
|     24 | `header_extra_bytes`        | uint32   |    4 | Reserved future header growth. `0` today.          |
|     28 | `sidecar_path_len`          | uint16   |    2 | UTF-8 byte length of the sidecar path (0 if none). |

### 3.1 `coordinate_scale_factor`

Records the scale the points were packed at. Mirror of
`data.schema.SCALE_MODES`:

| `scale_mode` | factor                |
|--------------|----------------------:|
| `au`         |  206 264.806          |
| `ly`         |       3.261 564       |
| `pc`         |       1.0             |
| `kpc`        |       1.0e-3          |
| `mpc`        |       1.0e-6          |

The C++ reader stores the factor verbatim; the artist's preferred
viewport scale is independent of this value.

### 3.2 `flags`

Reserved. `0` today. v1 does not define any bits; readers must
ignore unknown bits and writers must emit `0`.

### 3.3 `header_extra_bytes`

Reserved for future header growth. v1 always emits `0`. v2+
formats may extend the fixed header with up to
`header_extra_bytes` bytes of additional fixed-layout content
between the optional sidecar string and the source table.

A v1 reader that encounters `header_extra_bytes != 0` MAY warn
or fail closed; the v0.8 Python reader fails closed because v1
never emits a non-zero value.

### 3.4 Sidecar path

Immediately after the fixed 30-byte header, exactly
`sidecar_path_len` UTF-8 bytes carry an optional relative path
to a metadata sidecar. The sidecar resolves `uid_hash → uid`
back to the original UNAV uid string and (for full inspection)
to the JSONL row.

`sidecar_path_len = 0` means "no sidecar"; the file's points
carry only `uid_hash` and the inspector's search-based fallback
must resolve uids by other means.

---

## 4. Source table

`source_count` entries appear right after the (optional) sidecar
path. Each entry is variable-length:

| Field        | Type    | Size                      |
|--------------|--------:|--------------------------:|
| `source_id`  | uint32  | 4 bytes                   |
| `name_len`   | uint16  | 2 bytes                   |
| `name`       | UTF-8   | `name_len` bytes          |

Source IDs are non-zero positive integers. `0` is reserved as
the "unknown / no source" sentinel; writers do not include `0`
in the table.

Source names are the human-readable labels the v0.5+ pipeline
already uses: `"Gaia DR3"`, `"SDSS"`, `"DESI"`, `"JPL Horizons"`,
`"unav_sample"`, etc.

The Python writer assigns IDs in **first-seen order starting at
1** for stability across re-exports; the C++ reader takes the
table verbatim and never re-assigns IDs.

---

## 5. Point block

`point_count` records, **52 bytes each**, packed
(`#pragma pack(push, 1)` on the C++ side; `<dddffffQI` on the
Python side):

| Field        | Type      | Size | Notes                                                   |
|--------------|----------:|-----:|---------------------------------------------------------|
| `x`          | float64   |    8 | C4D world-space, in the file's `coordinate_scale_factor` units. |
| `y`          | float64   |    8 | Same.                                                   |
| `z`          | float64   |    8 | Same.                                                   |
| `size`       | float32   |    4 | Render radius in C4D world units.                       |
| `r`          | float32   |    4 | sRGB red channel, normalised to `[0, 1]`.               |
| `g`          | float32   |    4 | sRGB green channel.                                     |
| `b`          | float32   |    4 | sRGB blue channel.                                      |
| `uid_hash`   | uint64    |    8 | BLAKE2b 64-bit digest of the original UNAV uid.         |
| `source_id`  | uint32    |    4 | Index into the source table (≥ 1), or `0` for unknown.  |

Total: 52 bytes. `static_assert` in `unav_point_buffer.h` keeps
the C++ struct in sync; the Python writer uses `struct.pack` with
the format string `<dddffffQI`.

### 5.1 `uid_hash`

The original UNAV uid string (e.g. `"gaia:1234567890"`) is hashed
via BLAKE2b (64-bit digest, little-endian), stored as a single
`uint64`. The mapping from `uid_hash` back to `uid` lives in the
metadata sidecar; the binary file has no other record of the
original string.

Collision risk: 2⁶⁴ keys is enough to keep the birthday-paradox
collision probability negligible at any plausible visible-sector
size (1 M points → ≈ 2.7e-8 collision probability).

### 5.2 Floating-origin

The packed positions are in absolute world coordinates. The
v0.10+ native renderer subtracts the navigator's pose at draw
time to keep the float32 viewport stack accurate at parsec
scale. This file format is not floating-origin-aware; it
records the raw positions and lets the renderer manage
precision.

---

## 6. Footer (8 bytes)

| Offset       | Field        | Type     | Size | Notes                                            |
|--------------|--------------|---------:|-----:|--------------------------------------------------|
| `len-8`      | `magic_end`  | char[4]  |    4 | ASCII `"UEND"`. Mismatch → fail closed.          |
| `len-4`      | `crc32`      | uint32   |    4 | zlib CRC32 over the payload (see below).         |

### 6.1 CRC payload

The CRC is computed over **every byte** between the end of the
4-byte `magic` and the start of the footer:

```
crc_input = file_bytes[4 : -8]     # everything except magic and footer
```

This includes the rest of the header (version, flags, scale,
counts, sidecar path length), the optional sidecar path,
the source table, and the point block. A reader that recomputes
the CRC and compares it to the stored value catches every
single-bit flip, every truncation, and every misalignment.

---

## 7. Validation

The Python reference reader
(`unav_pro/data/binary_export.read_visible_sector`) validates,
in order:

1. File length ≥ `HEADER_SIZE + FOOTER_SIZE`.
2. `magic == "UNAV"`.
3. `version == 1` (today).
4. Sidecar path length is consistent with the file size.
5. Source table entries do not overrun the file.
6. The point block has exactly `point_count × 52` bytes.
7. No trailing bytes after the footer.
8. `magic_end == "UEND"`.
9. `crc32(payload)` matches the stored CRC.

Any failure raises `BinaryExportError` with a clear message.

The C++ loader (when v0.9 implements it) is constrained to
match this validation set bit-for-bit so a file that loads on
one side never silently fails on the other.

---

## 8. Example sizes

| Scene                                | File size                       |
|--------------------------------------|---------------------------------|
| Empty (header + footer + 0 sources)  | 30 + 0 + 0 + 8 = **38 bytes**   |
| 100 points / 1 source ("Gaia DR3")   | 30 + 0 + (6 + 8) + 100*52 + 8 = **5260 bytes** |
| 200 000 points / 4 sources           | 30 + 0 + ~50 + 200000*52 + 8 ≈ **10.4 MB** |
| 1 000 000 points / 5 sources         | 30 + 0 + ~70 + 1000000*52 + 8 ≈ **52 MB** |

The format is intentionally not compressed; mmap-driven random
access is the priority. v2+ may add a "compressed point block"
flag bit if the scaling demands it.

---

## 9. Versioning

The format's `version` field is the contract:

* **v1** (today, v0.8). Every field above. CRC32. No
  compression, no deltas.
* **v2** (reserved, no current plan). Examples of changes that
  would warrant a version bump:
  * Per-vertex sprite size encoded as a different type.
  * Optional zlib / zstd compressed point block.
  * A second per-point uid hash for collision detection.
  * Time-varying point clouds (a per-point timestamp).

The `header_extra_bytes` slot in v1 is the lever for backwards-
compatible header extensions; structural changes get a new
version.

A reader that encounters a higher version than it understands
**must** fail closed. The Python `read_visible_sector` raises
`BinaryExportError("unsupported format version N")`.

---

## 10. Sidecar contract

When `sidecar_path_len > 0` the sidecar is a UTF-8 path,
relative to the binary file's directory, pointing at a JSONL
file containing the originating UNAV `CatalogObject` rows for
the points. The Python pipeline already produces this JSONL
(it's the catalog file `tools/fetch_*.py` writes); the binary
file just records its location.

The sidecar is the *only* link from `uid_hash` back to a real
UNAV uid; without it, the v0.6 metadata inspector falls back to
"unresolved" for clicked points.

The sidecar is **never required** to read the binary file —
positions, sizes, colours, and source IDs all come from the
binary's own bytes. The sidecar is needed only when the artist
clicks a point and wants its astronomical metadata.
