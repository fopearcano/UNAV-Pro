# Maxon SDK Plugin Types for UNAV

Which Cinema 4D 2023+ C++ plugin types apply to UNAV Pro's needs,
which combinations the v0.9 native build will register, and which
ones we explicitly choose **not** to use. This document is the
research record from the v0.8 spike; v0.9 implements against it.

The Maxon SDK exposes plugin classes via subclasses of
`NodeData`-rooted base types. Each one has a different role in the
host's lifecycle. The categories below are the ones UNAV Pro
either uses or rejected.

For the architectural rationale behind UNAV Pro's design see
[`UNAV_PRO_ARCHITECTURE.md`](UNAV_PRO_ARCHITECTURE.md). For the
v0.7 layer above this work see
[`V0_7_PERFORMANCE_LAYER.md`](V0_7_PERFORMANCE_LAYER.md).

---

## 1. ObjectData — the visible-sector renderer

**Used by UNAV.** This is the central type for v0.9.

`ObjectData` plugins behave as scene objects: they have a
`BaseObject` representation in the Object Manager, they
participate in the document's hierarchy, they round-trip
through `.c4d` save/load, and — critical for our needs — they
expose a `Draw` callback that the editor viewport calls per
redraw to issue GL/Metal/DX commands.

UNAV Pro's plan:

* Register a single `ObjectData`-derived class
  `UnavStarfield` with a stable PluginID assigned via Maxon's
  PluginCafe.
* The object owns one `unav::UnavPointBuffer`
  (`native/include/unav_point_buffer.h`) carrying the packed
  point list from the v0.8 binary file.
* `Draw(BaseObject*, BaseDraw*, BaseDrawHelp*)` issues a
  single draw call (one `glDrawArrays(GL_POINTS, ...)` or the
  platform equivalent) per pass.
* `Read` / `Write` serialise the buffer's source path into
  the document — not the points themselves; the points come
  from the cached binary file by reference.

Why ObjectData and not just a `BaseDraw` extension hanging off
nothing: scenes are saved by the artist and reopened weeks
later. The buffer needs an entry in the Object Manager for the
artist to delete, hide, lock, parent under groups, and (with
the metadata sidecar) inspect.

---

## 2. SceneHookData — navigator-change observer

**Used by UNAV.** Optional but recommended for v0.10+.

`SceneHookData` plugins receive callbacks on every document
event the host emits — `MSG_DESCRIPTION_INITIALIZE`,
`MSG_UPDATE`, message that the active object changed, etc. They
do not have a scene representation themselves.

UNAV Pro's plan:

* Register an `UnavSceneHook` that watches:
  * `UNAV_Navigator` matrix changes — to trigger the live
    Auto Sync path that today is just a placeholder checkbox.
  * `UNAV_VisibleSector` parent removals — so the native
    buffer is freed when the user clears the scene.
* The hook has no GUI; it's a passive listener.
* SceneHook execution priority is configurable; UNAV registers
  at a low priority so it runs after user-facing hooks.

This is **not** in v0.9. v0.9 ships a passive read-only
`UnavStarfield`; the SceneHook arrives when Auto Sync becomes a
real feature in v0.10.

---

## 3. CommandData — diagnostic command

**Used by UNAV (small surface).**

`CommandData` plugins are the mechanism for menu items / scripts
the user invokes on demand. Maxon registers them in the user's
*Customize Commands* dialog and they can be bound to keyboard
shortcuts.

UNAV Pro's plan:

