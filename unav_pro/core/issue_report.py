"""v3.5 issue-report bundle generator.

When a public-alpha tester hits a bug, the dialog's
*Diagnostics → Create Issue Report* button assembles a
**single Markdown document** that captures everything a
maintainer would ask for first:

* plug-in version + codename;
* Cinema 4D version (when running inside the host);
* Python version + platform;
* OS info (kernel + machine);
* the workspace status (path + intact / broken);
* the dataset registry status (entry count + active
  count);
* the most recent health-check report;
* the last N status-log lines from the dialog.

The report is **plain text**; it never includes the
artist's catalog data, mission JSONs, or scene file. It is
safe to attach to a GitHub issue or paste into a forum
thread.

This module is **pure stdlib**. It probes ``c4d`` lazily
(falls back gracefully when not loaded). Tests drive
``build_issue_report(...)`` directly with synthetic
inputs.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


#: Version of the issue-report format. Bumps when the
#: layout changes incompatibly so a maintainer can read
#: an old report unambiguously.
ISSUE_REPORT_SCHEMA_VERSION: int = 1

#: Default number of recent log lines included.
DEFAULT_LOG_TAIL_LINES: int = 50

#: Hard cap on the bundled log length so the report can
#: never balloon past a sensible attachment size.
MAX_LOG_BYTES: int = 32 * 1024


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------


@dataclass
class HostEnvironment:
    """Snapshot of the runtime UNAV is running under."""

    plugin_version: str = ""
    plugin_codename: str = ""
    python_version: str = ""
    platform_string: str = ""
    machine: str = ""
    inside_c4d: bool = False
    c4d_api_version: str = ""
    c4d_build_version: str = ""

    def render(self) -> str:
        lines: List[str] = []
        if self.plugin_version:
            tag = (
                f"UNAV Pro v{self.plugin_version}"
                + (f" ({self.plugin_codename})" if self.plugin_codename else "")
            )
            lines.append(f"- **Plug-in**: {tag}")
        lines.append(f"- **Python**: {self.python_version}")
        lines.append(f"- **OS**: {self.platform_string}")
        if self.machine:
            lines.append(f"- **Machine**: {self.machine}")
        if self.inside_c4d:
            lines.append(
                f"- **Cinema 4D**: API {self.c4d_api_version}"
                + (f", build {self.c4d_build_version}"
                   if self.c4d_build_version else "")
            )
        else:
            lines.append("- **Cinema 4D**: not running inside the host (CLI / test).")
        return "\n".join(lines)


def probe_host_environment() -> HostEnvironment:
    """Defensive probe: every reachable subsystem is
    queried inside its own try/except so a single
    failure can't break the rest of the report."""
    env = HostEnvironment()
    try:
        from version import get_version_info  # type: ignore
        info = get_version_info()
        env.plugin_version = info.plugin_version
        env.plugin_codename = info.codename
    except Exception:  # noqa: BLE001
        pass
    env.python_version = ".".join(str(x) for x in sys.version_info[:3])
    try:
        env.platform_string = platform.platform(aliased=True)
    except Exception:  # noqa: BLE001
        env.platform_string = sys.platform
    try:
        env.machine = platform.machine()
    except Exception:  # noqa: BLE001
        pass
    try:
        import c4d  # type: ignore
        env.inside_c4d = True
        env.c4d_api_version = str(getattr(c4d, "API_VERSION", "?"))
        env.c4d_build_version = str(getattr(c4d, "VERSION", "?"))
    except ImportError:
        env.inside_c4d = False
    except Exception:  # noqa: BLE001
        env.inside_c4d = False
    return env


# ---------------------------------------------------------------------------
# Workspace + dataset status (defensive)
# ---------------------------------------------------------------------------


@dataclass
class WorkspaceStatus:
    active: bool = False
    root: str = ""
    intact: bool = False
    project_name: str = ""
    plugin_version: str = ""
    note: str = ""

    def render(self) -> str:
        if not self.active:
            return f"- **Workspace**: not active{self._note_suffix()}"
        intact = "intact" if self.intact else "missing one or more subdirectories"
        return (
            f"- **Workspace**: `{self.root}` ({intact})"
            + (f" · {self.project_name}" if self.project_name else "")
            + self._note_suffix()
        )

    def _note_suffix(self) -> str:
        return f" — {self.note}" if self.note else ""


def probe_workspace_status() -> WorkspaceStatus:
    status = WorkspaceStatus()
    try:
        from core.state_manager import current_workspace
        ws = current_workspace()
    except Exception as exc:  # noqa: BLE001
        status.note = f"state_manager.current_workspace() failed: {exc}"
        return status
    if ws is None:
        return status
    status.active = True
    try:
        status.root = str(getattr(ws, "root", "") or "")
        status.intact = bool(getattr(ws, "is_intact", lambda: False)())
        manifest = getattr(ws, "manifest", None)
        if manifest is not None:
            status.project_name = str(getattr(manifest, "project_name", "") or "")
            status.plugin_version = str(getattr(manifest, "plugin_version", "") or "")
    except Exception as exc:  # noqa: BLE001
        status.note = f"workspace probe partial failure: {exc}"
    return status


@dataclass
class DatasetStatus:
    total: int = 0
    enabled: int = 0
    indexed: int = 0
    note: str = ""

    def render(self) -> str:
        if self.total == 0 and not self.note:
            return "- **Datasets**: registry is empty."
        line = (
            f"- **Datasets**: {self.enabled}/{self.total} enabled"
            f" · {self.indexed} indexed"
        )
        if self.note:
            line += f" — {self.note}"
        return line


