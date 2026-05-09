"""v2.3 dataset summary export.

Pure-Python helpers that turn the active dataset registry
+ navigator state + science-layer settings into a JSON
summary the artist (or a colleague consuming the export
package) can read without UNAV.

Output is plain Python dicts → JSON; no Cinema 4D
dependency. Tests drive this module directly.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Format version
# ---------------------------------------------------------------------------

#: Stable schema version for the dataset-summary JSON.
DATASET_SUMMARY_VERSION: int = 1


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class DatasetSummary:
    """Aggregate dataset / navigator / science-layer summary.

    The dialog's "Export Dataset Summary" button writes this
    verbatim. Tests build it directly from synthetic registry
    + navigator + science-layer inputs.
    """

    schema_version: int = DATASET_SUMMARY_VERSION
    plugin_version: str = ""
    exported_at_iso: str = ""

    dataset_count: int = 0
    enabled_dataset_count: int = 0
    datasets: List[Dict[str, Any]] = field(default_factory=list)

    object_count_estimate: int = 0
    sources: Dict[str, int] = field(default_factory=dict)
    object_types: Dict[str, int] = field(default_factory=dict)

    coordinate_scale: Optional[str] = None
    max_visible_objects: Optional[int] = None
    cone_half_angle_deg: Optional[float] = None
    far_clip_parsec: Optional[float] = None
    near_clip_parsec: Optional[float] = None

    active_science_layers: List[str] = field(default_factory=list)
    mission_references: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "plugin_version": self.plugin_version,
            "exported_at_iso": self.exported_at_iso,

            "dataset_count": int(self.dataset_count),
            "enabled_dataset_count": int(self.enabled_dataset_count),
            "datasets": list(self.datasets),

            "object_count_estimate": int(self.object_count_estimate),
            "sources": dict(self.sources),
            "object_types": dict(self.object_types),

            "coordinate_scale": self.coordinate_scale,
            "max_visible_objects": self.max_visible_objects,
            "cone_half_angle_deg": self.cone_half_angle_deg,
            "far_clip_parsec": self.far_clip_parsec,
            "near_clip_parsec": self.near_clip_parsec,

            "active_science_layers": list(self.active_science_layers),
            "mission_references": list(self.mission_references),
            "notes": list(self.notes),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_dataset_summary(
    *,
    registry=None,
    navigator_params=None,
    science_layer_settings=None,
    objects: Optional[Iterable[Any]] = None,
    plugin_version: str = "",
    exported_at_iso: str = "",
    mission_references: Optional[Iterable[str]] = None,
) -> DatasetSummary:
    """Build a ``DatasetSummary`` from the active state.

    All inputs are optional — a missing piece produces zero /
    empty values + a note. The dialog hands in whatever it
    has; tests can hand in just one piece at a time.
    """
    summary = DatasetSummary(
        plugin_version=plugin_version,
        exported_at_iso=exported_at_iso,
    )

    # --- Dataset registry ---
    if registry is not None:
        entries = list(getattr(registry, "entries", None) or ())
        summary.dataset_count = len(entries)
        for e in entries:
            if getattr(e, "enabled", False):
                summary.enabled_dataset_count += 1
            entry_dict: Dict[str, Any] = {
                "name": getattr(e, "name", ""),
                "enabled": bool(getattr(e, "enabled", False)),
                "path": getattr(e, "path", "") or "",
                "db_path": getattr(e, "db_path", None),
                "namespace": getattr(e, "namespace", True),
            }
            stats = getattr(e, "stats", None)
            if stats is not None:
                entry_dict["object_count"] = getattr(stats, "object_count", None)
                entry_dict["bounding_radius_pc"] = getattr(
                    stats, "bounding_radius_pc", None,
                )
            summary.datasets.append(entry_dict)
    else:
        summary.notes.append(
            "registry not supplied; dataset list is empty."
        )

    # --- Navigator params ---
    if navigator_params is not None:
        summary.coordinate_scale = getattr(
            navigator_params, "c4d_scale", None,
        )
        summary.max_visible_objects = getattr(
            navigator_params, "max_visible_objects", None,
        )
        summary.cone_half_angle_deg = getattr(
            navigator_params, "cone_angle_deg", None,
        )
        summary.far_clip_parsec = getattr(
            navigator_params, "far_clip_parsec", None,
        )
        summary.near_clip_parsec = getattr(
            navigator_params, "near_clip_parsec", None,
        )

    # --- Science-layer enabled list ---
    if science_layer_settings is not None:
        try:
            summary.active_science_layers = list(
                science_layer_settings.enabled_layer_ids()
            )
        except Exception:  # noqa: BLE001 — boundary
            summary.notes.append(
                "science-layer settings shape unrecognised; "
                "active layer list is empty."
            )

    # --- Object-level histograms (optional) ---
    if objects is not None:
        rows = list(objects)
        summary.object_count_estimate = len(rows)
        summary.sources = dict(Counter(
            (getattr(o, "catalog_source", "") or "<unspecified>")
            for o in rows
        ))
        summary.object_types = dict(Counter(
            (getattr(o, "object_type", "") or "<unspecified>")
            for o in rows
        ))

    if mission_references:
        summary.mission_references = [str(m) for m in mission_references if m]

    return summary


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def write_dataset_summary(
    summary: DatasetSummary, path: str,
) -> Optional[str]:
    """Atomic JSON write."""
    from core.config import safe_write_json
    return safe_write_json(path, summary.to_json())


def render_summary_text(summary: DatasetSummary) -> str:
    """Multi-line plain-text render the dialog drops into the
    log after an export."""
    lines: List[str] = ["=== Dataset summary ==="]
    lines.append(
        f"  datasets       : {summary.dataset_count} "
        f"({summary.enabled_dataset_count} enabled)"
    )
    if summary.object_count_estimate:
        lines.append(
            f"  objects (est.) : {summary.object_count_estimate}"
        )
    if summary.sources:
        lines.append("  sources        : " + ", ".join(
            f"{k}={v}" for k, v in sorted(summary.sources.items())
        ))
    if summary.coordinate_scale:
        lines.append(f"  scale          : {summary.coordinate_scale}")
    if summary.active_science_layers:
        lines.append(
            "  science layers : " + ", ".join(summary.active_science_layers)
        )
    for n in summary.notes:
        lines.append(f"  ! {n}")
    return "\n".join(lines)
