"""v2.4 plugin health check.

Pre-flight diagnostics that verify the plugin's runtime
environment is sane: paths exist, the per-user config /
cache directory is writable, the dataset registry loads,
the sample catalog is reachable, the optional DB module
imports cleanly, and the plugin's own version metadata is
intact.

Each probe is wrapped in a defensive try / except. The
report's ``ok`` flag is the dialog's "is anything broken
right now" answer; per-probe ``HealthCheckEntry`` rows
carry the detail.

No Cinema 4D dependency. Pure stdlib + the v0.x persistence
helpers. Tests drive every probe directly without the host.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from core.logging_util import get_logger

_log = get_logger("core.health_check")


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

STATUS_OK: str = "ok"
STATUS_WARNING: str = "warning"
STATUS_ERROR: str = "error"
STATUS_INFO: str = "info"

STATUSES: tuple = (STATUS_OK, STATUS_WARNING, STATUS_ERROR, STATUS_INFO)


@dataclass
class HealthCheckEntry:
    """One health-check finding."""

    name: str
    status: str = STATUS_OK
    detail: str = ""

    def is_ok(self) -> bool:
        return self.status == STATUS_OK

    def is_error(self) -> bool:
        return self.status == STATUS_ERROR

    def is_warning(self) -> bool:
        return self.status == STATUS_WARNING


@dataclass
class HealthReport:
    """Aggregate of every probe's finding."""

    entries: List[HealthCheckEntry] = field(default_factory=list)

    def is_healthy(self) -> bool:
        return not any(e.is_error() for e in self.entries)

    def has_warnings(self) -> bool:
        return any(e.is_warning() for e in self.entries)

    def errors(self) -> List[HealthCheckEntry]:
        return [e for e in self.entries if e.is_error()]

    def warnings(self) -> List[HealthCheckEntry]:
        return [e for e in self.entries if e.is_warning()]

    def summary_line(self) -> str:
        if self.is_healthy() and not self.has_warnings():
            return f"Health: OK ({len(self.entries)} probe(s))."
        if self.is_healthy():
            return (
                f"Health: OK ({len(self.entries)} probe(s); "
                f"{len(self.warnings())} warning(s))."
            )
        return (
            f"Health: FAIL ({len(self.errors())} error(s) / "
            f"{len(self.warnings())} warning(s))."
        )

    def render(self) -> str:
        lines: List[str] = ["=== UNAV Health Check ==="]
        lines.append(self.summary_line())
        lines.append("")
        for e in self.entries:
            mark = (
                "[OK]" if e.is_ok()
                else "[!!]" if e.is_warning()
                else "[ERR]" if e.is_error()
                else "[..]"
            )
            lines.append(f"  {mark} {e.name:22} {e.detail}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual probes
# ---------------------------------------------------------------------------


def _probe_version() -> HealthCheckEntry:
    try:
        from unav_pro.version import VersionInfo, get_version_info
    except ImportError:
        try:
            from version import get_version_info  # type: ignore
        except ImportError:
            return HealthCheckEntry(
                name="version",
                status=STATUS_ERROR,
                detail="version module not importable.",
            )
    try:
        info = get_version_info()
        return HealthCheckEntry(
            name="version",
            status=STATUS_OK,
            detail=info.display_line(),
        )
    except Exception as exc:  # noqa: BLE001
        return HealthCheckEntry(
            name="version",
            status=STATUS_ERROR,
            detail=f"version probe raised: {exc}",
        )


def _probe_config_dir() -> HealthCheckEntry:
    try:
        from core.config import default_config_dir
    except ImportError as exc:
        return HealthCheckEntry(
            name="config_dir",
            status=STATUS_ERROR,
            detail=f"core.config not importable: {exc}",
        )
    cfg_dir = default_config_dir()
    try:
        os.makedirs(cfg_dir, exist_ok=True)
    except OSError as exc:
        return HealthCheckEntry(
            name="config_dir",
            status=STATUS_ERROR,
            detail=f"could not create {cfg_dir}: {exc}",
        )
    # Probe writability with a tempfile.
    try:
        with tempfile.NamedTemporaryFile(
            dir=cfg_dir, prefix=".unav_health_", delete=True,
        ) as fh:
            fh.write(b"ok")
    except OSError as exc:
        return HealthCheckEntry(
            name="config_dir",
            status=STATUS_ERROR,
            detail=f"config dir not writable: {exc}",
        )
    return HealthCheckEntry(
        name="config_dir",
        status=STATUS_OK,
        detail=f"writable at {cfg_dir}",
    )


def _probe_cache_dir() -> HealthCheckEntry:
    try:
        from core.config import load_config
    except ImportError as exc:
        return HealthCheckEntry(
            name="cache_dir",
            status=STATUS_ERROR,
            detail=f"core.config not importable: {exc}",
        )
    try:
        cfg = load_config()
        cache_dir = getattr(cfg, "cache_root", "") or ""
    except Exception as exc:  # noqa: BLE001
        return HealthCheckEntry(
            name="cache_dir",
            status=STATUS_WARNING,
            detail=f"could not load config: {exc}",
        )
    if not cache_dir:
        return HealthCheckEntry(
            name="cache_dir",
            status=STATUS_INFO,
            detail="no cache_root configured (preprocessing tools will pick a default).",
        )
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError as exc:
        return HealthCheckEntry(
            name="cache_dir",
            status=STATUS_WARNING,
            detail=f"cache dir not writable: {exc}",
        )
    return HealthCheckEntry(
        name="cache_dir",
        status=STATUS_OK,
        detail=f"writable at {cache_dir}",
    )


def _probe_dataset_registry() -> HealthCheckEntry:
    try:
        from core.dataset_registry import (
            DatasetRegistry, default_registry_path,
        )
    except ImportError as exc:
        return HealthCheckEntry(
            name="dataset_registry",
            status=STATUS_ERROR,
            detail=f"core.dataset_registry not importable: {exc}",
        )
    path = default_registry_path()
    if not os.path.isfile(path):
        return HealthCheckEntry(
            name="dataset_registry",
            status=STATUS_INFO,
            detail=(
                "no registry on disk yet — first launch will "
                "seed the bundled sample."
            ),
        )
    try:
        reg = DatasetRegistry.load(path)
    except Exception as exc:  # noqa: BLE001
        return HealthCheckEntry(
            name="dataset_registry",
            status=STATUS_ERROR,
            detail=f"registry load raised: {exc}",
        )
    enabled = sum(1 for e in reg.entries if getattr(e, "enabled", False))
    return HealthCheckEntry(
        name="dataset_registry",
        status=STATUS_OK,
        detail=f"{len(reg.entries)} entries ({enabled} enabled)",
    )


def _probe_sample_catalog() -> HealthCheckEntry:
    """The bundled sample catalog must exist for a fresh
    install to be useful. The path is fixed inside the
    plugin package."""
    try:
        from data.sample_catalog_generator import (
            default_sample_catalog_path,
        )
    except ImportError:
        # Fall back to a hardcoded relative probe.
        return _probe_sample_catalog_fallback()
    path = default_sample_catalog_path()
    if not os.path.isfile(path):
        return HealthCheckEntry(
            name="sample_catalog",
            status=STATUS_WARNING,
            detail=(
                f"missing bundled sample at {path}; the demo "
                "workflow won't work without it."
            ),
        )
    try:
        size_kb = os.path.getsize(path) / 1024.0
    except OSError:
        size_kb = 0.0
    return HealthCheckEntry(
        name="sample_catalog",
        status=STATUS_OK,
        detail=f"present ({size_kb:.1f} KB) at {path}",
    )


def _probe_sample_catalog_fallback() -> HealthCheckEntry:
    """Best-effort sample probe used when the helper module
    isn't available (very early installs, hand-edited
    layouts)."""
    here = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.dirname(here)
    candidate = os.path.join(
        plugin_root, "data", "samples", "sample_catalog_100.jsonl",
    )
    if os.path.isfile(candidate):
        return HealthCheckEntry(
            name="sample_catalog",
            status=STATUS_OK,
            detail=f"present at {candidate}",
        )
    return HealthCheckEntry(
        name="sample_catalog",
        status=STATUS_WARNING,
        detail=(
            f"missing bundled sample at {candidate}."
        ),
    )


def _probe_db_module() -> HealthCheckEntry:
    """The v1.1 DB layer is optional — UNAV runs without it
    when the artist sticks to JSONL. The probe reports
    presence + version, never an error."""
    try:
        import sqlite3
        return HealthCheckEntry(
            name="db_module",
            status=STATUS_OK,
            detail=f"sqlite3 {sqlite3.sqlite_version} available",
        )
    except ImportError:
        return HealthCheckEntry(
            name="db_module",
            status=STATUS_WARNING,
            detail=(
                "sqlite3 stdlib module unavailable — DB-backed "
                "datasets will fall back to JSONL streaming."
            ),
        )


def _probe_voyage_module() -> HealthCheckEntry:
    """v1.4 voyage stack must be importable."""
    try:
        from voyage import Mission, MissionWaypoint  # noqa: F401
        return HealthCheckEntry(
            name="voyage",
            status=STATUS_OK,
            detail="voyage package importable.",
        )
    except ImportError as exc:
        return HealthCheckEntry(
            name="voyage",
            status=STATUS_ERROR,
            detail=f"voyage not importable: {exc}",
        )


def _probe_export_module() -> HealthCheckEntry:
    """v2.3 export stack must be importable."""
    try:
        from export import EXPORT_FORMATS  # noqa: F401
        return HealthCheckEntry(
            name="export",
            status=STATUS_OK,
            detail="export package importable.",
        )
    except ImportError as exc:
        return HealthCheckEntry(
            name="export",
            status=STATUS_ERROR,
            detail=f"export not importable: {exc}",
        )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


_PROBES: tuple = (
    _probe_version,
    _probe_config_dir,
    _probe_cache_dir,
    _probe_dataset_registry,
    _probe_sample_catalog,
    _probe_db_module,
    _probe_voyage_module,
    _probe_export_module,
)


def run_health_check() -> HealthReport:
    """Run every v2.4 probe and return the aggregate report.

    Each probe is wrapped in a defensive boundary handler so
    a buggy probe can't break the rest of the report. Tests
    drive this top-level function + each probe directly.
    """
    report = HealthReport()
    for probe in _PROBES:
        try:
            entry = probe()
        except Exception as exc:  # noqa: BLE001 — boundary
            entry = HealthCheckEntry(
                name=getattr(probe, "__name__", "probe").lstrip("_"),
                status=STATUS_ERROR,
                detail=f"probe raised: {exc}",
            )
        report.entries.append(entry)
    return report


def list_probe_names() -> List[str]:
    """Used by tests + by the diagnostics panel to show
    "we're about to run these probes" before executing."""
    return [
        getattr(p, "__name__", "").lstrip("_") for p in _PROBES
    ]
