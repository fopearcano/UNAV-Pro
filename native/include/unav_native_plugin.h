// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native plugin entry-point declarations (v0.9 prototype).
//
// Pins the surface the v0.9 implementation exposes to:
//
//   - Cinema 4D (via the standard `PluginStart` / `PluginEnd` /
//     `PluginMessage` entry points wrapped by the Maxon SDK), and
//   - the Python plugin (via the file-based bridge documented in
//     `docs/BINARY_BRIDGE_WORKFLOW.md`).
//
// The Maxon SDK headers (`c4d.h` etc.) are only included when
// `UNAV_USE_MAXON_SDK` is defined; the build harness sets it
// automatically when CMake locates the SDK. Without the SDK, the
// types here remain valid C++17 declarations so the buffer module
// and the bridge logic compile and unit-test cleanly.

#pragma once

#include <cstdint>
#include <string>

#include "unav_point_buffer.h"

namespace unav {

// Placeholder ID type. Maxon's SDK uses `Int32` plus a stable
// per-plugin random ID assigned via the PluginCafe registration
// portal. v0.9 keeps placeholder IDs; v0.10 replaces them with
// PluginCafe-issued ones.
using PluginId = std::int32_t;

constexpr PluginId kPluginIdUnavStarfield     = 1000001;
constexpr PluginId kPluginIdUnavSceneHook     = 1000002;
constexpr PluginId kPluginIdUnavCommandEngine = 1000003;

// ----------------------------------------------------------------------------
// EngineStatus mirrors core.native_bridge.NativeStatus.
// ----------------------------------------------------------------------------

struct EngineStatus {
  bool engine_available;
  std::string engine_version;
  std::string description;
  // Last load mirror.
  std::string last_request_id;
  std::string binary_path;
  std::size_t point_count = 0;
  std::uint64_t file_size_bytes = 0;
  double load_seconds = 0.0;
  std::string error;
};

// ----------------------------------------------------------------------------
// Plugin lifecycle (Maxon SDK contract).
// ----------------------------------------------------------------------------

bool PluginStart();
void PluginEnd();
bool PluginMessage(int message, void* data);

// ----------------------------------------------------------------------------
// File-based bridge entry points.
// ----------------------------------------------------------------------------
//
// These are usable from a plain C++ host (the v0.9 unit tests
// exercise `LoadFromRequestFile` and `WriteStatusFile` directly
// without the SDK). Inside the Cinema 4D plugin they are
// invoked from `PluginMessage(MSG_UPDATE)` and from the
// "Reload Native Viewer" command.

// Read the JSON request file at `requestPath`, load the binary
// file it points at into `buffer`, and write the result to the
// status file at `statusPath`. Returns the number of points the
// buffer holds after the load (0 on parse error / cleared
// requests). All errors land in the status file's `error` field
// for Python to surface.
std::size_t LoadFromRequestFile(UnavPointBuffer& buffer,
                                const std::string& requestPath,
                                const std::string& statusPath);

// Write a status payload back to the bridge directory. Used by
// the load path above and by the plugin shutdown to record an
// "engine: gone" final state.
bool WriteStatusFile(const EngineStatus& status,
                     const std::string& statusPath);

// Write a selection (uid_hash + position) back to the bridge.
bool WriteSelectionFile(std::uint64_t uidHash,
                        std::size_t pointIndex,
                        double x, double y, double z,
                        std::uint32_t sourceId,
                        const std::string& selectionPath);

// Build the EngineStatus the v0.9 diagnostic command returns.
EngineStatus QueryEngineStatus();

}  // namespace unav
