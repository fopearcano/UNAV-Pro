"""UNAV Pro — Cinema 4D plugin entry point.

Cinema 4D scans its plugin directories for ``*.pyp`` files at startup
and executes them. This file:

  1. Adds the plugin package directory to ``sys.path`` so the
     ``core``, ``ui``, ``data``, and ``c4d_objects`` sub-packages are
     importable without a parent package prefix.
  2. Initializes the plugin logger.
  3. Verifies that the host meets our minimum C4D 2023+ requirement.
  4. Registers all plugin classes (currently: the main menu command).

Every step is wrapped in defensive error handling. The plugin must
either register cleanly or refuse to register with a clear log line —
it must never leave Cinema 4D in a half-initialized state or raise an
exception out of ``PluginMessage`` / ``main``.
"""

from __future__ import annotations

import os
import sys
import traceback


# --- 1. sys.path bootstrap ----------------------------------------------------
# This file lives at <plugin_root>/unav_plugin.pyp. We add <plugin_root>
# to sys.path so "from core import ..." and "from ui import ..." work.

_PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)


def _emergency_print(msg: str) -> None:
    """Last-resort logging when our logger is not yet available."""
    try:
        print(f"[UNAV Pro] {msg}")
    except Exception:
        pass


# --- 2. Imports ---------------------------------------------------------------

try:
    import c4d  # type: ignore  # noqa: F401  (presence check)
except ImportError:
    _emergency_print("Cinema 4D module not available; aborting plugin load.")
    raise

try:
    from core.logging_util import init_logging, get_logger, log_file_path
    from core.version_check import check_host
    from ui import main_command
except Exception:  # noqa: BLE001 — startup boundary
    _emergency_print("Failed to import UNAV Pro modules:")
    _emergency_print(traceback.format_exc())
    raise


# --- 3. Plugin lifecycle ------------------------------------------------------

def _register_all() -> None:
    log = get_logger("bootstrap")
    log.info("UNAV Pro starting (plugin root: %s).", _PLUGIN_ROOT)

    ok, message = check_host()
    if not ok:
        log.error("Host version check failed: %s", message)
        log.error("UNAV Pro will not register any plugin classes.")
        return
    log.info(message)

    try:
        main_command.register()
    except Exception:  # noqa: BLE001
        log.exception("Exception during command registration; UNAV Pro disabled.")
        return

    if log_file_path():
        log.info("Log file: %s", log_file_path())
    log.info("UNAV Pro registration complete.")


def main() -> None:
    """Called by Cinema 4D when the .pyp file is loaded."""
    try:
        init_logging()
        _register_all()
    except Exception:  # noqa: BLE001 — never raise out of main()
        _emergency_print("Unhandled exception during UNAV Pro startup:")
        _emergency_print(traceback.format_exc())


if __name__ == "__main__":
    main()
