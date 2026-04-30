// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native point buffer stubs (v0.8 feasibility spike).
//
// Every method here is intentionally a thin stub. The point of v0.8
// is to lock the surface in `unav_point_buffer.h` so the v0.9
// implementer can fill these bodies without negotiating the API
// shape with the rest of the plugin.
//
// When the binary loader lands in v0.9, it should:
//
//   - mmap or fread the file produced by
//     `unav_pro/data/binary_export.write_visible_sector(...)`,
//   - parse the header (`UNAV` magic, version 1, packed layout),
//   - read the source table and populate `sources_`,
//   - read the point block directly into a contiguous `points_`
//     vector (the on-disk layout matches `UnavPoint` exactly under
//     `#pragma pack(push, 1)` — see the static_assert in the
//     header),
//   - validate the CRC32 in the footer and reject mismatches with
//     a clear `errorOut` message.
//
// The format spec lives in `docs/BINARY_VISIBLE_SECTOR_FORMAT.md`;
// the Python reference reader lives in
// `unav_pro/data/binary_export.read_visible_sector(...)`. The two
// implementations must agree.

#include "unav_point_buffer.h"

#include <cstring>
#include <utility>

namespace unav {

void UnavPointBuffer::clear() {
  points_.clear();
  sources_.clear();
}

void UnavPointBuffer::reserve(std::size_t count) {
  points_.reserve(count);
}

std::size_t UnavPointBuffer::addPoint(const UnavPoint& point) {
  points_.push_back(point);
  return points_.size();
}

void UnavPointBuffer::setSourceTable(
    std::vector<UnavSourceEntry> sources) {
  sources_ = std::move(sources);
}

std::size_t UnavPointBuffer::loadFromFile(
    const std::string& /*path*/, std::string* errorOut) {
  // v0.8: not implemented. v0.9 ships the real loader.
  if (errorOut != nullptr) {
    *errorOut = "UnavPointBuffer::loadFromFile is a v0.8 placeholder; "
                "implementation lands in v0.9. See "
                "docs/BINARY_VISIBLE_SECTOR_FORMAT.md and "
                "unav_pro/data/binary_export.py for the spec / "
                "reference reader.";
  }
  return 0;
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

bool UnavPointBuffer::uploadPlaceholder() {
  // v0.8: no GPU upload happens. v0.9 hands the contiguous buffer
  // to the Maxon viewport via a `BaseDraw` callback or the SDK's
  // raw GL/Metal draw extension; see
  // `docs/NATIVE_VIEWPORT_DRAWING_RESEARCH.md`.
  return false;
}

bool UnavPointBuffer::drawPlaceholder() {
  // v0.8: no draw happens. v0.9 issues a single `glDrawArrays` /
  // `[id<MTLRenderCommandEncoder> drawPrimitives:...]` per pass,
  // guarded by the platform Maxon's renderer is using.
  return false;
}

std::size_t UnavPointBuffer::queryNearestPointPlaceholder(
    double /*rayOriginX*/, double /*rayOriginY*/,
    double /*rayOriginZ*/, double /*rayDirX*/, double /*rayDirY*/,
    double /*rayDirZ*/, double /*maxDistance*/) const {
  // v0.8: no hit-test. v0.9 walks the buffer with an early-out
  // bounding-sphere check and a depth-buffer readback to produce
  // the closest visible point's index. The dialog's selection
  // bridge then maps `points_[index].uid_hash` back to the
  // catalog uid via the metadata sidecar.
  return kInvalidIndex;
}

}  // namespace unav
