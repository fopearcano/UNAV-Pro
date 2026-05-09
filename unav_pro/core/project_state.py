"""Project state — the per-scene snapshot UNAV Pro saves and reloads.

Pure CPython data layer for everything the artist would expect a
"Save UNAV State" / "Load UNAV State" pair to round-trip:

  * The list of dataset names currently *enabled* in the registry
    (full registry contents are not embedded — too heavy and the
    user owns those entries elsewhere).
  * The navigator filter parameters.
  * The current route waypoints.
  * The current visual encoding (color mode, size scale,
    brightness scale, exaggeration, ramps).
  * A snapshot of the user config at save time, for forensics if
    behaviour drifts after a reload.

The c4d-bound glue (writing scene-level metadata into the
``BaseDocument`` container, computing a sidecar JSON path next to
the saved scene file, walking the registry to update enabled
flags) lives in ``ui/main_dialog.py`` and ``core/mock_actions.py``.
This module is the data source of truth; it is fully unit-tested
without Cinema 4D.

JSON shape
----------

::

    {
      "schema_version": 1,
      "saved_at_iso":   "2026-01-01T12:00:00",
      "enabled_datasets": ["UNAV Sample (bundled)", "Gaia Pleiades"],
      "navigator":      { ...NavigationParams... },
      "route":          { ...Route... },
      "visual_encoding":{ ...VisualEncodingParams... },
      "config":         { ...UnavConfig... },
      "notes":          ""
    }
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional

from core.config import UnavConfig
from core.dataset_registry import DatasetRegistry
from core.logging_util import get_logger
from core.navigation_state import NavigationParams
from core.route import Route
from core.visual_encoding import VisualEncodingParams

_log = get_logger("core.project_state")

PROJECT_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class ProjectState:
    """The bundle that "Save UNAV State" writes and "Load UNAV State"
    consumes.

    Every sub-payload is kept as a plain dict so this dataclass does
    not couple to the live shapes of ``NavigationParams`` /
    ``VisualEncodingParams`` / ``Route`` / ``UnavConfig`` — they each
    own their own ``to_dict`` / ``from_dict`` pair, and ``apply`` /
    ``gather`` are the only places the conversion happens.
    """

    schema_version: int = PROJECT_SCHEMA_VERSION
    saved_at_iso: Optional[str] = None
    enabled_datasets: List[str] = field(default_factory=list)
    navigator: Dict[str, Any] = field(default_factory=dict)
    route: Dict[str, Any] = field(default_factory=dict)
    visual_encoding: Dict[str, Any] = field(default_factory=dict)
    config: Optional[Dict[str, Any]] = None
    notes: str = ""
    # v2.0: per-project overlay visibility + sizing.
    # Stored as a plain dict (the live ``OverlaySettings`` is
    # built on demand by ``procedural.OverlaySettings.from_dict``)
    # so the project_state layer keeps zero coupling to the
    # procedural module's import surface.
    overlays: Dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------- (de)serialization
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "saved_at_iso": self.saved_at_iso,
            "enabled_datasets": list(self.enabled_datasets),
            "navigator": dict(self.navigator),
            "route": dict(self.route),
            "visual_encoding": dict(self.visual_encoding),
            "config": dict(self.config) if self.config else None,
            "notes": self.notes,
            "overlays": dict(self.overlays) if self.overlays else {},
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "ProjectState":
        d = d or {}
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in d.items() if k in known}
        if "enabled_datasets" in clean:
            clean["enabled_datasets"] = [
                str(x) for x in clean["enabled_datasets"] if x
            ]
        return cls(**clean)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "ProjectState":
        try:
            return cls.from_dict(json.loads(s or "{}"))
        except (TypeError, ValueError):
            return cls()


# ---------------------------------------------------------------------------
# Gather (live -> ProjectState)
# ---------------------------------------------------------------------------


def gather_project_state(
    *,
    registry: Optional[DatasetRegistry] = None,
    navigator: Optional[NavigationParams] = None,
    route: Optional[Route] = None,
    encoding: Optional[VisualEncodingParams] = None,
    config: Optional[UnavConfig] = None,
    notes: str = "",
) -> ProjectState:
    """Snapshot the current in-memory pieces into a ``ProjectState``.

    Every argument is optional so partial gathers (e.g. when the
    navigator hierarchy isn't in the scene yet) still produce a
    valid, save-able state — the missing pieces just round-trip as
    empty dicts and ``apply_project_state`` falls back to defaults
    for them on reload.
    """
    return ProjectState(
        schema_version=PROJECT_SCHEMA_VERSION,
        saved_at_iso=time.strftime("%Y-%m-%dT%H:%M:%S"),
        enabled_datasets=(
            [e.name for e in registry.enabled_entries()]
            if registry is not None else []
        ),
        navigator=navigator.to_dict() if navigator is not None else {},
        route=route.to_dict() if route is not None else {},
        visual_encoding=asdict(encoding) if encoding is not None else {},
        config=config.to_dict() if config is not None else None,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Apply (ProjectState -> live objects)
# ---------------------------------------------------------------------------


@dataclass
class ApplyReport:
    """Describes what ``apply_project_state`` did. The dialog logs
    this so the user knows whether the route restored, whether any
    datasets were missing, and so on."""

    navigator_restored: bool = False
    route_restored: bool = False
    encoding_restored: bool = False
    datasets_enabled: List[str] = field(default_factory=list)
    datasets_disabled: List[str] = field(default_factory=list)
    datasets_missing: List[str] = field(default_factory=list)

    def short_summary(self) -> str:
        parts: List[str] = []
        for label, ok in (
            ("navigator", self.navigator_restored),
            ("route", self.route_restored),
            ("encoding", self.encoding_restored),
        ):
            parts.append(f"{label} {'✓' if ok else '—'}")
        if self.datasets_enabled:
            parts.append(f"{len(self.datasets_enabled)} dataset(s) enabled")
        if self.datasets_missing:
            parts.append(f"{len(self.datasets_missing)} dataset(s) missing")
        return ", ".join(parts)


def apply_project_state(
    state: ProjectState,
    *,
    registry: Optional[DatasetRegistry] = None,
) -> Dict[str, Any]:
    """Re-hydrate the live objects from ``state``.

    Returns a dict carrying:
      * ``navigator`` — ``NavigationParams`` (clamped),
      * ``route``     — ``Route``,
      * ``encoding``  — ``VisualEncodingParams``,
      * ``config``    — ``UnavConfig`` if one was saved,
      * ``report``    — ``ApplyReport``.

    The returned objects are fresh: the caller decides whether to
    replace the live ones (the dialog does), to merge them, or just
    inspect them (tests).

    The ``registry``, when provided, is mutated in place: enabled
    flags are aligned with ``state.enabled_datasets`` (extra entries
    in the registry are *disabled*; entries listed in the state but
    absent from the registry are recorded in
    ``ApplyReport.datasets_missing``).
    """
    report = ApplyReport()

    # Navigator.
    if state.navigator:
        navigator = NavigationParams.from_dict(state.navigator).clamped()
        report.navigator_restored = True
    else:
        navigator = NavigationParams()

    # Route.
    if state.route:
        try:
            route = Route.from_dict(state.route)
            report.route_restored = True
        except Exception:  # noqa: BLE001 — boundary
            _log.exception("Failed to restore route; using empty.")
            route = Route()
    else:
        route = Route()

    # Visual encoding.
    if state.visual_encoding:
        try:
            encoding = VisualEncodingParams(**{
                k: v
                for k, v in state.visual_encoding.items()
                if k in {f.name for f in fields(VisualEncodingParams)}
            })
            report.encoding_restored = True
        except (TypeError, ValueError) as exc:
            _log.warning("Saved visual encoding rejected: %s", exc)
            encoding = VisualEncodingParams()
    else:
        encoding = VisualEncodingParams()

    # Optional saved config.
    config_obj: Optional[UnavConfig] = None
    if state.config is not None:
        config_obj = UnavConfig.from_dict(state.config)

    # Registry alignment.
    if registry is not None:
        wanted = set(state.enabled_datasets)
        present = {e.name for e in registry.entries}
        for entry in registry.entries:
            should_be_enabled = entry.name in wanted
            if entry.enabled != should_be_enabled:
                entry.enabled = should_be_enabled
                if should_be_enabled:
                    report.datasets_enabled.append(entry.name)
                else:
                    report.datasets_disabled.append(entry.name)
        for name in wanted:
            if name not in present:
                report.datasets_missing.append(name)

    return {
        "navigator": navigator,
        "route": route,
        "encoding": encoding,
        "config": config_obj,
        "report": report,
    }


# ---------------------------------------------------------------------------
# Disk paths
# ---------------------------------------------------------------------------


def project_state_dir() -> str:
    """Per-user directory holding sidecar project-state files."""
    return os.path.expanduser("~/.unav_pro/projects")


def sidecar_path_for(scene_path: Optional[str]) -> str:
    """Return the JSON sidecar path that pairs with ``scene_path``.

    Untitled scenes (``scene_path`` is None or an empty string) get
    a stable ``_untitled.json`` so the artist still has somewhere to
    save and reload until the scene is renamed.
    """
    base = project_state_dir()
    if not scene_path:
        return os.path.join(base, "_untitled.json")
    stem = os.path.splitext(os.path.basename(scene_path))[0] or "_untitled"
    return os.path.join(base, f"{stem}.json")


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def save_project_state(
    state: ProjectState, path: str,
) -> Optional[str]:
    """Persist ``state`` to ``path``. Returns the path on success or
    ``None`` on failure. Failures are logged, never raised."""
    parent = os.path.dirname(os.path.abspath(path))
    try:
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(state.to_json())
    except OSError as exc:
        _log.warning("Could not write project state %s: %s", path, exc)
        return None
    return path


def load_project_state(path: str) -> ProjectState:
    """Load ``path``. Missing or corrupt files yield a default
    ``ProjectState`` rather than raising."""
    if not os.path.isfile(path):
        return ProjectState()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return ProjectState.from_dict(json.load(fh))
    except (OSError, ValueError, TypeError) as exc:
        _log.warning(
            "Could not read project state %s: %s; using defaults.", path, exc,
        )
        return ProjectState()
