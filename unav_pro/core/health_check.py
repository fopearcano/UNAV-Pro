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
# v3.4 internal-beta probes
# ---------------------------------------------------------------------------


def _probe_python_runtime() -> HealthCheckEntry:
    """Report the Python interpreter UNAV is running under.

    Cinema 4D 2023+ ships Python 3.11; the plugin is
    written + tested against that. We log the live
    version so the diagnostics panel shows it, and warn
    when the runtime is older than 3.10."""
    import sys
    ver = ".".join(str(x) for x in sys.version_info[:3])
    if sys.version_info < (3, 10):
        return HealthCheckEntry(
            name="python_runtime",
            status=STATUS_WARNING,
            detail=(
                f"Python {ver}; UNAV expects 3.10+ "
                "(C4D 2023+ ships 3.11)."
            ),
        )
    return HealthCheckEntry(
        name="python_runtime",
        status=STATUS_OK,
        detail=f"Python {ver}.",
    )


def _probe_c4d_host() -> HealthCheckEntry:
    """Report the Cinema 4D version when running inside
    the host. Outside the host (CLI / test suite) the
    probe reports informationally — that's not a failure."""
    try:
        import c4d  # type: ignore
    except ImportError:
        return HealthCheckEntry(
            name="c4d_host",
            status=STATUS_INFO,
            detail="not running inside Cinema 4D (CLI / test suite).",
        )
    api_version = "?"
    build_version = "?"
    try:
        api_version = str(getattr(c4d, "API_VERSION", "?"))
    except Exception:  # noqa: BLE001
        pass
    try:
        build_version = str(getattr(c4d, "VERSION", "?"))
    except Exception:  # noqa: BLE001
        pass
    return HealthCheckEntry(
        name="c4d_host",
        status=STATUS_OK,
        detail=f"Cinema 4D API={api_version} build={build_version}.",
    )


def _probe_workspace_state() -> HealthCheckEntry:
    """v3.1 workspace surface: inspect the in-memory
    workspace facade (when the dialog has loaded one).

    No workspace active ⇒ info, not a failure — many
    workflows don't require one.
    """
    try:
        from project import Workspace  # noqa: F401
    except ImportError as exc:
        return HealthCheckEntry(
            name="workspace",
            status=STATUS_ERROR,
            detail=f"project package not importable: {exc}",
        )
    try:
        from core.state_manager import (  # noqa: F401
            current_workspace,
        )
        ws = current_workspace()
    except Exception:  # noqa: BLE001 — boundary
        ws = None
    if ws is None:
        return HealthCheckEntry(
            name="workspace",
            status=STATUS_INFO,
            detail="no workspace active.",
        )
    try:
        intact = bool(getattr(ws, "is_intact", lambda: True)())
    except Exception:  # noqa: BLE001
        intact = False
    return HealthCheckEntry(
        name="workspace",
        status=STATUS_OK if intact else STATUS_WARNING,
        detail=(
            f"workspace at {getattr(ws, 'root', '?')!r} "
            + ("intact." if intact else "missing one or more subdirectories.")
        ),
    )


def _probe_active_mission_state() -> HealthCheckEntry:
    """v1.4 mission surface: report whether a mission is
    currently active, plus its waypoint count.

    Looks the active mission up via the state-manager
    facade. No mission active ⇒ info."""
    try:
        from core.state_manager import current_mission
        mission = current_mission()
    except (ImportError, Exception):  # noqa: BLE001
        mission = None
    if mission is None:
        return HealthCheckEntry(
            name="active_mission",
            status=STATUS_INFO,
            detail="no mission active.",
        )
    try:
        wp_count = len(getattr(mission, "waypoints", ()) or ())
        title = getattr(mission, "title", "?")
    except Exception:  # noqa: BLE001
        wp_count = 0
        title = "?"
    return HealthCheckEntry(
        name="active_mission",
        status=STATUS_OK,
        detail=f"mission {title!r} ({wp_count} waypoint(s)).",
    )


def _probe_visible_sector_state() -> HealthCheckEntry:
    """Report the materialised visible-sector size.

    Walks the active C4D document via the state-manager
    facade. Outside Cinema 4D ⇒ info; inside C4D with
    no sector ⇒ info; with a sector ⇒ ok with the count."""
    try:
        from core.state_manager import visible_sector_summary
        line = visible_sector_summary(None)
    except Exception:  # noqa: BLE001
        return HealthCheckEntry(
            name="visible_sector",
            status=STATUS_INFO,
            detail="visible-sector summary unavailable outside C4D.",
        )
    return HealthCheckEntry(
        name="visible_sector",
        status=STATUS_OK,
        detail=line,
    )


def _probe_presentation_module() -> HealthCheckEntry:
    """v3.3 presentation stack must be importable."""
    try:
        from presentation import PresentationSequence  # noqa: F401
        return HealthCheckEntry(
            name="presentation",
            status=STATUS_OK,
            detail="presentation package importable.",
        )
    except ImportError as exc:
        return HealthCheckEntry(
            name="presentation",
            status=STATUS_ERROR,
            detail=f"presentation not importable: {exc}",
        )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


_PROBES: tuple = (
    _probe_version,
    _probe_python_runtime,
    _probe_c4d_host,
    _probe_config_dir,
    _probe_cache_dir,
    _probe_dataset_registry,
    _probe_sample_catalog,
    _probe_db_module,
    _probe_voyage_module,
    _probe_export_module,
    _probe_workspace_state,
    _probe_active_mission_state,
    _probe_visible_sector_state,
    _probe_presentation_module,
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
