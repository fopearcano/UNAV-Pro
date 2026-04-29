# UNAV Pro — Pro Workflow

The recommended professional workflow for assembling a multi-
catalog scene end to end. Treats the plugin as a *navigation tool
over a pre-built local cache* rather than a "click and download
the universe" button. Every step is offline once the data is
fetched, so a render farm or an artist on a flaky link sees
exactly the same scene as the supervisor who ingested the data.

For the corresponding "what does each button do" walkthrough see
[`USER_GUIDE.md`](USER_GUIDE.md).

---

## Phase 0 — Pick a region and an objective

Decide before touching the plugin:

* **Sky region.** UNAV is offline-cone first; you tell every
  connector exactly where to look. Pick `(ra_deg, dec_deg,
  radius_deg)` once and reuse for all sources.
* **Distance scale.** Are you visualizing parsec-scale
  neighborhoods (Gaia stars), kiloparsec galactic structure, or
  megaparsec cosmology (DESI/SDSS galaxies + quasars)? This
  determines the navigator's `c4d_scale` later.
* **Object types.** Stars only, galaxies only, "everything in
  this cone." This determines which connectors you call.

Concrete example used throughout this document: a 1° cone around
the Pleiades (`ra=56.75 dec=24.12`) for a "looking back at the
Sun from a nearby cluster" shot. Stars from Gaia DR3, a few
distant galaxies from SDSS DR18 for context, plus Mars + Jupiter
from JPL Horizons as foreground.

---

## Phase 1 — Fetch real catalogs (offline, repeatable)

Each connector is a CLI in `tools/`. They're stdlib-only and
dependency-free; running them on a render farm or in a Docker
image needs no setup beyond Python 3.9+.

### Stars (Gaia DR3)

```bash
python tools/fetch_gaia_region.py \
    --ra 56.75 --dec 24.12 --radius-deg 1.0 \
    --limit 5000 \
    --output data/gaia_pleiades.jsonl
```

Brightest first, parallax SNR filter on by default at 5σ. Below
that the parallax is too noisy to trust the distance, and the row
flows through with `distance_parsec=None` → the schema places it
on the placeholder sphere so the inspector still has something to
say.

### Galaxies / quasars (SDSS DR18)

```bash
python tools/fetch_sdss_region.py \
    --ra 56.75 --dec 24.12 --radius-deg 0.2 \
    --limit 2000 \
    --output data/sdss_pleiades.jsonl
```

Default joins `PhotoObj` with `SpecObj` so rows that have a
spectrum carry redshift; `--no-spectro` disables the join.

### Galaxies (DESI EDR)

```bash
python tools/fetch_desi_region.py \
    --ra 56.75 --dec 24.12 --radius-deg 1.0 \
    --limit 2000 --spectype GALAXY \
    --output data/desi_pleiades_galaxies.jsonl
```

`ZWARN`-gated: any non-zero quality bit suppresses the Hubble-
distance derivation but keeps the row + the warning code in
metadata.

### Solar-system bodies (JPL Horizons)

```bash
python tools/fetch_jpl_body.py \
    --body "Mars" --epoch "2026-01-01" --object-type planet \
    --output data/jpl_mars.jsonl
python tools/fetch_jpl_body.py \
    --body "Jupiter" --epoch "2026-01-01" --object-type planet \
    --output data/jpl_jupiter.jsonl
```

One body per call, heliocentric ICRF Cartesian → spherical → UNAV
schema. Static point at the requested epoch; live animation is on
the roadmap.

See [`DATA_SOURCE_OVERVIEW.md`](DATA_SOURCE_OVERVIEW.md) for the
column-mapping summary across all four sources.

---

## Phase 2 — Index for fast queries

The plugin **never** loads the whole catalog into RAM. For
≥ 5 000 rows or any catalog you'll query repeatedly, build a
chunked spatial index up front:

```bash
python tools/build_spatial_index.py \
    --input data/gaia_pleiades.jsonl \
    --output cache/gaia_pleiades \
    --chunk-size 5000
```

Produces `cache/gaia_pleiades/index.json` plus per-cell JSONL
chunks under `cache/gaia_pleiades/chunks/cell_<i>_<j>_<k>/`. The
index is forgiving: rerun the CLI any time and it overwrites the
cells.

