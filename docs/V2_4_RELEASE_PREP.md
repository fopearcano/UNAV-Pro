# UNAV Pro v2.4 — Production QA & Packaging

UNAV's v2.4 milestone is the **release-engineering pass**.
No new navigation or rendering features. Every change is
reliability, packaging, and documentation. The plugin is
now installable from a deterministic release zip, the
artist can run a single health-check command before filing
a bug, and the test suite walks through one CLI script.

For the user-facing release notes see
[`../RELEASE_NOTES_v2.4.md`](../RELEASE_NOTES_v2.4.md). For
the packaging mechanics see
[`PACKAGING.md`](PACKAGING.md). For the pre-release ritual
see [`QA_CHECKLIST.md`](QA_CHECKLIST.md).

---

## 1. What v2.4 actually delivers

| Surface | Change |
|---------|--------|
| `unav_pro/version.py` | New module: `PLUGIN_VERSION`, `PLUGIN_CODENAME`, `MIN_C4D_API`, `VersionInfo`, `parse_version`. |
| `unav_pro/core/health_check.py` | New module: `HealthReport`, `HealthCheckEntry`, `run_health_check()`. Eight built-in probes (version, config dir, cache dir, dataset registry, sample catalog, DB module, voyage import, export import). |
| `scripts/package_plugin.py` | New: deterministic release-zip builder with required-file allowlist + size cap + extension exclude list. |
| `scripts/run_tests.py` | New: one-script test runner that classifies tests by category. |
| `dist/README.md` | New: how to consume the release zip. |
| `samples/minimal_unav_demo/` | New: tiny self-contained catalog + mission + route + README. |
| `RELEASE_NOTES_v2.4.md`, `CHANGELOG.md` | New entries for the v2.4 milestone. |
| `docs/INSTALL_C4D_2023_PLUS.md`, `QUICK_START.md`, `TROUBLESHOOTING.md` | Refreshed for the v2.4 install flow. |
| `docs/V2_4_RELEASE_PREP.md`, `PACKAGING.md`, `QA_CHECKLIST.md` | Three new release-engineering docs. |
| `unav_pro/ui/main_dialog.py` | Diagnostics panel learns to render the v2.4 health-check output and the version info. |
| Tests | New `test_v24_*` files cover version, health check, packaging, sample demo, run-tests categorisation. |

**No new features beyond release engineering.** No
rendering, no IPC, no external renderer bridge. Every
v1.x + v2.0–v2.3 feature surface is preserved unchanged.

---

## 2. The version contract

```python
from unav_pro.version import PLUGIN_VERSION, get_version_info, parse_version

info = get_version_info()
print(info.display_line())
# "UNAV Pro v2.4.0 (Production QA & Packaging; requires C4D API ≥ 26000)"

major, minor, patch = parse_version(PLUGIN_VERSION)
```

Three callers use this module:

* The dialog's status log + diagnostics panel.
* The export manifest (``PackageManifest.plugin_version``).
* The packaging script (``scripts/package_plugin.py``
  reads the version to name the output zip).

`parse_version` is fail-closed: a malformed input returns
``(0, 0, 0)`` rather than raising — the dialog must never
crash because a future hand-edited version string is
malformed.

---

## 3. The health check

```python
from unav_pro.core.health_check import run_health_check

report = run_health_check()
print(report.render())
```

Eight probes:

| Probe | Asserts |
|-------|---------|
| `version` | `version.py` is importable + `display_line` works. |
| `config_dir` | `~/.unav_pro/` exists + is writable (uses a tempfile probe, not a permanent file). |
| `cache_dir` | The configured cache root exists + is writable. Warns when the cache root is unset. |
| `dataset_registry` | `~/.unav_pro/datasets.json` is parseable when present; absence is informational. |
| `sample_catalog` | `data/samples/sample_catalog_100.jsonl` is shipped. |
| `db_module` | `sqlite3` stdlib module imports + reports its version. Warning (not error) when absent — UNAV runs without it on JSONL streaming. |
| `voyage` | `voyage` package imports cleanly. |
| `export` | `export` package imports cleanly. |

The probe set is the v2.4 **release-engineer's smoke test**.
Every fresh install ships with all probes green; warnings
are informational; errors mean the install is broken.

The diagnostics panel renders the report on demand. Tests
in `test_v24_health_check.py` drive every probe directly +
assert the report shape.

---

## 4. The packaging script

```bash
python scripts/package_plugin.py
# → dist/unav_pro-2.4.0.zip
```

What it does:

1. Reads the version from `unav_pro/version.py`.
2. Walks the include list (`PACKAGE_INCLUDE` +
   `PACKAGE_DOCS`) under the repo root.
3. Excludes path fragments (`__pycache__`, `tests`,
   `cache`, `data/catalogs`, `native`, hidden files, etc.).
4. Skips files larger than `MAX_FILE_SIZE_BYTES` (5 MB).
5. Stages every kept file into a tempdir.
6. Validates that every entry in `REQUIRED_FILES` is
   present.
7. Zips the staging into `dist/unav_pro-<version>.zip`,
   files written in sorted order so the zip is reproducible
   between runs.

The script returns a `PackageReport` whose `success` flag
the caller can act on. Tests in `test_v24_packaging.py`
exercise the build with a synthetic repo + assert that
required files are flagged when missing.

---

## 5. The test runner

```bash
python scripts/run_tests.py
python scripts/run_tests.py --filter v22       # only v2.2 tests
python scripts/run_tests.py --quiet            # minimal output
```

The runner walks `unav_pro/tests/`, classifies each
`test_*.py` file by category (`state`, `animation`,
`voyage`, `knowledge`, `overlays`, `science`, `export`,
`v18`, `v19`, `release`, `other`), and reports per-
category file counts before / after invoking
``pytest.main``.

Categorisation is driven by `TEST_CATEGORIES`; tests in
`test_v24_run_tests.py` assert the bucket logic without
running pytest itself.

---

## 6. The minimal demo

`samples/minimal_unav_demo/` carries:

* `catalog.jsonl` — five rows (3 stars, 1 galaxy, 1 demo
  planet) covering the canonical class set.
* `mission.json` — five-waypoint mission JSON (v1.4
  schema), references all five catalog rows.
* `route.json` — three-waypoint route JSON (v0.6 schema).
* `README.md` — five-step workflow.

Total size is in the low kilobytes. The demo lets a fresh
install verify Sync → Inspect → Mission Import → Bake →
Export without downloading any catalogs.

---

## 7. The acceptance contract

* [x] The plugin packages into a deterministic zip.
* [x] The package excludes heavy / generated / cache files.
* [x] Install docs are step-by-step.
* [x] Health check works and is reachable from the
  diagnostics panel.
* [x] Sample demo loads cleanly without external data.
* [x] Tests run through one script.
* [x] Release notes exist (`RELEASE_NOTES_v2.4.md`).
* [x] No render-engine assumptions.
* [x] No RelativityRender bridge.

---

## 8. What v2.4 explicitly does **not** do

| Out of scope                                  | Why                                          |
|-----------------------------------------------|----------------------------------------------|
| New navigation features                       | Release-engineering pass only.               |
| New rendering features                        | Same.                                        |
| New science layers / overlays                 | Same.                                        |
| RelativityRender / external integration       | Explicitly excluded by the v2.4 spec.        |
| IPC / sockets                                 | Explicitly excluded.                         |
| Auto-update / online check                    | UNAV is offline-first.                       |
| Plugin signing / notarisation                 | Maxon's plugin distribution doesn't require it; out of scope. |
