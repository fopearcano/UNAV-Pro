// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native point buffer (v1.0).
//
// Owns the visible-sector points + the metadata read from the
// binary file's header. v0.9 introduced the v1 loader; v1.0
// adds:
//
//   - dual-version (v1 + v2) parser,
//   - sector-origin / bounding-sphere / AABB / renderer-flags
//     decoded from the v2 extra header,
//   - camera-relative reconstruction
//     (`worldPosition(index)`),
//   - a uniform-grid spatial-acceleration structure for the
//     picking system,
//   - safety caps and "absurd file" rejection, and
//   - a v1.0 LoadStats payload the bridge writes back to Python.
//
// SDK-free by construction; the Maxon-bound layer lives in
// `unav_native_plugin.cpp`.

#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace unav {

// ----------------------------------------------------------------------------
// UnavPoint — mirrors the on-disk record exactly (52 bytes packed).
// ----------------------------------------------------------------------------

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

struct UnavSourceEntry {
  std::uint32_t source_id;
  std::string name;
};

// ----------------------------------------------------------------------------
// v2 extra-header fields.
// ----------------------------------------------------------------------------

namespace renderer_flags {
constexpr std::uint32_t kPointsRelativeToSectorOrigin = 1u << 0;
constexpr std::uint32_t kDisableDistanceFade         = 1u << 1;
constexpr std::uint32_t kDebugDraw                   = 1u << 2;
constexpr std::uint32_t kPreferBillboard             = 1u << 3;
constexpr std::uint32_t kBoundingSphereValid         = 1u << 4;
constexpr std::uint32_t kBoundingBoxValid            = 1u << 5;
}  // namespace renderer_flags

struct V2Extras {
  std::uint32_t renderer_flags = 0;
  std::uint32_t visual_encoding_id = 0;
  double sector_origin[3]        = {0.0, 0.0, 0.0};
  double bounding_sphere[4]      = {0.0, 0.0, 0.0, 0.0};  // cx, cy, cz, r
  double aabb_min[3]             = {0.0, 0.0, 0.0};
  double aabb_max[3]             = {0.0, 0.0, 0.0};

  bool pointsAreRelative() const noexcept {
    return (renderer_flags & renderer_flags::kPointsRelativeToSectorOrigin) != 0;
  }
  bool boundingSphereValid() const noexcept {
    return (renderer_flags & renderer_flags::kBoundingSphereValid) != 0;
  }
  bool boundingBoxValid() const noexcept {
    return (renderer_flags & renderer_flags::kBoundingBoxValid) != 0;
  }
};

// ----------------------------------------------------------------------------
// LoadStats — what the bridge writes back to Python.
// ----------------------------------------------------------------------------

struct LoadStats {
  std::size_t point_count = 0;
  std::size_t source_count = 0;
  std::uint64_t file_size_bytes = 0;
  double load_seconds = 0.0;
  std::string sidecar_path;
  double coordinate_scale_factor = 1.0;
  std::uint16_t format_version = 0;
  // v1.0: an estimate of the GPU-buffer footprint a renderer
  // would allocate for this load. The renderer may report its
  // own number once the buffer is up; this is the budget the
  // safety advisory uses.
  std::uint64_t estimated_gpu_bytes = 0;
};

// ----------------------------------------------------------------------------
// UnavPointBuffer — the in-engine container.
// ----------------------------------------------------------------------------

class UnavPointBuffer {
 public:
  // Hard ceiling: the loader rejects files claiming more than this.
  // The renderer cap is configurable per-load via setMaxPoints.
  static constexpr std::size_t kAbsurdPointCount = 50'000'000;
  static constexpr std::size_t kDefaultMaxPoints = 5'000'000;

  UnavPointBuffer();
  explicit UnavPointBuffer(std::size_t maxPoints);
  ~UnavPointBuffer() = default;

  UnavPointBuffer(const UnavPointBuffer&) = delete;
  UnavPointBuffer& operator=(const UnavPointBuffer&) = delete;
  UnavPointBuffer(UnavPointBuffer&&) noexcept = default;
  UnavPointBuffer& operator=(UnavPointBuffer&&) noexcept = default;

  // ------------------------------------------------------------- mutators
  void clear();
  void reserve(std::size_t count);
  std::size_t addPoint(const UnavPoint& point);
  void setSourceTable(std::vector<UnavSourceEntry> sources);
  void setMaxPoints(std::size_t maxPoints);

