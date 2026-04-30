# Future GPU Point Renderer

The v0.7 Point Cloud Mode (`render_mode = "point_cloud"`) is a
**placeholder** for the v0.8+ work that swaps in a real native /
GPU-accelerated point renderer. Today it satisfies the v0.7
contract — backend interface conformance, search-based inspection
fallback, in-memory uid bookkeeping — but draws nothing in the
viewport beyond a single placeholder null. This document records
what the placeholder buys us and what the production path looks
like.

For the v0.7 backend interface see
[`RENDER_BACKENDS.md`](RENDER_BACKENDS.md). For the migration
plan from Python prototype to native code see
[`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md).

---

## 1. What the placeholder ships today

`PointCloudBackend` (`unav_pro/c4d_objects/render_backend.py`)
implements:

* `clear(doc)` — removes any `UNAV_PointCloudPlaceholder` null
  from the visible sector and forgets the in-memory
  `uid → CatalogObject` map.
* `build_visible_sector(doc, objects, ...)` — caps to the
  per-mode hard cap (1 000 000 by default), records the
  visible-uid map, drops a single placeholder null with the
  count in its name (e.g. `UNAV_PointCloudPlaceholder (12345)`).
* `update_visible_sector(doc, ...)` — applies the
  add/keep/remove deltas to the in-memory map and refreshes
  the placeholder.
* `get_object_uid_from_selection(...)` — returns `None`. There
  is no per-object selection.
* `supports_metadata_selection() → False` — the dialog uses
  this to switch the inspector to search-based fallback.

The placeholder's editor visibility is intentionally minimal so
the artist sees that the cloud exists without it interfering
with the rest of the scene.

---

## 2. Why a placeholder satisfies v0.7

* **Interface lock-in.** Every later iteration replaces the
  body of `build_visible_sector` / `update_visible_sector`,
  not the surface. Every caller (the dialog, scene_sync,
  mock_actions, the safety advisory) talks to
  `BackendUpdateResult` / `BackendStats` and to the
  selection contract. None of them needs to know whether the
  cloud is rendered by a placeholder, by Cinema 4D's own
  built-in point cloud (when that ships in a future host
  release), or by a native plugin.
* **Inspection fallback today.** v0.6 already gave us a
  search-based way to resolve any uid in the active lookup.
  Point Cloud Mode wires the dialog to surface that path
  whenever the click does not yield a uid; the artist still
  has a working workflow.
* **Safety integration today.** The per-mode hard cap, the
  generated-count stat, and the visible-sector-only mode all
  apply to the placeholder identically to how they apply to
  the future real renderer.

---

## 3. The production target

The eventual implementation has three layers:

### 3.1 Native point buffer

A C++ object that the plugin owns a Python handle to. It
holds:

* A packed array of (x, y, z, r, g, b, radius) for every
  visible point in the cloud.
* A parallel array of uids (or stable integer IDs that map to
  uids via an external table).
* GPU upload state — vertex buffer, attribute layouts, draw
  call.

The Python-side `PointCloudBackend.build_visible_sector(...)`
becomes:

1. Pack `(c4d_x, c4d_y, c4d_z, r, g, b, render_radius)` from
   each `CatalogObject` into a `bytes` buffer.
2. Hand the buffer + the uid list to the native object.
3. The native object uploads to the GPU.

`update_visible_sector(...)` becomes a delta update against
the same buffer (insert / delete by uid index).

### 3.2 BaseDraw callback

Cinema 4D exposes a `MSG_DRAW` / `BaseDraw` extension point
that lets a plugin emit raw OpenGL / Metal / DX calls into
the editor viewport. The cloud's draw callback issues a
single `glDrawArrays(GL_POINTS, ...)` (or the platform
equivalent) per pass, with a tiny vertex shader that turns
each point into a screen-space sprite of the right size and
colour.

Render-pass parity is intentionally *not* full: GPU points
are an editor-only preview. For final-frame rendering the
artist either:

* **Snapshots** the cloud back into Instance Mode (one
  template + one `Oinstance` per point) and renders that, or
* **Plugs** a Thinking Particles / Cycles / Octane / Redshift
  point-cloud emitter into the same uid stream — a render
  hook the v0.8+ work will document.

### 3.3 Selection bridge

GPU points are not Object Manager nodes, so the v0.7
"`get_object_uid_from_selection` returns `None`" contract
stays. The selection bridge provides:

* Picking by viewport click via a depth-buffer readback (the
  native object resolves a screen-space click to the closest
  packed-point uid).
* A "Lock to nearest" button in the v0.6 Navigation tab that
  uses the same depth-buffer pick.
* Always-available search-based selection via the v0.6 search
  panel. (This is the one we ship today.)

The dialog's metadata inspector consumes whichever of the
three picks the user performed; the inspector itself doesn't
care about the picking mechanism.

---

## 4. Performance targets

The placeholder is profile-neutral; the production renderer is
designed to:

* Hold ≥ 5 000 000 points in the editor viewport at 30+ FPS on
  a modern integrated GPU (entry target).
* Hold ≥ 50 000 000 points on a discrete GPU (stretch target).
* Build / update in < 100 ms wall-clock for 1 M-point deltas
  (so a Sync click feels instant).
* Round-trip a click → uid in < 16 ms (one frame).

Until the C++ + native draw lands, the v0.7 hard cap of
1 000 000 visible-uid entries is advisory: the placeholder
itself is fast (just an in-memory dict), but the artist
should not load a million-row catalog into the lookup and
rely on the placeholder for any kind of preview yet.

---

## 5. What changes when the real renderer lands

### 5.1 Inside `PointCloudBackend`

* `_ensure_placeholder` → `_ensure_native_buffer`.
* `clear` releases the GPU buffer and removes the BaseDraw
  callback registration.
* `build_visible_sector` packs + uploads.
* `update_visible_sector` delta-updates.
* `get_object_uid_from_selection` returns the uid the
  depth-pick bridge produced.
* `supports_metadata_selection()` flips to `True`.

### 5.2 Outside the backend

* Nothing in the dialog needs to change. The combo, the
  stats strip, and the soft-warning machinery all keep their
  v0.7 semantics.
* `mock_actions.last_render_stats()` keeps reporting the
  four `BackendStats` numbers; `generated_count` becomes
  "delta points uploaded this pass" and
  `estimated_scene_objects` stays `1` (the cloud counts as
  one C4D node from the safety advisory's perspective).
* The metadata-inspector `point_cloud_panel_text()` /
  `point_cloud_search_hint()` helpers stay in place and the
  search-based path remains the recommended workflow even
  after viewport pick lands; both paths coexist.

### 5.3 In the docs

* This file gets edited to describe the shipping renderer,
  not its placeholder ancestor.
* `INSTANCE_MODE_LIMITATIONS.md` cross-references the new
  GPU mode as the "use this past 200 k objects" recommendation.
* `RENDER_BACKENDS.md` updates the Point Cloud row of the
  comparison table.

---

## 6. What this milestone deliberately leaves out

* Any C++ code. The whole v0.7 layer is Python; the next
  milestone owns the native bridge.
* Any GPU buffer management.
* Any depth-buffer pick.
* Any change to Cinema 4D's installation requirements.
* Any change to the public Python interface; the v0.7
  backend contract is the long-lived surface.

Point Cloud Mode in v0.7 is a **promise the interface keeps**:
when the GPU code arrives, no caller of `RenderBackend` has
to be rewritten.
