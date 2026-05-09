"""v2.3 central export manager.

Single import surface for every UNAV exporter:

* per-format writers (Mission JSON, Route JSON, Waypoint
  CSV, Route Markdown, Camera Path JSON, Timeline keyframe
  JSON, Science-layer JSON, Dataset summary JSON);
* the v2.3 export-package builder that bundles a curated
  set of assets under one directory tree with a manifest.

Everything goes through atomic writes (the v1.7
``safe_write_json`` helper); every export runs the v2.3
validators first and returns a structured ``ExportResult``.

Pure stdlib. No Cinema 4D dependency.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from core.logging_util import get_logger

from .export_package import (
    PACKAGE_MANIFEST_VERSION,
    PackageBuildReport,
    PackageManifest,
    PackagePayload,
    build_export_package,
)
from .export_validation import (
    SEVERITY_ERROR,
    ValidationIssue,
    ValidationReport,
    validate_camera_path_for_export,
    validate_dataset_registry,
    validate_mission_for_export,
    validate_writable_path,
)

_log = get_logger("export.export_manager")


#: Stable string identifiers for the supported export
#: formats. The dialog keys off these; tests assert the
#: registry exposes every one.
FORMAT_MISSION_JSON: str = "mission_json"
FORMAT_ROUTE_JSON: str = "route_json"
FORMAT_WAYPOINT_CSV: str = "waypoint_csv"
FORMAT_ROUTE_MARKDOWN: str = "route_markdown"
FORMAT_CAMERA_PATH_JSON: str = "camera_path_json"
FORMAT_TIMELINE_KEYFRAMES_JSON: str = "timeline_keyframes_json"
FORMAT_SCIENCE_LAYER_JSON: str = "science_layer_json"
FORMAT_DATASET_SUMMARY_JSON: str = "dataset_summary_json"

EXPORT_FORMATS: Tuple[str, ...] = (
    FORMAT_MISSION_JSON,
    FORMAT_ROUTE_JSON,
    FORMAT_WAYPOINT_CSV,
    FORMAT_ROUTE_MARKDOWN,
    FORMAT_CAMERA_PATH_JSON,
    FORMAT_TIMELINE_KEYFRAMES_JSON,
    FORMAT_SCIENCE_LAYER_JSON,
    FORMAT_DATASET_SUMMARY_JSON,
)


@dataclass
class ExportResult:
    """Outcome of one export call.

    ``path`` is the absolute path written (or empty on
    failure); ``validation`` carries the pre-flight findings;
    ``success`` is the dialog-friendly summary flag.
    """

    success: bool = False
    format: str = ""
    path: str = ""
    validation: ValidationReport = field(default_factory=ValidationReport)
    detail: str = ""

    def render_text(self) -> str:
        prefix = "[ok]" if self.success else "[fail]"
        line = f"{prefix} export {self.format} → {self.path or '(no path)'}"
        if self.detail:
            line += f"  {self.detail}"
        return line


# ---------------------------------------------------------------------------
# Format dispatch
# ---------------------------------------------------------------------------


@dataclass
class _FormatEntry:
    name: str
    label: str
    writer: Callable[..., Optional[str]]
    file_extension: str


def _writer_mission_json(*, mission, path, **_kw) -> Optional[str]:
    from voyage import mission_to_json_file
    return mission_to_json_file(mission, path)


def _writer_route_json(*, route, path, **_kw) -> Optional[str]:
    from core.config import safe_write_json
    return safe_write_json(path, route.to_json())


def _writer_waypoint_csv(*, mission, path, **_kw) -> Optional[str]:
    from voyage import write_csv
    return write_csv(mission, path)


def _writer_route_markdown(*, mission, path, **_kw) -> Optional[str]:
    from voyage import write_markdown
    return write_markdown(mission, path)


def _writer_camera_path_json(*, mission, path, camera_path, frame_range,
                             plugin_version="", **_kw) -> Optional[str]:
    from .camera_exchange import (
        build_camera_exchange_from_mission, write_camera_exchange,
    )
    doc = build_camera_exchange_from_mission(
        mission, camera_path,
        frame_range=frame_range,
        plugin_version=plugin_version,
        exported_at_iso=_now_iso(),
    )
    return write_camera_exchange(doc, path)


def _writer_timeline_keyframes_json(*, keyframes, path, **_kw) -> Optional[str]:
    from core.config import safe_write_json
    payload = {
        "schema_version": 1,
        "exported_at_iso": _now_iso(),
        "keyframes": [
            {
                "frame": int(k.frame),
                "position": list(k.position),
                "rotation_hpb": list(k.rotation_hpb),
                "fov_rad": k.fov_rad,
            }
            for k in (keyframes or [])
        ],
    }
    return safe_write_json(path, json.dumps(payload, sort_keys=True, indent=2))


def _writer_science_layer_json(*, science_layer_settings, path, **_kw) -> Optional[str]:
    from core.config import safe_write_json
    payload = {
        "schema_version": 1,
        "exported_at_iso": _now_iso(),
        "settings": science_layer_settings.to_dict(),
        "enabled_layers": science_layer_settings.enabled_layer_ids(),
    }
    return safe_write_json(path, json.dumps(payload, sort_keys=True, indent=2))


def _writer_dataset_summary_json(*, summary, path, **_kw) -> Optional[str]:
    from .dataset_summary import write_dataset_summary
    return write_dataset_summary(summary, path)


_FORMAT_REGISTRY: Tuple[_FormatEntry, ...] = (
    _FormatEntry(FORMAT_MISSION_JSON,
                 "Mission JSON", _writer_mission_json, ".json"),
    _FormatEntry(FORMAT_ROUTE_JSON,
                 "Route JSON", _writer_route_json, ".json"),
    _FormatEntry(FORMAT_WAYPOINT_CSV,
                 "Waypoint CSV", _writer_waypoint_csv, ".csv"),
    _FormatEntry(FORMAT_ROUTE_MARKDOWN,
                 "Route Markdown", _writer_route_markdown, ".md"),
    _FormatEntry(FORMAT_CAMERA_PATH_JSON,
                 "Camera Path JSON", _writer_camera_path_json, ".json"),
    _FormatEntry(FORMAT_TIMELINE_KEYFRAMES_JSON,
                 "Timeline Keyframes JSON",
                 _writer_timeline_keyframes_json, ".json"),
    _FormatEntry(FORMAT_SCIENCE_LAYER_JSON,
                 "Science Layer JSON", _writer_science_layer_json, ".json"),
    _FormatEntry(FORMAT_DATASET_SUMMARY_JSON,
                 "Dataset Summary JSON",
                 _writer_dataset_summary_json, ".json"),
)


def list_export_formats() -> List[Dict[str, str]]:
    """Return the registry as a list of (name, label,
    extension) triples. The dialog renders the picker from
    this list."""
    return [
        {"name": e.name, "label": e.label, "extension": e.file_extension}
        for e in _FORMAT_REGISTRY
    ]


# ---------------------------------------------------------------------------
# Single-format export
# ---------------------------------------------------------------------------


@dataclass
class ExportSettings:
    """Knobs the dialog exposes to a single-format export."""

    allow_overwrite: bool = False
    plugin_version: str = ""


def export_one(
    format_name: str,
    path: str,
    *,
    mission=None,
    route=None,
    camera_path=None,
    keyframes=None,
    science_layer_settings=None,
    summary=None,
    frame_range=None,
    settings: Optional[ExportSettings] = None,
) -> ExportResult:
    """Run one export. Pre-flight validations are baked in.
    The dialog calls this from each per-format button.
    """
    cfg = settings or ExportSettings()
    result = ExportResult(format=format_name)

    # Resolve the writer.
    entry: Optional[_FormatEntry] = None
    for e in _FORMAT_REGISTRY:
        if e.name == format_name:
            entry = e
            break
    if entry is None:
        result.detail = f"unknown format: {format_name}"
        result.validation.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="unknown_format",
            detail=result.detail,
        ))
        return result

    # Pre-flight: writable path.
    path_check = validate_writable_path(
        path, allow_overwrite=cfg.allow_overwrite,
    )
    result.validation.issues.extend(path_check.issues)
    if path_check.has_errors():
        return result

    # Per-format pre-flights.
    if format_name in (FORMAT_MISSION_JSON, FORMAT_WAYPOINT_CSV,
                       FORMAT_ROUTE_MARKDOWN, FORMAT_CAMERA_PATH_JSON):
        result.validation.issues.extend(
            validate_mission_for_export(mission).issues
        )
    if format_name == FORMAT_CAMERA_PATH_JSON:
        result.validation.issues.extend(
            validate_camera_path_for_export(camera_path).issues
        )
    if result.validation.has_errors():
        return result

    # Dispatch.
    try:
        written = entry.writer(
            mission=mission,
            route=route,
            camera_path=camera_path,
            keyframes=keyframes,
            science_layer_settings=science_layer_settings,
            summary=summary,
            frame_range=frame_range,
            plugin_version=cfg.plugin_version,
            path=path,
        )
    except Exception as exc:  # noqa: BLE001 — boundary handler
        _log.exception("export %s failed at %s", format_name, path)
        result.detail = f"writer raised: {exc!r}"
        result.validation.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="writer_exception",
            detail=str(exc),
        ))
        return result

    if written is None:
        result.detail = "writer returned None (atomic write failed)."
        result.validation.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="write_failed",
            detail=result.detail,
        ))
        return result

    result.success = True
    result.path = written
    return result


# ---------------------------------------------------------------------------
# Full-package export
# ---------------------------------------------------------------------------


@dataclass
class PackageBuildSettings:
    """Knobs the dialog passes to ``export_package``."""

    plugin_version: str = ""
    allow_existing: bool = True
    coordinate_convention: str = "C4D world units, Y-up"
    notes: str = ""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def export_package(
    package_root: str,
    *,
    missions: Optional[Iterable] = None,
    routes: Optional[Iterable] = None,
    camera_paths_by_label: Optional[Dict[str, Tuple[Any, Any, Any]]] = None,
    timeline_keyframes_by_label: Optional[Dict[str, Tuple[Any, Any]]] = None,
    science_layer_settings=None,
    dataset_summary_data=None,
    extra_docs: Optional[Dict[str, str]] = None,
    active_dataset_names: Optional[Iterable[str]] = None,
    settings: Optional[PackageBuildSettings] = None,
) -> PackageBuildReport:
    """v2.3 high-level package export.

    Build a single export-package directory under
    ``package_root`` containing one or more missions, routes,
    camera paths, timelines, dataset summaries, and arbitrary
    extra docs, plus a top-level manifest.

    Every input is optional. Empty inputs simply produce no
    files in the corresponding subdirectory; the manifest's
    ``included_assets`` map reflects only what was written.

    ``camera_paths_by_label`` is a mapping
    ``{label: (mission, camera_path, frame_range)}``; the
    builder evaluates the v2.3 camera-exchange document for
    each entry.

    ``timeline_keyframes_by_label`` is a mapping
    ``{label: (keyframes, frame_range)}``; the builder writes
    each as a v2.3 timeline-keyframe JSON.
    """
    cfg = settings or PackageBuildSettings()
    payload = PackagePayload()

    # --- Missions ---
    for mission in missions or ():
        try:
            filename = _safe_filename(
                mission.title or mission.mission_id, ext=".json",
            )
            payload.missions[filename] = mission.to_json()
        except Exception as exc:  # noqa: BLE001
            _log.warning("export_package: mission skipped: %s", exc)

    # --- Routes ---
    for i, route in enumerate(routes or ()):
        try:
            filename = _safe_filename(
                route.name or f"route_{i}", ext=".json",
            )
            payload.routes[filename] = route.to_json()
        except Exception as exc:  # noqa: BLE001
            _log.warning("export_package: route skipped: %s", exc)

    # --- Camera paths ---
    if camera_paths_by_label:
        from .camera_exchange import build_camera_exchange_from_mission
        for label, (mission, camera_path, frame_range) in camera_paths_by_label.items():
            try:
                doc = build_camera_exchange_from_mission(
                    mission, camera_path,
                    frame_range=frame_range,
                    plugin_version=cfg.plugin_version,
                    coordinate_convention=cfg.coordinate_convention,
                    exported_at_iso=_now_iso(),
                )
                filename = _safe_filename(label, ext=".json")
                payload.camera_paths[filename] = doc.to_json()
            except Exception as exc:  # noqa: BLE001
                _log.warning("export_package: camera path '%s' skipped: %s", label, exc)

    # --- Timelines ---
    if timeline_keyframes_by_label:
        for label, (keyframes, frame_range) in timeline_keyframes_by_label.items():
            try:
                payload.timelines[_safe_filename(label, ext=".json")] = json.dumps({
                    "schema_version": 1,
                    "exported_at_iso": _now_iso(),
                    "fps": int(frame_range.fps),
                    "start_frame": int(frame_range.start_frame),
                    "end_frame": int(frame_range.end_frame),
                    "keyframes": [
                        {
                            "frame": int(k.frame),
                            "position": list(k.position),
                            "rotation_hpb": list(k.rotation_hpb),
                            "fov_rad": k.fov_rad,
                        }
                        for k in (keyframes or [])
                    ],
                }, sort_keys=True, indent=2)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "export_package: timeline '%s' skipped: %s", label, exc,
                )

    # --- Datasets ---
    if dataset_summary_data is not None:
        try:
            payload.summaries["dataset_summary.json"] = (
                dataset_summary_data.to_json()
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("export_package: dataset summary skipped: %s", exc)

    if science_layer_settings is not None:
        try:
            payload.datasets["science_layers.json"] = json.dumps({
                "schema_version": 1,
                "exported_at_iso": _now_iso(),
                "settings": science_layer_settings.to_dict(),
                "enabled_layers": science_layer_settings.enabled_layer_ids(),
            }, sort_keys=True, indent=2)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "export_package: science-layer settings skipped: %s", exc,
            )

    # --- Extra docs ---
    for name, body in (extra_docs or {}).items():
        payload.docs[_safe_filename(name, ext=".md")] = str(body)

    # Build the manifest.
    manifest = PackageManifest(
        plugin_version=cfg.plugin_version,
        coordinate_convention=cfg.coordinate_convention,
        notes=cfg.notes,
        active_datasets=[str(n) for n in (active_dataset_names or []) if n],
    )
    return build_export_package(
        package_root, payload,
        manifest=manifest,
        allow_existing=cfg.allow_existing,
    )


# ---------------------------------------------------------------------------
# Filename hygiene
# ---------------------------------------------------------------------------


_INVALID_FILENAME_CHARS: str = "/\\:*?\"<>|"


def _safe_filename(name: str, *, ext: str = "") -> str:
    """Sanitise a candidate filename. Strips path separators
    + Windows-illegal characters, collapses runs of
    whitespace, and appends the requested extension when the
    cleaned name doesn't already end with it.

    Returns a non-empty string; falls back to ``"unnamed"``
    when the input is empty / whitespace-only."""
    raw = (name or "").strip() or "unnamed"
    cleaned: List[str] = []
    for ch in raw:
        if ch in _INVALID_FILENAME_CHARS:
            cleaned.append("_")
            continue
        if ch in (" ", "\t"):
            cleaned.append("_")
            continue
        cleaned.append(ch)
    out = "".join(cleaned).strip("_") or "unnamed"
    # Cap length so the filesystem doesn't refuse it.
    if len(out) > 96:
        out = out[:96]
    if ext and not out.lower().endswith(ext.lower()):
        out += ext
    return out
