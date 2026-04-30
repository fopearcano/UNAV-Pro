// SPDX-License-Identifier: MIT
//
// UNAV Pro — GPU buffer (v1.0) — base implementation.
//
// CPU-side shadow + safe fallback. The default upload returns
// false ("no GPU available") so v1.0 in a CI box exercises the
// fallback path. SDK-aware subclasses override `uploadImpl` /
// `freeImpl` to push to a Maxon `BaseDraw` VBO when the host is
// available.

#include "unav_gpu_buffer.h"

#include <chrono>
#include <utility>

namespace unav {

bool UnavGpuBuffer::buildFromCpu(const UnavPointBuffer& buf) {
  vertices_.clear();
  stats_.last_error.clear();
  stats_.uploaded_to_gpu = false;
  stats_.gpu_bytes = 0;
  stats_.last_upload_seconds = 0.0;

  const std::size_t n = buf.size();
  if (n == 0) {
    stats_.vertex_count = 0;
    stats_.cpu_bytes = 0;
    return true;
  }
  vertices_.resize(n);
  for (std::size_t i = 0; i < n; ++i) {
    double wx, wy, wz;
    buf.worldPosition(i, &wx, &wy, &wz);
    const auto& src = buf.data()[i];
    auto& v = vertices_[i];
    v.x = static_cast<float>(wx);
    v.y = static_cast<float>(wy);
    v.z = static_cast<float>(wz);
    v.size = src.size;
    v.r = src.r;
    v.g = src.g;
    v.b = src.b;
    v.uid_hash = src.uid_hash;
    v.source_id = src.source_id;
  }
  stats_.vertex_count = vertices_.size();
  stats_.cpu_bytes =
      static_cast<std::uint64_t>(vertices_.size()) * sizeof(GpuVertex);

  // Try the GPU path. Subclasses may succeed; the base class
  // returns false. The fallback path is then "renderer walks
  // the CPU array".
  const auto t0 = std::chrono::steady_clock::now();
  const bool ok = uploadImpl();
  const auto t1 = std::chrono::steady_clock::now();
  if (ok) {
    stats_.last_upload_seconds =
        std::chrono::duration<double>(t1 - t0).count();
  } else if (stats_.last_error.empty()) {
    stats_.last_error =
        "GPU upload not available; using CPU fallback "
        "(this is expected outside Cinema 4D's render context)";
  }
  return true;
}

void UnavGpuBuffer::clear() {
  freeImpl();
  vertices_.clear();
  stats_ = GpuBufferStats{};
  stats_.backend = "cpu_fallback";
}

bool UnavGpuBuffer::uploadImpl() {
  // Base class: always reports "no GPU available". An SDK-aware
  // subclass overrides this to attempt the actual upload.
  return false;
}

void UnavGpuBuffer::freeImpl() {
  // Base class: nothing to release.
}

void UnavGpuBuffer::setBackendName(std::string name) {
  stats_.backend = std::move(name);
}

void UnavGpuBuffer::recordError(std::string message) {
  stats_.last_error = std::move(message);
}

void UnavGpuBuffer::recordUploadOk(
    std::uint64_t gpuBytes, double uploadSeconds) {
  stats_.gpu_bytes = gpuBytes;
  stats_.last_upload_seconds = uploadSeconds;
  stats_.uploaded_to_gpu = true;
  stats_.last_error.clear();
}

}  // namespace unav
