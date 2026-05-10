# UNAV Pro — Technical Director Guide

The TD's reference for UNAV Pro v2.5. Covers the data
pipeline, performance limits, scene-sync model, timeline-
bake model, export package shape, and the safe large-data
workflow.

For the artist-facing reference see
[`USER_MANUAL.md`](USER_MANUAL.md). For the five-minute
install + first-mission run see
[`ARTIST_QUICKSTART.md`](ARTIST_QUICKSTART.md). For the
audit of every internal contract see
[`V1_7_ARCHITECTURE_AUDIT.md`](V1_7_ARCHITECTURE_AUDIT.md)
and [`PLUGIN_LIFECYCLE.md`](PLUGIN_LIFECYCLE.md).

---

## 1. The data pipeline at a glance

```
+----------------------+        +----------------------+
| External survey      |  HTTP  | Preprocessing CLI    |
| (Gaia / SDSS /       |------->| (tools/fetch_*.py)   |
|  DESI / JPL Horizons)|        +----------+-----------+
+----------------------+                   |
                                           v
                                    +-------------+
                                    | JSONL       |
                                    | catalog     |
                                    +------+------+
                                           |
                  +------------------------+------------------------+
                  |                                                 |
                  v                                                 v
            +-------------+                                   +-------------+
            | Spatial idx | <- tools/build_spatial_index.py   | SQLite DB   |  <- tools/import_catalog_to_db.py
            | (cache/<n>) |                                   | (data/*.db) |
            +------+------+                                   +------+------+
                   |                                                  |
                   v                                                  v
            +------------------------------------------------------------+
            | UNAV plugin (C4D)                                          |
            |   navigator pose -> bbox prefilter -> exact cone refine    |
            |   visible sector -> Cinema 4D scene tree                   |
            +------------------------------------------------------------+
```

* **Stdlib-only at runtime.** The plugin runs on the
  Python that Cinema 4D bundles. No external libraries
  required.
* **Offline-first preprocessing.** The CLIs do all HTTP +
  normalisation work; the plugin never makes a network
  call.
* **Streaming visible-sector pipeline.** A million-row
  catalog never enters memory at once.

---

## 2. The canonical schema

`unav_pro/data/schema.py` carries the canonical
`CatalogObject` dataclass:

| Group | Required | Optional |
|-------|----------|----------|
| Identity | `uid`, `catalog_source`, `object_type` | `name`, `common_name` |
| Astrometry | `ra_deg`, `dec_deg` | `distance_parsec`, `parallax_mas`, `redshift`, `radial_velocity_kms`, `proper_motion_ra`, `proper_motion_dec` |
| Photometry | — | `apparent_magnitude`, `absolute_magnitude`, `color_index`, `spectral_type` |
| Free-form | — | `metadata_json` |
| Computed | — | `cartesian_x/y/z`, `c4d_x/y/z`, `render_radius`, `display_color_rgb` |

Coordinate convention: ICRS spherical (ra, dec, distance)
→ ICRS Cartesian (parsec) → Cinema 4D world units (via the
active scale mode). Right-handed system, Y-up.

Adapters may extend the `OBJECT_TYPES` list at ingest time;
the plugin treats unknown types as `"unknown"` for
rendering.

---

## 3. DB import + query

### 3.1 Importing

```bash
python tools/import_catalog_to_db.py \
    --input data/gaia_pleiades.jsonl \
    --db data/unav.db
```

The importer creates the v1.1 SQLite schema (schema_version
= 2 includes the v1.2 `object_states` table). B-tree
indexes on `cartesian_x/y/z` make the bbox prefilter the
fast path.

See [`SQL_SCHEMA.md`](SQL_SCHEMA.md) and
[`DB_IMPORT_WORKFLOW.md`](DB_IMPORT_WORKFLOW.md).

### 3.2 Cone query

The visible-sector pipeline runs a two-step query:

1. **Bbox prefilter** (SQL, indexed). Pulls the candidate
   set inside the navigator's axis-aligned bounding box.
2. **Exact cone refine** (Python). Drops candidates outside
   the actual cone.

The v1.7 stabilisation milestone added a SQL `LIMIT`
derived from `max_visible_objects × 4` so the working
memory stays bounded on million-row catalogs.

Performance reference (1M-row Gaia DR3 subset, modern
laptop):

