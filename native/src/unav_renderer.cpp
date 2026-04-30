// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native renderer (v1.0) — base implementation.
//
// CPU-side shader reference + base draw loop. The base draw walks
// the GPU buffer's CPU shadow and counts what *would* be emitted.
// The SDK-aware subclass in `unav_native_plugin.cpp` overrides
// `drawImpl(...)` to push the real `BaseDraw` calls.

#include "unav_renderer.h"

#include <algorithm>
#include <chrono>
#include <cmath>

namespace unav {

namespace {

float clamp01(float v) {
  if (v < 0.0f) return 0.0f;
  if (v > 1.0f) return 1.0f;
  return v;
}

}  // namespace

UnavRenderer::UnavRenderer() = default;

float effectivePointSize(const GpuVertex& v, const RenderConfig& cfg) {
  return v.size * std::max(0.0f, cfg.point_size_scale);
}

void shadeVertex(const GpuVertex& v, double distance,
                 const RenderConfig& cfg,
                 float* outR, float* outG, float* outB, float* outA) {
  float r = v.r * cfg.brightness_scale;
  float g = v.g * cfg.brightness_scale;
  float b = v.b * cfg.brightness_scale;
  if (cfg.debug_draw) {
    // Recolour by source_id for QA: low bits → primary tints.
    const std::uint32_t s = v.source_id;
    r = ((s >> 0) & 0x3) / 3.0f;
    g = ((s >> 2) & 0x3) / 3.0f;
    b = ((s >> 4) & 0x3) / 3.0f;
  }
  float a = 1.0f;
  if (cfg.fade_distance > 0.0f) {
    const double d = distance / static_cast<double>(cfg.fade_distance);
    a = static_cast<float>(1.0 / (1.0 + d));
  }
  if (outR) *outR = clamp01(r);
  if (outG) *outG = clamp01(g);
  if (outB) *outB = clamp01(b);
  if (outA) *outA = clamp01(a);
}

FrameStats UnavRenderer::draw() {
  FrameStats stats{};
  stats.backend = backend_;
  if (buffer_ == nullptr || buffer_->empty()) {
    return stats;
  }
  const auto t0 = std::chrono::steady_clock::now();
  const std::size_t n = drawImpl(
      buffer_->vertices(), buffer_->vertexCount(), config_);
  const auto t1 = std::chrono::steady_clock::now();
  stats.drawn_points = n;
  stats.culled_points = buffer_->vertexCount() - n;
  stats.draw_seconds = std::chrono::duration<double>(t1 - t0).count();
  lastFrame_ = stats;
  return stats;
}

std::size_t UnavRenderer::drawImpl(
    const GpuVertex* vertices, std::size_t count,
    const RenderConfig& cfg) {
  // Base class: walk every vertex, run the shader-side config so
  // tests can verify the math, but emit nothing. The SDK-bound
  // subclass overrides this and issues the actual draw call.
  if (vertices == nullptr) return 0;
  std::size_t drawn = 0;
  for (std::size_t i = 0; i < count; ++i) {
    const auto& v = vertices[i];
    const double dx = v.x - cfg.camera_origin[0];
    const double dy = v.y - cfg.camera_origin[1];
    const double dz = v.z - cfg.camera_origin[2];
    const double distance = std::sqrt(dx * dx + dy * dy + dz * dz);
    float r, g, b, a;
    shadeVertex(v, distance, cfg, &r, &g, &b, &a);
    if (a <= 0.0f) continue;  // Fully faded → cull.
    (void)effectivePointSize(v, cfg);  // exercise the helper
    ++drawn;
  }
  return drawn;
}

void UnavRenderer::shutdown() {
  shutdownImpl();
  if (buffer_ != nullptr) {
    buffer_->clear();
  }
}

}  // namespace unav
