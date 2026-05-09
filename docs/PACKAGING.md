# Packaging

How the v2.4 release zip gets built. Lives in
`scripts/package_plugin.py`; tests drive
`build_release_zip(...)` directly without spawning a
subprocess.

For the milestone overview see
[`V2_4_RELEASE_PREP.md`](V2_4_RELEASE_PREP.md). For the
release-engineer's pre-publish ritual see
[`QA_CHECKLIST.md`](QA_CHECKLIST.md).

---

## 1. The contract

> Given a clean repo and a green test suite, produce a
> deterministic zip the artist can drop into Cinema 4D's
> plugins folder.

The zip:

* contains every file in `PACKAGE_INCLUDE` and
  `PACKAGE_DOCS`,
* excludes everything in `EXCLUDE_PATH_FRAGMENTS`,
* excludes files with `EXCLUDE_EXTENSIONS`,
* excludes any file > `MAX_FILE_SIZE_BYTES` (5 MB),
* contains every file in `REQUIRED_FILES` (or refuses to
  build),
* has a stable name — `dist/unav_pro-<version>.zip` —
  derived from `unav_pro/version.py`,
* is byte-reproducible across runs (modulo zip metadata
  timestamps).

---

## 2. The include list

```python
PACKAGE_INCLUDE = (
    "unav_pro",                       # the plugin package
    "README.md",
    "CHANGELOG.md",
    "RELEASE_NOTES_v2.4.md",
    "samples/minimal_unav_demo",      # bundled demo
)

PACKAGE_DOCS = (
    "docs/INSTALL_C4D_2023_PLUS.md",
    "docs/QUICK_START.md",
    "docs/TROUBLESHOOTING.md",
    "docs/V2_4_RELEASE_PREP.md",
    "docs/PACKAGING.md",
    "docs/QA_CHECKLIST.md",
    "docs/KNOWN_LIMITATIONS.md",
    "docs/PLUGIN_LIFECYCLE.md",
)
```

Everything else in the repo is excluded by default. To
ship an additional doc with the release, append it to
`PACKAGE_DOCS`.

---

## 3. The exclude list

```python
EXCLUDE_PATH_FRAGMENTS = (
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".github",
    ".venv",
    "build",
    "dist",
    "tools",            # preprocessing CLIs ship with source repo
    "tests",            # test suite ships with source repo
    "data/catalogs",    # large generated catalogs
    "cache",            # spatial-index caches
    "native",           # C++ scaffold ships with source repo
)

EXCLUDE_EXTENSIONS = (
    ".pyc", ".pyo", ".log", ".coverage",
    ".db", ".bin",
)
```

Hidden files (`.gitignore`, `.DS_Store`, `.env`, etc.) are
also excluded.

The exclusion check runs on every relative path during the
walk; matching either the fragment list or the extension
list drops the file.

---

## 4. The required-file allowlist

After staging, the script verifies that every entry in
`REQUIRED_FILES` is present. The list covers:

* `unav_pro/version.py`,
* `unav_pro/unav_plugin.pyp`,
* every package's `__init__.py`,
* the v2.4-specific modules (`core/health_check.py`,
  `core/state_manager.py`),
* the canonical entry-point modules
  (`voyage/mission.py`, `data/schema.py`),
* the install + release docs (`README.md`,
  `CHANGELOG.md`, `RELEASE_NOTES_v2.4.md`,
  `docs/INSTALL_C4D_2023_PLUS.md`, `docs/QUICK_START.md`),
* the sample demo's README (`samples/minimal_unav_demo/README.md`).

Missing entries flip `PackageReport.success` to `False`
and the zip is not written. The dialog log / CLI prints
the missing list so the release-engineer can fix the
include rules.

---

## 5. The size cap

`MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024` (5 MB). Any file
that exceeds the cap is logged + skipped — the package
build refuses to ship multi-megabyte assets unless the
release-engineer explicitly raises the cap. This guards
against accidentally including a 100 MB Gaia chunk that
slipped past the path-fragment exclude list.

The cap is not user-tweakable from the CLI; bumping it
needs a code change.

---

## 6. The CLI

```bash
python scripts/package_plugin.py
python scripts/package_plugin.py --output dist/unav_pro-2.4.0.zip
python scripts/package_plugin.py --staging /tmp/unav_stage --keep-staging
```

Flags:

* `--output PATH` — override the default zip path.
* `--staging PATH` — use a specific staging directory
  instead of a fresh tempdir.
* `--keep-staging` — leave the staging directory in place
  after the build (useful for hand-walking the file tree
  before publishing).
* `--repo-root PATH` — override the repo root.

Exit code 0 = success; exit code 1 = a validation /
required-file failure.

---

## 7. The Python API

```python
from scripts.package_plugin import build_release_zip

report = build_release_zip(
    output_zip="/tmp/test.zip",
    keep_staging=True,
    staging="/tmp/unav_stage",
)
print(report.summary_line())
```

Tests in `test_v24_packaging.py` drive this directly
against a synthetic repo so the test suite never touches
the real `dist/` directory.

The function returns a `PackageReport` with:

* `success` — overall pass/fail.
* `zip_path` — absolute path of the output zip.
* `file_count` — number of files written.
* `total_size_bytes` — sum of file sizes.
* `skipped` — files dropped for size-cap reasons.
* `warnings` — every soft issue surfaced.
* `missing_required` — required files absent from the
  staging copy.

---

## 8. Determinism

The script is deterministic by construction:

* `_collect_files` returns a sorted list.
* `_zip_staging` sorts dirnames + filenames before adding
  to the zip.
* The filename pattern (`unav_pro-<version>.zip`) is
  derived from a single source of truth.

Re-running the script on a clean repo produces a zip
with the same file count and total bytes. The only non-
determinism is the per-file modification timestamps that
`zipfile` writes; tooling that compares zips should
ignore those.

---

## 9. The release-engineer's flow

1. `git checkout` the release branch.
2. `python scripts/run_tests.py` — verify the suite is
   green.
3. Bump `PLUGIN_VERSION` in `unav_pro/version.py`.
4. Update `CHANGELOG.md` + write `RELEASE_NOTES_<version>.md`.
5. `python scripts/package_plugin.py --keep-staging`.
6. Walk the staging directory; sanity-check.
7. `cp` the zip into the GitHub release / artefact bucket.
8. Tag the commit (`git tag v2.4.0`).
9. Run the QA checklist (`docs/QA_CHECKLIST.md`).

The whole flow is meant to take five minutes on a clean
repo. If a step fails, fix the cause + re-run from step 2.
