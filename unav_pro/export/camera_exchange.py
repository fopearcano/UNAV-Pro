"""v2.3 DCC-agnostic camera-path interchange JSON.

A flat, human-readable JSON layout other DCCs can ingest
without having to grok UNAV's internal voyage data model.
Includes:

* a top-level metadata block (units, coordinate convention,
  fps, frame range, plugin version),
* one record per frame with position, rotation (HPB radians),
  optional FOV, optional epoch, waypoint index.

The format is intentionally simple. Importers in Houdini /
Maya / Blender / etc. can walk the per-frame array and apply
each record to a camera object.

Pure-Python; no Cinema 4D dependency. Tested without the
host.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from animation.animated_state import (
    AnimatedTimeline,
    evaluate_animated_state,
)
from c4d_objects.timeline_keys import BakeRange, KeyframeRecord
from voyage.camera_path import CameraPath
from voyage.mission import Mission

# ---------------------------------------------------------------------------
# Format version
# ---------------------------------------------------------------------------

#: Stable schema version for the camera-path JSON. Bumped
#: when the on-disk layout changes; downstream importers can
#: refuse newer versions they don't understand.
CAMERA_EXCHANGE_VERSION: int = 1

#: UNAV's canonical coordinate convention. The C4D scene
#: lives in Cartesian C4D world units; the export stamps the
#: convention so a Maya / Blender importer knows what to do.
DEFAULT_COORDINATE_CONVENTION: str = "C4D world units, Y-up"

#: UNAV's distance unit at the export layer is parsec
#: when the v0.x dataset registry resolves it; the camera
#: path's positions are *C4D world units* (the dialog scales
#: parsec → C4D via the v0.x scale mode). The exporter labels
#: the unit so the importer can multiply back.
DEFAULT_UNITS: Dict[str, str] = {
    "position": "C4D_world_units",
    "rotation": "radians_HPB",
    "fov": "radians_horizontal",
    "epoch": "julian_date",
    "time": "seconds",
}


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class CameraExchangeRecord:
    """One frame in the exchange JSON."""

    frame: int
    seconds: float
    position: List[float]
    rotation_hpb: List[float]
    fov_rad: Optional[float] = None
    epoch_jd: Optional[float] = None
    waypoint_index: int = 0


@dataclass
class CameraExchangeDocument:
    """The full export document."""

    schema_version: int = CAMERA_EXCHANGE_VERSION
    plugin_version: str = ""
    exported_at_iso: str = ""
    fps: int = 30
    start_frame: int = 0
    end_frame: int = 0
    frame_count: int = 0
    coordinate_convention: str = DEFAULT_COORDINATE_CONVENTION
    units: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_UNITS))
    records: List[CameraExchangeRecord] = field(default_factory=list)
    mission_title: Optional[str] = None
    mission_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "plugin_version": self.plugin_version,
            "exported_at_iso": self.exported_at_iso,
            "fps": int(self.fps),
            "start_frame": int(self.start_frame),
            "end_frame": int(self.end_frame),
            "frame_count": int(self.frame_count),
            "coordinate_convention": self.coordinate_convention,
            "units": dict(self.units),
            "mission_title": self.mission_title,
            "mission_id": self.mission_id,
            "records": [
                {
                    "frame": r.frame,
                    "seconds": r.seconds,
                    "position": list(r.position),
                    "rotation_hpb": list(r.rotation_hpb),
                    "fov_rad": r.fov_rad,
                    "epoch_jd": r.epoch_jd,
                    "waypoint_index": r.waypoint_index,
                }
                for r in self.records
            ],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_camera_exchange_from_timeline(
    timeline: AnimatedTimeline,
    *,
    frame_range: BakeRange,
    plugin_version: str = "",
    mission_title: Optional[str] = None,
    mission_id: Optional[str] = None,
    coordinate_convention: str = DEFAULT_COORDINATE_CONVENTION,
    exported_at_iso: str = "",
) -> CameraExchangeDocument:
    """Turn a v2.2 ``AnimatedTimeline`` + the ``BakeRange``
    that produced it into a ``CameraExchangeDocument``."""
    doc = CameraExchangeDocument(
        plugin_version=plugin_version,
        exported_at_iso=exported_at_iso,
        fps=int(frame_range.fps),
        start_frame=int(frame_range.start_frame),
        end_frame=int(frame_range.end_frame),
        frame_count=int(frame_range.frame_count),
        coordinate_convention=coordinate_convention,
        mission_title=mission_title,
        mission_id=mission_id,
    )
    for sample in timeline.samples:
        doc.records.append(CameraExchangeRecord(
            frame=int(sample.frame),
            seconds=float(sample.seconds),
            position=[
                float(sample.camera_position[0]),
                float(sample.camera_position[1]),
                float(sample.camera_position[2]),
            ],
            rotation_hpb=[
                float(sample.rotation_hpb[0]),
                float(sample.rotation_hpb[1]),
                float(sample.rotation_hpb[2]),
            ],
            fov_rad=sample.fov_rad,
            epoch_jd=sample.epoch_jd,
            waypoint_index=int(sample.waypoint_index),
        ))
    return doc


def build_camera_exchange_from_mission(
    mission: Mission,
    path: CameraPath,
    *,
    frame_range: Optional[BakeRange] = None,
    config=None,
    plugin_version: str = "",
    coordinate_convention: str = DEFAULT_COORDINATE_CONVENTION,
    exported_at_iso: str = "",
) -> CameraExchangeDocument:
    """Convenience: evaluate the v2.2 animated state then
    flatten into the exchange document. The dialog calls
    this for "Export Camera Path"."""
    fr = frame_range or BakeRange()
    timeline = evaluate_animated_state(
        mission, path, frame_range=fr, config=config,
    )
    return build_camera_exchange_from_timeline(
        timeline,
        frame_range=fr,
        plugin_version=plugin_version,
        mission_title=mission.title,
        mission_id=mission.mission_id,
        coordinate_convention=coordinate_convention,
        exported_at_iso=exported_at_iso,
    )


def build_camera_exchange_from_keyframes(
    keyframes: List[KeyframeRecord],
    *,
    frame_range: BakeRange,
    plugin_version: str = "",
    mission_title: Optional[str] = None,
    mission_id: Optional[str] = None,
    coordinate_convention: str = DEFAULT_COORDINATE_CONVENTION,
    exported_at_iso: str = "",
) -> CameraExchangeDocument:
    """Turn a flat ``KeyframeRecord`` list into a
    ``CameraExchangeDocument``. Useful when the caller has
    already baked keyframes via the v1.8 ``generate_keyframes``
    pipeline and just wants to publish them in the exchange
    format."""
    doc = CameraExchangeDocument(
        plugin_version=plugin_version,
        exported_at_iso=exported_at_iso,
        fps=int(frame_range.fps),
        start_frame=int(frame_range.start_frame),
        end_frame=int(frame_range.end_frame),
        frame_count=int(frame_range.frame_count),
        coordinate_convention=coordinate_convention,
        mission_title=mission_title,
        mission_id=mission_id,
    )
    for k in keyframes:
        seconds = (
            (k.frame - frame_range.start_frame) / float(frame_range.fps)
            if frame_range.fps > 0 else 0.0
        )
        doc.records.append(CameraExchangeRecord(
            frame=int(k.frame),
            seconds=float(seconds),
            position=[float(k.position[0]), float(k.position[1]), float(k.position[2])],
            rotation_hpb=[
                float(k.rotation_hpb[0]),
                float(k.rotation_hpb[1]),
                float(k.rotation_hpb[2]),
            ],
            fov_rad=k.fov_rad,
            epoch_jd=None,
            waypoint_index=0,
        ))
    return doc


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def write_camera_exchange(
    doc: CameraExchangeDocument, path: str,
) -> Optional[str]:
    """Write the exchange document to ``path`` atomically.

    Uses the v1.7 ``safe_write_json`` helper so a crash mid-
    write cannot truncate an existing file. Returns ``path``
    on success or ``None`` on failure (matches the rest of
    the codebase's error contract)."""
    from core.config import safe_write_json
    return safe_write_json(path, doc.to_json())
