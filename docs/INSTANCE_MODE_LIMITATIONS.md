# Instance Mode Limitations

The v0.7 Instance Mode (`render_mode = "instances"`) is the middle
gear: lighter than Debug Objects, heavier than the future GPU
point renderer. This document lists what it can and cannot do
today, so artists pick the right mode for their scene size and
workflow.

For the full backend contract see
[`RENDER_BACKENDS.md`](RENDER_BACKENDS.md). For the future native
path see
[`FUTURE_GPU_POINT_RENDERER.md`](FUTURE_GPU_POINT_RENDERER.md).

---

## 1. What Instance Mode does

* Creates **one** shared template null
  (`UNAV_InstanceTemplate`) parented under `UNAV_Debug`. The
  template is hidden in the editor and in the renderer.
* Creates one `c4d.Oinstance` per visible row, parented under
  `UNAV_VisibleSector`. Each instance carries:
  * world-space position (`SetAbsPos`),
  * colour (`ID_BASEOBJECT_COLOR`),
  * uniform local scale matching the visual encoder's radius,
  * a minimal marker BaseContainer with **just** `uid` + `kind`
    + `is_unav` + `schema_version`.
* Routes every colour / radius decision through the shared
  `core.visual_encoding.encode(...)` path so visual parity with
  Debug Objects is preserved at identical encoding parameters.

---

## 2. What Instance Mode cannot do (today)

### 2.1 No richer per-instance metadata

The instance marker is intentionally tiny: only the uid is
stored on the instance node. The Debug Objects backend stuffs
`name`, `catalog_source`, `object_type`, `ra_deg`, `dec_deg`,
`distance_parsec` into every marker; Instance Mode trades that
embedding for a smaller `.c4d` save and faster scene traversal.

**Consequence.** When the inspector runs against an instance,
the v0.5 Identity / Astrometry / Photometry / Survey-Class /
Raw-JSON sections all come from the active `MetadataLookup`,
not the marker. If the artist disables every dataset before
clicking Inspect, the panel falls back to "marker only" with
just the uid + kind. *This is by design* — the lookup is the
source of truth; the marker is a pointer.

### 2.2 No GPU-accelerated draw

Each `Oinstance` is still a real BaseObject in the scene graph.
At 200 000 instances Cinema 4D's viewport is faster than
200 000 nulls but still slower than a packed buffer pushed to
the GPU. The hard cap (`DEFAULT_CAPS["instances"] = 200_000`)
exists because that is the Python-prototype responsiveness
ceiling, not because instances themselves cap there.

### 2.3 No instance-array via MoGraph

UNAV Pro deliberately does **not** use C4D's MoGraph
`MatrixObject` / `Cloner` / `MoSpline` because MoGraph is paid
on Maxon's licensing tiers. Instance Mode runs on every C4D
edition (Free, Studio, Maxon One) without any add-on.

### 2.4 No per-instance shading per render-mode

The instance template is a `c4d.Onull` with display style
`NULLOBJECT_DISPLAY_DOT`. Render-pass parity (Standard /
Physical / Redshift / Octane / etc.) is identical to the v0.1
debug-object behaviour: nulls render as nothing by default.
For final-frame rendering the artist swaps the template
manually (e.g. for a low-poly sphere or a Thinking Particles
emitter); the template's `INSTANCEOBJECT_LINK` slot makes that
a one-edit operation.

### 2.5 No mid-sync mode swap

Switching render mode requires a full Sync click; in-flight
edits to the visible sector under one mode are not migrated to
another. Artists who want to compare modes at the same
navigator pose simply re-click *Sync Visible Sector* after
flipping the dropdown.

---

## 3. Selection contract

* Clicking an instance in the Object Manager → marker carries
  the uid → `_do_inspect` resolves it via the active
  `MetadataLookup` → the inspector renders the full record.
* Clicking the template (under `UNAV_Debug`) → marker is the
  template's `_named_kind_marker`; the uid is empty; the
  inspector reports "marker only — no catalog match" so the
  artist sees they didn't pick a real instance.
* `acquire_target(uid, lookup)` (v0.6 target lock) and the
  v0.6 search panel both work unchanged because both consult
  the lookup, not the marker.

The route planner's *Add Selected Object as Waypoint* path
also works: it reads the marker's uid (which Instance Mode
provides) and fills the rest from the lookup.

---

## 4. Save-file behaviour

* The template + 200 000 instances save to a `.c4d` measurably
  smaller than 200 000 nulls each carrying a 12-field marker.
  The saving comes from the marker being uid-only, plus C4D's
  internal instance-handling sharing template state.
* The lookup is **not** embedded in the `.c4d`. Reopening a
  scene on a machine without the matching JSONL produces a
  scene with the right geometry but inspector misses (the
  marker-only fallback). Save the project state JSON sidecar
  to keep the dataset list with the scene.

---

## 5. When to choose Instance Mode

| Scene size       | Recommended mode  |
|------------------|--------------------|
| ≤ 5 k objects    | Debug Objects     |
| 5 k – 10 k       | Debug Objects (with the soft warning) or Instances |
| 10 k – 50 k      | Instances (with the soft warning above 50 k) |
| 50 k – 200 k     | Instances         |
| > 200 k          | Point Cloud (experimental, search-based inspection) |

The Render Mode strip in the dialog enforces the per-mode hard
cap regardless of the navigator's `max_visible_objects` slot,
so a setting that allows 1 M visible objects under
`debug_objects` still gets clamped to 10 k by the v0.7 layer.

---

## 6. Future tightening

* **Per-render-pass templates.** A "render template" slot the
  artist points at a mesh / particle / Octane object so the
  same instance population swaps to a final-frame look without
  re-syncing.
* **Instance-array fast path.** If C4D ever exposes a
  free-tier `BaseObject` that wraps a C-side instance array
  (similar to the deprecated `c4d.utils.Neighbor` fast paths),
  Instance Mode can adopt it without changing its public
  contract.
* **GPU bridge.** When the Point Cloud backend's GPU buffer
  ships, an "Instances + GPU" hybrid (template instances for
  selection, GPU dots for the rest) becomes a natural third
  render-quality preset.

Until then: Instance Mode = the production workhorse for
multi-tens-of-thousands of objects. Debug Objects = the
inspection workshop. Point Cloud = the future.
