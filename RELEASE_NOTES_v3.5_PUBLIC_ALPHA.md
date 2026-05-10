# UNAV Pro v3.5 — Public Alpha

Release date: 2026-05-10
Codename: *Public Alpha*

v3.5 is the **public alpha** release of UNAV Pro — a
Cinema 4D 2023+ plug-in for astronomical navigation,
voyage / camera animation, and guided presentations.

This is **not** a feature phase. **Not** rendering.
**Not** new authoring surfaces. v3.45 runtime preserved
byte-for-byte; v3.5 is packaging + communication +
first-user readiness.

For the artist guide read
[`docs/PUBLIC_ALPHA_TESTING_GUIDE.md`](docs/PUBLIC_ALPHA_TESTING_GUIDE.md).
For the install steps read
[`docs/INSTALL_C4D_2023_PLUS.md`](docs/INSTALL_C4D_2023_PLUS.md).
For the first-run walkthrough read
[`docs/FIRST_RUN_GUIDE.md`](docs/FIRST_RUN_GUIDE.md).
For bug reports read
[`docs/ISSUE_REPORTING.md`](docs/ISSUE_REPORTING.md).

---

## Feature summary (cumulative)

The public alpha exercises the full v0.1 → v3.45
feature surface:

* **Real catalog ingestion** — Gaia DR3, SDSS DR18,
  DESI EDR, JPL Horizons via offline preprocessing
  CLIs that emit UNAV-format JSONL.
* **Spatial indexing** — chunked per-cell JSONL +
  v1.1 SQLite back end with bbox-prefiltered cone
  queries.
* **Navigator-bounded scene** — `UNAV_Navigator`
  null defines origin + forward + cone half-angle +
  clip range; only catalog rows passing the cone
  materialise.
* **Diff-and-update sync** — `Sync Visible Sector`
  adds / keeps / removes; selection survives.
* **Time navigator** — Julian-date model + proper-
  motion propagation + JPL ephemeris snapshot
  resolution.
* **Knowledge layer** — deterministic classifier +
  plain-text summary + glossary + physical
  interpretation.
* **Mission system** — waypoints, Catmull-Rom +
  slerp camera path, deterministic playback.
* **Voyage tools** — templates, route analytics,
  mission organiser, annotations, exporters.
* **Procedural overlays** — grid, galactic /
  ecliptic planes, distance rings, sector cone,
  route corridor, waypoint labels.
* **Astrophysical science layers** — distance /
  redshift / magnitude shells, motion vectors,
  catalog source regions, solar-system orbits,
  density / constellation placeholders.
* **Animation timeline** — frame-aware
  `AnimatedSample`, sync markers, epoch-change
  frames, baked PSR + FOV tracks.
* **Export pipelines** — Mission JSON, Route JSON,
  CSV, Markdown, Camera Path JSON, Timeline JSON,
  Science Layer JSON, Dataset Summary JSON, plus
  the v2.3 export package + manifest.
* **Large-scale streaming (v3.0)** — chunk-reuse
  cache, paged loading, cooperative task queue,
  query timing log.
* **Project workspaces (v3.1)** — eight-subdir
  directory tree + manifest + mission packs +
  notes system.
* **Data integrity (v3.2)** — provenance records,
  validation reports, audit CLI, scientifically
  self-describing exports.
* **Presentation mode (v3.3)** — declarative
  sequences, runtime state, per-step overlays /
  annotations, presenter notes, Markdown
  summaries.
* **Internal beta hardening (v3.4)** — six new
  health probes, safe reset tools, internal beta
  sample workspace, refreshed test runner.
* **Native C4D integration (v3.45)** — declarative
  undo policy + `UndoSession`, central
  deterministic naming, lifecycle planner,
  Object Manager view, viewport visibility
  profiles + label clutter policy.

## Highlights of v3.5

* **Apache 2.0 LICENSE.** Added to repository
  root.
* **NOTICE.md.** Required attribution + bundled-
  data disclosure.
* **`docs/DATA_SOURCE_ATTRIBUTION.md`** — per-
  source citation + license notes (Gaia, SDSS,
  DESI, JPL Horizons, bundled samples).
* **Issue report bundle** —
  `unav_pro/core/issue_report.py` produces a
  Markdown document with environment + state +
  health + log tail. Surfaced as
  *Diagnostics → Create Issue Report*.
* **First-run experience** —
  `unav_pro/core/first_run.py` produces a
  welcome banner + per-stage next-step
  recommendation. Drives the dialog's *Welcome*
  panel.
* **Three new docs:**
  * `docs/PUBLIC_ALPHA_TESTING_GUIDE.md` —
    canonical "what to test" guide.
  * `docs/ISSUE_REPORTING.md` — how to file a
    bug.
  * `docs/FIRST_RUN_GUIDE.md` — first-ten-minutes
    walkthrough.
* **Packaging cleanup.** `scripts/package_plugin.py`
  ships LICENSE + NOTICE.md + the new docs.
  Excludes generated / cache / dist artefacts as
  before; the v3.5 zip stays under 2 MB.
