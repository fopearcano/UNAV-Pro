# UNAV Pro — User Guide

A button-by-button walkthrough of the plugin's controls, in the
order an artist typically encounters them. Each section is short
and points to the deep doc for the underlying feature.

If you haven't installed the plugin yet, see
[`INSTALL_C4D_2023_PLUS.md`](INSTALL_C4D_2023_PLUS.md).
For the "I just want to see something work" path, the README's
**Quick start** is faster.

---

## 1. The dialog

**Extensions → Universal Navigator Pro** opens the main control
panel. Top to bottom:

| Section            | What it controls                                    |
|--------------------|-----------------------------------------------------|
| **Display**        | Visual encoding mode + size/brightness scales.      |
| **Safety**         | Hard cap, navigator-gate override, status strip.    |
| **Visible Sector** | Sync workflow + Auto Sync (placeholder) + Debug Cone toggle. |
| **Actions**        | The dataset / generation / scene / inspector / route / state / diagnostics buttons. |
| **Status Log**     | Append-only one-liner per action.                   |
| **Metadata Inspector** | Multi-line panel for the selected object.       |
| **Route Planner**  | Multi-line summary panel + four route buttons.      |

The **Status Log** is your friend: every button writes a status
line there, and read-only as it is, you can scroll back to see
what every recent click actually did.

---

## 2. Loading data

### Load Dataset

Reads the bundled `sample_catalog_100.jsonl` and reports the row
count. No scene side effects. Use this to confirm the catalog
backend is alive before doing anything that mutates the scene.

### Dataset Manager…

Opens a dedicated window for managing local catalogs. Full
walkthrough in [`DATASET_MANAGER.md`](DATASET_MANAGER.md). Buttons:

* **Add Dataset** — file-pick a JSONL/CSV. The registry scans it
  on add (object count, bounding radius, populated fields,
  catalog sources). Per-user persistence to
  `~/.unav_pro/datasets.json`.
* **Remove Dataset** — drops the currently selected entry.
* **Enable/Disable** — toggle whether the dataset participates in
  *Load Active Datasets*.
* **Build Index** — runs
  `core.spatial_index.build_index` against the catalog and stores
  the resulting cache directory on the entry.
* **Load Active Datasets** — merges every enabled entry into a
  single in-memory `MetadataLookup` with namespaced uids
  (`<entry.name>:<original_uid>`) so collisions are impossible.
  The metadata inspector and route resolver pick up the new
  lookup immediately.
* **Refresh Stats** — rescans the file (e.g. after re-running an
  ingestion CLI).

---

## 3. The navigator

UNAV Pro's filter is bounded by a `UNAV_Navigator` null. Without
one, generation is blocked by the safety system (see §5).

### Create Navigation Null

Adds the hierarchy at the scene root:

```
UNAV_Navigator                  (Onull, axis display)
  ├── UNAV_Camera               (Ocamera)
  └── UNAV_ViewRay              (linear spline along local −Z)
```

Idempotent — clicking it again selects the existing null instead
of creating a duplicate. The null's local **−Z** is the forward
direction; the camera and ray inherit it.

### Editing navigator parameters

The null's user data is the parameter source for filtering:

