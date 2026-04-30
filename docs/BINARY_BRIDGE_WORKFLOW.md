# Binary Bridge Workflow

The file-based protocol the v0.9 Python plugin uses to talk to
the native C++ point viewer. Three small JSON files plus the
binary visible-sector cache implement a uni-directional
"Python writes, C++ reads, C++ writes back" bus that:

* needs **no** pybind11 / ctypes / shared-memory plumbing,
* survives Python and C++ being out of sync (each side validates
  its inputs and falls back gracefully),
* works identically on Windows / macOS / Linux,
* is transparent — you can watch the protocol in action by
  `tail -f`-ing the JSON files in `~/.unav_pro/native_bridge/`.

Reference implementations:

* Python: `unav_pro/core/native_bridge.py` (writer + reader),
  `unav_pro/c4d_objects/native_viewer_backend.py` (driver).
* C++: `native/src/unav_native_plugin.cpp`
  (`LoadFromRequestFile`, `WriteStatusFile`,
  `WriteSelectionFile`).

---

## 1. The bridge directory

By default `~/.unav_pro/native_bridge/`. Override with the
`bridge_dir=` argument on `NativeViewerBackend(...)` (used by
tests).

```
~/.unav_pro/native_bridge/
├── visible_sector.bin       # v0.8 binary visible-sector file (Python writes)
├── visible_sector.jsonl     # metadata sidecar — original CatalogObject rows
├── native_request.json      # v0.9 request the native plugin polls
├── native_status.json       # v0.9 status the native plugin writes
└── native_selection.json    # v0.9 selection result the native plugin writes
```

Each side **only** writes the files it owns:

* Python writes `visible_sector.bin`, `visible_sector.jsonl`,
  `native_request.json`.
* Native plugin writes `native_status.json` and (on a
  viewport pick) `native_selection.json`.

Files are atomic-ish: the writer truncates and rewrites; the
reader tolerates a missing file.

---

## 2. Schemas

Every JSON payload carries a `schema_version` (currently `1`).
Both sides reject any version they do not understand —
forward-compatibility is opt-in via a future bump.

### 2.1 Request — `native_request.json`

Python writes this when the artist clicks Sync Visible Sector
(under Native Viewer Mode), Export Visible Sector (Binary), or
Reload Native Viewer.

```json
{
  "schema_version": 1,
  "action": "load",
  "binary_path": "~/.unav_pro/native_bridge/visible_sector.bin",
  "sidecar_path": "~/.unav_pro/native_bridge/visible_sector.jsonl",
  "requested_at_iso": "2026-04-30T07:30:00",
  "request_id": "req_1714457400123",
  "max_points": 0
}
```

* `action` — `"load"` to read the binary file, `"clear"` to drop
  the buffer, `"noop"` for explicit no-ops.
* `binary_path` / `sidecar_path` — absolute paths the native side
  opens. Empty `sidecar_path` means "no metadata sidecar"; the
  inspector falls back to search-based selection.
* `request_id` — opaque echo. The status file echoes this back
  as `last_request_id` so Python can tell whether the native
  plugin processed the most recent request.
* `max_points` — optional per-load cap (`0` = use the native
  plugin's default).

### 2.2 Status — `native_status.json`

Native plugin writes this after every load attempt. Python's
`Reload Native Viewer` button reads it and surfaces the
short-summary string in the dialog.

```json
{
  "schema_version": 1,
  "engine_available": true,
  "engine_version": "0.9.0",
  "description": "UNAV native engine (v0.9 prototype)",
  "last_request_id": "req_1714457400123",
  "last_load_iso": "2026-04-30T07:30:01",
  "binary_path": "~/.unav_pro/native_bridge/visible_sector.bin",
  "point_count": 12345,
  "file_size_bytes": 642234,
  "load_seconds": 0.087,
  "error": ""
}
```

* `engine_available=false` (typically because the native plugin
  is not installed) is the signal the Python dialog uses to fall
  back to "engine: python (fallback)" in the status strip.
* `error` is a human-readable message — bad CRC, missing file,
  unsupported version, etc. Python surfaces it directly in the
  dialog log.

### 2.3 Selection — `native_selection.json`

Native plugin writes this when the user clicks a point in the
viewport. Python's metadata inspector polls / consumes it on
demand.

```json
{
  "schema_version": 1,
  "timestamp_iso": "2026-04-30T07:32:14",
  "uid_hash": 12345678901234567890,
  "point_index": 42,
  "x": 1.234,
  "y": -5.678,
  "z": 9.012,
  "source_id": 1
}
```

* `uid_hash` — the BLAKE2b 64-bit digest of the original UNAV
  uid. The Python side resolves it via
  `core.native_bridge.resolve_uid_from_hash(uid_hash, candidate_uids)`
  against the active `MetadataLookup`.
* `point_index` — index into the C++ `UnavPointBuffer`. Useful
  for debugging.
* `(x, y, z)` — world-space C4D coordinates (in the file's
  scale). Lets Python sanity-check the pick.

---

## 3. The pickup loop

The C++ plugin processes the request in two situations:

1. **Manual command.** The artist clicks the "UNAV Reload
   Native Viewer" command inside Cinema 4D (registered by
   `UnavReloadCommand`). This is the canonical v0.9 path.
