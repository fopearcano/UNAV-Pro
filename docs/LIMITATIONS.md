# UNAV Pro — Known Limitations

What the plugin doesn't do yet, and the rationale for each gap.
The complete migration plan beyond the Python prototype is in
[`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md);
this document is the user-facing "no, that doesn't work yet"
list.

---

## 1. Scale: ≤ 100 000 objects per scene

**Hard cap (default).** The safety system refuses to materialize
more than 100 000 C4D nulls per build. Above ~ 10 000 the
viewport gets noticeably less responsive on selection / undo /
redraw.

**Why.** Each catalog object is a dedicated `c4d.BaseObject`
allocated through Cinema 4D's Python API. The cost is not in
math (the spatial filter handles 1 M rows in well under a
second) but in C4D's per-object overhead: marker container,
display flags, undo stack entries, MSG_DRAW callbacks. The
GIL-bound Python builder produces these one at a time.

**Impact.** Any scene above this scale needs the C++ /
matrix-instance / GPU render path described in
[`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md). Today
the workflow is *filter aggressively, render the visible
sector*.

---

## 2. No real-time / animated navigation

**Auto Sync is a placeholder.** The checkbox in the dialog logs
`Auto Sync: not yet implemented; click Sync Visible Sector
manually.` *Sync Visible Sector* is user-triggered.

**Why.** Per-frame re-sync requires a `MessageData` listener on
the navigator's transformation, a debouncer (so dragging the
navigator doesn't flood the engine), and the same cone-vs-tile
prefilter the offline pipeline already implements — it is a
small piece of work, deferred until the rest of the workflow
proved stable.

**Workaround.** Click *Sync Visible Sector* whenever you want to
refresh after moving the navigator. Diff-based updates are fast
enough that this is acceptable for stills; flythroughs need the
roadmap path.

---

## 3. No live route playback

**Routes draw splines and snap the navigator** to a chosen
waypoint. They do not animate the navigator along the spline.

**Why.** Animation requires a per-frame interpolator + a
keyframe writer. The data model is in place
([`ROUTE_PLANNER.md`](ROUTE_PLANNER.md)), the c4d-bound writer
is not.

**Workaround.** Use *Build Route Spline* to draw the path, then
attach a C4D camera with an *Align to Spline* tag. Keyframe the
spline position manually.

---

## 4. Cosmology-aware distances

**High-redshift quasars sit on a placeholder sphere.**
`safe_redshift_to_distance` for SDSS and DESI applies a coarse
Hubble-law inversion `d = c·z / H₀` only when `0 < z ≤ 0.1`.
Above that the naive inversion diverges from comoving distance
significantly and the row's `distance_parsec` stays `None`.

**Why.** Proper cosmology-aware distances need a FlatLambdaCDM
integrator with `(Ω_m, Ω_Λ)` parameters and a redshift-velocity
kernel. The MVP keeps things deterministic and physically
honest by refusing the bad approximation rather than producing
plausible-looking nonsense.

**Workaround.** Visualization scenes with high-z objects render
them on the placeholder sphere; the metadata inspector still
shows the redshift. For scientifically meaningful cosmological
distances, pre-compute them externally (`astropy.cosmology`)
and inject a `distance_parsec` column into the JSONL before
ingestion.

---

## 5. No catalog crossmatch

**Two catalogs that describe the same physical object** (e.g.
the same star in Gaia and Hipparcos) appear in the merged
lookup as two separate uids with no link between them.

**Why.** The pipeline's planned `match_group_id` field
([`UNAV_PRO_DATA_PIPELINE.md`](UNAV_PRO_DATA_PIPELINE.md) §7) is
defined but not implemented. The crossmatch stage requires a
per-region k-d tree over Cartesian-pc positions plus a tolerance
table by source pair, which is a real chunk of code.

**Workaround.** Pick one catalog as authoritative for a given
region; disable the rest.

---

## 6. Render-pass parity

**UNAV objects are nulls** with `NULLOBJECT_DISPLAY_DOT`. They
appear in the C4D editor viewport but most third-party render
engines either ignore them or render them as invisible
locators.

**Why.** Nulls are the cheapest cross-version C4D primitive;
they make the diff-and-update workflow correct and the marker-
based selection clean. A *Thinking Particles* / matrix-instance
render emitter is the next-but-not-yet feature
([`POINT_CLOUD_GENERATION.md`](POINT_CLOUD_GENERATION.md) §3).

**Workaround.** *Mograph Cloner → Per Object* against a low-poly
sphere is a one-click bridge for final renders. Or bake the
visible sector to Alembic and import as static geometry.

