# UNAV Pro v0.1 — Universal Navigator Pro (Python prototype)

The first milestone release. A working C4D 2023+ Python plugin
that turns real-data astrophysical catalogs into a
navigator-bounded point cloud, with metadata inspection, route
planning, scene-sync diff/update, persistence, and hard safety
guardrails.

## Acceptance criteria — status

| Criterion                                                  | Status |
|------------------------------------------------------------|:------:|
| C4D 2023+ plugin opens                                     | ✓      |
| User can create `UNAV_Navigator`                           | ✓      |
| User can load sample catalog                               | ✓      |
| User can generate visible point field                      | ✓      |
| User can filter by navigator ray / cone                    | ✓      |
| User can inspect selected object metadata                  | ✓      |
| User can save / load basic state                           | ✓      |
| User can use external CLI to generate / normalize catalog data | ✓  |
| Large-data safety prevents scene bloat                     | ✓      |
| Docs explain Gaia / JPL / SDSS / DESI architecture         | ✓      |

All ten criteria pass.

## Highlights

* **Real catalog data, offline.** Stdlib-only connectors for Gaia
  DR3, SDSS DR18, DESI EDR, and JPL Horizons. No `astroquery`,
  no `astropy`, no credentials. Each connector is a CLI in
  `tools/` that can run on a render farm or in a clean Python
  3.9+ install.
* **Navigator-bounded scene.** A `UNAV_Navigator` null defines
  origin + forward + cone half-angle + clip range. The default
  safety mode refuses to materialize the catalog without a
  navigator in place. Full-catalog override exists but is
  loud about it.
* **Diff-and-update workflow.** *Sync Visible Sector* adds /
  removes / keeps individual uids without touching the rest of
  the materialized set. Selection / animation / per-object tags
  survive every iteration.
* **Live metadata inspector.** Click any UNAV object → the panel
  fills with full RA/Dec/distance/magnitude/spectral type. The
  marker on each C4D node carries only the uid; the full record
  comes from the external lookup.
* **Project persistence.** *Save UNAV State* writes the
  navigator + route + active datasets + visual encoding into the
  C4D document's BaseContainer **and** a sidecar JSON, so a
  `.c4d` reopens with the scene exactly as it was assembled.
* **Hard safety guardrails.** 100 000-object hard cap by
  default; visible-sector-only mode requires a navigator;
  advisory warnings for big catalogs / heavy scenes / large
  `.c4d` files; minimal-marker policy keeps the full metadata
  blob *out* of every generated node.

## Headline numbers

* **551 c4d-free pytest tests** — all green.
* **0 credentials / API keys** committed.
* **0 hardcoded machine paths** in plugin code or tests.
* **84 KB** largest committed data file (the bundled sample
  catalog).
* **5 CLI tools** under `tools/`, all stdlib-only.
* **4 real-source connectors** (Gaia / SDSS / DESI / JPL
  Horizons).
* **6 colour modes** + 3 size modes for the visual encoding.

## Documentation

Read in this order:

1. [`README.md`](README.md) — what it does + quick start.
2. [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — every dialog
   button, in order.
3. [`docs/PRO_WORKFLOW.md`](docs/PRO_WORKFLOW.md) — recommended
   professional workflow.
4. [`docs/DATA_SOURCE_OVERVIEW.md`](docs/DATA_SOURCE_OVERVIEW.md)
   — Gaia / SDSS / DESI / JPL Horizons at a glance.
5. [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — what's not in
   v0.1 yet.
6. [`docs/ROADMAP_CPP_GPU_VERSION.md`](docs/ROADMAP_CPP_GPU_VERSION.md)
   — how this scales.
7. [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) —
   conventions for new contributors.

## Install

See [`docs/INSTALL_C4D_2023_PLUS.md`](docs/INSTALL_C4D_2023_PLUS.md).
Short version: copy or symlink the `unav_pro/` directory into your
Cinema 4D plugins folder; restart C4D; **Extensions → Universal
Navigator Pro**.

Cinema 4D **2023, 2024, or 2025** required (API ≥ 26000).

## Quick start

```text
1. Open Cinema 4D 2023+.
2. Extensions → Universal Navigator Pro.
3. Click "Create Navigation Null"          (creates UNAV_Navigator)
4. Click "Generate Point Cloud"            (uses bundled sample)
5. Click any sample-* object in the OM.
6. Click "Inspect Selected Object"         (full metadata appears)
7. Click "Add Selected Object as Waypoint" (route gains a stop)
8. Repeat 5+7, then "Build Route Spline".
9. Click "Save UNAV State"                 (state goes into .c4d)
```

## Audit summary

Final pre-release pass found:

* No huge committed files (sample catalog is 84 KB JSONL).
* No credentials, API keys, or auth tokens.
* No hardcoded user-machine paths in plugin code or tests.
* All claims in user-facing docs match the shipped feature set.
  The `docs/LIMITATIONS.md` file is honest about what does *not*
  work yet.
* All `import c4d` / `from c4d ...` imports are guarded behind
  `try/except` blocks; tests run on a clean Python 3.9+ install
  with no Cinema 4D present.

## Known limitations carried into v0.2

See [`TODO_v0.2.md`](TODO_v0.2.md) for the prioritized backlog.
The full rationale per item is in
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

Headline items the prototype intentionally does **not** ship:

* > 100 000 generated objects per scene.
* Real-time / animated navigation (Auto Sync placeholder).
* Live route playback.
* Cosmology-aware distances above z = 0.1.
* Catalog crossmatch.
* Native render-pass parity (UNAV objects are nulls in v0.1).
* Productionized plugin IDs (dev range until external release).

## Feedback + bug reports

Reproduce the issue, then open the **Diagnostics** dialog and
**Copy Diagnostics** — that payload contains the C4D version,
Python version, plugin root, registered datasets, generated
count, and recent log records. Attach it to the report.
