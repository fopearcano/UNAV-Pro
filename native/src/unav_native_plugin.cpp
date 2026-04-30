// SPDX-License-Identifier: MIT
//
// UNAV Pro — Native plugin entry-point stubs (v0.8 spike).
//
// Every function here is a placeholder the v0.9 build harness
// turns into a real Cinema 4D plugin entry point. Today these
// stubs make the C++ surface declared in `unav_native_plugin.h`
// compile against any C++17 toolchain without dragging in the
// Maxon SDK.
//
// When v0.9 lands, this file will:
//
//   1. Include `c4d.h` and the SDK helpers we need.
//   2. Register an `ObjectData`-derived class for the
//      `UnavStarfield` scene object that wraps an
//      `UnavPointBuffer` and draws it via `BaseDraw`.
//   3. Register a `SceneHookData`-derived class that monitors
//      the `UNAV_VisibleSector` parent so navigator changes can
//      trigger a re-bind of the buffer.
//   4. Register a `CommandData`-derived class for the
//      "Engine: native available" diagnostic the Python
//      Diagnostics dialog reads.
//
// See `docs/MAXON_SDK_PLUGIN_TYPES_FOR_UNAV.md` for the rationale
// behind each plugin type.

#include "unav_native_plugin.h"

#include <iostream>

namespace unav {

bool PluginStart() {
  // v0.8: nothing to register; the plugin does not load yet. v0.9
  // wires up the ObjectData / SceneHookData / CommandData classes.
  std::cerr << "[unav-native] v0.8 placeholder: PluginStart called; "
               "no registrations performed.\n";
  return false;
}

void PluginEnd() {
  // v0.8: no resources to release. v0.9 tears down the GPU
  // buffers, unregisters scene hooks, drops the command class.
}

bool PluginMessage(int /*message*/, void* /*data*/) {
  // v0.8: ignore every message. v0.9 handles
  // C4DPL_INIT_SYS, C4DPL_DEVICECHANGE, MSG_DOCUMENTINFO etc.
  return false;
}

EngineStatus QueryEngineStatus() {
  // v0.8: report unavailable. v0.9 fills in the real version
  // string and (where applicable) the active GPU backend.
  return EngineStatus{
      /*available=*/false,
      /*version=*/"0.8.0-spike",
      /*description=*/
      "UNAV native engine is a v0.8 feasibility skeleton; the "
      "production renderer ships in v0.9. The Python prototype "
      "is the active engine until then.",
  };
}

}  // namespace unav