| Field                       | Purpose                                                        |
|-----------------------------|----------------------------------------------------------------|
| `max_distance_parsec`       | Reserved (ceiling for the cone's far reach).                  |
| `field_of_view_deg`         | Camera FOV (used by the camera; not by the cone filter).      |
| `cone_angle_deg`            | Half-angle of the selection / filter cone.                    |
| `near_clip_parsec`          | Minimum distance to keep an object.                           |
| `far_clip_parsec`           | Maximum distance to keep an object.                           |
| `selected_catalog_sources`  | Comma-separated list to gate by source.                       |
| `max_visible_objects`       | Hard cap on what the filter returns per query.                |
| `c4d_scale`                 | One of `au`, `ly`, `pc`, `kpc`, `mpc`.                        |

Edit them in the C4D Attribute Manager, then click **Sync Visible
Sector** to refresh the scene. Out-of-range values are clamped at
the C4D boundary by `NavigationParams.clamped()`. See
[`NAVIGATION_NULL_SYSTEM.md`](NAVIGATION_NULL_SYSTEM.md).

---

## 4. Generating the scene

### Generate Point Cloud

The full path: load the bundled (or registered) catalog → filter
against the active navigator → apply visual encoding → safety
gate → build C4D nulls under
`UNAV_Starfield → UNAV_VisibleSector`.

If no navigator exists, the safety gate **blocks** the build by
default. The status log explains how to either create a navigator
or flip the override.

### Sync Visible Sector

The pro workflow. Diffs the materialized children of
`UNAV_VisibleSector` against the new filter result and:

* removes objects that fell out of view,
* keeps objects that are still visible (selection / animation /
  per-object tags survive),
* adds the newly visible ones.

Faster and less destructive than re-running *Generate Point Cloud*
every time you nudge the navigator. See
[`SCENE_SYNC_WORKFLOW.md`](SCENE_SYNC_WORKFLOW.md).

### Apply View Filter

Runs the spatial filter and reports the rejection breakdown
without touching the scene. Use it to tune navigator parameters
before committing to a rebuild.

### Regenerate Visible Field

Clears the existing starfield and rebuilds from the current
filter result. The "burn-it-down-and-start-fresh" version of
*Sync*.

### Clear Scene

Removes only UNAV-tagged objects (the marker container is the
identifier). User content is untouched.

### Auto Sync (placeholder)

Reserved for the future *MessageData*-driven per-frame sync.
Toggling it currently logs `Auto Sync: not yet implemented; click
Sync Visible Sector manually.`

### Show Debug Cone

Adds a translucent cone primitive under `UNAV_Starfield → UNAV_Debug`
whose apex sits at the navigator origin and whose dimensions
match `cone_angle_deg` and `far_clip_parsec`. Editor-only — render
visibility is forced off.

---

## 5. Safety strip

Always visible above the action grid. Three controls + one read-
only status line. The status line reports the current mode (one
of *Visible-sector only* / *Sector-aware* / **FULL CATALOG
OVERRIDE**) and the generated-vs-cap counts.

| Control                | What it does                                                 |
|------------------------|--------------------------------------------------------------|
| **Max generated objects** | Hard cap. Default 100 000. Edited inline.                |
| **Allow Full Catalog** | The override. Bypasses the navigator gate **and** the cap. Logged loudly. |
| **Refresh**            | Re-counts visible-sector children and re-renders the strip. |

See [`LARGE_DATA_SAFETY.md`](LARGE_DATA_SAFETY.md).

---

## 6. Visual encoding (Display group)

Two controls that change what the build looks like:

* **Color mode**: `Natural Star Color` (default — schema's
  spectral palette for stars, type defaults elsewhere) /
  `Catalog Source` / `Object Type` / `Redshift` / `Magnitude` /
  `BP-RP Color Index`.
* **Size scale** + **Brightness scale**: multipliers applied
  after the per-mode size function.

Modes whose underlying field is missing (e.g. *Redshift* on a
star with no redshift) self-heal to the natural fallback so a
mixed catalog doesn't end up with silently grey objects. See
[`VISUAL_ENCODING.md`](VISUAL_ENCODING.md).

---

## 7. Inspecting metadata

### Inspect Selected Object

Reads the C4D selection's UNAV marker, looks up the full record
in the active `MetadataLookup`, and renders the metadata panel
with four sections (Identity / Astrometry / Photometry / Raw
JSON). When the lookup misses, the panel falls back to whatever
the marker carries and says so.

### Copy Metadata JSON

Copies a self-contained JSON document for the most recently
inspected object. Includes a parsed copy of the schema's
`metadata_json` blob alongside the canonical fields. See
[`METADATA_INSPECTOR.md`](METADATA_INSPECTOR.md).

---

## 8. Route planning

The route panel shows a summary of the live `Route` plus four
buttons. Routes are visual — no propulsion, no orbital mechanics.
See [`ROUTE_PLANNER.md`](ROUTE_PLANNER.md).

* **Add Selected Object as Waypoint** — UNAV selection becomes
  an `object` waypoint with the uid + cached coords; non-UNAV
  selection becomes a `coordinate` waypoint from the object's
  world position.
* **Clear Route** — empties the live route and removes any
  existing route spline.
* **Build Route Spline** — creates a linear `c4d.SplineObject`
  through the resolvable waypoints under a fresh `UNAV_Route`
  null at the scene root.
* **Focus Navigator on Waypoint** — moves the navigator's origin
  to the last-added waypoint (rotation untouched).

---

## 9. State persistence

* **Save UNAV State** — writes navigator + route + active
  datasets + visual encoding to (1) the C4D document's
  `BaseContainer` (so it travels with the `.c4d`) and (2)
  `~/.unav_pro/projects/<scene-stem>.json` (sidecar for cross-
  machine workflows).
* **Load UNAV State** — restores from whichever location finds
  data first (scene container → sidecar). Reports the apply
  summary in the log.
* **Reset Preferences** — wipes the per-user config back to
  defaults (`~/.unav_pro/config.json`). Does **not** touch
  project state files or the dataset registry.

See [`PERSISTENCE_AND_CONFIG.md`](PERSISTENCE_AND_CONFIG.md).

---

## 10. Diagnostics

**Diagnostics…** opens a separate window with a level-filter combo
(All / Debug / Info / Warning / Error), a multi-line panel showing
environment + recent log records, and four buttons:

* **Refresh** — re-renders the snapshot.
* **Copy Diagnostics** — clipboard payload for support tickets.
* **Open Log Folder** — `c4d.storage.GeExecuteFile` against the
  rotating-log directory.
* **Clear Recent Logs** — empties the in-memory ring buffer.

The environment block lists C4D version, Python version, plugin
root, cache root, log file/folder, registered datasets (with
indexed flag), the active lookup's row count, and the count of
materialized objects under `UNAV_VisibleSector`. See
[`DIAGNOSTICS.md`](DIAGNOSTICS.md).

---

## 11. Status log

Every button click appends a one-liner. Multi-line content (the
metadata panel, the route summary) lands in dedicated panels
above. **Clear Log** wipes the log without affecting anything
else.

---

## 12. Where things live in the scene

```
Scene root
├── UNAV_Navigator                 (Onull)
│   ├── UNAV_Camera                (Ocamera — usable as render cam)
│   └── UNAV_ViewRay               (visual forward indicator)
├── UNAV_Starfield                 (Onull, parent for everything UNAV makes)
│   ├── UNAV_VisibleSector         (Onull, holds the materialized point set)
│   │   └── point objects (Onull each, marker-tagged)
│   └── UNAV_Debug                 (Onull, holds the optional debug cone)
└── UNAV_Route                     (Onull, holds the route spline)
    └── UNAV_RoutePath             (linear SplineObject)
```

Every UNAV-created object carries a `BC_ID_UNAV_MARKER`
sub-container, so **Clear Scene** can identify and remove them
without touching anything else. See
[`POINT_CLOUD_GENERATION.md`](POINT_CLOUD_GENERATION.md) and
[`SCENE_SYNC_WORKFLOW.md`](SCENE_SYNC_WORKFLOW.md).
