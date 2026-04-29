# TODO — v0.2

The v0.2 backlog. Ordered roughly by user-visible payoff per unit
of work. Each item references the deeper rationale in
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) and the migration
plan in [`docs/ROADMAP_CPP_GPU_VERSION.md`](docs/ROADMAP_CPP_GPU_VERSION.md)
where applicable.

## P0 — User-visible quality of life (Python only)

These ship without any native code. Each is a small commit on
top of the v0.1 surfaces.

* **Auto-load on scene open.** Hook a `MessageData` listener for
  `MSG_DOCUMENTINFO_TYPE_LOAD`; when fired, run
  `mock_actions.load_unav_state` automatically when the user's
  config has `auto_load_state = True`. (LIMITATIONS §10.)
* **Connector retries with backoff.** Wrap `_http_fetch` in each
  connector with a small retry loop that respects HTTP 429 /
  503 *Retry-After*. The CLI exit-code contract stays the same.
  (LIMITATIONS §13.)
* **Multiple-match disambiguation in the JPL CLI.** When
  Horizons returns ambiguous candidates today the connector
  raises; the CLI can instead print the candidate list and
  re-prompt with a NAIF ID. (See `docs/JPL_HORIZONS_CONNECTOR.md`
  §7.)
* **Bulk *Build Index* in the dataset manager.** A "Build Index
  for all unindexed datasets" button. (See
  `docs/DATASET_MANAGER.md` §11.)
* **Refresh-on-toggle for the safety strip.** The status line
  already re-renders on Refresh; toggling Allow Full Catalog
  should also refresh.
* **Live route playback.** Per-frame interpolator + keyframe
  writer that animates the navigator along the route spline.
  (LIMITATIONS §3.)

## P1 — Headline scaling work (Python prototype)

Numpy / pyarrow vectorization. No native code yet; preprocessing
ergonomics improve, runtime stays stdlib-only at the C4D-bundled
interpreter unless the user opts in.

* **Phase A of the migration plan.** Replace the Python loops in
  `core.spatial_filter.apply_filter`,
  `data.catalog_io._load_jsonl`, and
  `core.spatial_index.build_index` with numpy / pyarrow code.
  Targets ~10× ingest + filter speedup. (ROADMAP §3 Phase A.)
* **Multi-process index build.** Parallel-process the
  cell-bucketing in `core.spatial_index.build_index` so a 10 M-
  row Gaia subset finishes in minutes, not hours. (LIMITATIONS
  §7.)
* **Cosmology-aware distance helper.** A FlatLambdaCDM
  integrator `redshift_to_distance(z, h0, omega_m)` that the
  SDSS / DESI connectors call when `z > 0.1`. Optional pyarrow
  / numpy dependency for the offline pipeline only.
  (LIMITATIONS §4.)

## P1 — Headline scaling work (C++ engine)

Once the Python prototype proves the contract, the native engine
takes over the hot paths. The contract that must survive is
spelled out in
[`docs/ROADMAP_CPP_GPU_VERSION.md`](docs/ROADMAP_CPP_GPU_VERSION.md)
§5.

* **Phase B of the migration plan.** Replace per-row `Onull`
  materializer with a single `c4d.MatrixObject` carrying an
  array of `Matrix` instances. Per-instance metadata moves to
  a side-car array on the parent's marker container. Headroom:
  100 k → 200 k objects. (ROADMAP §3 Phase B.)
* **Phase C (multi-month).** C++ `ObjectData` plugin with packed
  point buffer + `ViewportDraw` callback. The headline
  migration; gates phase D / E. (ROADMAP §3 Phase C.)

## P2 — Production hardening

* **Replace dev-range plugin IDs.** Allocate real IDs from
  Maxon's PluginCafe and bump the schema version before public
  distribution. (LIMITATIONS §11.)
* **Catalog crossmatch.** Implement the `match_group_id` field
  the schema reserves; per-region k-d tree on Cartesian-pc
  positions with a tolerance table per source pair.
  (LIMITATIONS §5.)
* **`.unavbake` round-trip.** Bake-and-write the format
  documented in `UNAV_PRO_ARCHITECTURE.md` §3.9. Ships a
  filtered subset alongside a `.c4d` for cross-machine handoff.
  (LIMITATIONS §9.)
* **Catalog signing.** Record SHA-256 of every registered
  catalog file in the dataset registry stats; warn on mismatch
  at *Load Active Datasets* time.

## P2 — UX polish

* **Tabbed dialog redesign.** Promote the seven conceptual
  groups (`Display` / `Safety` / `Visible Sector` / `Actions` /
  `Status Log` / `Metadata Inspector` / `Route Planner`) into
  literal tabs. (LIMITATIONS §12.)
* **Per-waypoint focus picker in the route panel.** Combo box
  to pick any waypoint by index instead of always focusing on
  the last-added one.
* **Per-source visual encoding overrides.** A multi-source
  scene that wants Gaia in spectral colour and DESI in redshift
  colour simultaneously needs the encoding picker to operate
  per-dataset.

## P2 — Diagnostics + observability

* **Async log streaming.** A `MessageData` hook that re-renders
  the diagnostics panel periodically so the user sees logs
  flowing live during long-running actions.
* **Issue bundle export.** Combine the diagnostics text with
  the rolled log file into a zip that the user can attach to a
  support ticket.
* **Inline crash reporter.** Catch unhandled exceptions in
  dialog commands and append a fully-rendered traceback to the
  diagnostics panel.

## P3 — Future, big swings

These show up in the roadmap but are not committed targets for
v0.2. Listed here so they don't get lost.

* **GPU compute filter** (ROADMAP Phase D).
* **Real-time sector streaming** (ROADMAP Phase E).
* **Binary chunk format** (ROADMAP Phase F + LIMITATIONS §7).
* **Per-renderer instance integrations** (ROADMAP Phase G):
  Standard / Physical via MatrixObject, Redshift / Octane /
  Cycles via per-renderer SDKs.

## Definition of done — v0.2

* All P0 items shipped.
* At least one of the P1 native phases (B *or* numpy
  vectorization) merged and benchmarked.
* All v0.2 features documented under `docs/`; `LIMITATIONS.md`
  trimmed of items now done; `ROADMAP_CPP_GPU_VERSION.md`
  updated to mark phases complete.
* `CHANGELOG.md` `[0.2.0]` entry written.
* `RELEASE_NOTES_v0.2.md` cut.
* All tests green; no new credentials, hardcoded paths, or
  huge committed files.
* Dev-range plugin IDs replaced **only if** the milestone is the
  external public release; otherwise carry forward to v1.0.
