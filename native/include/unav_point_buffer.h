// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native point buffer header (v0.8 feasibility spike).
//
// This file pins the C++ surface that the v0.9 implementation will
// flesh out. Every member declared here corresponds to either a
// field in the on-disk binary visible-sector format (see
// `docs/BINARY_VISIBLE_SECTOR_FORMAT.md`) or a method the future
// `BaseDraw` callback / picking bridge needs.
//
// Today, all method bodies live in `src/unav_point_buffer.cpp` as
// stubs that return safely-empty values. The point of v0.8 is to
// freeze the shape, not to ship the implementation.

#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace unav {

// ----------------------------------------------------------------------------
// UnavPoint — mirrors the on-disk record exactly.
// ----------------------------------------------------------------------------
//
// On-disk layout (little-endian, packed, 52 bytes per record):
//
//   double x, y, z         (3 × 8 = 24 bytes)
//   float  size            (4 bytes)
//   float  r, g, b         (3 × 4 = 12 bytes)
//   uint64 uid_hash        (8 bytes)
//   uint32 source_id       (4 bytes)
//
// The C++ struct is *also* 52 bytes when compiled with the packing
// pragma below; the implementation in `unav_point_buffer.cpp` is
// expected to use `static_assert(sizeof(UnavPoint) == 52)` to lock
// the parity with the Python exporter.
//
// `uid_hash` is a 64-bit BLAKE2b digest of the original UNAV uid;
// the original string lives in the metadata sidecar referenced by
// the file's header.

#pragma pack(push, 1)
struct UnavPoint {
  double x;
  double y;
  double z;
  float size;
  float r;
  float g;
  float b;
  std::uint64_t uid_hash;
  std::uint32_t source_id;
};
#pragma pack(pop)

// ----------------------------------------------------------------------------
// UnavSourceEntry — one row of the file's source table.
// ----------------------------------------------------------------------------

struct UnavSourceEntry {
  std::uint32_t source_id;
  std::string name;
};

// ----------------------------------------------------------------------------
// UnavPointBuffer — the in-engine container.
// ----------------------------------------------------------------------------
//
// Designed for two use cases:
//
//   1. Bulk-load from the binary visible-sector file. The CPU-side
//      vector lives here; in v0.9 a parallel GPU-uploaded handle
//      lives in a private member.
//   2. Query the nearest point to a screen-space click for the
//      selection bridge that returns a uid_hash.
//
// All methods are intentionally cheap stubs in v0.8 so the header
// can compile against any C++17 host without a real Maxon SDK
// install.

class UnavPointBuffer {
 public:
  UnavPointBuffer() = default;
  ~UnavPointBuffer() = default;

  // Disable copy; allow move (the buffer is large in production).
  UnavPointBuffer(const UnavPointBuffer&) = delete;
  UnavPointBuffer& operator=(const UnavPointBuffer&) = delete;
  UnavPointBuffer(UnavPointBuffer&&) noexcept = default;
  UnavPointBuffer& operator=(UnavPointBuffer&&) noexcept = default;

  // ------------------------------------------------------------- mutators
  // Drop every point and source entry. Safe to call multiple times.
  void clear();

  // Reserve capacity for `count` upcoming `addPoint` / `loadFromFile`
  // calls. A no-op in v0.8; in v0.9 this allocates GPU buffers.
  void reserve(std::size_t count);

  // Append one point. Returns the new total point count. In v0.8
  // the point lives only in CPU memory; v0.9 also flags the GPU
  // buffer as dirty so the next draw uploads the delta.
  std::size_t addPoint(const UnavPoint& point);

  // Replace the source-id table. In production the rendering side
  // never mutates this; the table is a join key for the metadata
  // sidecar.
  void setSourceTable(std::vector<UnavSourceEntry> sources);

  // Read the binary visible-sector file documented in
  // `docs/BINARY_VISIBLE_SECTOR_FORMAT.md`. Returns the number of
  // points loaded on success. Returns 0 and sets `errorOut` on
  // failure (bad magic / version / CRC). v0.8 returns 0 and notes
  // "not implemented" in `errorOut` so callers can integrate the
  // glue without the body landing yet.
  std::size_t loadFromFile(const std::string& path,
                           std::string* errorOut);

  // ---------------------------------------------------------- accessors
  std::size_t size() const noexcept;
  bool empty() const noexcept { return size() == 0; }

  // Read-only view of the contiguous point storage. Returns nullptr
  // when empty so the caller never dereferences a stale pointer.
  const UnavPoint* data() const noexcept;

  // Read-only view of the source table, in the order it was loaded.
  const std::vector<UnavSourceEntry>& sources() const noexcept;

  // ------------------------------------------------------- placeholders
  //
  // These are the v0.9 hot path. They exist as named symbols today
  // so the integration plan can compile against them; their bodies
  // are no-ops that record an "unimplemented" state for the
  // diagnostic dialog.

  // Push the CPU buffer to the GPU. v0.8 placeholder.
  bool uploadPlaceholder();

  // Issue a single draw call for the entire buffer. v0.8 placeholder.
  bool drawPlaceholder();

  // Hit-test: given a world-space ray, return the index of the
  // closest point within `maxDistance`, or `kInvalidIndex` if no
  // point is in range. v0.8 placeholder.
  std::size_t queryNearestPointPlaceholder(double rayOriginX,
                                           double rayOriginY,
                                           double rayOriginZ,
                                           double rayDirX,
                                           double rayDirY,
                                           double rayDirZ,
                                           double maxDistance) const;

  // Sentinel for "no hit". v0.9 swaps this for a Maxon-native
  // ID type.
  static constexpr std::size_t kInvalidIndex =
      static_cast<std::size_t>(-1);

 private:
  std::vector<UnavPoint> points_;
  std::vector<UnavSourceEntry> sources_;

  // v0.9 will add: GPU buffer handle, dirty flag, upload watermark.
};

// ----------------------------------------------------------------------------
// Static assertions that make the v0.8 ↔ v0.9 contract enforceable
// by the compiler.
// ----------------------------------------------------------------------------

static_assert(sizeof(UnavPoint) == 52,
              "UnavPoint must match the on-disk record size (52 bytes). "
              "If this assertion fires, the binary format spec and the "
              "Python exporter are out of sync with the C++ side.");

}  // namespace unav