See [`SPATIAL_INDEXING_AND_CHUNKING.md`](SPATIAL_INDEXING_AND_CHUNKING.md).

---

## Phase 3 — Register catalogs in C4D

Open Cinema 4D 2023+. **Extensions → Universal Navigator Pro →
Dataset Manager…**.

1. **Add Dataset** for each JSONL file. The registry scans on
   add and shows: row count, bounding radius (pc), populated
   schema fields, source list, and `[idx]` if a sister
   `<path>.index/` directory exists.
2. **Build Index** for any unindexed entry directly from the
   manager. (Equivalent to step 2 above; convenient for
   small catalogs already registered without indexing first.)
3. **Enable** the entries you want active in this scene; disable
   the rest. The combo box's selection drives the per-row
   buttons.
4. **Load Active Datasets**. The merged `MetadataLookup`
   namespaces uids as `<dataset.name>:<original_uid>` so two
   catalogs that share a uid prefix can't collide. The
   inspector and the route resolver see the new lookup
   immediately.

See [`DATASET_MANAGER.md`](DATASET_MANAGER.md).

---

## Phase 4 — Place the navigator

In the main dialog, click **Create Navigation Null**. The three-
object hierarchy (`UNAV_Navigator`, `UNAV_Camera`, `UNAV_ViewRay`)
appears at the scene root. Use the C4D viewport to:

1. Translate the navigator to the spatial origin of your shot.
   In Pleiades coordinates with `c4d_scale=pc`, that's somewhere
   around (200, 0, 0) C4D units.
2. Rotate it so the **−Z** axis points where you want to "look."
   The view ray spline shows the forward direction visually.
3. In the Attribute Manager, edit the navigator's user data:
   * `c4d_scale = "pc"` for a stellar-scale shot, `kpc` for
     galactic structure, `mpc` for cosmology.
   * `cone_angle_deg` to roughly match your camera FOV.
   * `near_clip_parsec` and `far_clip_parsec` to bound the
     distance shell (e.g. `0.1` and `500` for the Pleiades + a
     bit of foreground).
   * `max_visible_objects` to a number you trust C4D to handle —
     start with 10 000.

See [`NAVIGATION_NULL_SYSTEM.md`](NAVIGATION_NULL_SYSTEM.md).

---

## Phase 5 — Build the visible sector

In the **Display** group, pick a colour mode:

* **Natural Star Color** — the standard for stellar-scale shots.
* **Catalog Source** — useful for multi-source scenes where you
  want Gaia / SDSS / DESI / JPL to each be visually distinct.
* **Redshift** — for "the universe is redshifted" shots; works
  best when the catalog is dominated by galaxies / quasars.

Click **Apply View Filter** first to verify the rejection
breakdown looks right (`kept N/M; X far, Y outside cone, Z behind`).
Tighten the cone or pull the navigator if too few survive.

Click **Generate Point Cloud**. The safety system (`100 000`
default cap, navigator gate on) refuses any build that would
exceed those limits — see [`LARGE_DATA_SAFETY.md`](LARGE_DATA_SAFETY.md).

The resulting hierarchy under `UNAV_Starfield → UNAV_VisibleSector`
holds one C4D null per surviving catalog row, with markers
carrying uid + source + type + name + RA/Dec/distance. The full
catalog blob does **not** ride along by default; the inspector
pulls it from the lookup on demand. See
[`POINT_CLOUD_GENERATION.md`](POINT_CLOUD_GENERATION.md).

---

## Phase 6 — Iterate without rebuilding

Move the navigator around. Each time you want to refresh the
scene:

* Click **Sync Visible Sector** rather than *Generate Point Cloud*.
  The diff workflow only adds the newly visible uids and only
  removes the uids that fell out of view; objects that are still
  in view are *untouched* (selection / animation / per-object
  tags survive).

The dialog's status log shows the diff summary:
`+312 added, =1218 kept, -47 removed`. With a typical artist
workflow (small navigator nudges) the kept-count dwarfs the others
and the iteration is essentially free. See
[`SCENE_SYNC_WORKFLOW.md`](SCENE_SYNC_WORKFLOW.md).

For large reshapes (changed `cone_angle_deg`, swapped active
datasets), use **Regenerate Visible Field** to clear and rebuild.