2. **Plugin tick.** When the v0.10 SceneHook lands, it polls
   the request file's mtime per redraw and re-loads when
   it changes. v0.9 does not implement this; the manual
   command is the entire surface.

Either way, on pickup the C++ side:

1. Reads `native_request.json`.
2. If `action == "clear"`, calls `buffer.clear()`.
3. If `action == "load"`, calls
   `buffer.loadFromFile(request.binary_path, &error)`.
4. Writes `native_status.json` with the result.
5. Calls Maxon's `EventAdd()` so the editor redraws.

Errors land in the status file's `error` field; the buffer
remains empty so the editor draws nothing rather than partial
garbage.

---

## 4. The Python side

`NativeViewerBackend` (the v0.7 RenderBackend implementation)
drives the Python half of the bridge:

* **`build_visible_sector(...)`** — calls
  `data.binary_export.export_objects(...)` to write the binary,
  writes the JSONL sidecar, posts a load request, and reads the
  most recent status (if any) for the dialog strip.
* **`update_visible_sector(...)`** — same path; the native side
  rebuilds the buffer from the file, so updates are full
  snapshots, not deltas.
* **`clear(doc)`** — removes the binary and sidecar, posts a
  `clear` request, and removes the placeholder null.

All file paths route through the backend's `bridge_dir` so the
test harness can isolate per-test directories.

---

## 5. Selection flow end-to-end

1. Artist clicks a point in the C4D viewport.
2. Maxon delivers the click as a pick event to the
   `UnavStarfield` ObjectData.
3. The plugin casts a ray, calls
   `buffer.queryNearestPointToRay(...)`, gets the index.
4. The plugin writes `native_selection.json` with the
   matching uid_hash + position.
5. Python's metadata inspector reads
   `native_selection.json`, resolves `uid_hash → uid` against
   the active `MetadataLookup.uids()`, runs the v0.5+
   inspector path on the resolved uid, and surfaces the
   result.

If the selection file is stale (older than the most recent
request) or absent, Python falls back to the v0.6 search panel
("Use the Search tab to look up an object by name / uid …").
This is the same fallback the v0.7 Point Cloud Mode uses.

---

## 6. Failure modes

| Scenario                                | What happens                                                         |
|-----------------------------------------|----------------------------------------------------------------------|
| Native plugin not installed             | No `status.json` exists → Python shows "(not loaded — Python fallback)". Every other backend keeps working. |
| Request schema_version unknown          | `read_request` raises `NativeBridgeError`; the plugin logs and skips. |
| Status schema_version unknown           | `read_status` returns None; the dialog reports "(read failed)".        |
| Binary file missing                     | C++ writes `error: could not open file …` into status; Python surfaces it. |
| Binary corrupted (CRC mismatch)         | C++ writes `error: CRC mismatch …`; buffer stays empty.              |
| Binary too large                        | C++ caps at `maxPoints` and records `warning: file held N; capped to M`. |
| Selection file from old request         | Python detects via `last_request_id` mismatch and ignores.           |
| User switches render mode mid-flight    | The new backend's first build clears the visible sector; bridge files become stale and inert. |

---

## 7. Why files instead of pybind11

* **No build coupling.** A user who installs the Python plugin
  but not the native plugin still uses every other render
  backend. A user who installs the native plugin doesn't care
  what Python version Maxon ships.
* **Cross-platform without a CI matrix.** The protocol surface
  is JSON on disk. Windows, macOS, and Linux all read the
  same files.
* **Debuggable.** Open `~/.unav_pro/native_bridge/native_status.json`
  in any text editor to see what the plugin is reporting.
* **Forward-compatible.** When v0.10 ships shared-memory or a
  pybind11 binding for hot-path latency, the file protocol
  stays as the always-on fallback. The dialog never needs to
  flip a feature flag.
