# UNAV Pro — Diagnostics

How UNAV Pro answers the "what version am I running, what catalogs
are loaded, why did the last action fail?" questions. Two pieces:

  * **`core/logger.py`** — the centralized logging entry point: a
    ring-buffer handler, level-filtered convenience shortcuts, an
    environment-snapshot helper, and the formatter the dialog uses.
  * **`ui/diagnostics_panel.py`** — a stand-alone Diagnostics dialog
    showing recent logs + environment info, plus three buttons
    (Refresh, Copy Diagnostics, Open Log Folder) and a Clear-Recent-
    Logs helper.

Companion to:

  * `INSTALL_C4D_2023_PLUS.md` (the troubleshooting section that
    points users at the log file).
  * `PERSISTENCE_AND_CONFIG.md` (the source of `cache_root` and
    `log_level` shown in the diagnostics).
  * `DATASET_MANAGER.md` and `METADATA_INSPECTOR.md` (the registry
    and lookup the diagnostics summarise).

---

## 1. Logging policy

All modules under `unav_pro/` route through `core.logging_util.get_logger`
(or the convenience shortcuts in `core/logger.py`). The package
logger is `unav_pro` and per-module children get sub-paths like
`unav_pro.core.scene_sync` or `unav_pro.ui.dataset_manager`.

The two surviving `print()` calls in the package are deliberate:

  * `unav_plugin.pyp::_emergency_print` — last-resort stderr at
    plugin import time, before the logger is available. If this
    path fires, the logger module itself failed to import, so a
    logger call would re-fail.
  * `data/sample_catalog_generator.py` (inside `if __name__ ==
    "__main__"`) — the script's CLI usage prints the output path
    to stdout. That's user-facing CLI behaviour, not plugin
    runtime.

CLI tools under `tools/` also use `print` for stdout — the same
exemption applies; CLIs treat stdout as the user channel.

Any new module added to the plugin runtime must use `get_logger`
(or `core.logger.{info,warning,error,debug}`); regular `print()`
inside `unav_pro/` would be a regression.

---

## 2. The four levels

| Level     | When to use                                                                  |
|-----------|------------------------------------------------------------------------------|
| `DEBUG`   | Diagnostic-only detail — coordinate transforms, per-row decisions, cache hits/misses. Captured by the ring buffer; rendered in the dialog when the level filter is **Debug** or **All**. |
| `INFO`    | Successful actions: "Built starfield with N points", "Wrote sample catalog to …". |
| `WARNING` | Recovered-from problems: "Skipped 12 unusable rows", "Could not write log file; falling back to console". |
| `ERROR`   | Action failed in a way the caller surfaces to the user, even after the boundary handler returned a status string. |

Convenience shortcuts in `core.logger` route to the package logger
without forcing every module to call `get_logger` first:

```python
from core import logger
logger.info("hello %s", target)
logger.warning("something off")
logger.error("boom")
logger.debug("inside loop, i=%d", i)
```

`name=` lets a one-off site land in a more specific sub-logger
without instantiating a child logger:

```python
logger.info("from cli", name="cli.fetch")
# -> emits under "unav_pro.cli.fetch"
```

---

## 3. Ring-buffer handler

Every log record under `unav_pro.*` is mirrored into a bounded
in-memory ring buffer (`RingBufferHandler`). The default size is
500 records — large enough to cover a long debugging session
without unbounded growth. Tests can request a smaller buffer via
`install_ring_buffer(maxlen=...)`.

`install_ring_buffer()` is **idempotent**: the first call attaches
the handler and lowers the package logger to `DEBUG` so all four
levels reach the buffer; subsequent calls return the existing
singleton.

Lowering the logger to DEBUG is intentional and documented: the
diagnostics layer's contract is "show me everything". The rotating
file handler also receives DEBUG records once the ring buffer is
installed; the on-disk log is bounded by `RotatingFileHandler`'s
2 MiB / 3-backup configuration.

API:

```python
install_ring_buffer(maxlen=500) -> RingBufferHandler   # idempotent
recent_logs(level=None, limit=None) -> List[dict]       # filter + tail
clear_recent_logs() -> None
reset_ring_buffer_for_tests() -> None                   # tests only
```

