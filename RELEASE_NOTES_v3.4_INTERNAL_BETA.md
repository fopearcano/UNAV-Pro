# UNAV Pro v3.4 — Internal Beta

Release date: 2026-05-10
Codename: *Internal Beta Hardening*

v3.4 is the **internal beta hardening** milestone. Goal:
prepare UNAV for serious internal testing as a stable
Cinema 4D navigation, voyage, animation, and
presentation plugin.

This is **not** a feature phase. **Not** rendering.
**Not** new authoring surfaces. The runtime feature
surface is unchanged from v3.3; v3.4 is consistency
+ release discipline + the scaffolding testers need.

---

## Current feature set (cumulative)

The internal beta exercises everything UNAV does. The
shipped surface:

* **v0.1 → v0.7** — catalog schema, JSONL/CSV I/O,
  spatial filter, sample catalog, navigator null,
  visible-sector point cloud, render-mode dispatch.
* **v0.8 → v1.0** — native point viewer (file-bridge
  protocol, GPU buffer architecture).
* **v1.1 → v1.2** — SQLite catalog backend, time-aware
  schema, time navigator.
* **v1.3** — knowledge layer (classifier, summary,
  glossary, physical interpretation).
* **v1.4 → v1.9** — mission system, voyage tools,
  templates, mission organiser, annotations.
* **v1.7 → v1.8** — stability + cinematic polish.
* **v2.0 → v2.5** — overlays, science layers, animation
  timeline, export pipelines, packaging, docs.
* **v3.0** — large-scale streaming, chunk-reuse cache,
  cooperative task queue, query-timing log.
* **v3.1** — project workspaces, canonical scene
  hierarchy, mission packs, notes system.
* **v3.2** — data provenance, validation reports,
  audit CLI, scientifically self-describing
  exports.
* **v3.3** — presentation sequences, runtime state,
  per-step overlays/annotations, presenter notes,
  Markdown summaries.
* **v3.4** — internal beta hardening (this release).

## Highlights of v3.4

* **Six new health-check probes.**
  `core/health_check.py` gains `python_runtime`,
  `c4d_host`, `workspace`, `active_mission`,
  `visible_sector`, and `presentation`. The
  diagnostics panel now lists 14 probes total.
* **Safe reset tools.** New `core/reset_tools.py`
  with five idempotent operations: Reset UI State,
  Reset Workspace State, Clear Generated UNAV
  Objects, Clear Cache References, Rebuild Scene
  Hierarchy. Pure planning helpers; no on-disk
  artefacts ever touched.
* **State-manager helpers.** `current_workspace` /
  `set_current_workspace` and `current_mission` /
  `set_current_mission` round out the v3.1 / v1.4
  surfaces so the dialog has a single source of
  truth for "what is active right now."
* **Internal beta sample workspace.**
  `samples/internal_beta_demo/` is a self-contained
  v3.1 workspace with five Gaia rows, three JPL
  bodies, a three-stop mission, a route, a
  presentation, and project notes. Walks the
  beta-checklist procedure end-to-end.
* **Test-runner refresh.**
  `scripts/run_tests.py::TEST_CATEGORIES` now
  buckets v25 / v30 / v31 / v32 / v33 / v34 tests
  into named categories so the summary tells you
  "workflow tests OK, scalability tests OK,
  workspace tests OK," etc.
* **Beta checklist.**
  `docs/V3_4_INTERNAL_BETA_CHECKLIST.md` — 17
  numbered sections walking through fresh
  install → reload → reset tools.
* **Troubleshooting refresh.**
  `docs/TROUBLESHOOTING.md` gains a v3.4 reset-
  tools section.

## What didn't change

* No new on-disk schemas. Mission JSON, Route JSON,
  Camera Path JSON, Export Manifest, DB schema,
  binary format, provenance JSON, presentation JSON
  are byte-identical to v3.3.
* No new runtime dependencies. Stdlib-only at
  runtime.
* No rendering, no IPC, no RelativityRender bridge.
* No threading.
* No replacement of core architecture. Every v0.1
  → v3.3 surface continues to work unmodified.

## Known limitations (carried over)

* **No rendering.** UNAV populates the C4D scene;
  Cinema 4D's renderers (Standard / Redshift /
  Octane / Arnold) draw it.
