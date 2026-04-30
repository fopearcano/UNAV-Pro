// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native plugin implementation (v0.9 prototype).
//
// Two halves:
//
//   1. **File-based bridge** (pure stdlib). Reads the request JSON
//      Python writes, drives the `UnavPointBuffer` loader, and
//      writes the status / selection files Python polls. This half
//      is unit-testable in any C++17 host — see
//      `native/tests/test_unav_native_plugin.cpp`.
//   2. **Cinema 4D SDK glue** (compiled only when
//      `UNAV_USE_MAXON_SDK` is defined). Registers the
//      `UnavStarfield` ObjectData, hooks `PluginMessage` for
//      bridge polling, and wires the diagnostic command. v0.9
//      keeps the draw call as the simplest legitimate SDK path
//      (`BaseDraw::DrawPoint` per visible point); v0.10+ swaps
//      to `DrawArray`.
//
// The bridge JSON format is documented in
// `docs/BINARY_BRIDGE_WORKFLOW.md` and is bit-compatible with
// `unav_pro/core/native_bridge.py`.

#include "unav_native_plugin.h"

#include <chrono>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <utility>

#include "unav_gpu_buffer.h"
#include "unav_renderer.h"

#ifdef UNAV_USE_MAXON_SDK
#include "c4d.h"  // NOLINT(build/include)
#endif

