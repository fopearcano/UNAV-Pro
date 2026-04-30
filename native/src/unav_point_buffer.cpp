// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native point buffer (v0.9 prototype implementation).
//
// Real binary loader + nearest-point hit-test. Pure stdlib (no
// Maxon SDK, no zlib) so the loader logic compiles against any
// C++17 host and the unit tests in
// `native/tests/test_unav_point_buffer.cpp` exercise it without
// Cinema 4D.
//
// The CRC32 implementation below uses the standard IEEE 802.3
// polynomial (0xEDB88320 reflected) — bit-exact compatible with
// zlib's `crc32`, which is what the Python exporter writes.

#include "unav_point_buffer.h"

#include <algorithm>
#include <array>
#include <chrono>
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
constexpr std::uint16_t kFormatVersion = 1;
constexpr std::size_t kHeaderSize = 30;
constexpr std::size_t kFooterSize = 8;
constexpr std::size_t kSourceHeaderSize = 6;  // uint32 + uint16
constexpr std::size_t kPointSize = sizeof(UnavPoint);  // 52 bytes

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
  // IEEE 754 little-endian. Most modern hosts already store doubles
  // little-endian; copy via memcpy to avoid strict-aliasing issues.
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

// ----------------------------------------------------------------------------
// Minimal helpers for error messages.
// ----------------------------------------------------------------------------

void setError(std::string* out, const std::string& msg) {
  if (out != nullptr) {
    *out = msg;
  }
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

// ----------------------------------------------------------------------------
// loadFromFile — the v0.9 work that v0.8 deferred.
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
  if (version != kFormatVersion) {
    std::ostringstream oss;
    oss << "unsupported format version " << version
        << "; this build understands " << kFormatVersion;
    setError(errorOut, oss.str());
    return 0;
  }
  // const std::uint16_t flags = readUInt16LE(raw.data() + 6);
  const double scaleFactor = readDoubleLE(raw.data() + 8);
  const std::uint32_t pointCount = readUInt32LE(raw.data() + 16);
  const std::uint32_t sourceCount = readUInt32LE(raw.data() + 20);
  const std::uint32_t headerExtra = readUInt32LE(raw.data() + 24);
  const std::uint16_t sidecarLen = readUInt16LE(raw.data() + 28);
  if (headerExtra != 0) {
    // v1 never emits non-zero header_extra_bytes; reject
    // forward-compatibility files we cannot parse.
    setError(errorOut,
             "header_extra_bytes is non-zero; this v0.9 build only "
             "understands version-1 files with no extra header bytes");
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

  // Apply the safety cap.
  const std::size_t cappedCount = std::min<std::size_t>(
      static_cast<std::size_t>(pointCount), maxPoints_);
  std::vector<UnavPoint> pts;
  pts.reserve(cappedCount);
  // Bulk copy: the on-disk layout matches `UnavPoint` byte-for-byte.
  if (cappedCount > 0) {
    pts.resize(cappedCount);
    std::memcpy(pts.data(),
                raw.data() + cursor,
                cappedCount * kPointSize);
  }
  cursor += pointBlockBytes;

  // ---- Footer ------------------------------------------------------------
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
  // CRC payload: every byte after the 4-byte magic up to the footer.
  const std::uint32_t computedCrc =
      crc32(raw.data() + kMagic.size(),
            cursor - kMagic.size());
  if (storedCrc != computedCrc) {
    std::ostringstream oss;
    oss << "CRC mismatch: stored 0x" << std::hex << storedCrc
        << ", computed 0x" << computedCrc;
    setError(errorOut, oss.str());
    return 0;
  }

  // ---- Commit + stats ----------------------------------------------------
  points_ = std::move(pts);
  sources_ = std::move(srcTable);
  lastStats_.point_count = points_.size();
  lastStats_.source_count = sources_.size();
  lastStats_.file_size_bytes = static_cast<std::uint64_t>(raw.size());
  lastStats_.sidecar_path = std::move(sidecar);
  lastStats_.coordinate_scale_factor = scaleFactor;
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
// queryNearestPointToRay — closest perpendicular distance ≤ maxDistance
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
    const auto& p = points_[i];
    // Vector from ray origin to point.
    const double ox = p.x - rx;
    const double oy = p.y - ry;
    const double oz = p.z - rz;
    // Project onto direction; require non-negative t (point in
    // front of the ray origin).
    const double t = (ox * dx + oy * dy + oz * dz) / dirLen2;
    if (t < 0.0) continue;
    // Closest point on the ray.
    const double cx = rx + dx * t;
    const double cy = ry + dy * t;
    const double cz = rz + dz * t;
    const double ddx = p.x - cx;
    const double ddy = p.y - cy;
    const double ddz = p.z - cz;
    const double d2 = ddx * ddx + ddy * ddy + ddz * ddz;
    if (d2 < bestDist2) {
      bestDist2 = d2;
      bestIdx = i;
    }
  }
  return bestIdx;
}

std::size_t UnavPointBuffer::queryNearestPointToPosition(
    double x, double y, double z, double maxDistance) const {
  if (points_.empty() || maxDistance <= 0.0) {
    return kInvalidIndex;
  }
  const double maxDist2 = maxDistance * maxDistance;
  std::size_t bestIdx = kInvalidIndex;
  double bestDist2 = maxDist2;
  for (std::size_t i = 0; i < points_.size(); ++i) {
    const auto& p = points_[i];
    const double dx = p.x - x;
    const double dy = p.y - y;
    const double dz = p.z - z;
    const double d2 = dx * dx + dy * dy + dz * dz;
    if (d2 < bestDist2) {
      bestDist2 = d2;
      bestIdx = i;
    }
  }
  return bestIdx;
}

bool UnavPointBuffer::uploadPlaceholder() {
  // v0.9 does not maintain a GPU buffer. The plugin draws each
  // visible point per `Draw` callback via the simplest SDK path
  // (`BaseDraw::DrawPoint`) — fine for prototype scale, replaced
  // by a single `DrawArray` call in v0.10.
  return false;
}

bool UnavPointBuffer::drawPlaceholder() {
  // Draw is plugin-side; see `unav_native_plugin.cpp`.
  return false;
}

}  // namespace unav