def probe_dataset_status() -> DatasetStatus:
    status = DatasetStatus()
    try:
        from core.state_manager import get_dataset_registry
        registry = get_dataset_registry()
    except Exception as exc:  # noqa: BLE001
        status.note = f"dataset registry probe failed: {exc}"
        return status
    try:
        entries = list(getattr(registry, "entries", ()) or ())
        status.total = len(entries)
        status.enabled = sum(
            1 for e in entries if bool(getattr(e, "enabled", False))
        )
        status.indexed = sum(
            1 for e in entries
            if str(getattr(e, "index_path", "") or "")
        )
    except Exception as exc:  # noqa: BLE001
        status.note = f"dataset enumeration partial failure: {exc}"
    return status


# ---------------------------------------------------------------------------
# Health snapshot
# ---------------------------------------------------------------------------


@dataclass
class HealthSnapshot:
    overall: str = ""
    rendered: str = ""
    note: str = ""

    def render(self) -> str:
        lines: List[str] = []
        if self.overall:
            lines.append(f"- **Health**: {self.overall}")
        if self.note:
            lines.append(f"  - note: {self.note}")
        if self.rendered:
            lines.append("```text")
            lines.append(self.rendered.strip())
            lines.append("```")
        return "\n".join(lines)


def probe_health_snapshot() -> HealthSnapshot:
    snap = HealthSnapshot()
    try:
        from core.health_check import run_health_check
        report = run_health_check()
        snap.overall = report.summary_line()
        snap.rendered = report.render()
    except Exception as exc:  # noqa: BLE001
        snap.note = f"health_check.run_health_check() failed: {exc}"
    return snap


# ---------------------------------------------------------------------------
# Log tail
# ---------------------------------------------------------------------------


def trim_log_tail(
    lines: Iterable[str],
    *,
    max_lines: int = DEFAULT_LOG_TAIL_LINES,
    max_bytes: int = MAX_LOG_BYTES,
) -> List[str]:
    """Take the last ``max_lines`` entries, then truncate
    from the front so the joined text stays under
    ``max_bytes`` (UTF-8). Pure helper."""
    raw = [str(s) for s in lines]
    if max_lines > 0:
        raw = raw[-max_lines:]
    if max_bytes <= 0:
        return raw
    out: List[str] = []
    running = 0
    for line in reversed(raw):
        size = len(line.encode("utf-8")) + 1
        if running + size > max_bytes:
            break
        out.append(line)
        running += size
    out.reverse()
    return out


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------


@dataclass
class IssueReport:
    """The assembled Markdown document. ``body`` is the
    text the dialog hands to the artist (saved to disk
    or copied to clipboard)."""

    schema_version: int = ISSUE_REPORT_SCHEMA_VERSION
    generated_at_iso: str = ""
    title: str = "UNAV Pro Issue Report"
    body: str = ""

    def to_markdown(self) -> str:
        """Alias used by tests + the dialog status log."""
        return self.body


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_issue_report(
    *,
    user_summary: str = "",
    log_tail: Optional[Sequence[str]] = None,
    host_env: Optional[HostEnvironment] = None,
    workspace_status: Optional[WorkspaceStatus] = None,
    dataset_status: Optional[DatasetStatus] = None,
    health_snapshot: Optional[HealthSnapshot] = None,
) -> IssueReport:
    """Compose the full report.

    Each subsystem probe is **optional** — pass ``None``
    and the probe runs against the live state. Tests
    pass synthetic ``HostEnvironment`` / ``WorkspaceStatus``
    / etc. so the assertions stay deterministic.

    The output is **plain Markdown** safe for any text
    field on a bug-tracking site.
    """
    env = host_env if host_env is not None else probe_host_environment()
    ws = workspace_status if workspace_status is not None else probe_workspace_status()
    ds = dataset_status if dataset_status is not None else probe_dataset_status()
    hs = health_snapshot if health_snapshot is not None else probe_health_snapshot()
    log_lines = trim_log_tail(log_tail or [])

    stamp = _utc_iso()
    lines: List[str] = []
    lines.append("# UNAV Pro Issue Report")
    lines.append("")
    lines.append(f"*Generated: {stamp}*")
    lines.append("")
    if user_summary:
        lines.append("## User-supplied summary")
        lines.append("")
        lines.append(user_summary.strip())
        lines.append("")
    lines.append("## Environment")
    lines.append("")
    lines.append(env.render())
    lines.append("")
    lines.append("## State")
    lines.append("")
    lines.append(ws.render())
    lines.append(ds.render())
    lines.append("")
    lines.append("## Health check")
    lines.append("")
    if hs.rendered or hs.overall or hs.note:
        lines.append(hs.render())
    else:
        lines.append("(no health check captured)")
    lines.append("")
    lines.append("## Recent status log")
    lines.append("")
    if log_lines:
        lines.append("```text")
        for line in log_lines:
            lines.append(line)
        lines.append("```")
    else:
        lines.append("(no log lines captured)")
    lines.append("")
    lines.append("## Boundary reminder")
    lines.append("")
    lines.append(
        "UNAV Pro is a Cinema 4D astronomical navigation + voyage / "
        "camera-animation plug-in. It is **not** a renderer, **not** "
        "a network service, and runs single-threaded inside Cinema "
        "4D. See `docs/ROADMAP.md` §4 for the full out-of-scope list."
    )
    lines.append("")
    body = "\n".join(lines).rstrip() + "\n"
    return IssueReport(
        schema_version=ISSUE_REPORT_SCHEMA_VERSION,
        generated_at_iso=stamp,
        body=body,
    )


def write_issue_report(
    report: IssueReport, path: str,
) -> str:
    """Atomic write helper. Returns the absolute path the
    report was written to."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(report.body)
    os.replace(tmp, path)
    return os.path.abspath(path)
