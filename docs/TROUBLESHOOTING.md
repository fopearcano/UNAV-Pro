# UNAV Pro — Troubleshooting

Common issues + fixes. Read top-down; the early entries
catch most installs.

For the per-OS install reference see
[`INSTALL_C4D_2023_PLUS.md`](INSTALL_C4D_2023_PLUS.md). For
the smoke-test workflow see
[`QUICK_START.md`](QUICK_START.md).

---

## 1. The dialog menu entry doesn't appear

**Symptoms.** ``Extensions → Universal Navigator Pro`` is
absent. Cinema 4D logs nothing at startup about UNAV.

**Causes:**

* The plugin folder is in the wrong location.
* Cinema 4D is older than 2023 (API < 26000).
* The plugin's ``unav_plugin.pyp`` failed to import (a
  syntax error in a hand-edited file, a missing
  dependency).

**Fix.**

1. Verify the plugin path matches your Cinema 4D version's
   plugins directory.
   * **macOS:** ``~/Library/Preferences/Maxon/Maxon Cinema
     4D 2024_<HASH>/plugins/``
   * **Windows:** ``%APPDATA%\Maxon\Maxon Cinema 4D
     2024_<HASH>\plugins\``
   * **Linux:** ``~/.config/Maxon/Maxon Cinema 4D
     2024_<HASH>/plugins/``
2. The plugin directory must contain ``unav_plugin.pyp``
   directly: ``plugins/unav_pro/unav_plugin.pyp``.
3. Open Cinema 4D's Console (``Script → Console…``) and
   look for ``UNAV`` lines at startup. Errors there are
   the actual reason the plugin didn't register.
4. Run ``python scripts/run_tests.py --quiet`` against
   the source repo to confirm the plugin's modules import
   cleanly.

---

## 2. Health check reports `[ERR] version`

The plugin's ``unav_pro/version.py`` is missing or unreadable.

**Fix.** Reinstall — re-extract the release zip over the
plugin folder. ``version.py`` is part of the required-file
allowlist, so a clean release zip always carries it.

---

## 3. Health check reports `[ERR] config_dir`

The per-user UNAV directory (``~/.unav_pro/``) is not
writable.

**Causes:**

* The home directory is on a read-only filesystem.
* Permissions on ``~/.unav_pro/`` block writes.
* Disk is full.

**Fix.** Make ``~/.unav_pro/`` writable (``chmod`` /
properties → security). On rare locked-down Windows
deployments, run Cinema 4D as a user with write access to
the user profile.

---

## 4. Health check reports `[!!] sample_catalog`

The bundled ``sample_catalog_100.jsonl`` is missing.

**Fix.** Re-extract the release zip. The packaging script's
required-file check covers the sample, so a properly
shipped release zip always carries it.

If you're running from the source repo:

```
unav_pro/data/samples/sample_catalog_100.jsonl
```

Should exist in the working tree. ``git status`` will tell
you if it has been deleted.

---

## 5. Sync Visible Sector produces zero objects

**Symptoms.** ``UNAV_VisibleSector`` is empty after a sync.

**Causes:**

* No dataset is enabled (``Load Active Datasets`` was
  never clicked).
* The navigator's cone is too narrow / pointing the wrong
  way.
* The active dataset has zero objects.
* ``max_visible_objects`` is 0.

**Fix.**

1. **Dataset Manager…** → confirm the dataset is checked.
2. Click **Load Active Datasets**.
3. Look at the navigator's user data:
   * ``cone_angle_deg`` — try 60° or 90° while debugging.
   * ``far_clip_parsec`` — make it larger than the dataset's
     bounding radius.
   * ``max_visible_objects`` — ≥ 1.
4. Inspect the dialog log for "no objects in active dataset"
   warnings.

---

## 6. Mission baking produces zero keyframes

**Symptoms.** ``Bake to Timeline`` logs ``0 keyframe(s)``.

**Causes:**

* The mission has fewer than two waypoints with cached
  positions.
* The bake range is too narrow (``MIN_FRAMES_FOR_BAKE = 2``).
* ``end_frame <= start_frame``.

**Fix.**

1. Verify the mission has ≥ 2 waypoints with positions.
   The `Preview Path` button drops a Cinema 4D spline if
   the path is buildable; if no spline appears, the path
   is empty.
2. Reset **Start frame** + **End frame** to defaults
   (``0``, ``240``).
3. Verify the project's FPS in Cinema 4D's project settings.

---

## 7. Export refuses with `overwrite_refused`

UNAV's export-validation layer fails closed by default. The
target file already exists.

**Fix.** Pick a different filename or check
``Allow overwrite`` (currently exposed via the
``ExportSettings`` API; the dialog buttons pass
``allow_overwrite=True`` automatically when overwriting,
so this only happens when calling the export manager
programmatically).

---

## 8. The visible sector freezes Cinema 4D

**Symptoms.** Sync triggers a multi-minute freeze; the host
becomes unresponsive.

**Cause.** The navigator's cone is wide and the active
dataset is huge.

**Fix.**

1. Lower ``max_visible_objects`` (start with 10,000).
2. Narrow ``cone_angle_deg`` (30° is the typical default).
3. Reduce ``far_clip_parsec``.
4. Switch the dataset entry to DB-backed if you have a
   ``.db`` file (``v1.1`` SQLite query path is much
   faster than chunked JSONL on million-row catalogs).

The v1.7 stabilization milestone added a SQL-level
``LIMIT`` derived from ``max_visible_objects``, so the
working memory is bounded; the wall-clock time still
scales with the cap.

---

## 9. Tests fail when running ``scripts/run_tests.py``

The runner shells into ``pytest.main(...)``. Common
failures:

* **``ImportError: No module named pytest``** — install
  pytest (``pip install pytest``).
* **Per-test failures** — ``--filter <name>`` to narrow.
  Then file an issue with the failure log.

---

## 10. Where to find the dialog log

The dialog's **Status Log** widget shows every UNAV log
line. The same lines also flow through Python's logging
to a rotating file at:

```
~/.unav_pro/logs/unav_pro.log
```

Read this file when debugging a freeze — the freeze itself
might block the dialog log update, but the file gets
flushed periodically.

---

## 11. None of the above

1. Run ``python scripts/run_tests.py --quiet``.
2. Run **Diagnostics → Run Health Check**.
3. Capture the dialog log (Status Log widget).
4. Capture ``~/.unav_pro/logs/unav_pro.log``.
5. File an issue with all four artefacts.

The QA checklist in
[`docs/QA_CHECKLIST.md`](QA_CHECKLIST.md) is the canonical
"are you sure it's UNAV?" filter — every item there is a
reproduction step a maintainer will ask for first.
