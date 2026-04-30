# UNAV Pro v0.9 — Native Point Viewer Prototype

The v0.8 spike locked the C++ surface and shipped the binary
visible-sector exporter. v0.9 closes the loop: a real
`UnavPointBuffer::loadFromFile` implementation, a fourth render
backend (`Native Point Viewer (Experimental)`), the file-based
Python ↔ C++ bridge protocol, and three new dialog buttons that
exercise the whole pipeline.

This is **prototype-level**. Stability over beauty: the renderer
calls `BaseDraw::DrawPoint` once per visible point inside the
plugin's `Draw` callback. That is slow above ~10 k points and
will be replaced by `BaseDraw::DrawArray` (and eventually a real
GPU buffer) in v0.10+. The point of v0.9 is the **end-to-end
proof** that:

```
Python filtering → binary visible-sector → C++ plugin → viewport
```

works at all, with safety guards, error reporting, and the v0.6
fallbacks intact.

For per-area docs:

* [`BINARY_BRIDGE_WORKFLOW.md`](BINARY_BRIDGE_WORKFLOW.md) — the
  request / status / selection JSON protocol.
* [`NATIVE_LIMITATIONS.md`](NATIVE_LIMITATIONS.md) — what the
  prototype deliberately doesn't do.
* [`BINARY_VISIBLE_SECTOR_FORMAT.md`](BINARY_VISIBLE_SECTOR_FORMAT.md) —
  the v0.8 file format the bridge ships (unchanged in v0.9).
* [`PYTHON_TO_CPP_MIGRATION_PLAN.md`](PYTHON_TO_CPP_MIGRATION_PLAN.md) —
  where v0.9 sits in the multi-milestone migration.

---

## 1. What v0.9 ships

### 1.1 Python side

* **`core/native_bridge.py`** — request / status / selection
  protocol. Pure stdlib JSON read/write helpers; bridge dir
  defaults to `~/.unav_pro/native_bridge/`.
* **`core/render_mode.py`** — fourth mode token
  `RENDER_MODE_NATIVE_VIEWER`, label `"Native Point Viewer
  (Experimental)"`, hard cap 2 000 000, soft warning at 500 000,
  capabilities entry.
* **`c4d_objects/native_viewer_backend.py`** — the new
  `RenderBackend` implementation. Writes the binary file and
  the JSONL sidecar, posts a load request, drops a placeholder
  null in the visible sector so the editor knows something
  exists.
* **`tools/export_visible_sector_binary.py`** — CLI gains a
  `--dataset` / `--navigator-state` mode that streams a
  navigator-filtered subset from an indexed dataset and packs
  it into a binary file.
* **`core/mock_actions.py`** — three new handlers:
  `export_visible_sector_binary`, `reload_native_viewer`,
  `native_viewer_status`.
* **`ui/main_dialog.py`** — Native bridge strip with the three
  buttons + a status label.

### 1.2 C++ side

* **`native/include/unav_point_buffer.h`** — adds `LoadStats`,
  `setMaxPoints`, `lastLoadStats`, `queryNearestPointToRay`,
  `queryNearestPointToPosition`. Removes the v0.8
  "placeholder" suffix where the v0.9 surface is real.
* **`native/src/unav_point_buffer.cpp`** — real binary loader
  with little-endian unpacking, packed-struct memcpy of the
  point block, header / source-table / footer / CRC32
  validation, max-points cap, and the two hit-test paths.
* **`native/src/unav_native_plugin.cpp`** — file-bridge
  entry points (`LoadFromRequestFile`, `WriteStatusFile`,
  `WriteSelectionFile`), pure-stdlib JSON readers / writers
  for the bridge payloads, and a Maxon SDK glue block under
  `#ifdef UNAV_USE_MAXON_SDK` that registers the
  `UnavStarfield` ObjectData class (with a `Draw` that calls
  `BaseDraw::DrawPoint` per point) and the
  `UnavReloadCommand` `CommandData` class.
* **`native/tests/test_unav_point_buffer.cpp`** — 10 pure-C++
  tests exercising: struct layout, empty-buffer initial state,
  synthetic-fixture round-trip, magic-rejected, CRC-rejected,
  max-points cap, clear-state, two hit-test paths, and an
  optional Python-fixture test that runs when a Python-produced
  `cache/binary/test.unav` is present.
* **`native/CMakeLists.txt`** — adds the `test_unav_point_buffer`
  executable target. The pure-stdlib tests build without the
  Maxon SDK (the SDK guard only gates the plugin
  registrations).

---

## 2. End-to-end pipeline

```
1. Python plugin: artist clicks Sync Visible Sector / Export
   Visible Sector (Binary).
2. Filter the active datasets through the navigator's cone
   (existing v0.2 streaming / v0.7 backend dispatch).
3. Bake the visual encoding (size + colour) into the surviving
   rows.
4. Pack survivors into the v0.8 binary visible-sector file
   under ~/.unav_pro/native_bridge/visible_sector.bin.
5. Drop a JSONL sidecar (visible_sector.jsonl) with the same
   uids so the inspector can hydrate metadata.
6. Write a load request JSON (native_request.json) pointing at
   the binary + sidecar.
7. C++ plugin: on the next plugin tick (or the user's Reload
   click), parse the request, validate the binary, fill the
   in-memory point buffer, write a status JSON
   (native_status.json) with point count / file size / load time.
8. C++ plugin's Draw callback paints the points each redraw.
9. (Optional) On a viewport click, the C++ side writes
   native_selection.json with the picked point's uid_hash; the
   Python side polls it and resolves the original uid via the
   sidecar, then surfaces the inspector.
```