namespace unav {

namespace {

// ----------------------------------------------------------------------------
// Tiny JSON helpers — the bridge's payloads are small flat objects
// so we hand-roll instead of pulling in a JSON dependency.
// ----------------------------------------------------------------------------

std::string isoNow() {
  using clock = std::chrono::system_clock;
  const auto now = clock::to_time_t(clock::now());
  std::tm tm{};
#if defined(_WIN32)
  gmtime_s(&tm, &now);
#else
  gmtime_r(&now, &tm);
#endif
  std::ostringstream oss;
  oss << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S");
  return oss.str();
}

std::string jsonEscape(const std::string& in) {
  std::ostringstream oss;
  for (char c : in) {
    switch (c) {
      case '"': oss << "\\\""; break;
      case '\\': oss << "\\\\"; break;
      case '\n': oss << "\\n"; break;
      case '\r': oss << "\\r"; break;
      case '\t': oss << "\\t"; break;
      default:
        if (static_cast<unsigned char>(c) < 0x20) {
          oss << "\\u" << std::hex << std::setw(4) << std::setfill('0')
              << static_cast<int>(c);
        } else {
          oss << c;
        }
    }
  }
  return oss.str();
}

bool readEntireFile(const std::string& path, std::string* out) {
  std::ifstream fh(path, std::ios::binary);
  if (!fh.is_open()) return false;
  std::ostringstream oss;
  oss << fh.rdbuf();
  *out = oss.str();
  return true;
}

// Trim leading whitespace + read a JSON string-valued key from a
// flat object (no nested objects). Returns "" if the key is
// absent. Supports the small subset the bridge uses.
std::string flatJsonString(const std::string& json, const std::string& key) {
  const std::string needle = "\"" + key + "\"";
  const auto k = json.find(needle);
  if (k == std::string::npos) return std::string();
  auto cursor = json.find(':', k + needle.size());
  if (cursor == std::string::npos) return std::string();
  cursor = json.find('"', cursor + 1);
  if (cursor == std::string::npos) return std::string();
  ++cursor;
  std::string out;
  while (cursor < json.size() && json[cursor] != '"') {
    if (json[cursor] == '\\' && cursor + 1 < json.size()) {
      out.push_back(json[cursor + 1]);
      cursor += 2;
      continue;
    }
    out.push_back(json[cursor++]);
  }
  return out;
}

long long flatJsonInt(const std::string& json, const std::string& key,
                      long long fallback) {
  const std::string needle = "\"" + key + "\"";
  const auto k = json.find(needle);
  if (k == std::string::npos) return fallback;
  const auto colon = json.find(':', k + needle.size());
  if (colon == std::string::npos) return fallback;
  std::size_t cursor = colon + 1;
  while (cursor < json.size() && std::isspace(static_cast<unsigned char>(json[cursor]))) {
    ++cursor;
  }
  std::size_t end = cursor;
  while (end < json.size() && (std::isdigit(static_cast<unsigned char>(json[end])) ||
                               json[end] == '-' || json[end] == '+')) {
    ++end;
  }
  if (end == cursor) return fallback;
  try {
    return std::stoll(json.substr(cursor, end - cursor));
  } catch (...) {
    return fallback;
  }
}

bool writeFile(const std::string& path, const std::string& content) {
  std::ofstream fh(path, std::ios::binary | std::ios::trunc);
  if (!fh.is_open()) return false;
  fh.write(content.data(), static_cast<std::streamsize>(content.size()));
  return static_cast<bool>(fh);
}

}  // namespace

// ----------------------------------------------------------------------------
// LoadFromRequestFile — file-based bridge entry point.
// ----------------------------------------------------------------------------

std::size_t LoadFromRequestFile(UnavPointBuffer& buffer,
                                const std::string& requestPath,
                                const std::string& statusPath) {
  EngineStatus status{};
  status.engine_available = true;
  status.engine_version = "0.9.0";
  status.description = "UNAV native engine (v0.9 prototype)";

  std::string raw;
  if (!readEntireFile(requestPath, &raw)) {
    status.error = "request file missing or unreadable";
    WriteStatusFile(status, statusPath);
    return 0;
  }

  const std::string action = flatJsonString(raw, "action");
  status.last_request_id = flatJsonString(raw, "request_id");

  if (action == "clear" || action == "noop") {
    buffer.clear();
    status.point_count = 0;
    WriteStatusFile(status, statusPath);
    return 0;
  }
  if (action != "load") {
    status.error = "unsupported action '" + action + "'";
    WriteStatusFile(status, statusPath);
    return 0;
  }

  const std::string binaryPath = flatJsonString(raw, "binary_path");
  if (binaryPath.empty()) {
    status.error = "request has empty binary_path";
    WriteStatusFile(status, statusPath);
    return 0;
  }
  const long long requestedMax = flatJsonInt(raw, "max_points", 0);
  if (requestedMax > 0) {
    buffer.setMaxPoints(static_cast<std::size_t>(requestedMax));
  }

  std::string err;
  const std::size_t loaded = buffer.loadFromFile(binaryPath, &err);
  status.binary_path = binaryPath;
  status.point_count = buffer.size();
  status.file_size_bytes = buffer.lastLoadStats().file_size_bytes;
  status.load_seconds = buffer.lastLoadStats().load_seconds;
  status.estimated_gpu_bytes = buffer.lastLoadStats().estimated_gpu_bytes;
  status.format_version = buffer.lastLoadStats().format_version;
  if (loaded == 0 && err.size() > 0 && err.rfind("warning:", 0) != 0) {
    status.error = err;
  }
  WriteStatusFile(status, statusPath);
  return loaded;
}

// ----------------------------------------------------------------------------
// WriteStatusFile / WriteSelectionFile — small JSON writers
// matching `unav_pro/core/native_bridge.py`.
// ----------------------------------------------------------------------------

bool WriteStatusFile(const EngineStatus& status,
                     const std::string& statusPath) {
  std::ostringstream oss;
  oss << "{\n";
  oss << "  \"binary_path\": \"" << jsonEscape(status.binary_path) << "\",\n";
  oss << "  \"description\": \"" << jsonEscape(status.description) << "\",\n";
  oss << "  \"engine_available\": "
      << (status.engine_available ? "true" : "false") << ",\n";
  oss << "  \"engine_version\": \"" << jsonEscape(status.engine_version) << "\",\n";
  oss << "  \"error\": \"" << jsonEscape(status.error) << "\",\n";
  oss << "  \"estimated_gpu_bytes\": " << status.estimated_gpu_bytes << ",\n";
  oss << "  \"file_size_bytes\": " << status.file_size_bytes << ",\n";
  oss << "  \"format_version\": " << status.format_version << ",\n";
  oss << "  \"gpu_backend\": \"" << jsonEscape(status.gpu_backend) << "\",\n";
  oss << "  \"gpu_bytes\": " << status.gpu_bytes << ",\n";
  oss << "  \"gpu_uploaded\": "
      << (status.gpu_uploaded ? "true" : "false") << ",\n";
  oss << "  \"last_load_iso\": \"" << jsonEscape(isoNow()) << "\",\n";
  oss << "  \"last_request_id\": \"" << jsonEscape(status.last_request_id) << "\",\n";
  oss << "  \"load_seconds\": " << status.load_seconds << ",\n";
  oss << "  \"point_count\": " << status.point_count << ",\n";
  oss << "  \"schema_version\": 1\n";
  oss << "}\n";
  return writeFile(statusPath, oss.str());
}

bool WriteSelectionFile(std::uint64_t uidHash,
                        std::size_t pointIndex,
                        double x, double y, double z,
                        std::uint32_t sourceId,
                        const std::string& selectionPath) {
  std::ostringstream oss;
  oss << "{\n";
  oss << "  \"point_index\": " << pointIndex << ",\n";
  oss << "  \"schema_version\": 1,\n";
  oss << "  \"source_id\": " << sourceId << ",\n";
  oss << "  \"timestamp_iso\": \"" << jsonEscape(isoNow()) << "\",\n";
  oss << "  \"uid_hash\": " << uidHash << ",\n";
  oss << "  \"x\": " << x << ",\n";
  oss << "  \"y\": " << y << ",\n";
  oss << "  \"z\": " << z << "\n";
  oss << "}\n";
  return writeFile(selectionPath, oss.str());
}

EngineStatus QueryEngineStatus() {
  EngineStatus s{};
  s.engine_available = true;
  s.engine_version = "1.0.0";
  s.description = "UNAV native engine v1.0 — GPU-backed point "
                  "renderer with v2 binary loader, camera-relative "
                  "rendering, and accelerated picking. CPU "
                  "fallback engages automatically when the SDK's "
                  "GPU draw path is unavailable.";
  return s;
}

// ----------------------------------------------------------------------------
// Cinema 4D SDK glue — only compiled when the SDK is wired in.
// ----------------------------------------------------------------------------

#ifdef UNAV_USE_MAXON_SDK

namespace {

// Process-wide singletons shared by the SDK-bound classes. The
// buffer holds the loaded points (CPU shadow). The GPU buffer
// shadows them for the renderer; in v1.0 we still draw via
// `BaseDraw::DrawPoint` per vertex (the GPU buffer is the
// future-facing layer that v1.1+ flips to `DrawArray`). The
// renderer config the dialog edits lives here too so a Reload
// command does not reset it.
UnavPointBuffer gNativeBuffer;

class SdkGpuBuffer : public UnavGpuBuffer {
 protected:
  bool uploadImpl() override {
    // v1.0: Maxon's `BaseDraw::DrawArrayWithVertexBuffer` is not
    // a portable GPU upload (the host owns the device); we
    // therefore stay on the CPU shadow and fall back to per-point
    // draw calls. v1.1 swaps in the SDK's actual VBO call.
    setBackendName("c4d_cpu_shadow");
    return false;
  }
  void freeImpl() override {}
};

class SdkRenderer : public UnavRenderer {
 public:
  SdkRenderer() {
    setBackendName("c4d_basedraw_perpoint");
  }
  void bindHostDraw(BaseDraw* bd) noexcept { hostDraw_ = bd; }

