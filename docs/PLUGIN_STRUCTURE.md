# UNAV Pro — Plugin Structure

Reference for what lives where inside the ``unav_pro/`` package, why,
and what is intentionally still empty.

---

## 1. Top-level layout

```
unav_pro/
  __init__.py            package marker; version constant
  unav_plugin.pyp        Cinema 4D entry point (loaded at C4D startup)
  core/                  framework-agnostic helpers (logging, IDs, version, mocks)
  ui/                    GeDialog subclasses and CommandData entries
  data/                  cache readers and engine protocol client (placeholder)
  c4d_objects/           ObjectData / TagData plugin classes (placeholder)
  docs/                  plugin-local documentation
  tests/                 pytest suite for non-C4D modules
```

---

## 2. ``unav_plugin.pyp`` — the entry point

Cinema 4D scans plugin directories for ``*.pyp`` files at startup and
runs each file's ``main()`` function. Our entry point is intentionally
small:

1. Computes ``_PLUGIN_ROOT`` from ``__file__`` and prepends it to
   ``sys.path`` so the sub-packages (``core``, ``ui``, ...) are
   importable as top-level names.
2. Imports ``c4d`` and our package modules. Failures here are reported
   via a stderr fallback and re-raised — there is no point continuing
   if imports broke.
3. Calls ``init_logging()`` (creates ``<temp>/unav_pro/unav_pro.log``).
4. Calls ``check_host()``; aborts registration with an ``ERROR`` log
   line if the C4D version is below ``26000``.
5. Calls ``main_command.register()`` to attach the menu command.
6. Logs a final "registration complete" line.

Every step runs inside ``try/except``. The ``main()`` function never
raises out into the C4D event loop.

---

## 3. ``core/`` — framework-agnostic helpers

These modules don't import ``c4d`` and are unit-tested directly with
``pytest``.

| File                | Responsibility                                                |
|---------------------|---------------------------------------------------------------|
| ``logging_util.py`` | ``init_logging`` / ``get_logger`` / ``log_file_path``. Stream + rotating file handler. Tolerates read-only filesystems. |
| ``version_check.py``| ``is_supported`` / ``describe`` / ``check_host``. Accepts both R26 (``26000``) and 2024+ (``2024xxx``) version schemes. Importable without ``c4d``. |
| ``plugin_ids.py``   | Registry of plugin IDs. Contains development placeholders in the 1,000,001+ range with a TODO to replace before release. |
| ``mock_actions.py`` | Stand-in handlers for the four MVP buttons. Each returns a status string and never raises. |

---

## 4. ``ui/`` — Cinema 4D dialog and command

| File                | Responsibility                                                |
|---------------------|---------------------------------------------------------------|
| ``main_dialog.py``  | ``UnavMainDialog(GeDialog)``. Layout: 2×2 button grid + multiline read-only log + "Clear Log" button. All ``Command`` handlers wrapped in try/except. |
| ``main_command.py`` | ``UnavMainCommand(CommandData)`` and a ``register()`` function. Owns a single dialog instance for ``Open`` / ``Restore`` symmetry. |

Both modules degrade gracefully when imported outside Cinema 4D — the
``c4d`` import is guarded so static analysis and tooling can read the
files without a host present.

---

## 5. ``data/`` — placeholder

Reserved for:

- Engine-protocol client (``EngineClient`` from ARCHITECTURE §3.10).
- Cache readers (Parquet tile loader, SQLite manifest reader).
- ``.unavscene`` / ``.unavbake`` (de)serializers.

Currently contains only ``__init__.py``. The MVP dialog talks to
``core.mock_actions`` instead.

---

## 6. ``c4d_objects/`` — placeholder

Reserved for the scene-object plugin classes named in
PLUGIN_STRATEGY §4.1:

- ``UnavUniverse`` (ObjectData) — root generator, floating origin.
- ``UnavDataset`` (ObjectData) — cached dataset reference.
- ``UnavFilterCone`` (TagData) — camera/null cone filter.

Each will get its own module here (``universe.py``, ``dataset.py``,
``filter_cone.py``). Currently empty.

---

## 7. ``docs/`` — plugin-local docs

Plugin-shipped documentation (release notes, end-user quickstart).
Project-wide architecture lives in the **top-level** ``docs/``
directory, not here.

---

## 8. ``tests/`` — pytest suite

Tests target the modules in ``core/`` that have no C4D dependency.
Run from the ``unav_pro/`` directory:

```
python -m pytest tests/ -v
```

A ``conftest.py`` adds the plugin root to ``sys.path`` so ``from core
import ...`` resolves identically to how it resolves inside C4D.

---

## 9. Robustness rules followed in this skeleton

These are invariants the rest of the plugin code must keep:

1. **No exception escapes the C4D boundary.** ``main()``, ``Execute``,
   ``RestoreLayout``, ``Command``, and any future ``Message`` /
   ``Draw`` handlers wrap their bodies in ``try/except`` and log the
   exception.
2. **Missing paths produce messages, not crashes.** ``mock_actions``
   already shows the pattern: a missing dataset path falls back to a
   built-in mock and reports the fallback.
3. **Version gating is centralized.** ``core.version_check.check_host``
   is the only place that decides whether the host is supported.
4. **Plugin IDs are centralized.** ``core.plugin_ids`` is the single
   source of truth; tests assert uniqueness.
5. **Logging never blocks startup.** A failure to open the log file is
   logged to the stream handler and the plugin continues.
6. **No top-level ``c4d`` import in testable modules.** ``core/*`` is
   importable in plain CPython; tests run without a host.

---

## 10. Where to add new code

| Adding...                          | Goes in                              |
|------------------------------------|--------------------------------------|
| New menu command                   | ``ui/<name>_command.py`` + register from ``unav_plugin.pyp`` |
| New dialog                         | ``ui/<name>_dialog.py``              |
| New scene-object plugin class      | ``c4d_objects/<name>.py``            |
| Cache or protocol code             | ``data/<name>.py``                   |
| New plugin ID                      | append to ``core/plugin_ids.py``     |
| New unit test                      | ``tests/test_<module>.py``           |
