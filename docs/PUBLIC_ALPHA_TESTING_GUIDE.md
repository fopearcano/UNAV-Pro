# UNAV Pro — Public Alpha Testing Guide

Welcome to the UNAV Pro public alpha. This guide tells
you what to expect, how to install, what to test, and
how to report what you find.

For the install steps + per-OS notes see
[`INSTALL_C4D_2023_PLUS.md`](INSTALL_C4D_2023_PLUS.md).
For first-launch help see
[`FIRST_RUN_GUIDE.md`](FIRST_RUN_GUIDE.md). For bug
reports see [`ISSUE_REPORTING.md`](ISSUE_REPORTING.md).

---

## 1. What this alpha is

UNAV Pro v3.5 is a **public alpha** of an astronomical
navigation + voyage / camera-animation plug-in for
**Cinema 4D 2023+**. The plug-in:

* loads real catalog data (Gaia, SDSS, DESI, JPL
  Horizons) into a Cinema 4D scene;
* lets you plan camera movement through it via
  missions, routes, and a v1.4 voyage system;
* bakes the camera path to the timeline so Cinema
  4D's renderers (Standard / Redshift / Octane /
  Arnold) can render it;
* organises everything inside a v3.1 project
  workspace + supports v3.3 guided presentations.

This is **not** a beta. Expect rough edges. Expect to
file bugs. The **tested environment** matrix below
captures what we've actually run; everything else is
"should work" rather than "verified."

## 2. What this alpha is not

* **Not a renderer.** UNAV populates the scene; Cinema
  4D's renderers draw it. There are no shaders, no
  render kernels, no real-time preview engine.