Toggle **Show Debug Cone** when troubleshooting "why did this
object survive / get cut?" — the orange cone visualizes the
current `cone_angle_deg × far_clip_parsec` extent in the
viewport (editor-only; never renders).

---

## Phase 7 — Inspect, label, route

Now that the scene matches the data:

* **Click any UNAV object → Inspect Selected Object** to verify
  the metadata panel shows what you expect (uid, source, RA/Dec,
  distance, magnitude, redshift, raw JSON).
* **Copy Metadata JSON** to paste an object's full record into
  external tools (Slack, JIRA, your render farm's job log).
* **Add Selected Object as Waypoint** to start a flythrough.
  Routes are pure visual — they do not animate the navigator on
  their own (live route playback is on the roadmap), but they
  give you the spline + the focus-here button for snappy
  hand-keyed camera moves. See [`ROUTE_PLANNER.md`](ROUTE_PLANNER.md).

---

## Phase 8 — Save state

When the scene matches your intent:

* **Save UNAV State** writes the navigator parameters, the live
  route, the enabled-dataset list, the visual encoding choice,
  and a snapshot of the user config into:
  1. The C4D document's `BaseContainer` (persists with the
     `.c4d` save).
  2. `~/.unav_pro/projects/<scene-stem>.json` (sidecar for
     cross-machine workflows).
* Save the C4D scene normally. Both halves of the state survive.
* Open the same `.c4d` on another machine: the scene container
  carries the state. **Load UNAV State** restores it.

See [`PERSISTENCE_AND_CONFIG.md`](PERSISTENCE_AND_CONFIG.md).

---

## Phase 9 — Render

UNAV objects are nulls with `NULLOBJECT_DISPLAY_DOT`. They render
in the editor viewport but most third-party render engines ignore
them (this is intentional; it's the point-cloud render path's
explicit non-goal — see
[`POINT_CLOUD_GENERATION.md`](POINT_CLOUD_GENERATION.md) §3 and
[`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md)).

For the MVP, the recommended render strategies are:

1. **Viewport playback / capture.** Use C4D's *Make Preview*
   against the editor viewport; the dots render as drawn.
2. **Manual instance pass.** Replace each null with a low-poly
   sphere or a billboard via *Mograph Cloner → Per Object*. This
   is a one-click conversion in C4D and lets any render engine
   pick them up.
3. **Bake to alembic.** Export the visible sector as Alembic /
   FBX geometry once you're done iterating — the renderer treats
   it as static geometry.

The native render path (a GL `BaseDraw` callback feeding a packed
point buffer + a future TP / matrix render emitter for final
frames) is the headline item in the roadmap.

---

## Sanity checks while working

The plugin's diagnostics + safety strips give you four numbers
to glance at while iterating:

* **Safety strip**: `Mode: Visible-sector only — Generated 1530 / cap 100000`.
* **Status log**: filter rejection breakdown after every action.
* **Diagnostics dialog**: total registered datasets, active
  lookup size, generated count, recent log records.
* **Object Manager**: should *only* show your scene plus the
  three UNAV roots (`UNAV_Navigator`, `UNAV_Starfield`,
  `UNAV_Route`). If anything else has a UNAV marker, **Clear
  Scene** removes it.

If anything is surprising, check the diagnostics panel first —
a single recent log line usually points at the cause (catalog
not loaded, navigator missing, safety override on, …).

---

## Don'ts

* **Don't disable visible-sector-only mode by default.** The
  safety system blocks accidental "materialize-the-universe"
  builds for a reason. Only flip *Allow Full Catalog* when you
  *know* the build is small.
* **Don't embed full metadata into every null** unless you're
  shipping a self-contained `.c4d` to a machine without the
  catalog. Toggle
  `SafetyLimits.embed_full_metadata_in_marker = True` only for
  that handoff.
* **Don't manually re-parent UNAV objects** outside the
  `UNAV_VisibleSector` null. The sync diff walks immediate
  children only; misplaced objects survive *Sync* but not
  *Clear Scene*.
* **Don't generate before saving the registered datasets.** *Load
  Active Datasets* is what populates the inspector; without it,
  every inspection falls back to "marker only" rendering even
  though the catalog is on disk.