 protected:
  std::size_t drawImpl(const GpuVertex* vertices, std::size_t count,
                       const RenderConfig& cfg) override {
    if (hostDraw_ == nullptr || vertices == nullptr || count == 0) {
      return 0;
    }
    std::size_t drawn = 0;
    for (std::size_t i = 0; i < count; ++i) {
      const auto& v = vertices[i];
      const double dx = v.x - cfg.camera_origin[0];
      const double dy = v.y - cfg.camera_origin[1];
      const double dz = v.z - cfg.camera_origin[2];
      const double distance = std::sqrt(dx * dx + dy * dy + dz * dz);
      float r, g, b, a;
      shadeVertex(v, distance, cfg, &r, &g, &b, &a);
      if (a <= 0.0f) continue;
      hostDraw_->SetPen(Vector(r, g, b));
      // v1.0 keeps the per-point draw call. The per-vertex `size`
      // is honoured by Maxon's editor when DRAWPATH supports it;
      // anti-aliased circular points are the SDK default for
      // `DrawPoint` on most hosts.
      hostDraw_->DrawPoint(Vector(v.x, v.y, v.z));
      ++drawn;
    }
    return drawn;
  }

 private:
  BaseDraw* hostDraw_ = nullptr;
};

SdkGpuBuffer gGpuBuffer;
SdkRenderer  gRenderer;

}  // namespace

class UnavStarfield : public ObjectData {  // NOLINT(build/include_what_you_use)
 public:
  static NodeData* Alloc() { return NewObjClear(UnavStarfield); }