---

## 7. Single-threaded ingest

**`build_spatial_index` is a Python `for` loop.** A 10 M-row
catalog takes minutes on a single core; the index isn't
incremental.

**Why.** The MVP optimizes for clarity, correctness, and zero-
dependency. Numpy vectorization of the bucketing is a one-commit
change; multi-process parallelism is one commit on top of that.
Both deferred until measurements demand them.

**Workaround.** For huge catalogs, partition by sky region
(a script wrapper around the Gaia connector's
`--ra/--dec/--radius-deg`), index each partition separately,
register them as separate datasets in the manager.

---

## 8. No incremental persistence

**Save UNAV State** writes the whole snapshot every time. A 1 MB
state isn't a problem, but a project with hundreds of route
waypoints and thousands of registered datasets would benefit
from delta-only saves. Today the path is full-rewrite.

**Why.** State sizes haven't approached the threshold where this
matters. The two-storage-path strategy (BaseContainer + sidecar)
already provides crash robustness; incremental writes are a
correctness simplification, not a survival feature.

---

## 9. No bake / `.unavbake` round-trip

**The plugin never produces a self-contained baked dataset
file.** The architecture doc ([`UNAV_PRO_ARCHITECTURE.md`](UNAV_PRO_ARCHITECTURE.md)
§3.9) defines a `.unavbake` format for shipping a filtered
catalog with the `.c4d` to a machine without the source data;
the bake operation is not implemented yet.

**Why.** Bake is a write-only thing whose only consumer is "open
this scene on a machine without the catalog cache." That
workflow is well-served today by the
`embed_full_metadata_in_marker = True` safety opt-out: at the
cost of a larger save, the .c4d carries every row's metadata
inside its own BaseContainers.

**Workaround.** Toggle the safety flag, save, ship the `.c4d`.
Or zip the relevant dataset files alongside the `.c4d`.

---

## 10. No Auto-load on scene open

**`UnavConfig.auto_load_state = True` is a config flag without
a listener.** The state in a `.c4d`'s BaseContainer is real, but
the user has to click *Load UNAV State* to apply it after
reopening.

**Why.** Implementing it requires a `MessageData` plugin
listening for `MSG_DOCUMENTINFO_TYPE_LOAD`. Same story as the
auto-sync — small bit of work, not yet wired.

**Workaround.** Click *Load UNAV State* after opening a saved
scene.

---

## 11. Plugin IDs are placeholders

**The plugin IDs in `core/plugin_ids.py`** are in the
development-range (1 000 001–1 000 010). For a public release
they must be replaced with IDs registered with Maxon's
PluginCafe.

**Why.** Plugin IDs are a Maxon-managed resource; allocating them
costs nothing but is a deliberate public-release step.

**Impact.** None during development or in-house use; before
distributing the plugin externally, re-issue the IDs and bump
the schema version.

---

## 12. UI scale

**The main dialog has grown to 16 buttons + 4 panels + 5
controls.** It works, but a tabbed redesign would help discover-
ability. The existing groups (`Display` / `Safety` / `Visible
Sector` / `Actions` / `Status Log` / `Metadata Inspector` /
`Route Planner`) are conceptual tabs; making them literal tabs
is a `c4d.gui.GeDialog` layout change, not an API change.

**Why.** Tabs in Cinema 4D `GeDialog` aren't first-class. They
require nested groups + manual show/hide on a tab bar. The MVP
optimizes for "every control is one click away" over discover-
ability.

---

## 13. Connectors don't retry

**Network failures fail.** The four connectors raise
`<Source>QueryError` on HTTP non-200 / connection error; the
CLI exits with status 3.

**Why.** Backoff-and-retry is a small amount of code (a loop
plus `time.sleep`), but it interacts badly with archive rate-
limiting (HTTP 429) and would mask real outages on the public
endpoints.

**Workaround.** Wait, rerun. Or wrap the CLI in your own retry
loop that respects the archive's documented rate limit.

---

## When you hit a limitation

1. Check this document and the per-feature deep doc for the
   feature you're using.
2. Open the **Diagnostics** dialog, click **Copy Diagnostics**,
   look at the recent log records — most "why didn't it work?"
   answers are in there.
3. The roadmap in [`ROADMAP_CPP_GPU_VERSION.md`](ROADMAP_CPP_GPU_VERSION.md)
   is honest about which limitations the Python prototype can
   solve incrementally and which require the native /
   GPU-accelerated successor.
