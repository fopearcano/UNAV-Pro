// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native renderer (v1.0).
//
// Owns the shader-style render configuration the v0.9 prototype's
// `Draw` callback used implicitly. v1.0 turns those knobs into
// data the dialog can adjust, and tucks the actual draw call
// behind a virtual hook so the SDK-bound subclass in the plugin
// shell can swap in `BaseDraw::DrawArrayWithVertexBuffer` (or any
// later GPU path) without touching the buffer or the bridge.
//
// Two layers:
//
//   - `RenderConfig` — pure data; identical to what the dialog
//     UI exposes.
//   - `UnavRenderer` — base class owning the GPU buffer. The
//     base implementation walks the CPU shadow when the buffer
//     is not GPU-uploaded; this is the v1.0 CPU fallback path
//     that the test suite covers.
//
// SDK-free; the SDK-bound subclass lives in
// `unav_native_plugin.cpp` and overrides `drawImpl(...)`.

#pragma once

#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>

#include "unav_gpu_buffer.h"
#include "unav_point_buffer.h"

namespace unav {

// ----------------------------------------------------------------------------
// RenderConfig — the artist-facing shader-style knobs.
// ----------------------------------------------------------------------------

struct RenderConfig {
  // Multiplier on per-point `size`. 1.0 = file value verbatim.
  float point_size_scale = 1.0f;
  // Multiplier on per-point colour. 1.0 = file value verbatim.
  float brightness_scale = 1.0f;
  // Distance fade applied as alpha = 1 / (1 + distance / fade_distance).
  // 0.0 disables fade.
  float fade_distance = 0.0f;
  // Anti-aliased circular points when supported; otherwise a
  // square billboard fallback. Hint, not requirement.
  bool antialiased_points = true;
  // Camera-relative origin in world units. The renderer subtracts
  // this from each vertex right before emitting it; combined with
  // the v2 file's pre-relative storage, this is the floating-
  // origin pattern.
  double camera_origin[3] = {0.0, 0.0, 0.0};
  // When true, draws colour-by-source-id and bypasses the file's
  // baked colour. Useful for catalog QA.
  bool debug_draw = false;
};

// ----------------------------------------------------------------------------
// FrameStats — what the renderer reports back per draw.
// ----------------------------------------------------------------------------

struct FrameStats {
  std::size_t drawn_points = 0;
  std::size_t culled_points = 0;
  double draw_seconds = 0.0;
  std::string backend = "cpu_fallback";
};

// ----------------------------------------------------------------------------
// UnavRenderer — base class.
// ----------------------------------------------------------------------------

class UnavRenderer {
 public:
  UnavRenderer();
  virtual ~UnavRenderer() = default;

  UnavRenderer(const UnavRenderer&) = delete;
  UnavRenderer& operator=(const UnavRenderer&) = delete;

  // Bind an external GPU buffer. The renderer keeps a non-owning
  // reference; the plugin shell owns the lifetime so binding +
  // unbinding can happen across SceneHook reloads without
  // releasing the GPU handle.
  void setGpuBuffer(UnavGpuBuffer* buffer) noexcept { buffer_ = buffer; }
  UnavGpuBuffer* gpuBuffer() noexcept { return buffer_; }
  const UnavGpuBuffer* gpuBuffer() const noexcept { return buffer_; }

  // Configure the artist-facing knobs.
  void setConfig(const RenderConfig& cfg) { config_ = cfg; }
  const RenderConfig& config() const noexcept { return config_; }

  // Run a draw pass. Returns the FrameStats the dialog can show.
  // The base class walks the CPU shadow and counts what would be
  // drawn (the actual emit is a no-op in CI). SDK-aware
  // subclasses override `drawImpl` to issue the real
  // `BaseDraw::DrawArrayWithVertexBuffer` call.
  FrameStats draw();

  // Free any GPU-side state the renderer owns. Idempotent. Called
  // from the plugin's PluginEnd / scene-shutdown path.
  void shutdown();

 protected:
  virtual std::size_t drawImpl(const GpuVertex* vertices,
                               std::size_t count,
                               const RenderConfig& cfg);

  // Subclasses can record their backend name + shutdown work.
  void setBackendName(std::string name) { backend_ = std::move(name); }
  virtual void shutdownImpl() {}

 private:
  UnavGpuBuffer* buffer_ = nullptr;
  RenderConfig config_;
  std::string backend_ = "cpu_fallback";
  FrameStats lastFrame_;
};

// ----------------------------------------------------------------------------
// CPU-side shading reference. Pure functions; tested directly.
// ----------------------------------------------------------------------------

// Compute the per-vertex colour after shader-style configuration.
// Returns (r, g, b, a) in [0, 1]. `distance` is the world-space
// distance from the camera; `cfg.fade_distance == 0` disables
// the fade.
void shadeVertex(const GpuVertex& v, double distance,
                 const RenderConfig& cfg,
                 float* outR, float* outG, float* outB, float* outA);

// Compute the final point size for `v` after `cfg.point_size_scale`.
float effectivePointSize(const GpuVertex& v, const RenderConfig& cfg);

}  // namespace unav