* **README — public-facing intro.** A new banner
  + Issue Reporting section near the top so a
  first-time visitor doesn't need to scroll
  through milestone history to find install +
  bug-reporting.

## Tested environment

| OS | Cinema 4D | Python | Status |
| --- | --- | --- | --- |
| macOS 14 / 15 | 2024.5+, 2025 | 3.11.x | known good |
| Windows 11 | 2024.5+, 2025 | 3.11.x | known good |
| Linux (CLI tools only) | n/a | 3.10 / 3.11 | known good |

Anything outside this matrix is *probably* fine.
Bug reports welcome.

## Required dependencies

* **Cinema 4D 2023+** (API ≥ 26000). Older hosts
  refuse to register the plug-in.
* **Python**: comes with Cinema 4D — no extra
  install needed.
* **Optional**: `pytest` for running the test
  suite outside Cinema 4D.

There are **no** pip dependencies at runtime. UNAV
is stdlib-only.

## Installation

1. Download `unav_pro-3.5.0.zip` from the GitHub
   release page.
2. Quit Cinema 4D.
3. Unzip into the Cinema 4D plug-ins folder
   (macOS: `~/Library/Preferences/Maxon/.../plugins/`;
   Windows: `%APPDATA%\Maxon\...\plugins\`).
4. Restart Cinema 4D.
5. `Extensions → Universal Navigator Pro` opens
   the dialog. The first line of the status log
   reads `UNAV Pro v3.5.0 (Public Alpha; …)`.
6. `Project → Open Workspace…` → point at
   `samples/internal_beta_demo/` (bundled inside
   the release zip).

For the long-form install guide see
[`docs/INSTALL_C4D_2023_PLUS.md`](docs/INSTALL_C4D_2023_PLUS.md).

## Known limitations

The full canonical list lives in
[`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).
Highlights:

* **No rendering.** UNAV populates the C4D scene;
  C4D's renderers (Standard / Redshift / Octane /
  Arnold) draw it.
* **No multi-process scaling.** UNAV is single-
  threaded and single-process. The v3.0 task
  queue is cooperative.
* **`Auto Sync` placeholder.** Click *Sync
  Visible Sector* manually.
* **Substring search.** No FTS5 yet.
* **Per-document time-navigator state.** Two C4D
  documents share one process-wide time
  navigator; the v3.x ROADMAP §2 plans a per-
  document split.
* **Coarse redshift→distance proxy.** Hubble-law
  approximation only; loudly tagged
  `approximate`.
* **No extinction correction** in Gaia distances /
  magnitudes.

## Unstable areas (may evolve before v4)

* Workflow profile names + label-clutter defaults
  (v3.45).
* Some health-check probe wording.
* Some status-log message wording.
* Some panel layouts on small displays.

If you build downstream tooling, key on the v3.x
schema files (stable) rather than panel strings.

## Expected bugs (don't file these)

* `Auto Sync` is a placeholder — that's by design.
* The redshift→distance proxy is loudly tagged
  `approximate` — that's by design.
* Two C4D docs share one time-navigator state — on
  the v3.x ROADMAP.
* Some panels squeeze on 13"-class displays — UI
  polish is a v4.x candidate.

## Feedback we want most

Listed in [`docs/PUBLIC_ALPHA_TESTING_GUIDE.md`](docs/PUBLIC_ALPHA_TESTING_GUIDE.md)
§6:

1. Crashes + hangs.
2. Workflow friction (buttons in wrong place,
   confusing copy).
3. Data integrity (catalog rows that load wrong;
   provenance mismatches).
4. Documentation gaps.
5. Determinism regressions.
6. Performance on heavy datasets.

## Acceptance

* [x] Public alpha zip builds cleanly.
* [x] README is user-facing.
* [x] LICENSE + NOTICE.md +
  `docs/DATA_SOURCE_ATTRIBUTION.md` exist.
* [x] Package contains no heavy / generated data.
* [x] First-run guidance is clear (welcome
  banner + 5-stage recommendation engine).
* [x] Issue report bundle works (Markdown
  Markdown; safe content; deterministic).
* [x] Known limitations are honest
  (canonical list referenced from every public
  doc).
* [x] No rendering engine assumptions.
* [x] No RelativityRender integration.

## Testing

* Full suite passes: **2488 v3.45 baseline + new
  v3.5 tests** (counts in the v3.5 commit).
* New v3.5 test files:
  * `test_v35_issue_report` — bundle generation,
    log-tail trimming, defensive probes.
  * `test_v35_first_run` — stage classification,
    recommendation messages, welcome banner.
  * `test_v35_package_manifest` — LICENSE +
    NOTICE inclusion in the package.
  * `test_v35_release_artifacts` — public-alpha
    artefacts present + correctly versioned.

## Boundary, restated

UNAV Pro v3.5 is a public-alpha **astronomical
navigation + voyage / camera-animation tool for
Cinema 4D**. Rendering, IPC, real-time scientific
simulation, online services, and render-engine
bridges remain explicitly out of scope. See
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4.

## Thanks

This alpha exists because someone is going to find
the weird interaction nobody on the maintainer side
has seen. Thank you for running it through.
