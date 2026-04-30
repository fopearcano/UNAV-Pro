// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native point buffer (v0.9 prototype).
//
// The C++ surface that owns the visible-sector points the future
// Cinema 4D plugin draws. v0.9 implements a real binary loader
// against the format documented in
// `docs/BINARY_VISIBLE_SECTOR_FORMAT.md`, plus a simple
// nearest-point hit-test for the selection bridge.
//
// The class is intentionally SDK-free so the loader / hit-test /
// safety logic can be unit-tested in a plain C++17 host — see
// `native/tests/test_unav_point_buffer.cpp`. The Maxon-bound
// drawing wrapper lives in `unav_native_plugin.cpp`.

#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace unav {

// ----------------------------------------------------------------------------
// UnavPoint — mirrors the on-disk record exactly (52 bytes packed).
// ----------------------------------------------------------------------------
//
// On-disk layout (little-endian, packed):
//
//   double x, y, z         (3 × 8 = 24 bytes)
//   float  size            (4 bytes)
//   float  r, g, b         (3 × 4 = 12 bytes)
//   uint64 uid_hash        (8 bytes)
//   uint32 source_id       (4 bytes)
//
// Cross-checked against the Python writer via `static_assert`
// below.

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
// LoadStats — what the v0.9 status file surfaces back to Python.
// ----------------------------------------------------------------------------

struct LoadStats {
  std::size_t point_count = 0;
  std::size_t source_count = 0;
  std::uint64_t file_size_bytes = 0;
  double load_seconds = 0.0;
  std::string sidecar_path;
  // Coordinate scale factor recorded by the Python writer.
  double coordinate_scale_factor = 1.0;
};

// ----------------------------------------------------------------------------
// UnavPointBuffer — the in-engine container.
// ----------------------------------------------------------------------------

class UnavPointBuffer {
 public:
  // Default safety cap. The Python load request can lower this for
  // a per-load override; the hard ceiling is enforced regardless
  // so a malformed (or malicious) file cannot exhaust memory.
  static constexpr std::size_t kDefaultMaxPoints = 5'000'000;

  UnavPointBuffer();
  explicit UnavPointBuffer(std::size_t maxPoints);
  ~UnavPointBuffer() = default;

  // Disable copy; allow move (the buffer is large in production).
  UnavPointBuffer(const UnavPointBuffer&) = delete;
  UnavPointBuffer& operator=(const UnavPointBuffer&) = delete;
  UnavPointBuffer(UnavPointBuffer&&) noexcept = default;
  UnavPointBuffer& operator=(UnavPointBuffer&&) noexcept = default;

  // ------------------------------------------------------------- mutators
  void clear();
  void reserve(std::size_t count);
  std::size_t addPoint(const UnavPoint& point);
  void setSourceTable(std::vector<UnavSourceEntry> sources);

  // Load the binary visible-sector file at `path`. Returns the
  // number of points loaded on success, 0 on failure (and sets
  // `errorOut` to a human-readable message). Validates magic,
  // version, point-count vs file size, footer magic, and CRC32.
  // The hard cap (`maxPoints()`) clips after parsing — points past
  // the cap are skipped and recorded in `errorOut` as a warning.
  std::size_t loadFromFile(const std::string& path,
                           std::string* errorOut);

  // Configure the per-load safety cap. Values <= 0 reset to the
  // default.
  void setMaxPoints(std::size_t maxPoints);

  // ---------------------------------------------------------- accessors
  std::size_t size() const noexcept;
  bool empty() const noexcept { return size() == 0; }
  std::size_t maxPoints() const noexcept { return maxPoints_; }

  const UnavPoint* data() const noexcept;
  const std::vector<UnavSourceEntry>& sources() const noexcept;
  const LoadStats& lastLoadStats() const noexcept { return lastStats_; }
  const std::string& lastFilePath() const noexcept { return lastPath_; }

  // ---------------------------------------------------- selection / draw
  // Sentinel for "no hit" returned by `queryNearestPointToRay`.
  static constexpr std::size_t kInvalidIndex =
      static_cast<std::size_t>(-1);

  // World-space ray-vs-points hit-test. Returns the index of the
  // point with the smallest perpendicular distance to the ray,
  // bounded by `maxDistance` in world units. A "ray" that points
  // along +X picks the closest point under that ray; the selection
  // bridge in `unav_native_plugin.cpp` casts it from the editor
  // viewport's mouse position.
  std::size_t queryNearestPointToRay(double rayOriginX,
                                     double rayOriginY,
                                     double rayOriginZ,
                                     double rayDirX,
                                     double rayDirY,
                                     double rayDirZ,
                                     double maxDistance) const;

  // Convenience: world-space "closest point to a 3D position"
  // hit-test. Used by tests and by the v0.9 fallback when no
  // depth-buffer pick is wired yet.
  std::size_t queryNearestPointToPosition(double x, double y, double z,
                                          double maxDistance) const;

  // Buffer upload + draw. v0.9 implementation issues per-point
  // calls inside the plugin's `Draw` callback (see
  // `unav_native_plugin.cpp`); v0.10+ swaps to a single
  // `BaseDraw::DrawArray` call. These methods stay declared here
  // so the plugin shell can compile against a stable surface.
  bool uploadPlaceholder();
  bool drawPlaceholder();

 private:
  std::vector<UnavPoint> points_;
  std::vector<UnavSourceEntry> sources_;
  std::size_t maxPoints_ = kDefaultMaxPoints;
  LoadStats lastStats_;
  std::string lastPath_;
};

// ----------------------------------------------------------------------------
// Static assertions that lock the v0.8↔v0.9 contract at compile time.
// ----------------------------------------------------------------------------

static_assert(sizeof(UnavPoint) == 52,
              "UnavPoint must match the on-disk record size (52 bytes). "
              "If this assertion fires, the binary format spec and the "
              "Python exporter are out of sync with the C++ side.");

}  // namespace unav
