# Integrated External Tools

UNAV Pro keeps the Cinema 4D plugin **lightweight**: the heavy data
work (downloading catalogs, building spatial indexes, importing to a
database, auditing, exporting binary sectors) runs in a **separate
external Python interpreter** that you control — *never* inside Cinema
4D's embedded Python.

The plugin gives you an integrated front end for those tools. You pick
a tool, fill in a few safe fields, click **Run**, and the plugin shells
out to your external Python, streams the output into the panel, and —
on success — offers to register the result with the Dataset Manager.

This is the high-level guide. See also:

- [`TOOLS_PYTHON_ENVIRONMENT.md`](TOOLS_PYTHON_ENVIRONMENT.md) — how to
  point the plugin at an external Python.
- [`DATA_FETCH_UI_WORKFLOW.md`](DATA_FETCH_UI_WORKFLOW.md) — the
  fetch → index → register loop, step by step.
- [`REQUIREMENTS_TOOLS.md`](REQUIREMENTS_TOOLS.md) — what (if anything)
  to install in that environment.
- [`EXTERNAL_TOOLS_AUDIT.md`](EXTERNAL_TOOLS_AUDIT.md) — the per-script
  audit the registry is built from.

## Why a separate Python?

- Cinema 4D ships a fixed embedded Python you can't easily
  `pip install` into.
- The fetch tools need outbound network access. Doing that on the C4D
  main thread would freeze the viewport.
- Keeping the heavy environment external means the plugin ships without
  forcing **any** C4D-side installs. The plugin runtime stays
  stdlib-only.

## Opening the panel

Open the **External Tools** window from the main UNAV dialog. It has
four sections:

1. **Python Environment** — choose / detect / validate the external
   interpreter. Your choice persists in the UNAV config
   (`~/.unav_pro/config.json`, key `external_python_path`).
2. **Data Fetch** — Gaia DR3, JPL Horizons (single body or solar
   system), SDSS DR18, DESI EDR.
3. **Processing** — build a spatial index, import a catalog into a
   SQLite DB, run the data-integrity audit.
4. **Export** — export a visible sector to the UNAV binary buffer
   format.

## What runs where

| Concern | Lives in |
| --- | --- |
| Tool descriptions / form fields | `unav_pro/tools/tool_registry.py` (pure data) |
| Locating + validating the interpreter | `unav_pro/tools/python_env.py` |
| Building the command + running it | `unav_pro/tools/tool_runner.py` |
| The panel UI | `unav_pro/ui/tools_panel.py` |
| The actual heavy work | `tools/*.py` (external process) |

Nothing in `unav_pro/tools/` imports numpy / astroquery / pandas, so it
all imports cleanly inside Cinema 4D. The heavy work happens in the
spawned process.

## Safety

- **Never blocks Cinema 4D indefinitely.** Tools run in a child
  process; the runner supports a timeout and a cancellation hook.
- **Warns before long / networked runs.** Anything that hits the
  network or is slower than "short" pops a confirmation first.
- **Safe default limits.** Cone-search fetchers always pass a default
  `--limit` so a run can't accidentally pull an unbounded download.
- **No credentials stored.** The bundled fetchers use public,
  anonymous endpoints. The runner never injects secrets into the child
  environment.
- **No huge downloads by default.** Keep the search radius small; the
  defaults are sized for quick, demo-scale pulls.

## After a successful run

When a fetch produces a catalog, the panel offers to **register** it
with the Dataset Manager (and attach an index if the same run built
one). Processing tools attach their index / DB to the matching
dataset. From there the catalog flows into the rest of UNAV exactly
like any hand-registered dataset.