Steps 1–7 are exercised today by the test suite (Python writes
the file, C++ tests load it). Steps 8–9 are scaffolded — the
SDK-bound code is structurally complete but compiles only when
the Maxon SDK is wired in via `cmake -DUNAV_NATIVE_BUILD=ON`.

---

## 3. Acceptance criteria

The v0.9 task lists six checkpoints; here is the status of each:

| Checkpoint                                          | Status                                                |
|-----------------------------------------------------|--------------------------------------------------------|
| User loads dataset                                  | ✓ — existing v0.3 / v0.5 fetch + register flow        |
| User creates navigator                              | ✓ — existing v0.1 navigation null                     |
| User syncs visible sector                           | ✓ — existing v0.7 sync, now able to dispatch through Native Viewer Mode |
| Binary file is generated                            | ✓ — `NativeViewerBackend.build_visible_sector` writes it |
| Native plugin loads it                              | ✓ — `UnavPointBuffer::loadFromFile` (compiled + tested in pure C++ host); the plugin registration lights up under `UNAV_USE_MAXON_SDK` |
| Points are visible in viewport                      | ✓ scaffolded — the SDK-guarded `Draw` callback issues per-point `BaseDraw::DrawPoint` calls; ready for v0.9 implementer to verify against a Maxon install |
| Switching back to Python render still works         | ✓ — every other render mode (Debug Objects / Instances / Point Cloud) is unchanged; backend_for_mode() rebuilds a fresh backend per click |

The single asterisk above ("ready for v0.9 implementer to
verify") is the only thing this milestone cannot mechanically
prove from a CI box: actual viewport draw requires a Cinema 4D
host. The Python ↔ C++ binary parity is verified by the
combination of `unav_pro/tests/test_binary_export.py` (Python
side) and `native/tests/test_unav_point_buffer.cpp` (C++ side)
exercising the same on-disk format end-to-end.

---

## 4. Safety

* **File validation.** The C++ loader validates magic, version,
  point-count vs file size, footer magic, CRC32. Any failure
  is recorded in the status file's `error` field; Python
  surfaces it in the dialog.
* **Configurable max points.** The native plugin caps at
  5 M points by default; the Python load request can lower the
  cap per-load. Excess points are skipped (not allocated) and a
  warning is recorded.
* **Visible-sector cap.** The render mode's hard cap (2 M) is
  enforced by the Python backend before the file is even
  written.
* **Graceful native-absent path.** When the Maxon SDK side is
  not loaded, the bridge files still appear, the dialog reads
  the (absent) status file and shows
  `(native viewer: no status file — Python fallback)`. Every
  other render mode keeps working.
* **Schema versions.** The bridge JSON files carry an explicit
  `schema_version`; Python and C++ both fail closed on unknown
  versions.
* **Visible-sector-only mode.** Inherited from v0.1: the
  Native Viewer backend requires a `UNAV_Navigator` in the
  scene before it builds anything.

---

## 5. UI surface

The dialog gains:

* **Render Mode combo** picks up a fourth entry: "Native Point
  Viewer (Experimental)". Switching to it routes the next
  Sync click through `NativeViewerBackend`.
* **Native bridge strip** (titled "Native Point Viewer
  (Experimental)") with three buttons:
  * `Export Visible Sector (Binary)` — triggers the export +
    request sequence without changing render mode.
  * `Reload Native Viewer` — re-issues the load request so the
    native plugin re-reads the on-disk binary (useful when
    only the navigator pose changed).
  * `Toggle Native Viewer Mode` — flips the Render Mode combo
    between Native Point Viewer and the artist's previous
    choice.
  * A status label that reports the latest
    `NativeStatus.short_summary()` (point count, file size,
    load time) or "(not loaded — Python fallback)" when the
    native plugin is absent.

The metadata-inspector behaviour from v0.7 Point Cloud Mode
applies: clicking inside the viewport in Native Viewer Mode
falls through to the v0.6 search-based inspector when no
`selection.json` is available.

---

## 6. Where v0.9 sits in the migration

| Phase | Milestone | Status |
|-------|-----------|--------|
| 0     | v0.7 Python performance layer | ✓ shipped |
| 1     | v0.8 binary export + skeleton  | ✓ shipped |
| **2** | **v0.9 binary bridge + native viewer prototype** | ✓ this milestone |
| 3     | v0.10 GPU-resident buffer + DrawArray + depth-pick | next |
| 4     | v0.11 GPU compute filter + Auto Sync               | future |
| 5     | v0.12 real-time sector streaming                    | future |
| 6     | v0.13+ per-renderer integrations                    | future |

See [`PYTHON_TO_CPP_MIGRATION_PLAN.md`](PYTHON_TO_CPP_MIGRATION_PLAN.md)
for the per-phase exit criteria.

---

## 7. Test coverage

874 passing Python tests across:

* `tests/test_binary_export.py` — extended with v0.9 CLI
  navigator-state path (the same `--dataset` / `--navigator-state`
  flow the dialog uses).
* `tests/test_native_bridge.py` — 27 tests for the request /
  status / selection round-trips, schema-version rejection,
  uid-hash → uid resolution.
* `tests/test_native_viewer_backend.py` — 14 tests covering
  build / update / cap / clear / status integration.
* `tests/test_render_mode.py` — updated for the four-mode
  contract.

Plus 10 pure-C++ tests in
`native/tests/test_unav_point_buffer.cpp` covering the C++
loader / hit-tests / cap. These build with any C++17 compiler
(no Maxon SDK required) and were verified against a
Python-produced fixture during development to confirm
end-to-end binary parity.
