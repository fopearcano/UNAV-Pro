# UNAV Pro v3.9 — Integrated External Tools

Release date: 2026-05-25
Codename: *Integrated External Tools*

v3.9 makes the heavy preprocessing tools (Gaia / JPL
/ SDSS / DESI fetch, spatial indexing, DB import,
dataset audit, binary export) reachable **from inside
the plugin** — while they keep running in a *separate
external Python interpreter*, never in Cinema 4D's
embedded one. The C4D plugin runtime stays
stdlib-only. **Not** rendering. **Not** IPC. **No**
heavy dependencies inside C4D. v3.8 runtime preserved
byte-for-byte.

---

## Highlights

* **Tool registry**
  (`unav_pro/tools/tool_registry.py`). Pure-data
  `ToolSpec` / `ToolInput` describing nine tools
  across three categories (fetch / processing /
  export), the minimal *safe* form fields each
  exposes, runtime class, dependency profile, and
  whether a run produces a dataset / index / DB.
* **External Python environment**
  (`unav_pro/tools/python_env.py`). Auto-detects a
  system Python ≥ 3.10 (skipping the C4D embedded
  interpreter), validates a candidate with a
  timeout-bounded `--version` probe, and persists the
  choice in the UNAV config (`external_python_path`).
* **Subprocess runner**
  (`unav_pro/tools/tool_runner.py`). Builds the
  command safely, streams stdout/stderr into the
  diagnostics log, returns a structured
  `ToolRunResult`, classifies failures (missing
  Python / missing script / dependency / network),
  enforces safe default limits, and never stores
  credentials. Includes a cancellation placeholder.
* **External Tools panel**
  (`unav_pro/ui/tools_panel.py`). A pure
  `ToolsPanelController` (fully unit-tested) plus a
  c4d dialog with Python Environment / Data Fetch /
  Processing / Export sections, dynamic per-tool
  forms, and a warn-before-long-run guard.
* **Dataset Manager integration**. A successful fetch
  registers its catalog automatically (and attaches an
  index built in the same run); processing tools
  attach their index / DB to the matching dataset.
* **Setup helper + requirements**.
  `tools/setup_unav_tools_env.py` bootstraps a venv and
  prints the interpreter path; `requirements-tools.txt`
  documents that the bundled tools are stdlib-only.

## What didn't change

* No new runtime dependencies inside Cinema 4D.
  Stdlib-only; nothing imports numpy / astroquery /
  pandas in the host.
* No rendering, no IPC / sockets, no
  RelativityRender, no threading model changes.
* No huge downloads by default — cone fetchers always
  pass a safe `--limit`.
* All v0.x → v3.8 on-disk schemas unchanged
  (`external_python_path` is a new, optional config
  field; unknown keys were already dropped on load).

## Safety

* [x] Never blocks Cinema 4D indefinitely — tools run
  in a child process with a timeout + cancellation
  seam.
* [x] Warns before networked / long runs.
* [x] Safe default row limits; no unbounded fetches.
* [x] No credentials requested or stored; public
  anonymous endpoints only.

## Testing

* Full suite passes: **3139 tests** (3087 v3.8
  baseline + 52 new v3.9 tests).
* New test file `test_integrated_external_tools`:
  registry lookup / categories, external-Python
  detection + validation (injectable runner), command
  construction, summary parsing + failure
  classification, end-to-end `run_tool` with an
  injected runner, cancellation, dataset-manager
  registration, and the panel controller.

## Docs

* `docs/INTEGRATED_EXTERNAL_TOOLS.md`
* `docs/TOOLS_PYTHON_ENVIRONMENT.md`
* `docs/DATA_FETCH_UI_WORKFLOW.md`
* `docs/REQUIREMENTS_TOOLS.md`
* `docs/EXTERNAL_TOOLS_AUDIT.md`

## Boundary, restated

UNAV Pro v3.9 remains an **astronomical navigation +
voyage / camera-animation tool for Cinema 4D**. The
heavy data work runs *outside* the host by design.
Rendering, IPC, real-time scientific simulation, and
render-engine bridges remain explicitly out of scope.

For the long-form view of the boundary see
[`docs/ROADMAP.md`](docs/ROADMAP.md) §4.