* Bbox prefilter: **single-digit ms**.
* Cone refine: **~10–50 ms** depending on cap.
* Scene-sync diff + materialisation: dominated by the C4D
  scene-tree mutation cost.

See [`SPATIAL_QUERY_STRATEGY.md`](SPATIAL_QUERY_STRATEGY.md)
and [`V1_1_QUERY_ENGINE.md`](V1_1_QUERY_ENGINE.md).

---

## 4. Cache + index behaviour

The chunked spatial index lives at
`cache/<dataset>/index.json` plus per-cell JSONL chunks. The
JSONL streamer (`core/sector_streaming`) loads only the
cells the cone touches.

The cache directory is treated as **regenerable**. The
plugin never writes catalog content into `cache/`; the
preprocessing CLIs do. Deleting the cache and re-running
the index build is always safe.

---

## 5. Performance limits

| Surface | Cap / behaviour |
|---------|-----------------|
| `max_visible_objects` | The navigator's safety cap. Visible-sector pipeline + render backend honour it. |
| `bbox_max_rows` | Auto-derived from `max_visible_objects × 4` when not explicitly set (v1.7+). |
| `MAX_WAYPOINTS_PER_MISSION` | 200 per mission. |
| `MAX_FRAMES_FOR_BAKE` | 36 000 frames (10 min @ 60 fps). |
| `MAX_MOTION_VECTORS` | 5 000 motion-vector lines per science-layer build. |
| `MAX_MARKERS_PER_BAKE` | 4 096 UNAV-tagged timeline markers per bake. |
| `MAX_FILE_SIZE_BYTES` | 5 MB per file in the release zip. |

These are the *hard caps*. Soft hints (sync-marker count >
32, dataset row count, etc.) emit warnings but don't refuse
the operation. The dialog log surfaces every warning.

---

## 6. Scene-sync model

The visible sector lives at:

```
UNAV_Starfield/
  UNAV_VisibleSector/
    <one Onull per visible object>
```

`UNAV_Overlays/` (v2.0) and `UNAV_ScienceLayers/` (v2.1)
are siblings of `UNAV_Starfield`. The three roots never
walk under each other.

### 6.1 The compute_diff contract

`core.scene_sync.compute_diff(current_uids, wanted_uids,
max_visible)` returns a `SyncDiff`:

* `added_uids` — present in `wanted` but not in `current`.
* `kept_uids` — present in both.
* `removed_uids` — present in `current` but not in `wanted`.
* `capped_uids` — count of UIDs dropped by
  `max_visible_objects`.

The diff is **deterministic**: same inputs → same
SyncDiff. Idempotency is the v1.7 contract: re-running a
sync against the same scene + same wanted set produces no
adds and no removes.

### 6.2 Mode-switch safety

Switching render modes (debug-objects ↔ instances ↔ point-
cloud ↔ native-viewer) reuses the same UID-keyed marker
container on every backend, so the diff cleans up the
previous mode's children whether or not the UIDs have
changed.

---

## 7. Timeline-bake model

`bake_mission_to_timeline(mission, path, frame_range,
config, navigator, camera, doc)` is the v2.2 high-level
baker. It runs three phases in one transactional pass:

1. **Evaluate** the v2.2 animated state (`evaluate_animated_state`)
   — produces one `AnimatedSample` per frame.
2. **Apply keyframes** (`apply_keyframes`) — writes camera
   + navigator position / rotation / optional FOV.
3. **Apply markers** (`apply_markers`) — drops UNAV-tagged
   markers (waypoint / epoch / sync / science).

The bake **never** triggers a visible-sector sync. Sync
markers are *requests* the dialog (or a future SceneHook)
honours separately.

The pure-Python `evaluate_animated_state` is testable
without Cinema 4D and is byte-deterministic. The C4D-bound
appliers no-op outside the host.

---

## 8. Export package structure

```
UNAV_Export/
  manifest.json          # schema + version + units + coordinate convention + asset inventory
  missions/              # one v1.4 mission JSON per file
  routes/                # one v0.6 route JSON per file
  timelines/             # one flat keyframe JSON per label
  camera_paths/          # one DCC-agnostic camera-exchange JSON per label
  datasets/              # science_layers.json + dataset metadata
  summaries/             # dataset_summary.json + per-mission analytics
  docs/                  # caller-supplied Markdown
```

Every file goes through the v1.7 atomic-write helper. The
manifest is written *last*, so a partial export on a
crashed machine looks like:

