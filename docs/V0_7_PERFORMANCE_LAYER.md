# UNAV Pro v0.7 — Performance Layer

The first scaling pass. Up to v0.6 every visible row became one
``c4d.Onull`` with a marker BaseContainer; that worked beautifully
for ≤ 10 k objects but didn't scale beyond it. v0.7 splits "what
is in the visible sector" from "how it gets drawn" by introducing
a render-backend interface, three concrete backends, and a
mode-aware safety policy.

For per-area deep docs see:

* [`RENDER_BACKENDS.md`](RENDER_BACKENDS.md) — backend interface
  contract.
* [`INSTANCE_MODE_LIMITATIONS.md`](INSTANCE_MODE_LIMITATIONS.md) —
  what Instance Mode can and cannot do today.
* [`FUTURE_GPU_POINT_RENDERER.md`](FUTURE_GPU_POINT_RENDERER.md) —
  where the Point Cloud backend ends up in v0.8+.

---

## 1. The three render modes

| Mode             | Token            | What it builds                                | Hard cap   | Soft warning | Per-object selection |
|------------------|------------------|------------------------------------------------|-----------:|-------------:|----------------------|
| Debug Objects    | `debug_objects`  | One `c4d.Onull` per visible row + marker.     |    10 000  |     5 000    | Yes (full marker)    |
| Instances        | `instances`      | One template + one `c4d.Oinstance` per row.   |   200 000  |    50 000    | Yes (uid marker)     |
| Point Cloud      | `point_cloud`    | Placeholder; visible-uid map in memory.       | 1 000 000  |       —      | No (search fallback) |

Defaults live in `unav_pro/core/render_mode.py`. The dialog's combo
box uses `RENDER_MODE_LABELS`; the safety advisory uses
`cap_for_mode(...)` and `soft_warning_for_mode(...)`.

The default mode is **Debug Objects** so existing scenes keep
working unchanged after upgrading. The artist opts into the
lighter modes via the Render Mode strip in the dialog.

---

## 2. The backend interface

`unav_pro/c4d_objects/render_backend.py` defines `RenderBackend`,
the abstract base every backend implements:

```python
class RenderBackend:
    mode: str
    def clear(doc) -> int: ...
    def build_visible_sector(doc, objects, *, encoding, scale_mode, max_visible) -> BackendUpdateResult: ...
    def update_visible_sector(doc, *, added, removed_uids, kept_uids, encoding, scale_mode) -> BackendUpdateResult: ...
    def get_object_uid_from_selection(doc, c4d_object) -> Optional[str]: ...
    def supports_metadata_selection() -> bool: ...
    def get_stats() -> BackendStats: ...
```

The factory `backend_for_mode(mode)` returns a fresh instance per
sync; the dialog never reuses a backend across mode switches so
state never leaks.

`BackendStats` carries the four numbers the Render Mode strip
shows: `last_build_seconds`, `visible_count`, `generated_count`,
`estimated_scene_objects`. The dialog pulls them via
`mock_actions.last_render_stats()`.

The full interface contract lives in
[`RENDER_BACKENDS.md`](RENDER_BACKENDS.md).

---

## 3. How a sync click flows

```
                ┌─────────────────────┐
                │  UI: Sync click     │
                └─────────┬───────────┘
                          │ render_mode token from combo
                          ▼
                ┌─────────────────────┐
                │ mock_actions        │
                │ sync_visible_sector │
                └─────────┬───────────┘
                          │ render_mode forwarded
                          ▼
                ┌─────────────────────┐
                │ scene_sync          │
                │ sync_visible_sector │
                ├─────────────────────┤
                │ 1. compute_diff     │
                │ 2. backend = factory(mode)
                │ 3. backend.update_visible_sector(...)
                │ 4. update debug cone
                │ 5. record backend_stats on SyncDiff
                └─────────┬───────────┘
                          │
                          ▼
                ┌─────────────────────┐
                │ DebugObjectsBackend │  …or InstanceBackend
                │ updates UNAV_VisibleSector  …or PointCloudBackend
                └─────────────────────┘
```

`compute_diff` is unchanged from v0.6; the diff itself doesn't
care which backend will materialise it. The backend just
consumes `(added_objects, removed_uids, kept_uids)` and applies
its own creation strategy.

---