  // Load the binary visible-sector file at `path`. Validates magic,
  // version (v1 or v2), sizes, footer, CRC32. Returns the number of
  // points loaded; sets `errorOut` on failure / warning. The hard
  // cap (`maxPoints()`) trims after parsing — surplus points become
  // a "warning:" message in errorOut.
  std::size_t loadFromFile(const std::string& path,
                           std::string* errorOut);

  // ---------------------------------------------------------- accessors
  std::size_t size() const noexcept;
  bool empty() const noexcept { return size() == 0; }
  std::size_t maxPoints() const noexcept { return maxPoints_; }

  const UnavPoint* data() const noexcept;
  const std::vector<UnavSourceEntry>& sources() const noexcept;
  const LoadStats& lastLoadStats() const noexcept { return lastStats_; }
  const std::string& lastFilePath() const noexcept { return lastPath_; }
  const V2Extras& v2Extras() const noexcept { return extras_; }
  bool isV2() const noexcept { return lastStats_.format_version == 2; }

  // World-space position of point[i]. For v2 + camera-relative
  // files, applies sector_origin offset; for v1 / v2-absolute
  // files, returns the stored xyz unchanged. Out-of-range index
  // returns (0,0,0).
  void worldPosition(std::size_t index,
                     double* outX, double* outY, double* outZ) const;

  // ---------------------------------------------------- selection / picking
  static constexpr std::size_t kInvalidIndex =
      static_cast<std::size_t>(-1);

  // World-space "closest point to a 3D position" — used by the v0.9
  // selection fallback and by tests.
  std::size_t queryNearestPointToPosition(double x, double y, double z,
                                          double maxDistance) const;

  // World-space ray vs. points. Picks the point with the smallest
  // perpendicular distance to the ray, bounded by `maxDistance`.
  std::size_t queryNearestPointToRay(double rayOriginX,
                                     double rayOriginY,
                                     double rayOriginZ,
                                     double rayDirX,
                                     double rayDirY,
                                     double rayDirZ,
                                     double maxDistance) const;

  // v1.0 — screen-space radius pick driven by the spatial grid.
  // The renderer hands in the camera ray plus a screen-space
  // tolerance (in world units after projection); the buffer
  // returns the picked point's *world-space* index, or
  // kInvalidIndex.
  std::size_t pickByRayAndScreenRadius(double rayOriginX,
                                        double rayOriginY,
                                        double rayOriginZ,
                                        double rayDirX,
                                        double rayDirY,
                                        double rayDirZ,
                                        double screenRadiusWorld) const;

  // Number of grid cells in the spatial-acceleration structure.
  // Tests use this to confirm the grid was actually populated.
  std::size_t accelCellCount() const noexcept;

  // -------------------------------------------------- rendering hooks
  // The plugin's Draw callback queries these to decide its draw mode.
  bool wantsDistanceFade() const noexcept {
    return !(extras_.renderer_flags & renderer_flags::kDisableDistanceFade);
  }
  bool wantsDebugDraw() const noexcept {
    return (extras_.renderer_flags & renderer_flags::kDebugDraw) != 0;
  }
  bool prefersBillboard() const noexcept {
    return (extras_.renderer_flags & renderer_flags::kPreferBillboard) != 0;
  }

 private:
  std::vector<UnavPoint> points_;
  std::vector<UnavSourceEntry> sources_;
  std::size_t maxPoints_ = kDefaultMaxPoints;
  LoadStats lastStats_;
  std::string lastPath_;
  V2Extras extras_;

  // Uniform-grid acceleration for picking. Cell size is set during
  // load to `max(1.0, bbox_extent / 32)` so a 1000-pc cloud builds
  // a 32^3 grid; tiny clouds collapse to a single cell.
  struct AccelGrid {
    double origin[3] = {0.0, 0.0, 0.0};
    double cell_size = 1.0;
    int dims[3] = {0, 0, 0};
    std::vector<std::vector<std::uint32_t>> cells;
  };
  AccelGrid accel_;

  void rebuildAccelGrid();
  std::size_t cellIndex(int ix, int iy, int iz) const noexcept;
};

static_assert(sizeof(UnavPoint) == 52,
              "UnavPoint must match the on-disk record size (52 bytes)");

}  // namespace unav