`recent_logs` returns plain dicts (not `LogRecord` instances)
because the dialog and clipboard payload only need the rendered
fields:

```python
{
  "asctime":  "2026-04-29 20:15:32",
  "level":    "WARNING",
  "name":     "unav_pro.core.scene_sync",
  "message":  "max_visible cap dropped 84 uids",
  "pathname": "/.../scene_sync.py",
  "lineno":   312,
  "created":  1735504532.123,
}
```

---

## 4. Environment snapshot

`gather_environment(config=None, registry=None, lookup=None)`
collects:

| Key                   | Value                                                            |
|-----------------------|------------------------------------------------------------------|
| `c4d_version`         | `c4d.GetC4DVersion()` rendered as a string, or `"(not running inside C4D)"` outside the host. |
| `python_version`      | `sys.version.split()[0]`.                                        |
| `python_executable`   | `sys.executable`.                                                |
| `platform`            | `sys.platform` — `darwin`, `win32`, `linux`.                     |
| `plugin_root`         | Absolute path of `unav_pro/`.                                    |
| `log_file`            | Path of the active rotating log, or `(no file handler)`.         |
| `log_folder`          | Directory of `log_file`, used by **Open Log Folder**.            |
| `cache_root`          | `os.path.expanduser(config.cache_root)` when config is provided.  |
| `datasets_total` /<br>`datasets_enabled` | Counts from a `DatasetRegistry`, when provided.       |
| `datasets`            | Per-entry dicts: `name`, `enabled`, `indexed`, `object_count`, `sources`. |
| `lookup_object_count` | `len(lookup)` when a `MetadataLookup` is provided.               |
| `lookup_sources`      | `lookup.sources()` — sorted list of catalog sources.             |
| `generated_count`     | Number of children directly under `UNAV_VisibleSector` in the active document; `None` outside Cinema 4D or when no document is open. |

`registry` / `lookup` / `config` are dependency-injected so the
diagnostics controller (the dialog) can pass live instances and
tests can pass mocks.

---

## 5. Diagnostics formatter

`format_diagnostics(env, records)` renders a single multi-line
text block split into four sections — Environment, Datasets,
Runtime, Recent log entries — and is what the dialog displays and
the **Copy Diagnostics** button copies. Sample shape:

```
=== UNAV Pro Diagnostics ===

--- Environment ---
Cinema 4D       : 2024010
Python          : 3.11.15
Platform        : darwin
Plugin root     : /Users/me/.../unav_pro
Cache root      : /Users/me/.unav_pro/cache
Log file        : /tmp/unav_pro/unav_pro.log
Log folder      : /tmp/unav_pro

--- Datasets ---
Total/enabled  : 2 / 1
  [ON ] idx UNAV Sample (bundled) (100 objects, sources: unav_sample)
  [off] -   gaia_pleiades (4823 objects, sources: gaia_dr3)

--- Runtime ---
Lookup objects  : 100
Lookup sources  : unav_sample
Generated (vis) : 312

--- Recent log entries (12) ---
2026-04-29 20:15:32 [INFO] unav_pro.core.scene_sync: built starfield with 312 points...
...
```

Sections collapse cleanly when their inputs are missing:
- No registry attached → Datasets section reads "(no registry attached)".
- No active doc → Generated reads `(no active document)`.
- Empty record list → "Recent log entries" header omitted.

---

## 6. UI

`ui/diagnostics_panel.py` provides:

  * `DiagnosticsController` — pure-CPython class that owns the
    optional registry/lookup/config and produces snapshot text.
    Lazy-resolves to `DatasetRegistry.load(default_registry_path())`
    / `default_lookup()` / `load_config()` when caller passes
    `None`. Fully unit-tested without C4D.
  * `UnavDiagnosticsDialog` — stand-alone `GeDialog` (own plugin ID
    `1000010`) with:
      * Log-level filter combo (All / Debug / Info / Warning / Error).
      * Read-only multi-line text panel showing the snapshot.
      * **Refresh** — re-runs the snapshot.
      * **Copy Diagnostics** — `c4d.CopyStringToClipboard(snapshot)`.
      * **Open Log Folder** — `c4d.storage.GeExecuteFile(log_folder())`.
      * **Clear Recent Logs** — `clear_recent_logs()` + refresh.