* `manifest.json` present + every listed file present
  (success), or
* `manifest.json` absent + some files present (artist
  re-runs).

Filename hygiene: mission titles with `/`, `:`, etc. are
sanitised. Per-file size cap from the package builder is
soft (it logs + skips).

See [`V2_3_EXPORT_PIPELINES.md`](V2_3_EXPORT_PIPELINES.md)
and [`EXPORT_PACKAGE_FORMAT.md`](EXPORT_PACKAGE_FORMAT.md).

---

## 9. Safe large-data workflow

For catalogs above ~1M rows:

1. **Use the DB-backed path.** SQLite + indexed columns are
   an order of magnitude faster than chunked JSONL on the
   same hardware.
2. **Split the dataset.** The dataset registry handles
   multiple entries cleanly; UNAV's merge step namespaces
   uids per-entry so collisions are impossible.
3. **Set `max_visible_objects` conservatively.** 50 000 is
   typical for cinematic playback on a workstation; 100 000
   is the safety cap for authoring.
4. **Narrow the navigator's cone.** A 90° cone with a 1 kpc
   far clip is much more expensive than a 30° cone with a
   100 pc far clip.
5. **Enable namespace-by-default.** Source-prefixed uids
   (`<dataset>:<original-uid>`) survive cross-catalog
   merges without collisions.

The v1.7 `state_manager.health_summary()` reports per-
dataset row counts; the diagnostics panel renders them on
demand.

---

## 10. The plugin lifecycle

* **Open** — `unav_plugin.pyp` registers the dialog command
  on Cinema 4D startup. The dialog itself is constructed
  on first menu click.
* **Init** — `InitValues` lazily loads config / bookmarks /
  metadata lookup / time-navigator state. The dataset
  registry loads on first dataset-touching click.
* **Sync** — visible-sector pipeline runs on explicit
  click. Never per-frame, never on idle.
* **Bake** — explicit click. Pure-Python evaluation +
  scene-tree write in one transactional pass.
* **Save UNAV State** — explicit click. Persists every
  state surface to `~/.unav_pro/projects/<scene>.json`
  and the C4D document's BaseContainer.
* **Close** — closing the dialog window leaves the
  singletons alive in the host's Python interpreter; the
  artist can re-open without losing state.

See [`PLUGIN_LIFECYCLE.md`](PLUGIN_LIFECYCLE.md).

---

## 11. The state surfaces

Five on-disk persistence files, all under `~/.unav_pro/`:

| File | Contents | Atomic? |
|------|----------|---------|
| `config.json` | Per-user preferences. | yes (v1.7) |
| `bookmarks.json` | Saved navigator anchors. | yes (v1.7) |
| `datasets.json` | Dataset registry. | yes (v1.7) |
| `projects/<scene>.json` | Per-scene project state. | yes (v1.7) |
| `missions/<id>.json` | Mission library (one file per mission). | yes (v1.7) |

All five round-trip through `core.config.safe_write_json`
(temp file + rename). A crash mid-write cannot truncate a
previously valid file.

---

## 12. Diagnostics

Two top-level entry points:

* `core.health_check.run_health_check()` — eight pre-flight
  probes; renders as a plain-text report.
* `core.state_manager.health_summary()` — per-subsystem
  status (config, bookmarks, datasets, time-navigator,
  metadata-lookup, missions).

Both are exposed in the diagnostics panel; both are pure-
Python and run outside Cinema 4D.

The dialog's ring-buffer log captures the last 500 records
(`core.logger.RingBufferHandler`); the diagnostics panel
renders them on demand. Long-running issues also flow to
the rotating file at `~/.unav_pro/logs/unav_pro.log`.

---

## 13. Acceptance + verification

Every release runs through the QA checklist in
[`QA_CHECKLIST.md`](QA_CHECKLIST.md):

* `python scripts/run_tests.py` passes.
* `python scripts/package_plugin.py` produces a valid zip.
* `python -c "from unav_pro.core.health_check import
  run_health_check; print(run_health_check().render())"` is
  all green.
* The Cinema 4D smoke test (install → sync → mission →
  bake → export) passes against the bundled
  `samples/minimal_unav_demo/`.
* Saved state from previous releases loads cleanly.

For the full release ritual see
[`PACKAGING.md`](PACKAGING.md) and
[`V2_4_RELEASE_PREP.md`](V2_4_RELEASE_PREP.md).