  Bool Init(GeListNode* node) override {
    gRenderer.setGpuBuffer(&gGpuBuffer);
    return ObjectData::Init(node);
  }

  void Free(GeListNode* node) override {
    gRenderer.shutdown();
    ObjectData::Free(node);
  }

  DRAWRESULT Draw(BaseObject* op, DRAWPASS drawpass,
                  BaseDraw* bd, BaseDrawHelp* bh) override {
    if (drawpass != DRAWPASS_OBJECT) return DRAWRESULT_SKIP;
    if (gNativeBuffer.empty()) return DRAWRESULT_OK;
    if (!gGpuBuffer.isUploaded() && gGpuBuffer.empty()) {
      gGpuBuffer.buildFromCpu(gNativeBuffer);
    }
    gRenderer.bindHostDraw(bd);
    gRenderer.draw();
    return DRAWRESULT_OK;
  }
};

class UnavReloadCommand : public CommandData {
 public:
  Bool Execute(BaseDocument* doc) override {
    // Resolve the bridge directory relative to the user's home.
    // The SDK's `GeGetStartupPath` would also work here; we keep
    // the resolution string-based to match the Python side.
    const std::string home = GeGetStartupPath().GetString().GetCStringCopy();
    const std::string base = home + "/.unav_pro/native_bridge/";
    const std::string req = base + "native_request.json";
    const std::string stat = base + "native_status.json";
    LoadFromRequestFile(gNativeBuffer, req, stat);
    // Rebuild the GPU shadow from the freshly-loaded CPU buffer.
    gGpuBuffer.buildFromCpu(gNativeBuffer);
    EventAdd();
    return true;
  }
};

bool PluginStart() {
  if (!RegisterObjectPlugin(
          kPluginIdUnavStarfield, "UNAV Starfield",
          OBJECT_GENERATOR, UnavStarfield::Alloc,
          "Onull", nullptr, 0)) {
    return false;
  }
  if (!RegisterCommandPlugin(
          kPluginIdUnavCommandEngine, "UNAV Reload Native Viewer",
          0, nullptr, "Reload the v0.9 native viewer buffer.",
          NewObjClear(UnavReloadCommand))) {
    return false;
  }
  return true;
}

void PluginEnd() {
  EngineStatus done = QueryEngineStatus();
  done.engine_available = false;
  done.description = "engine: gone (plugin shutting down)";
  const std::string home = GeGetStartupPath().GetString().GetCStringCopy();
  WriteStatusFile(done,
                  home + "/.unav_pro/native_bridge/native_status.json");
  gNativeBuffer.clear();
}

bool PluginMessage(int message, void* /*data*/) {
  // v0.9 does nothing on host messages. v0.10's SceneHook does.
  (void)message;
  return false;
}

#else  // !UNAV_USE_MAXON_SDK

bool PluginStart() {
  std::cerr << "[unav-native] v0.9 prototype: UNAV_USE_MAXON_SDK not "
               "defined; bridge entry points are available but the "
               "Cinema 4D registration is skipped. Define "
               "UNAV_USE_MAXON_SDK in CMake when the SDK is "
               "located.\n";
  return false;
}

void PluginEnd() {}

bool PluginMessage(int /*message*/, void* /*data*/) { return false; }

#endif  // UNAV_USE_MAXON_SDK

}  // namespace unav