* Register one `CommandData` subclass `UnavEngineDiagnostic`
  whose only job is "print the active engine version into the
  Diagnostics dialog". This is the C++ side of the
  "engine: native v0.9.0" / "engine: python (fallback)"
  status line documented in
  [`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md) §6.
* The Python dialog calls into this command (or queries it via
  a Maxon `MAXON.PYTHON` bridge) to learn whether the native
  side is loaded.

The user does not invoke this command interactively — it's the
Python ↔ C++ status handshake. Wrapping it as `CommandData`
gives us a stable invocation point that survives across SDK
versions.

---

## 4. NodeData / GeListNode strategies

**Background only — not a separate registration.**

Every `ObjectData` and `SceneHookData` is itself a `NodeData`.
The base class supplies:

* `Init(GeListNode*)` — called once when the node enters the
  document. Allocates the `UnavPointBuffer`.
* `Free(GeListNode*)` — called once on removal. Releases the
  buffer.
* `Read(GeListNode*, HyperFile*, Int32 level)` /
  `Write(GeListNode*, HyperFile*)` — round-trip per-instance
  state through `.c4d` saves. UNAV stores the absolute path of
  the binary file plus the metadata sidecar; the buffer itself
  is never written into `.c4d` (see Phase F of the long
  roadmap).
* `Message(GeListNode*, Int32 type, void* data)` — receives
  generic messages. Used to flush the GPU buffer when the file
  on disk changes.
* `CopyTo(NodeData*, GeListNode*, GeListNode*, COPYFLAGS, AliasTrans*)` —
  duplicate-by-Ctrl+drag. UNAV's `CopyTo` shallow-copies the
  buffer (two `UnavStarfield` nodes can point at the same
  cached file safely).

The GeListNode base also provides the `BaseContainer` that the
v0.1+ marker contract uses. The native plugin writes the same
`BC_ID_UNAV_MARKER` payload the Python builders write today, so
the v0.6 metadata inspector / search panel / route planner all
keep working without code changes.

---

## 5. Custom viewport drawing

UNAV Pro wants single-draw-call rendering for big point clouds.
The Maxon SDK paths considered:

### 5.1 `BaseDraw::DrawPoint` family

**Rejected for the hot path.** `BaseDraw` exposes per-primitive
helpers (`DrawPoint`, `DrawLine`, `DrawPoly`) that issue one GL
call per primitive. Fine for the `UNAV_DebugCone` (a single
`Ocone`), useless for a 200 k-point cloud where a single
`glDrawArrays` is the whole point.

### 5.2 `BaseDraw::DrawArray` / `DrawSubObject`

**Used.** The SDK exposes a "draw an array of vertices in one
call" API the v0.9 implementation will hook into. The Maxon
docs call it the "low-level draw" path; it bypasses the
per-primitive helpers and lets a plugin push a packed vertex
buffer plus a single `MaterialMode` to the host renderer.

The exact symbol name varies by SDK version (R20 had
`SetMatrix_Matrix` / `DrawArray`; 2023 has the slightly
modernised `DrawArrayWithVertexBuffer` — Maxon's docs are the
source of truth for the call shape).

### 5.3 Raw GL/Metal/DX

**Open as a fallback.** The Maxon SDK lets a plugin escape into
a host-platform draw context inside its `Draw` callback. UNAV's
v0.10 GPU instancing / point sprite work uses this path on
each platform's native API. v0.9 deliberately does NOT escape —
it stays inside `BaseDraw::DrawArray` so the renderer is
single-source-of-truth across platforms.

Notes:

* The host's GL/Metal/DX context belongs to the editor; a plugin
  must not retain GPU buffers across `Draw` calls without
  registering for the SDK's own buffer-lifetime callbacks.
* Selection-pick uses the SDK's
  `BaseDraw::PickObject` family; UNAV's spike notes the API
  exists but defers the implementation.

See
[`NATIVE_VIEWPORT_DRAWING_RESEARCH.md`](NATIVE_VIEWPORT_DRAWING_RESEARCH.md)
for the deeper drawing-API study.

---

## 6. Plugin types we explicitly do not use

* **TagData.** Tags hang off existing `BaseObject`s. UNAV's
  scene model is "one starfield, many points"; tagging
  individual points is a regression to the per-row
  `BaseObject` model the native plugin is designed to
  eliminate.
* **MaterialData.** UNAV doesn't ship a custom material. The
  point colours are baked into the buffer.
* **Generators (`OBJECT_GENERATOR`).** A generator's
  `GetVirtualObjects` returns a hierarchy. Useful for
  procedural geometry; useless for "the buffer is its own
  geometry".
* **Modifiers (`OBJECT_MODIFIER`).** Modifiers transform
  upstream geometry. UNAV doesn't have upstream geometry.
* **Tool plugins.** Custom viewport tools are out of scope;
  the navigator + dialog provide the interaction surface.
* **Importers / Exporters.** UNAV has its own JSONL / CSV
  pipeline; rolling a `SceneSaverData` for `.c4d` is
  unnecessary.

---

## 7. SDK version constraints

* **Cinema 4D 2023+** is the support floor (matches the Python
  prototype's
  [`INSTALL_C4D_2023_PLUS.md`](INSTALL_C4D_2023_PLUS.md)).
* The v0.9 build will target the most recent SDK that supports
  C4D 2023, 2024, and 2025 simultaneously. Maxon publishes the
  matrix per SDK release.
* C++17 minimum; the skeleton in `native/CMakeLists.txt` pins
  this.
* The Maxon "PluginCafe" portal issues stable PluginIDs;
  v0.9 replaces the placeholder IDs in
  `native/include/unav_native_plugin.h` with portal-issued
  ones.

---

## 8. Threading

The Maxon SDK is broadly single-threaded for `Draw` callbacks
(the editor viewport calls them on the main thread) but
multi-threaded for `BakeAsAlembic`-style export passes. UNAV's
v0.9 plan:

* All buffer mutations run on the main thread inside the
  `ObjectData::Message(MSG_UPDATE)` callback.
* Buffer reads (the `Draw` callback) are read-only and
  threadsafe by construction.
* The optional GPU compute path (v0.10+) uses Maxon's
  `MaxonThreadJob` API for offload; it never owns the host's
  GPU context.

---

## 9. Memory ownership

* The `UnavPointBuffer` owns its CPU-side `std::vector<UnavPoint>`.
  It's part of the `ObjectData` instance and lives for the
  lifetime of the scene node.
* The GPU-side buffer (v0.10+) is owned by the same
  `UnavPointBuffer`; on destruction the buffer issues a
  `glDeleteBuffers` (or platform equivalent) inside the host's
  draw context.
* The metadata sidecar stays a Python-owned file on disk; both
  Python and C++ open it read-only.

---

## 10. Summary registration matrix

| v0.9 ships                    | v0.10 adds                  | v0.11+ adds                |
|-------------------------------|------------------------------|-----------------------------|
| `ObjectData(UnavStarfield)`   | `SceneHookData(UnavSceneHook)` | renderer integrations (Phase G of the long roadmap) |
| `CommandData(UnavEngineDiagnostic)` | depth-buffer pick path | GPU compute filter + Auto Sync |

The skeleton header in
`native/include/unav_native_plugin.h` declares all three plugin
IDs today (`kPluginIdUnavStarfield`, `kPluginIdUnavSceneHook`,
`kPluginIdUnavCommandEngine`) so v0.9, v0.10, and v0.11+ can
land without renumbering anything.