* **Substring search only.** No FTS5 yet.
* **Per-document time-navigator state.** Two C4D
  documents share one process-wide time navigator.
* **Coarse redshift→distance proxy.** Hubble-law
  approximation; not cosmology-grade. Tagged
  `approximate` in every overlay + manifest.
* **No extinction correction** in Gaia distances /
  magnitudes.
* **`Auto Sync`** is still a placeholder; the
  artist clicks `Sync Visible Sector` manually.

See [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md)
for the canonical list.

## Unsupported features (explicit non-goals)

The following are deliberately out of scope for the
internal beta and will remain so:

* **Render engine.** UNAV does not produce images.
* **RelativityRender bridge.** No external renderer
  integration.
* **Sockets / IPC / network protocols.** Offline-
  first.
* **Real-time per-frame visible-sector
  regeneration.** Sync is marker-based, not per-
  frame.
* **Auto-update / online check.** No phone-home.
* **Plugin signing / notarisation.** Maxon's
  distribution doesn't require it.
* **Cosmological inference / scientific publication
  output.** UNAV is a *visualisation* plugin.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) §4 for the
full out-of-scope list.

## Internal beta testing checklist

Walk through
[`docs/V3_4_INTERNAL_BETA_CHECKLIST.md`](docs/V3_4_INTERNAL_BETA_CHECKLIST.md)
on a fresh install:

1. Fresh install
2. Sample project load
3. Gaia sample import
4. JPL sample import
5. Create navigator
6. Sync visible sector
7. Inspect metadata
8. Create mission
9. Bake timeline
10. Create overlays
11. Export package
12. Create presentation
13. Reload C4D scene
14. Reopen workspace
15. Diagnostics + reset tools
16. No regressions (full automated suite)
17. Sign-off

## Installation steps

1. Download `unav_pro-3.4.0.zip` from the GitHub
   release page (or build it locally with
   `python scripts/package_plugin.py`).
2. Quit Cinema 4D 2023+.
3. Unzip into the Cinema 4D plugins folder
   (typically `~/Library/Preferences/Maxon/.../plugins/`
   on macOS or `%APPDATA%\Maxon\...\plugins\` on
   Windows).
4. Restart Cinema 4D.
5. `Extensions → Universal Navigator Pro` opens the
   dialog. The status log's first line shows
   `UNAV Pro v3.4.0 (Internal Beta Hardening; …)`.
6. `Project → Open Workspace…` → point at
   `samples/internal_beta_demo/` to start.

For the long-form guide see
[`docs/INSTALL_C4D_2023_PLUS.md`](docs/INSTALL_C4D_2023_PLUS.md).

## Testing

* Full suite passes: **2344 tests** (2277 v3.3
  baseline + 67 new v3.4 tests).
* New v3.4 test files:
  * `test_v34_reset_tools` — reset planners + reports.
  * `test_v34_health_check` — six new beta probes +
    full-report integration.
  * `test_v34_beta_demo` — bundled internal-beta
    workspace shape + content.
  * `test_v34_run_tests_categories` — verifies the
    test runner buckets every v3.x family
    correctly.

## Acceptance

* [x] Fresh package installs cleanly.
* [x] Sample demo works (`samples/internal_beta_demo/`).
* [x] Health check passes (14 probes).
* [x] No duplicate-object leaks on repeated sync (v3.0
  partial-rebuild planners + v3.4 reset tools).
* [x] Docs match real features (v3.4 doc-cleanup pass).
* [x] Reset tools recover broken states (5 ops; pure +
  idempotent).
* [x] Plugin is ready for internal beta testing.
* [x] No rendering engine assumptions.
* [x] No RelativityRender integration.

## Boundary, restated

UNAV Pro v3.4 is an **astronomical navigation +
voyage / camera-animation tool for Cinema 4D**, scaled
for very large catalogs (v3.0), organised for
production projects (v3.1), trustworthy on real data
(v3.2), guided through presentations (v3.3), and now
hardened for internal beta testing (v3.4).

Rendering, IPC, real-time scientific simulation,
online services, and render-engine bridges remain
explicitly out of scope. See
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4 for the full
list.
