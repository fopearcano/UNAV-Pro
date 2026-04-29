"""Centralized logging + diagnostics for UNAV Pro.

This module wraps the existing ``core.logging_util`` (the rotating
file + stream handlers used by every module's ``get_logger``) with:

  * **A ring-buffer handler** that captures the last N log records
    in memory so the diagnostics panel can show them without
    re-reading the rotating log file.
  * **Convenience shortcuts** (``info`` / ``warning`` / ``error``
    / ``debug``) for code that does not need a per-module logger.
  * **Environment snapshot helpers** the diagnostics dialog uses to
    answer "what versions am I running, what catalogs are loaded,
    how many objects are in the scene right now?".
  * **Diagnostics formatter** that produces the multi-line text the
    UI displays and the *Copy Diagnostics* button copies to the
    clipboard.

Logging policy
--------------

All modules under ``unav_pro/`` route through ``get_logger`` (or the
shortcuts here). The two surviving ``print`` calls in the plugin
package are deliberate:

  * ``unav_plugin.pyp::_emergency_print`` — last-resort stderr at
    import time, before the logger is available. If this path fires,
    the logger module itself failed to import, so calling the
    logger would re-fail.
  * ``data/sample_catalog_generator.py`` — inside ``if __name__ ==
    "__main__"``: that block runs as a CLI, where stdout *is* the
    user-facing output channel.

CLI tools under ``tools/`` deliberately use ``print`` for the same
reason — they're CLIs, not plugin runtime.
"""

from __future__ import annotations

import collections
import logging
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

from core.logging_util import (
    _LOGGER_NAME,
    get_logger,
    init_logging,
    log_file_path,
)

#: Default ring-buffer size. 500 records is comfortable for a
#: session of debugging while still bounded.
RING_BUFFER_DEFAULT = 500

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


# ---------------------------------------------------------------------------
# Ring-buffer handler
# ---------------------------------------------------------------------------


class RingBufferHandler(logging.Handler):
    """A bounded in-memory handler. Stores rendered records as plain
    dicts (formatter-rendered timestamp, level, name, message) so
    the diagnostics panel does not have to keep ``LogRecord``
    instances around."""

    def __init__(self, maxlen: int = RING_BUFFER_DEFAULT):
        super().__init__()
        self._buffer: collections.deque = collections.deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            asctime = (
                self.formatter.formatTime(record)
                if self.formatter is not None else ""
            )
            self._buffer.append({
                "asctime": asctime,
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage(),
                "pathname": record.pathname,
                "lineno": record.lineno,
                "created": record.created,
            })
        except Exception:  # noqa: BLE001 — the logger must never raise
            pass

    def buffer(self) -> List[Dict[str, Any]]:
        return list(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()


_ring: Optional[RingBufferHandler] = None


def install_ring_buffer(
    maxlen: int = RING_BUFFER_DEFAULT,
) -> RingBufferHandler:
    """Idempotently attach a ring-buffer handler to the UNAV
    logger. Returns the handler so tests can introspect it."""
    global _ring
    init_logging()
    if _ring is not None:
        return _ring
    handler = RingBufferHandler(maxlen=maxlen)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    ))
    handler.setLevel(logging.DEBUG)
    pkg_logger = logging.getLogger(_LOGGER_NAME)
    # Diagnostics is the contract that *all four* levels (DEBUG, INFO,
    # WARNING, ERROR) flow into the ring buffer. The package logger's
    # default INFO level would silently drop DEBUG records before any
    # handler sees them; lower it so the buffer can actually capture
    # the level it advertises in its filter dropdown.
    if pkg_logger.level == logging.NOTSET or pkg_logger.level > logging.DEBUG:
        pkg_logger.setLevel(logging.DEBUG)
    pkg_logger.addHandler(handler)
    _ring = handler
    return handler


def reset_ring_buffer_for_tests() -> None:
    """Detach and forget the singleton handler. Tests use this so
    each test starts with a clean state."""
    global _ring
    if _ring is not None:
        try:
            logging.getLogger(_LOGGER_NAME).removeHandler(_ring)
        except Exception:  # noqa: BLE001
            pass
    _ring = None


