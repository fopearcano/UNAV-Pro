"""v1.7 central state facade.

Every UNAV state surface is reachable through this module:

* the in-memory dataset registry,
* the metadata lookup,
* the time-navigator state,
* the per-user config,
* the bookmarks list,
* the mission manager.

The dialog used to import each of these from its own module
and chain through several lazy initialisers; v1.7 collects
the touch-points into one place. There is **no new state
here** — the underlying singletons are unchanged. This file
is the seam: a single import surface for diagnostics, a
single ``health_summary()`` for the dialog, a single
``reload_all()`` for the "Reset / Reload" button.

Pure stdlib. Zero c4d dependency. Importing this module is
side-effect-free; lazy initialisation only fires when each
``get_*`` helper is called.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.bookmarks import (
    BookmarkList,
    default_bookmarks_path,
    load_bookmarks,
    save_bookmarks,
)
from core.config import (
    UnavConfig,
    default_config_path,
    load_config,
    save_config,
)
from core.dataset_registry import (
    DatasetRegistry,
    bootstrap_with_sample,
    default_registry_path,
)
from core.logging_util import get_logger
from core.metadata_lookup import default_lookup, set_default_lookup
from core.time_navigator import (
    TimeNavigatorState,
    default_state as default_time_state,
    set_default_state as set_default_time_state,
)

_log = get_logger("core.state_manager")


# ---------------------------------------------------------------------------
# Health summary
# ---------------------------------------------------------------------------


@dataclass
class StateHealthEntry:
    """One line in the diagnostics panel's health summary."""

    name: str
    ok: bool = True
    detail: str = ""