## 4. Scene Sync integration

`core.scene_sync.sync_visible_sector` gained two new keyword
arguments:

* `render_mode` — token forwarded from the dialog. `None` means
  "use the default (debug_objects)" so any pre-v0.7 caller keeps
  working.
* `backend` — explicit backend instance for tests / advanced
  callers. The runtime passes `render_mode` and lets the factory
  build a fresh backend.

The diff still drives the add/keep/remove plan; the backend
dispatch only changes what each `add` call produces. Switching
modes between syncs is safe: backends call `clear_starfield` (or
just rebuild the visible-sector children), so leftover nodes
from the previous backend don't accumulate.

---

## 5. Visual encoding stays single-source

The backends consume `core.visual_encoding.encode(...)` directly
— no backend re-implements colour or radius logic. The Instance
Mode helper `encoded_color_radius` is deliberately a thin
forwarder that mirrors `point_cloud_builder.color_for_object` /
`radius_for_object` for the natural path and routes through
`encode_visuals(obj, params)` for any non-natural mode. The
unit tests assert this parity (`test_instance_builder.py
::test_null_radius_scale_matches_debug_backend`).

---

## 6. Safety integration

* **Per-mode hard caps.** The dialog's `max_visible_objects`
  user-data slot keeps working as the explicit per-navigator
  cap; backends additionally honour the per-mode default cap when
  the user-data is at its global ceiling.
* **Soft warnings.** Crossing
  `DEBUG_OBJECTS_SOFT_WARNING` (5 k) or
  `INSTANCES_SOFT_WARNING` (50 k) prints a warning into the dialog
  log so the artist knows they are entering heavy territory. Hard
  caps still apply on top.
* **Visible-sector-only mode.** Untouched. Every backend's
  `build_visible_sector` requires `UNAV_Navigator` to exist via
  `ensure_starfield_hierarchy` upstream — same contract as v0.1.
* **Mode-switch safety.** `clear_starfield` is invoked when a
  backend builds a fresh sector; the previous backend's children
  are removed in a single undo block.

---

## 7. Metadata inspector behaviour by mode

| Mode             | Click → Inspect Selected Object                                                      |
|------------------|---------------------------------------------------------------------------------------|
| Debug Objects    | Reads full marker; resolves uid against `MetadataLookup`; shows the v0.5 Survey/Class section, the v0.5 redshift-proxy warning, the raw JSON preview. |
| Instances        | Reads the minimal uid-only marker; resolves uid against `MetadataLookup`; full record arrives via the lookup. |
| Point Cloud      | The placeholder null carries no uid; the dialog shows a "use Search tab" hint instead — see `point_cloud_panel_text()` / `point_cloud_search_hint()`. |

The fallback path satisfies the v0.7 task requirement: even
without per-object selection, the search-based path (v0.6) lets
the artist resolve any visible uid.

---

## 8. What v0.7 explicitly does **not** do

* **No native / GPU buffer.** Point Cloud Mode is a placeholder.
  See [`FUTURE_GPU_POINT_RENDERER.md`](FUTURE_GPU_POINT_RENDERER.md).
* **No C++ migration.** The whole layer is still Python.
* **No removal of Debug Objects Mode.** It stays the default.
* **No automatic mode escalation.** The artist picks the mode;
  the dialog warns when the visible count exceeds the soft
  threshold but never silently switches.
* **No per-instance opaque-id selection cache.** Instance Mode
  keeps a per-instance uid marker so selection works without an
  external map; the external `_uid_to_object` map is bookkeeping
  for the search fallback, not the selection path.

---

## 9. Test coverage

| Module                            | Tests                                            |
|-----------------------------------|--------------------------------------------------|
| `core/render_mode.py`             | `tests/test_render_mode.py`                      |
| `c4d_objects/render_backend.py`   | `tests/test_render_backend.py`                   |
| `c4d_objects/instance_builder.py` | `tests/test_instance_builder.py`                 |
| `core/scene_sync.py` (dispatch)   | covered by the existing `tests/test_scene_sync.py` (compute_diff) and the new factory + capability tests above. |

The c4d-bound build/update halves of each backend are guarded
under `_C4D_AVAILABLE`; the test suite exercises every pure-Python
contract path including the Point Cloud Mode bookkeeping that
runs without Cinema 4D.