def recent_logs(
    level: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return captured records, optionally filtered by level and
    limited to the most-recent ``limit`` entries.

    Returns an empty list when no ring buffer is installed — the
    diagnostics panel can render even without ever attaching."""
    if _ring is None:
        return []
    records = _ring.buffer()
    if level:
        wanted = level.upper()
        if wanted in LEVELS:
            records = [r for r in records if r["level"] == wanted]
    if limit is not None and limit >= 0:
        records = records[-limit:]
    return records


def clear_recent_logs() -> None:
    if _ring is not None:
        _ring.clear()


# ---------------------------------------------------------------------------
# Convenience shortcuts (route to the package logger)
# ---------------------------------------------------------------------------


def info(msg: str, *args: Any, name: Optional[str] = None) -> None:
    get_logger(name).info(msg, *args)


def warning(msg: str, *args: Any, name: Optional[str] = None) -> None:
    get_logger(name).warning(msg, *args)


def error(msg: str, *args: Any, name: Optional[str] = None) -> None:
    get_logger(name).error(msg, *args)


def debug(msg: str, *args: Any, name: Optional[str] = None) -> None:
    get_logger(name).debug(msg, *args)


# ---------------------------------------------------------------------------
# Environment snapshot helpers
# ---------------------------------------------------------------------------


def plugin_root() -> str:
    """Absolute path of the ``unav_pro/`` package directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def log_folder() -> Optional[str]:
    """Directory containing the rotating log file, or None when
    file logging is disabled (read-only filesystem etc.)."""
    p = log_file_path()
    if p:
        return os.path.dirname(p)
    return None


def detect_c4d_version() -> Optional[str]:
    """Return ``c4d.GetC4DVersion()`` rendered for humans, or None
    when c4d is not importable."""
    try:
        import c4d  # type: ignore
    except ImportError:
        return None
    try:
        return str(c4d.GetC4DVersion())
    except Exception:  # noqa: BLE001
        return None


def _count_visible_sector_children() -> Optional[int]:
    """How many points are currently materialized under
    UNAV_VisibleSector. None outside Cinema 4D."""
    try:
        from c4d import documents  # type: ignore
        from c4d_objects.point_cloud_builder import find_visible_sector
    except ImportError:
        return None
    try:
        doc = documents.GetActiveDocument()
        if doc is None:
            return 0
        sector = find_visible_sector(doc)
        if sector is None:
            return 0
        n = 0
        child = sector.GetDown()
        while child is not None:
            n += 1
            child = child.GetNext()
        return n
    except Exception:  # noqa: BLE001
        return None


def gather_environment(
    *,
    config: Optional[Any] = None,
    registry: Optional[Any] = None,
    lookup: Optional[Any] = None,
) -> Dict[str, Any]:
    """Snapshot the runtime environment for the diagnostics panel.

    ``config`` / ``registry`` / ``lookup`` are dependency-injected
    so the caller can pass live instances (the dialog) or mocks
    (the tests).
    """
    env: Dict[str, Any] = {
        "c4d_version": detect_c4d_version() or "(not running inside C4D)",
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": sys.platform,
        "plugin_root": plugin_root(),
        "log_file": log_file_path() or "(no file handler)",
        "log_folder": log_folder() or "(none)",
    }

    if config is not None and hasattr(config, "cache_root"):
        env["cache_root"] = os.path.expanduser(config.cache_root)

    if registry is not None and hasattr(registry, "entries"):
        env["datasets_total"] = len(registry.entries)
        env["datasets_enabled"] = len(
            [e for e in registry.entries if getattr(e, "enabled", False)]
        )
        env["datasets"] = []
        for e in registry.entries:
            stats = getattr(e, "stats", None)
            env["datasets"].append({
                "name": e.name,
                "enabled": bool(e.enabled),
                "indexed": bool(getattr(e, "is_indexed", False)),
                "object_count": (
                    stats.object_count if stats is not None else None
                ),
                "sources": (
                    list(stats.sources) if stats is not None else []
                ),
            })

    if lookup is not None:
        env["lookup_object_count"] = len(lookup)
        try:
            env["lookup_sources"] = lookup.sources()
        except Exception:  # noqa: BLE001
            env["lookup_sources"] = []

    env["generated_count"] = _count_visible_sector_children()
    return env


# ---------------------------------------------------------------------------
# Pretty rendering
# ---------------------------------------------------------------------------


def format_diagnostics(
    env: Dict[str, Any],
    records: Iterable[Dict[str, Any]] = (),
) -> str:
    """Multi-line text block for the diagnostics panel + clipboard."""
    lines: List[str] = []
    lines.append("=== UNAV Pro Diagnostics ===")
    lines.append("")
    lines.append("--- Environment ---")
    lines.append(f"Cinema 4D       : {env.get('c4d_version', '?')}")
    lines.append(f"Python          : {env.get('python_version', '?')}")
    lines.append(f"Platform        : {env.get('platform', '?')}")
    lines.append(f"Plugin root     : {env.get('plugin_root', '?')}")
    if "cache_root" in env:
        lines.append(f"Cache root      : {env['cache_root']}")
    lines.append(f"Log file        : {env.get('log_file', '?')}")
    lines.append(f"Log folder      : {env.get('log_folder', '?')}")
    lines.append("")

    lines.append("--- Datasets ---")
    if env.get("datasets") is None:
        lines.append("(no registry attached)")
    elif not env["datasets"]:
        lines.append("(none registered)")
    else:
        lines.append(
            f"Total/enabled  : "
            f"{env.get('datasets_total', 0)} / {env.get('datasets_enabled', 0)}"
        )
        for ds in env["datasets"]:
            flag = "ON " if ds["enabled"] else "off"
            idx = "idx" if ds["indexed"] else "-  "
            oc = "?" if ds["object_count"] is None else ds["object_count"]
            sources = ",".join(ds["sources"]) if ds["sources"] else "—"
            lines.append(
                f"  [{flag}] {idx} {ds['name']} "
                f"({oc} objects, sources: {sources})"
            )
    lines.append("")

    lines.append("--- Runtime ---")
    if "lookup_object_count" in env:
        lines.append(f"Lookup objects  : {env['lookup_object_count']}")
        sources = env.get("lookup_sources") or []
        if sources:
            lines.append(f"Lookup sources  : {', '.join(sources)}")
    if env.get("generated_count") is None:
        lines.append("Generated (vis) : (no active document)")
    else:
        lines.append(f"Generated (vis) : {env['generated_count']}")
    lines.append("")

    rec_list = list(records)
    if rec_list:
        lines.append(f"--- Recent log entries ({len(rec_list)}) ---")
        for rec in rec_list:
            ts = rec.get("asctime", "")
            level = rec.get("level", "?")
            name = rec.get("name", "?")
            msg = rec.get("message", "")
            lines.append(f"{ts} [{level}] {name}: {msg}")

    return "\n".join(lines)