@dataclass
class StateHealth:
    """Aggregate snapshot of every UNAV state surface.

    The diagnostics panel renders this verbatim. Each entry's
    ``ok`` flag tells the artist whether that subsystem loaded
    cleanly; the ``detail`` string carries one short sentence of
    human-readable context (count of items, last error, …)."""

    entries: List[StateHealthEntry] = field(default_factory=list)

    def is_healthy(self) -> bool:
        return all(e.ok for e in self.entries)

    def summary_line(self) -> str:
        bad = [e.name for e in self.entries if not e.ok]
        if bad:
            return f"UNAV health: {len(bad)} subsystem(s) report issues — {', '.join(bad)}"
        return f"UNAV health: OK ({len(self.entries)} subsystems)"

    def render(self) -> str:
        lines: List[str] = ["=== UNAV State Health ==="]
        lines.append(self.summary_line())
        lines.append("")
        for entry in self.entries:
            mark = "[OK]" if entry.ok else "[!!]"
            lines.append(f"  {mark} {entry.name:18} {entry.detail}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Singletons — uniform get/set/reload
# ---------------------------------------------------------------------------


_dataset_registry: Optional[DatasetRegistry] = None


def get_dataset_registry(*, reload: bool = False) -> DatasetRegistry:
    """Return the process-wide ``DatasetRegistry``. Loaded from
    ``~/.unav_pro/datasets.json`` on first call (falls back to a
    sample-seeded registry when the file is missing).

    With ``reload=True`` the on-disk registry is re-read and the
    in-memory entries are replaced."""
    global _dataset_registry
    if reload or _dataset_registry is None:
        path = default_registry_path()
        try:
            loaded = DatasetRegistry.load(path)
            if not loaded.entries:
                loaded = bootstrap_with_sample()
            _dataset_registry = loaded
        except Exception as exc:  # noqa: BLE001 — boundary handler
            _log.warning("Falling back to sample registry: %s", exc)
            _dataset_registry = bootstrap_with_sample()
    return _dataset_registry


def set_dataset_registry(registry: Optional[DatasetRegistry]) -> None:
    global _dataset_registry
    _dataset_registry = registry


def reload_all() -> None:
    """Reset every singleton this facade tracks. Useful for the
    diagnostics panel's "Reload State" button and for tests that
    want a clean slate between runs."""
    set_dataset_registry(None)
    set_default_time_state(None)
    set_default_lookup(None)
    set_current_workspace(None)
    set_current_mission(None)


# ---------------------------------------------------------------------------
# v3.4: shared accessors the diagnostics + reset tools read.
#
# The dialog populates these from ui/main_dialog.py when the
# artist opens a workspace or activates a mission. Pure
# data; the facade itself does no I/O.
# ---------------------------------------------------------------------------


_current_workspace: Optional[object] = None
_current_mission: Optional[object] = None


def current_workspace():
    """Return the active v3.1 ``Workspace`` instance, or
    ``None`` when no workspace is loaded."""
    return _current_workspace


def set_current_workspace(workspace) -> None:
    """Replace the active workspace. The dialog calls this
    after ``project.open_workspace`` succeeds."""
    global _current_workspace
    _current_workspace = workspace


def current_mission():
    """Return the active v1.4 ``Mission`` instance, or
    ``None``."""
    return _current_mission


def set_current_mission(mission) -> None:
    """Replace the active mission. The dialog calls this
    when the artist clicks 'Activate' on a mission."""
    global _current_mission
    _current_mission = mission


# ---------------------------------------------------------------------------
# Health summary builders
# ---------------------------------------------------------------------------


def _check_config() -> StateHealthEntry:
    try:
        cfg = load_config()
        return StateHealthEntry(
            name="config",
            ok=True,
            detail=f"v{cfg.schema_version} at {default_config_path()}",
        )
    except Exception as exc:  # noqa: BLE001
        return StateHealthEntry(name="config", ok=False, detail=str(exc))


def _check_bookmarks() -> StateHealthEntry:
    try:
        bm = load_bookmarks()
        return StateHealthEntry(
            name="bookmarks",
            ok=True,
            detail=f"{len(bm)} bookmark(s) at {default_bookmarks_path()}",
        )
    except Exception as exc:  # noqa: BLE001
        return StateHealthEntry(name="bookmarks", ok=False, detail=str(exc))


def _check_dataset_registry() -> StateHealthEntry:
    try:
        reg = get_dataset_registry()
        enabled = sum(1 for e in reg.entries if e.enabled)
        return StateHealthEntry(
            name="datasets",
            ok=True,
            detail=f"{len(reg.entries)} entries ({enabled} enabled)",
        )
    except Exception as exc:  # noqa: BLE001
        return StateHealthEntry(name="datasets", ok=False, detail=str(exc))


def _check_time_navigator() -> StateHealthEntry:
    try:
        state = default_time_state()
        return StateHealthEntry(
            name="time_navigator",
            ok=True,
            detail=(
                f"epoch JD {state.current_epoch_jd:.3f}, "
                f"step {state.step_days:g}d"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return StateHealthEntry(name="time_navigator", ok=False, detail=str(exc))


def _check_metadata_lookup() -> StateHealthEntry:
    try:
        lookup = default_lookup()
        size = len(lookup) if lookup is not None else 0
        return StateHealthEntry(
            name="metadata_lookup",
            ok=True,
            detail=f"{size} object(s) cached",
        )
    except Exception as exc:  # noqa: BLE001
        return StateHealthEntry(name="metadata_lookup", ok=False, detail=str(exc))


def _check_missions() -> StateHealthEntry:
    try:
        from voyage.mission_manager import MissionManager
        mgr = MissionManager()
        return StateHealthEntry(
            name="missions",
            ok=True,
            detail=f"{len(mgr)} mission(s)",
        )
    except Exception as exc:  # noqa: BLE001
        return StateHealthEntry(name="missions", ok=False, detail=str(exc))


def health_summary() -> StateHealth:
    """Aggregate health snapshot. Never raises — every probe is
    wrapped in a boundary handler that logs and degrades to an
    ``ok=False`` entry."""
    return StateHealth(entries=[
        _check_config(),
        _check_bookmarks(),
        _check_dataset_registry(),
        _check_time_navigator(),
        _check_metadata_lookup(),
        _check_missions(),
    ])


# ---------------------------------------------------------------------------
# Per-subsystem summaries (for the diagnostics tab)
# ---------------------------------------------------------------------------


def dataset_summary() -> str:
    """Multi-line plain text summary of every registered
    dataset. Used by the diagnostics panel and by the
    ``/health`` slash command in tests."""
    reg = get_dataset_registry()
    if not reg.entries:
        return "No datasets registered."
    lines: List[str] = [f"=== Datasets ({len(reg.entries)}) ==="]
    for i, entry in enumerate(reg.entries):
        flag = "ON " if entry.enabled else "off"
        kind = (
            "db" if entry.is_db_backed
            else "idx" if entry.is_indexed
            else "jsonl"
        )
        lines.append(
            f"  [{i}] {flag}  {entry.name}  ({kind})  "
            f"{entry.path or entry.db_path or '<no path>'}"
        )
    return "\n".join(lines)


def visible_sector_summary(doc=None) -> str:
    """Count of currently-materialised UNAV scene objects.

    Pure-Python: when ``doc`` is None, returns a placeholder
    suitable for tests. The C4D-bound code path passes the
    active document and walks ``UNAV_VisibleSector`` to count
    children."""
    if doc is None:
        return "Visible sector: (no active document)"
    try:
        from c4d_objects.point_cloud_builder import (
            ROOT_NAME,
            VISIBLE_SECTOR_NAME,
        )
    except ImportError:
        return "Visible sector: (c4d_objects unavailable)"
    try:
        root = doc.SearchObject(ROOT_NAME)
        if root is None:
            return "Visible sector: 0 (no UNAV root in scene)"
        sector = None
        child = root.GetDown()
        while child is not None:
            if child.GetName() == VISIBLE_SECTOR_NAME:
                sector = child
                break
            child = child.GetNext()
        if sector is None:
            return "Visible sector: 0 (no UNAV_VisibleSector group)"
        count = 0
        node = sector.GetDown()
        while node is not None:
            count += 1
            node = node.GetNext()
        return f"Visible sector: {count} object(s)"
    except Exception as exc:  # noqa: BLE001 — boundary
        return f"Visible sector: scan failed: {exc}"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_config(cfg: UnavConfig) -> List[str]:
    """Return a list of human-readable issues for ``cfg``. Empty
    means valid. Used by the diagnostics panel's "validate
    config" button and by the v1.7 reload tests."""
    issues: List[str] = []
    if not isinstance(cfg, UnavConfig):
        issues.append("config is not a UnavConfig instance")
        return issues
    if cfg.schema_version <= 0:
        issues.append(f"schema_version must be > 0; got {cfg.schema_version}")
    return issues


def validate_bookmarks(bookmarks: BookmarkList) -> List[str]:
    issues: List[str] = []
    seen_ids = set()
    for i, bm in enumerate(bookmarks):
        if not bm.id:
            issues.append(f"bookmark[{i}] has no id")
            continue
        if bm.id in seen_ids:
            issues.append(f"duplicate bookmark id: {bm.id}")
        seen_ids.add(bm.id)
    return issues


def validate_registry(registry: DatasetRegistry) -> List[str]:
    issues: List[str] = []
    seen_names = set()
    for i, e in enumerate(registry.entries):
        if not e.name:
            issues.append(f"entry[{i}] has no name")
            continue
        if e.name in seen_names:
            issues.append(f"duplicate dataset name: {e.name}")
        seen_names.add(e.name)
        if not (e.path or e.db_path):
            issues.append(f"entry '{e.name}' has neither path nor db_path")
    return issues
