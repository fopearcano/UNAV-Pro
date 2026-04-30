// SPDX-License-Identifier: MIT
//
// UNAV Pro — GPU buffer abstraction (v1.0).
//
// Sits between the SDK-free `UnavPointBuffer` (which owns the
// CPU-side records loaded from the binary file) and the SDK-bound
// `UnavRenderer` (which issues draw calls). The GPU buffer:
//
//   - holds a packed, stride-tight CPU shadow of the per-vertex
//     attributes the renderer needs (the "GpuVertex" struct
//     below);
//   - keeps an opaque GPU handle, populated when an SDK-aware
//     subclass overrides `uploadImpl`;
//   - tolerates GPU upload failure by falling back to a plain
//     CPU array (the renderer queries `isUploaded()` and chooses
//     accordingly);
//   - never allocates on the GPU when the SDK is not present
//     (CI builds, this repository's CTest target, etc.).
//
// SDK-free by construction. The Maxon-bound subclass lives in
// `unav_native_plugin.cpp` (v1.0 still uses Maxon's own draw
// path; the GPU buffer abstraction is in place so v1.1 can move
// to a true VBO without rewriting the renderer).

#pragma once

#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>

#include "unav_point_buffer.h"

namespace unav {

// ----------------------------------------------------------------------------
// GpuVertex — packed per-vertex attributes pushed to the renderer.
// ----------------------------------------------------------------------------
//
// Cinema 4D viewport stack is float32; positions pre-translated by
// `sector_origin` happen in `UnavGpuBuffer::buildFromCpu`. Layout:
//
//   float32 x, y, z         (12 bytes)   — world-space, post-relative
//   float32 size            (4  bytes)
//   float32 r, g, b         (12 bytes)
//   uint64  uid_hash        (8  bytes)
//   uint32  source_id       (4  bytes)
//
// Total: 40 bytes per vertex (vs. 52 on disk; the GPU strips the
// CPU-side double-precision positions). Static_assert below pins
// it.

#pragma pack(push, 1)
struct GpuVertex {
  float x;
  float y;
  float z;
  float size;
  float r;
  float g;
  float b;
  std::uint64_t uid_hash;
  std::uint32_t source_id;
};
#pragma pack(pop)

static_assert(sizeof(GpuVertex) == 40,
              "GpuVertex must remain 40 bytes; renderer + tests "
              "depend on a stable layout.");

// ----------------------------------------------------------------------------
// GpuBufferStats — what the dialog surfaces.
// ----------------------------------------------------------------------------

struct GpuBufferStats {
  std::size_t vertex_count = 0;
  std::uint64_t cpu_bytes = 0;     // sizeof(GpuVertex) * vertex_count
  std::uint64_t gpu_bytes = 0;     // 0 when fallback path is active
  bool uploaded_to_gpu = false;
  std::string backend = "cpu_fallback";  // "cpu_fallback" | "vbo" | …
  std::string last_error;
  double last_upload_seconds = 0.0;
};

// ----------------------------------------------------------------------------
// UnavGpuBuffer — base class.
// ----------------------------------------------------------------------------

class UnavGpuBuffer {
 public:
  UnavGpuBuffer() = default;
  virtual ~UnavGpuBuffer() = default;

  UnavGpuBuffer(const UnavGpuBuffer&) = delete;
  UnavGpuBuffer& operator=(const UnavGpuBuffer&) = delete;
  UnavGpuBuffer(UnavGpuBuffer&&) noexcept = default;
  UnavGpuBuffer& operator=(UnavGpuBuffer&&) noexcept = default;

  // Build the GPU shadow from a CPU-side `UnavPointBuffer`. The
  // vertex array is rebuilt from scratch every call; v1.0 doesn't
  // attempt a delta upload (the binary file is a full snapshot).
  // Returns true on success.
  bool buildFromCpu(const UnavPointBuffer& buf);

  // Drop the CPU + GPU shadows. `freeImpl` releases the GPU
  // handle when one was allocated.
  void clear();

  // ----------------------------------------------------- accessors
  std::size_t vertexCount() const noexcept { return vertices_.size(); }
  bool empty() const noexcept { return vertices_.empty(); }
  bool isUploaded() const noexcept { return stats_.uploaded_to_gpu; }
  const GpuVertex* vertices() const noexcept {
    return vertices_.empty() ? nullptr : vertices_.data();
  }
  const GpuBufferStats& stats() const noexcept { return stats_; }

 protected:
  // SDK-aware subclasses override these. Default implementations
  // return false → "GPU upload not attempted" and the renderer
  // falls back to walking the CPU array.
  virtual bool uploadImpl();
  virtual void freeImpl();

  // Per-instance scratch the SDK subclass can stash a handle in.
  void setBackendName(std::string name);
  void recordError(std::string message);

  // Subclasses report success / size of the GPU buffer they own.
  void recordUploadOk(std::uint64_t gpuBytes, double uploadSeconds);

 private:
  std::vector<GpuVertex> vertices_;
  GpuBufferStats stats_;
};

}  // namespace unav
