// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native point buffer (v1.0).
//
// Real binary loader (v1 + v2), uniform-grid acceleration,
// nearest-point + screen-radius picking. Pure stdlib (no Maxon
// SDK, no zlib): the loader logic compiles in any C++17 host and
// the unit tests in `native/tests/test_unav_point_buffer.cpp`
// cover it without Cinema 4D.

#include "unav_point_buffer.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <ios>
#include <sstream>
#include <utility>

namespace unav {

namespace {

// ----------------------------------------------------------------------------
// Format constants. Mirror `unav_pro/data/binary_export.py`.
// ----------------------------------------------------------------------------

constexpr std::array<char, 4> kMagic = {'U', 'N', 'A', 'V'};
constexpr std::array<char, 4> kMagicEnd = {'U', 'E', 'N', 'D'};
constexpr std::uint16_t kFormatVersionV1 = 1;
constexpr std::uint16_t kFormatVersionV2 = 2;
constexpr std::size_t kHeaderSize = 30;
constexpr std::size_t kFooterSize = 8;
constexpr std::size_t kSourceHeaderSize = 6;  // uint32 + uint16
constexpr std::size_t kPointSize = sizeof(UnavPoint);  // 52 bytes
// v2 extra-header block size: 4 + 4 + 3*8 + 4*8 + 3*8 + 3*8 = 8 + 24 + 32 + 24 + 24 = 112 bytes.
constexpr std::size_t kV2ExtraHeaderSize = 112;

static_assert(kPointSize == 52,
              "Point record size must remain 52 bytes; binary format "
              "compatibility depends on it.");

// ----------------------------------------------------------------------------
// Little-endian read helpers.
// ----------------------------------------------------------------------------

std::uint16_t readUInt16LE(const std::uint8_t* p) {
  return static_cast<std::uint16_t>(p[0]) |
         (static_cast<std::uint16_t>(p[1]) << 8);
}

std::uint32_t readUInt32LE(const std::uint8_t* p) {
  return static_cast<std::uint32_t>(p[0]) |
         (static_cast<std::uint32_t>(p[1]) << 8) |
         (static_cast<std::uint32_t>(p[2]) << 16) |
         (static_cast<std::uint32_t>(p[3]) << 24);
}

double readDoubleLE(const std::uint8_t* p) {
  std::uint64_t bits = 0;
  for (int i = 0; i < 8; ++i) {
    bits |= static_cast<std::uint64_t>(p[i]) << (i * 8);
  }
  double out;
  std::memcpy(&out, &bits, sizeof(out));
  return out;
}

// ----------------------------------------------------------------------------
// CRC32 (zlib-compatible polynomial / init / xor-out).
// ----------------------------------------------------------------------------

std::uint32_t crc32(const std::uint8_t* data, std::size_t length) {
  static std::array<std::uint32_t, 256> kTable = []() {
    std::array<std::uint32_t, 256> t{};
    for (std::uint32_t i = 0; i < 256; ++i) {
      std::uint32_t c = i;
      for (int j = 0; j < 8; ++j) {
        c = (c & 1u) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
      }
      t[i] = c;
    }
    return t;
  }();

  std::uint32_t crc = 0xFFFFFFFFu;
  for (std::size_t i = 0; i < length; ++i) {
    crc = kTable[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
  }
  return crc ^ 0xFFFFFFFFu;
}

void setError(std::string* out, const std::string& msg) {
  if (out != nullptr) {
    *out = msg;
  }
}

double finiteOrZero(double v) {
  return std::isfinite(v) ? v : 0.0;
}

}  // namespace

// ----------------------------------------------------------------------------
// UnavPointBuffer — implementation
// ----------------------------------------------------------------------------

UnavPointBuffer::UnavPointBuffer()
    : maxPoints_(kDefaultMaxPoints) {}

UnavPointBuffer::UnavPointBuffer(std::size_t maxPoints) {
  setMaxPoints(maxPoints);
}

void UnavPointBuffer::setMaxPoints(std::size_t maxPoints) {
  maxPoints_ = (maxPoints == 0) ? kDefaultMaxPoints : maxPoints;
}

void UnavPointBuffer::clear() {
  points_.clear();
  sources_.clear();
  lastStats_ = LoadStats{};
  lastPath_.clear();
  extras_ = V2Extras{};
  accel_ = AccelGrid{};
}

void UnavPointBuffer::reserve(std::size_t count) {
  if (count > maxPoints_) {
    count = maxPoints_;
  }
  points_.reserve(count);
}

std::size_t UnavPointBuffer::addPoint(const UnavPoint& point) {
  if (points_.size() >= maxPoints_) {
    return points_.size();
  }
  points_.push_back(point);
  return points_.size();
}

void UnavPointBuffer::setSourceTable(
    std::vector<UnavSourceEntry> sources) {
  sources_ = std::move(sources);
}

std::size_t UnavPointBuffer::size() const noexcept {
  return points_.size();
}

const UnavPoint* UnavPointBuffer::data() const noexcept {
  return points_.empty() ? nullptr : points_.data();
}

const std::vector<UnavSourceEntry>& UnavPointBuffer::sources()
    const noexcept {
  return sources_;
}

void UnavPointBuffer::worldPosition(
    std::size_t index, double* outX, double* outY, double* outZ) const {
  double x = 0.0, y = 0.0, z = 0.0;
  if (index < points_.size()) {
    x = points_[index].x;
    y = points_[index].y;
    z = points_[index].z;
    if (extras_.pointsAreRelative()) {
      x += extras_.sector_origin[0];
      y += extras_.sector_origin[1];
      z += extras_.sector_origin[2];
    }
  }
  if (outX) *outX = x;
  if (outY) *outY = y;
  if (outZ) *outZ = z;
}

// ----------------------------------------------------------------------------
// loadFromFile — v1 + v2 parser.
// ----------------------------------------------------------------------------

std::size_t UnavPointBuffer::loadFromFile(
    const std::string& path, std::string* errorOut) {
  const auto t0 = std::chrono::steady_clock::now();
  clear();
  lastPath_ = path;

  std::ifstream fh(path, std::ios::binary);
  if (!fh.is_open()) {
    setError(errorOut, "could not open file: " + path);
    return 0;
  }
  fh.seekg(0, std::ios::end);
  const std::streamsize fileSize = fh.tellg();
  if (fileSize < static_cast<std::streamsize>(kHeaderSize + kFooterSize)) {
    setError(errorOut, "file too small to hold header / footer");
    return 0;
  }
  fh.seekg(0, std::ios::beg);
  std::vector<std::uint8_t> raw(static_cast<std::size_t>(fileSize));
  fh.read(reinterpret_cast<char*>(raw.data()),
          static_cast<std::streamsize>(raw.size()));
  if (!fh) {
    setError(errorOut, "short read on file: " + path);
    return 0;
  }

  // ---- Header ------------------------------------------------------------
  if (std::memcmp(raw.data(), kMagic.data(), kMagic.size()) != 0) {
    setError(errorOut, "bad header magic; expected 'UNAV'");
    return 0;
  }
  const std::uint16_t version = readUInt16LE(raw.data() + 4);
  if (version != kFormatVersionV1 && version != kFormatVersionV2) {
    std::ostringstream oss;
    oss << "unsupported format version " << version
        << "; this build understands v1 and v2";
    setError(errorOut, oss.str());
    return 0;
  }
  const double scaleFactor = readDoubleLE(raw.data() + 8);
  const std::uint32_t pointCount = readUInt32LE(raw.data() + 16);
  const std::uint32_t sourceCount = readUInt32LE(raw.data() + 20);
  const std::uint32_t headerExtra = readUInt32LE(raw.data() + 24);
  const std::uint16_t sidecarLen = readUInt16LE(raw.data() + 28);

  if (pointCount > kAbsurdPointCount) {
    std::ostringstream oss;
    oss << "rejecting absurd point count " << pointCount
        << " (cap " << kAbsurdPointCount << ")";
    setError(errorOut, oss.str());
    return 0;
  }
  if (version == kFormatVersionV1 && headerExtra != 0) {
    setError(errorOut,
             "v1 header has non-zero header_extra_bytes; this file "
             "claims version 1 but uses v2 layout");
    return 0;
  }
  if (version == kFormatVersionV2 && headerExtra != kV2ExtraHeaderSize) {
    std::ostringstream oss;
    oss << "v2 header_extra_bytes is " << headerExtra
        << "; expected " << kV2ExtraHeaderSize;
    setError(errorOut, oss.str());
    return 0;
  }
  std::size_t cursor = kHeaderSize;
  if (cursor + sidecarLen > raw.size()) {
    setError(errorOut, "sidecar_path_len overruns file");
    return 0;
  }
  std::string sidecar(reinterpret_cast<const char*>(raw.data() + cursor),
                      static_cast<std::size_t>(sidecarLen));
  cursor += sidecarLen;

  // ---- v2 extras (when present) -----------------------------------------
  V2Extras parsedExtras;
  if (version == kFormatVersionV2) {
    if (cursor + kV2ExtraHeaderSize > raw.size()) {
      setError(errorOut, "v2 extras block overruns file");
      return 0;
    }
    const std::uint8_t* e = raw.data() + cursor;
    parsedExtras.renderer_flags = readUInt32LE(e + 0);
    parsedExtras.visual_encoding_id = readUInt32LE(e + 4);
    for (int i = 0; i < 3; ++i) {
      parsedExtras.sector_origin[i] = finiteOrZero(readDoubleLE(e + 8 + i * 8));
    }
    for (int i = 0; i < 4; ++i) {
      parsedExtras.bounding_sphere[i] = finiteOrZero(readDoubleLE(e + 32 + i * 8));
    }
    for (int i = 0; i < 3; ++i) {
      parsedExtras.aabb_min[i] = finiteOrZero(readDoubleLE(e + 64 + i * 8));
    }
    for (int i = 0; i < 3; ++i) {
      parsedExtras.aabb_max[i] = finiteOrZero(readDoubleLE(e + 88 + i * 8));
    }
    cursor += kV2ExtraHeaderSize;
  }

  // ---- Source table ------------------------------------------------------
  std::vector<UnavSourceEntry> srcTable;
  srcTable.reserve(sourceCount);
  for (std::uint32_t i = 0; i < sourceCount; ++i) {
    if (cursor + kSourceHeaderSize > raw.size()) {
      setError(errorOut, "source table overruns file");
      return 0;
    }
    const std::uint32_t sid = readUInt32LE(raw.data() + cursor);
    const std::uint16_t nameLen = readUInt16LE(raw.data() + cursor + 4);
    cursor += kSourceHeaderSize;
    if (cursor + nameLen > raw.size()) {
      setError(errorOut, "source name overruns file");
      return 0;
    }
    UnavSourceEntry e;
    e.source_id = sid;
    e.name.assign(
        reinterpret_cast<const char*>(raw.data() + cursor), nameLen);
    cursor += nameLen;
    srcTable.push_back(std::move(e));
  }

  // ---- Point block -------------------------------------------------------
  const std::size_t pointBlockBytes =
      static_cast<std::size_t>(pointCount) * kPointSize;
  if (cursor + pointBlockBytes + kFooterSize > raw.size()) {
    setError(errorOut, "point block overruns file");
    return 0;
  }
  const std::size_t cappedCount = std::min<std::size_t>(
      static_cast<std::size_t>(pointCount), maxPoints_);
  std::vector<UnavPoint> pts;
  pts.reserve(cappedCount);
  if (cappedCount > 0) {
    pts.resize(cappedCount);
    std::memcpy(pts.data(), raw.data() + cursor,
                cappedCount * kPointSize);
  }
  cursor += pointBlockBytes;

  // ---- Footer / CRC ------------------------------------------------------
  if (cursor + kFooterSize != raw.size()) {
    setError(errorOut, "trailing bytes after footer");
    return 0;
  }
  if (std::memcmp(raw.data() + cursor, kMagicEnd.data(),
                  kMagicEnd.size()) != 0) {
    setError(errorOut, "bad footer magic; expected 'UEND'");
    return 0;
  }
  const std::uint32_t storedCrc =
      readUInt32LE(raw.data() + cursor + 4);
  const std::uint32_t computedCrc =
      crc32(raw.data() + kMagic.size(), cursor - kMagic.size());
  if (storedCrc != computedCrc) {
    std::ostringstream oss;
    oss << "CRC mismatch: stored 0x" << std::hex << storedCrc
        << ", computed 0x" << computedCrc;
    setError(errorOut, oss.str());
    return 0;
  }

  // ---- Commit + stats + accel grid ---------------------------------------
  points_ = std::move(pts);
  sources_ = std::move(srcTable);
  extras_ = parsedExtras;
  lastStats_.point_count = points_.size();
  lastStats_.source_count = sources_.size();
  lastStats_.file_size_bytes = static_cast<std::uint64_t>(raw.size());
  lastStats_.sidecar_path = std::move(sidecar);
  lastStats_.coordinate_scale_factor = scaleFactor;
  lastStats_.format_version = version;
  // GPU footprint estimate: per-vertex (xyz f32 + rgb f32 + size f32 + uid u64) = 32 bytes.
  lastStats_.estimated_gpu_bytes =
      static_cast<std::uint64_t>(points_.size()) * 32u;

  rebuildAccelGrid();

  const auto t1 = std::chrono::steady_clock::now();
  lastStats_.load_seconds =
      std::chrono::duration<double>(t1 - t0).count();

  if (cappedCount < pointCount) {
    std::ostringstream oss;
    oss << "warning: file held " << pointCount
        << " points; capped to " << cappedCount
        << " by maxPoints=" << maxPoints_;
    setError(errorOut, oss.str());
  } else {
    setError(errorOut, "");
  }
  return points_.size();
}

// ----------------------------------------------------------------------------
// queryNearestPointToPosition — brute force, used by tests + fallback
// ----------------------------------------------------------------------------

std::size_t UnavPointBuffer::queryNearestPointToPosition(
    double x, double y, double z, double maxDistance) const {
  if (points_.empty() || maxDistance <= 0.0) {
    return kInvalidIndex;
  }
  const double maxDist2 = maxDistance * maxDistance;
  std::size_t bestIdx = kInvalidIndex;
  double bestDist2 = maxDist2;
  for (std::size_t i = 0; i < points_.size(); ++i) {
    double wx, wy, wz;
    worldPosition(i, &wx, &wy, &wz);
    const double dx = wx - x;
    const double dy = wy - y;
    const double dz = wz - z;
    const double d2 = dx * dx + dy * dy + dz * dz;
    if (d2 < bestDist2) {
      bestDist2 = d2;
      bestIdx = i;
    }
  }
  return bestIdx;
}

// ----------------------------------------------------------------------------
// queryNearestPointToRay — brute force, perpendicular distance
// ----------------------------------------------------------------------------

std::size_t UnavPointBuffer::queryNearestPointToRay(
    double rx, double ry, double rz,
    double dx, double dy, double dz,
    double maxDistance) const {
  if (points_.empty() || maxDistance <= 0.0) {
    return kInvalidIndex;
  }
  const double dirLen2 = dx * dx + dy * dy + dz * dz;
  if (dirLen2 == 0.0) {
    return kInvalidIndex;
  }
  const double maxDist2 = maxDistance * maxDistance;
  std::size_t bestIdx = kInvalidIndex;
  double bestDist2 = maxDist2;
  for (std::size_t i = 0; i < points_.size(); ++i) {
    double px, py, pz;
    worldPosition(i, &px, &py, &pz);
    const double ox = px - rx;
    const double oy = py - ry;
    const double oz = pz - rz;
    const double t = (ox * dx + oy * dy + oz * dz) / dirLen2;
    if (t < 0.0) continue;
    const double cx = rx + dx * t;
    const double cy = ry + dy * t;
    const double cz = rz + dz * t;
    const double ddx = px - cx;
    const double ddy = py - cy;
    const double ddz = pz - cz;
    const double d2 = ddx * ddx + ddy * ddy + ddz * ddz;
    if (d2 < bestDist2) {
      bestDist2 = d2;
      bestIdx = i;
    }
  }
  return bestIdx;
}

// ----------------------------------------------------------------------------
// Accel grid — uniform 32^3 voxels over the bounding box.
// ----------------------------------------------------------------------------

namespace {

constexpr int kGridDimMax = 32;

}  // namespace

void UnavPointBuffer::rebuildAccelGrid() {
  accel_ = AccelGrid{};
  if (points_.empty()) {
    return;
  }
  // Compute world-space bbox (post-relative-correction).
  double mn[3] = {0.0, 0.0, 0.0};
  double mx[3] = {0.0, 0.0, 0.0};
  worldPosition(0, &mn[0], &mn[1], &mn[2]);
  mx[0] = mn[0]; mx[1] = mn[1]; mx[2] = mn[2];
  for (std::size_t i = 1; i < points_.size(); ++i) {
    double wx, wy, wz;
    worldPosition(i, &wx, &wy, &wz);
    if (wx < mn[0]) { mn[0] = wx; }
    if (wx > mx[0]) { mx[0] = wx; }
    if (wy < mn[1]) { mn[1] = wy; }
    if (wy > mx[1]) { mx[1] = wy; }
    if (wz < mn[2]) { mn[2] = wz; }
    if (wz > mx[2]) { mx[2] = wz; }
  }
  const double extent = std::max({
      mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2], 1e-9,
  });
  const double cellSize = std::max(1e-9, extent / kGridDimMax);
  for (int i = 0; i < 3; ++i) {
    accel_.origin[i] = mn[i];
    int dim = static_cast<int>(std::ceil((mx[i] - mn[i]) / cellSize));
    if (dim < 1) dim = 1;
    if (dim > kGridDimMax) dim = kGridDimMax;
    accel_.dims[i] = dim;
  }
  accel_.cell_size = cellSize;
  const std::size_t total = static_cast<std::size_t>(accel_.dims[0]) *
                            static_cast<std::size_t>(accel_.dims[1]) *
                            static_cast<std::size_t>(accel_.dims[2]);
  accel_.cells.assign(total, {});
  for (std::size_t i = 0; i < points_.size(); ++i) {
    double wx, wy, wz;
    worldPosition(i, &wx, &wy, &wz);
    int ix = static_cast<int>((wx - accel_.origin[0]) / cellSize);
    int iy = static_cast<int>((wy - accel_.origin[1]) / cellSize);
    int iz = static_cast<int>((wz - accel_.origin[2]) / cellSize);
    if (ix < 0) { ix = 0; }
    if (ix >= accel_.dims[0]) { ix = accel_.dims[0] - 1; }
    if (iy < 0) { iy = 0; }
    if (iy >= accel_.dims[1]) { iy = accel_.dims[1] - 1; }
    if (iz < 0) { iz = 0; }
    if (iz >= accel_.dims[2]) { iz = accel_.dims[2] - 1; }
    accel_.cells[cellIndex(ix, iy, iz)].push_back(
        static_cast<std::uint32_t>(i));
  }
}

std::size_t UnavPointBuffer::cellIndex(
    int ix, int iy, int iz) const noexcept {
  return static_cast<std::size_t>(ix)
       + static_cast<std::size_t>(accel_.dims[0]) * (
             static_cast<std::size_t>(iy)
           + static_cast<std::size_t>(accel_.dims[1]) *
                 static_cast<std::size_t>(iz));
}

std::size_t UnavPointBuffer::accelCellCount() const noexcept {
  return accel_.cells.size();
}

// ----------------------------------------------------------------------------
// pickByRayAndScreenRadius — accelerated picking
// ----------------------------------------------------------------------------

std::size_t UnavPointBuffer::pickByRayAndScreenRadius(
    double rx, double ry, double rz,
    double dx, double dy, double dz,
    double screenRadiusWorld) const {
  if (points_.empty() || screenRadiusWorld <= 0.0) {
    return kInvalidIndex;
  }
  // Without an accel grid (or for tiny clouds), fall back to brute
  // force; the result is the same.
  if (accel_.cells.empty()) {
    return queryNearestPointToRay(rx, ry, rz, dx, dy, dz, screenRadiusWorld);
  }
  const double dirLen2 = dx * dx + dy * dy + dz * dz;
  if (dirLen2 == 0.0) {
    return kInvalidIndex;
  }
  const double maxDist2 = screenRadiusWorld * screenRadiusWorld;
  std::size_t bestIdx = kInvalidIndex;
  double bestDist2 = maxDist2;
  // Walk every grid cell whose AABB intersects the ray's
  // axis-aligned bounding strip (sized by `screenRadiusWorld`).
  // For cell extents of `cell_size`, we consider any cell whose
  // centre lies within `cell_size + screenRadiusWorld` of the
  // closest ray point. v1.0 keeps the loop full-grid + early
  // reject; the win comes from the candidate set being
  // shrunk by the ``2 * radius / cell_size`` factor when the
  // radius is small compared to the bbox.
  for (int iz = 0; iz < accel_.dims[2]; ++iz) {
    for (int iy = 0; iy < accel_.dims[1]; ++iy) {
      for (int ix = 0; ix < accel_.dims[0]; ++ix) {
        const auto& bucket =
            accel_.cells[cellIndex(ix, iy, iz)];
        if (bucket.empty()) continue;
        // Cell centre.
        const double cx = accel_.origin[0] + (ix + 0.5) * accel_.cell_size;
        const double cy = accel_.origin[1] + (iy + 0.5) * accel_.cell_size;
        const double cz = accel_.origin[2] + (iz + 0.5) * accel_.cell_size;
        // Distance from ray to cell centre.
        const double ox = cx - rx;
        const double oy = cy - ry;
        const double oz = cz - rz;
        const double t = (ox * dx + oy * dy + oz * dz) / dirLen2;
        if (t < 0.0) continue;
        const double pX = rx + dx * t;
        const double pY = ry + dy * t;
        const double pZ = rz + dz * t;
        const double ddx = cx - pX;
        const double ddy = cy - pY;
        const double ddz = cz - pZ;
        const double cellPerp2 = ddx * ddx + ddy * ddy + ddz * ddz;
        // Early reject: cell too far from the ray to contain a hit.
        // A point inside the cell is at most cell_size * sqrt(3)/2
        // from the centre.
        const double cellHalfDiag =
            accel_.cell_size * 0.8660254037844386;  // sqrt(3)/2
        const double slack = cellHalfDiag + screenRadiusWorld;
        if (cellPerp2 > slack * slack) continue;
        // Refine over points in the bucket.
        for (std::uint32_t pIdx : bucket) {
          double px, py, pz;
          worldPosition(pIdx, &px, &py, &pz);
          const double pox = px - rx;
          const double poy = py - ry;
          const double poz = pz - rz;
          const double pt = (pox * dx + poy * dy + poz * dz) / dirLen2;
          if (pt < 0.0) continue;
          const double qx = rx + dx * pt;
          const double qy = ry + dy * pt;
          const double qz = rz + dz * pt;
          const double pdx = px - qx;
          const double pdy = py - qy;
          const double pdz = pz - qz;
          const double pd2 = pdx * pdx + pdy * pdy + pdz * pdz;
          if (pd2 < bestDist2) {
            bestDist2 = pd2;
            bestIdx = pIdx;
          }
        }
      }
    }
  }
  return bestIdx;
}

}  // namespace unav