`UnavMainDialog` exposes a **Diagnostics…** button that opens the
diagnostics dialog asynchronously. The instance is cached on the
main dialog so re-clicking re-opens the same window.

The startup path (`unav_plugin.pyp::_register_all`) calls
`install_ring_buffer()` after `init_logging()`, so the very first
log line of every session lands in the buffer and shows up in the
dialog.

---

## 7. Robustness rules

The diagnostics layer follows the standing plugin invariants
(`PLUGIN_STRUCTURE.md` §9):

  1. **The logger never raises.** `RingBufferHandler.emit` swallows
     any exception (a malformed `LogRecord`, a formatter bug, etc.)
     because a logging crash inside another handler would corrupt
     the application's flow.
  2. **Idempotent installation.** `install_ring_buffer` returns the
     existing handler on re-entry; tests use
     `reset_ring_buffer_for_tests()` to start clean.
  3. **Empty / missing inputs degrade gracefully.** The formatter
     produces a usable block whether or not a registry, lookup, or
     active document is available; absent sections render
     placeholder text instead of being skipped silently.
  4. **No exception escapes the C4D boundary.** Every dialog
     command is wrapped in a try/except that drops the error into
     the panel as `ERROR: <repr>` rather than killing the dialog.
  5. **No top-level c4d import in testable modules.**
     `core/logger.py` is c4d-free; the c4d-bound paths live in
     `ui/diagnostics_panel.py` and are guarded.

---

## 8. Test coverage

`unav_pro/tests/test_logger.py` covers (30 tests):

  * **Ring buffer.** Singleton, captures records, captures all four
    levels, respects `maxlen`, level filter (incl. unknown level →
    all), `limit` tail, empty list when not installed,
    `clear_recent_logs` empties the buffer, `emit` never raises on
    malformed records.
  * **Convenience shortcuts.** `info` / `warning` / `error` /
    `debug` route through the package logger; `name=` lands under
    a sub-logger.
  * **Environment snapshot.** Required keys present; outside-C4D
    placeholder for `c4d_version`; cache root rendered when config
    given; dataset table reflects registry; lookup section reflects
    `MetadataLookup`; `generated_count` is `None` outside C4D.
  * **Formatter.** Includes environment keys; renders the dataset
    flags `[ON ]` / `[off]` / `idx`; "no registry attached" when
    none; recent records appear when present; empty record list
    omits the section; lookup section renders; "no active
    document" when generated count is `None`.
  * **`DiagnosticsController`.** Composes the snapshot from injected
    registry/lookup/config; level filter limits records in the
    rendered output; fully lazy resolution when no inputs are
    given (controller never raises).
  * **`log_folder`.** Either returns a path under `…/unav_pro` or
    `None` on read-only filesystems.

The c4d-bound paths in `UnavDiagnosticsDialog` (the actual
`Open(...)`, the clipboard call, `GeExecuteFile`) are exercised by
loading the plugin in Cinema 4D 2023+; they are not part of the
automated suite.

---

## 9. Future extensions

  * **Async log streaming.** A `MessageData` hook can re-render the
    panel periodically so the user sees logs flowing live during
    a long-running action without manually clicking **Refresh**.
  * **Per-source level overrides.** Today `install_ring_buffer`
    flips every UNAV sub-logger to `DEBUG`. A future API can let
    the user dial down a noisy module without affecting the rest.
  * **Issue bundle export.** Combine the diagnostics text with the
    rolled log file into a zip the user can attach to a support
    ticket.
  * **Inline crash reporter.** Catch unhandled exceptions in
    dialog commands and append a fully-rendered traceback to the
    diagnostics panel for one-click reporting.

The MVP shipped here is intentionally narrow: one ring buffer, one
formatter, one dialog. Every future feature in this list slots in
behind the existing `gather_environment` / `format_diagnostics`
interface without touching the plumbing.
