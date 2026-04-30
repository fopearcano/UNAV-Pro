// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native plugin entry-point declarations (v0.8 spike).
//
// This header pins the symbols Maxon's plugin loader will call when
// the v0.9 build harness ships. v0.8 keeps every function as a
// declaration with a stub body in `unav_native_plugin.cpp` so the
// rest of the project can compile against the surface.
//
// The actual Maxon SDK types (`PluginMessage`, `BaseSceneHook`,
// `BaseObject`, …) are NOT included here so this header stays
// build-tool-agnostic in v0.8. v0.9 swaps the placeholder typedefs
// below for real `#include "c4d.h"` and friends.

#pragma once

#include <cstdint>
#include <string>

namespace unav {

// Placeholder ID type. Maxon's SDK uses `Int32` plus a stable
// per-plugin random ID assigned via the PluginCafe registration
// portal; v0.9 replaces this typedef.
using PluginId = std::int32_t;

// Stable plugin IDs are *registered* with Maxon, never invented.
// The constants below are placeholders the v0.9 implementer will
// replace with PluginCafe-issued IDs.
constexpr PluginId kPluginIdUnavStarfield     = 1000001;
constexpr PluginId kPluginIdUnavSceneHook     = 1000002;
constexpr PluginId kPluginIdUnavCommandEngine = 1000003;

// ----------------------------------------------------------------------------
// Plugin lifecycle (Maxon SDK contract).
// ----------------------------------------------------------------------------
//
// Maxon hosts call these symbols when loading / unloading a
// plugin. v0.8: stubs that log "not implemented" and return false
// so the host bails out cleanly without registering anything.

bool PluginStart();
void PluginEnd();
bool PluginMessage(int message, void* data);

// ----------------------------------------------------------------------------
// Engine availability (mirrored on the Python side).
// ----------------------------------------------------------------------------
//
// The Python diagnostics dialog asks the native side "are you
// alive?" via a small extern "C" entry point that the eventual
// pybind11 / extension module will expose. v0.8 declares the
// shape here; the actual export comes in v0.9.

struct EngineStatus {
  bool available;          // true iff the native renderer is loaded
  std::string version;     // human-readable version, e.g. "0.9.0"
  std::string description; // free-form (e.g. "GPU draw active")
};

EngineStatus QueryEngineStatus();

}  // namespace unav
