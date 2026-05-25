# UNAV Pro — External Tools Audit

The offline preprocessing scripts under `tools/`
are **heavy-dependency, run-once** programs:
they fetch real catalog data over HTTP, build
spatial indexes, import to SQLite, and audit /
export datasets. They are deliberately **not**
imported by the Cinema 4D plugin runtime — the
plugin stays stdlib-only so it ships without
forcing the user to `pip install` anything into
Cinema 4D's embedded Python.

This document classifies every script so the
v-`integrated-external-tools-ui` registry
(`unav_pro/tools/tool_registry.py`) can describe
them to the dialog.

For the runtime architecture see
[`INTEGRATED_EXTERNAL_TOOLS.md`](INTEGRATED_EXTERNAL_TOOLS.md).
For the Python-environment model see
[`TOOLS_PYTHON_ENVIRONMENT.md`](TOOLS_PYTHON_ENVIRONMENT.md).

---

## 1. Classification

| Script | Category | Heavy deps? | Safe inside C4D? | Runtime class |
| --- | --- | --- | --- | --- |
| `fetch_gaia_region.py` | data fetch | network (urllib stdlib) | no | medium |
| `fetch_jpl_body.py` | data fetch | network | no | short |
| `fetch_jpl_solar_system.py` | data fetch | network | no | medium |
| `fetch_sdss_region.py` | data fetch | network | no | medium |
| `fetch_desi_region.py` | data fetch | network | no | medium |
| `build_spatial_index.py` | processing | none (stdlib) | yes (but CPU-heavy) | medium |
| `import_catalog_to_db.py` | processing | sqlite3 (stdlib) | yes | medium |
| `audit_dataset.py` | processing | none (stdlib) | yes | short |
| `export_visible_sector_binary.py` | export | none (stdlib) | yes | short |
| `benchmark_visible_sector_export.py` | dev / bench | none | n/a (not registered) | long |

Notes:

* **"Heavy deps"** here means *anything beyond the
  Python standard library*. UNAV's connectors are
  written against `urllib` + `csv` + `json` — **no
  numpy / astropy / astroquery**. So the only real
  external requirement is *network access* for the
  fetch scripts. `requirements-tools.txt` exists
  for users who later want to add their own
  heavier analysis on top; the bundled scripts
  don't need it.
* **"Safe inside C4D"** marks whether a script
  *could* run inside Cinema 4D's embedded Python
  without crashing. The fetch scripts make HTTP
  calls + can run for tens of seconds — running
  them on the main thread would freeze the
  viewport, so they're marked `no` regardless of
  dependency weight. The processing / export
  scripts are stdlib-only + technically C4D-safe,
  but the integrated workflow runs **everything**
  through the external subprocess for a uniform UX
  + to keep long operations off the main thread.

## 2. Per-script CLI contract

### fetch_gaia_region.py

```
--ra FLOAT --dec FLOAT --radius-deg FLOAT
--limit INT --release STR --output PATH
--build-index PATH --index-chunk-size INT
--parallax-snr-min FLOAT --no-parallax-cut --quiet
```

Cone search against the Gaia ESA TAP endpoint.
Default 1° / 5000 rows.

### fetch_jpl_body.py

```
--body STR --epoch ISO --output PATH
--center STR --object-type STR
--build-index PATH --index-chunk-size INT --quiet
```

Single solar-system body at one epoch.

### fetch_jpl_solar_system.py

```
--epoch ISO --start ISO --end ISO --step-days FLOAT
--bodies CSV --default-object-type STR --center STR
--output PATH --build-index PATH --index-chunk-size INT
--db PATH --max-epochs INT --quiet
```

Multiple bodies, optionally across an epoch range.

### fetch_sdss_region.py

```
--ra FLOAT --dec FLOAT --radius-deg FLOAT
--limit INT --release STR --output PATH
--no-spectro --build-index PATH --index-chunk-size INT
--redshift-max-z FLOAT --quiet
```

### fetch_desi_region.py

```
--ra FLOAT --dec FLOAT --radius-deg FLOAT
--limit INT --release STR --spectype STR
--output PATH --build-index PATH
--index-chunk-size INT --redshift-max-z FLOAT --quiet
```

### build_spatial_index.py

```
--input PATH --output DIR --chunk-size INT
--cell-size-pc FLOAT --quiet
```

### import_catalog_to_db.py

```
--input PATH --db PATH --replace --skip-metadata
--batch-size INT --vacuum --quiet
```

### audit_dataset.py

```
--input PATH --output PATH --json-output PATH
--include-no-provenance --max-rows INT --quiet
```

### export_visible_sector_binary.py

```
--input PATH --dataset STR --navigator-state PATH
--output PATH --scale-mode STR --sidecar-path PATH
--max-points INT --quiet
```

## 3. Common conventions

* Every script accepts `--quiet` (suppress the
  summary line). The runner does **not** pass
  `--quiet` so the dialog can stream the summary.
* Every script `print()`s a one-line summary on
  success + uses a non-zero exit code on failure.
  The runner keys on the exit code.
* Output paths are caller-supplied; the runner
  resolves them against the active workspace's
  `datasets/` / `cache/` / `exports/` directories
  by default (see
  [`DATA_FETCH_UI_WORKFLOW.md`](DATA_FETCH_UI_WORKFLOW.md)).
* No script stores credentials. Gaia / SDSS / DESI
  / JPL public endpoints need none.

## 4. What's NOT registered

* `benchmark_visible_sector_export.py` — a
  developer benchmark, not an artist tool.
* `setup_unav_tools_env.py` — the env-setup helper
  (it bootstraps the environment the *other* tools
  run in; it isn't itself a data tool).

## 5. Registry mapping

Each row above maps to one `ToolSpec` in
`unav_pro/tools/tool_registry.py`. The registry is
the single source of truth the dialog reads to
build the *External Tools* panel + to construct
the subprocess command line.