* **Not a cosmology engine.** The redshift→distance
  helper is a coarse Hubble-law proxy; magnitude
  shells are cosmetic. See
  [`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md).
* **Not a network service.** UNAV is offline-first.
  The connectors fetch *once*, write JSONL to disk,
  and the plug-in reads from disk thereafter. The
  plug-in opens no sockets.
* **Not a GPU plug-in.** Stdlib-only at runtime; no
  numpy / numba / CUDA.

## 3. Tested environment

What we've actually tested the v3.5 alpha on:

| OS | Cinema 4D | Python (host) | Status |
| --- | --- | --- | --- |
| macOS 14 / 15 | 2024.5+, 2025 | 3.11.x | known good |
| Windows 11 | 2024.5+, 2025 | 3.11.x | known good |
| Linux | (no Maxon support; CLI tools only) | 3.10 / 3.11 | known good |

Anything outside that matrix is *probably* fine, but if
something breaks, please file a report — we want to
hear about it.

## 4. Install

1. Download `unav_pro-3.5.0.zip` from the GitHub
   release page.
2. Quit Cinema 4D.
3. Unzip into your Cinema 4D plug-ins folder:
   * **macOS**:
     `~/Library/Preferences/Maxon/.../plugins/`
   * **Windows**:
     `%APPDATA%\Maxon\...\plugins\`
4. Restart Cinema 4D.
5. `Extensions → Universal Navigator Pro` opens the
   dialog.

The status log's first line should read
`UNAV Pro v3.5.0 (Public Alpha; …)`.

For the long-form install guide see
[`INSTALL_C4D_2023_PLUS.md`](INSTALL_C4D_2023_PLUS.md).

## 5. What to test

### 5.1 Smoke test (10 minutes)

Walk through the bundled demo:

1. `Project → Open Workspace…` →
   `samples/internal_beta_demo/`
2. `Diagnostics → Run Health Check`
   (should report 14 probes; all `[OK]` or `[..]`).
3. `Sync Visible Sector` → eight objects appear
   under `UNAV_Project / UNAV_VisibleSector`.
4. `Inspect Selected Object` on any starfield
   child → metadata + provenance render.
5. Open the demo mission → `▶ Play` → camera
   scrubs through the path.
6. `Bake to Timeline` → camera + navigator
   keyframes appear.
7. `Export → Export Full Package…` → a manifest
   with v3.2 self-describing fields lands in
   `<workspace>/exports/`.
8. `Presentation → Open Presentation…` → `Start
   Presentation` → step through the demo talk.

If every step works, the install is healthy.

### 5.2 Real-data test (30 minutes)

* Use the offline preprocessing CLIs to fetch a small
  Gaia / SDSS / DESI / JPL region. Build the spatial
  index. Add the dataset to the workspace. Sync
  visible sector.
* Run `python tools/audit_dataset.py
  --input <path>` and check the v3.2 audit report.

### 5.3 Stress + lifecycle (60 minutes)

* Multi-document — open two scenes; switch between
  them; confirm UNAV state follows the active
  document.
* Plug-in reload — `Extensions → Reload Python
  Plug-ins`; confirm state re-binds cleanly.
* Save / reload C4D scene — confirm UNAV state
  restores via `Load UNAV State`.
* Reset tools — `Diagnostics → Reset` group; each
  reset is idempotent and never touches on-disk
  artefacts.

### 5.4 v3.4 internal-beta checklist

Walk the existing 17-section list in
[`V3_4_INTERNAL_BETA_CHECKLIST.md`](V3_4_INTERNAL_BETA_CHECKLIST.md).
Every step should still pass; if one regresses, file
a release blocker.

## 6. What feedback we want most

Listed roughly in priority order:

1. **Crashes + hangs.** Anything that hangs Cinema 4D
   or hits an unhandled traceback. Attach the issue
   report bundle (`Diagnostics → Create Issue
   Report`).
2. **Workflow friction.** Buttons that are in the
   wrong place; status messages that confuse;
   panels that hide what you need.
3. **Data integrity.** Catalog rows that load but
   look wrong; provenance records that don't match
   the source.
4. **Documentation gaps.** Anything you couldn't
   figure out from the docs.
5. **Determinism.** Same input → different output
   (we expect deterministic everywhere).
6. **Performance.** Anything noticeably slow on
   datasets the v3.0 chunk-reuse cache should
   handle.

We are **not** looking for:

* Render-feature requests. UNAV will not become a
  renderer.
* RelativityRender bridge requests. Out of scope.
* Network / IPC requests. Out of scope.
* Major new feature ideas at this stage —
  v3.5 is a stabilisation release.

## 7. Filing a bug

`Diagnostics → Create Issue Report` produces a
Markdown bundle with version + environment + state +
recent log lines. Paste it into a GitHub issue. Read
[`ISSUE_REPORTING.md`](ISSUE_REPORTING.md) for the
canonical workflow.

## 8. What you'll see go wrong

The **expected bugs** list (i.e. things we already know
about; **don't** file these):

* `Auto Sync` is still a placeholder — clicking it
  shows a status message; you sync manually.
* The redshift → distance helper is loudly tagged
  `approximate` everywhere.
* The metadata inspector renders nine v1.3 sections
  + a v3.2 provenance block; some panels squeeze
  on small displays.
* Two open Cinema 4D documents share one
  process-wide time-navigator state; the v3.x
  ROADMAP §2 plans a per-document split.

The full *known limitations* list:
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

## 9. What's stable, what isn't

**Stable** (low risk of changing in v3.x):

* Catalog schema (v0.1).
* Mission JSON v1.4 schema.
* Route JSON v0.6 schema.
* Camera path JSON v1 schema.
* Export package manifest v1 schema (with v3.2
  additive fields).
* DB schema v2 (v1.1 + v1.2 migrations).
* Provenance JSON v1 schema (v3.2).
* Presentation JSON v1 schema (v3.3).

**Less stable** (may evolve before v4):

* Workflow profile names + label-clutter policy
  defaults (v3.45).
* Some health-check probe wording.
* Some status-log message wording.
* Some panel layouts.

If you build downstream tooling, key on the schema
files (stable) rather than the panel strings.

## 10. License

UNAV Pro is **Apache 2.0**; see
[`LICENSE`](../LICENSE) and [`NOTICE.md`](../NOTICE.md).
Bundled sample data is **synthetic**; not redistributed
real catalog data. See
[`docs/DATA_SOURCE_ATTRIBUTION.md`](DATA_SOURCE_ATTRIBUTION.md).

## 11. Thank you

This alpha exists because someone is going to find the
weird interaction nobody on the maintainer side has
seen. That someone is — possibly — you. Thanks for
running it through.
