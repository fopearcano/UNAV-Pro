"""Navigation parameters for the UNAV Pro navigator.

Pure data layer for the parameters that drive view-frustum / cone
filtering of the catalog. The C4D side (``c4d_objects/navigation_null``)
exposes these as user data on the ``UNAV_Navigator`` null so artists
can edit them in the Attribute Manager; this module is the single
source of truth for their defaults, validation, and serialization.

No filtering is implemented here — that lands in a later phase. This
module's only job is to make the parameter set self-describing and
roundtrippable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Tuple

from data.schema import SCALE_MODES

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MAX_DISTANCE_PARSEC = 1000.0
DEFAULT_FIELD_OF_VIEW_DEG = 60.0
DEFAULT_CONE_ANGLE_DEG = 30.0
DEFAULT_NEAR_CLIP_PARSEC = 0.1
DEFAULT_FAR_CLIP_PARSEC = 10000.0
DEFAULT_SELECTED_SOURCES: Tuple[str, ...] = ("unav_sample",)
DEFAULT_MAX_VISIBLE_OBJECTS = 100_000
DEFAULT_C4D_SCALE = "pc"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class NavigationParams:
    """User-editable parameters that govern catalog filtering and
    view-frustum behaviour for the active ``UNAV_Navigator``.

    All fields have safe defaults. ``validate()`` returns a list of
    human-readable issues and is non-fatal; the C4D layer logs issues
    and clamps invalid values rather than refusing to operate.
    """

    max_distance_parsec: float = DEFAULT_MAX_DISTANCE_PARSEC
    field_of_view_deg: float = DEFAULT_FIELD_OF_VIEW_DEG
    cone_angle_deg: float = DEFAULT_CONE_ANGLE_DEG
    near_clip_parsec: float = DEFAULT_NEAR_CLIP_PARSEC
    far_clip_parsec: float = DEFAULT_FAR_CLIP_PARSEC
    selected_catalog_sources: List[str] = field(
        default_factory=lambda: list(DEFAULT_SELECTED_SOURCES)
    )
    max_visible_objects: int = DEFAULT_MAX_VISIBLE_OBJECTS
    c4d_scale: str = DEFAULT_C4D_SCALE

    # ------------------------------------------------------------------ dict
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_distance_parsec": float(self.max_distance_parsec),
            "field_of_view_deg": float(self.field_of_view_deg),
            "cone_angle_deg": float(self.cone_angle_deg),
            "near_clip_parsec": float(self.near_clip_parsec),
            "far_clip_parsec": float(self.far_clip_parsec),
            "selected_catalog_sources": list(self.selected_catalog_sources),
            "max_visible_objects": int(self.max_visible_objects),
            "c4d_scale": str(self.c4d_scale),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NavigationParams":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (d or {}).items() if k in known}
        if "selected_catalog_sources" in clean:
            clean["selected_catalog_sources"] = _coerce_source_list(
                clean["selected_catalog_sources"]
            )
        return cls(**clean)

    # ------------------------------------------------------------------ json
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "NavigationParams":
        try:
            return cls.from_dict(json.loads(s or "{}"))
        except (TypeError, ValueError):
            return cls()

    # ------------------------------------------------------------------ misc
    def validate(self) -> List[str]:
        issues: List[str] = []

        if self.max_distance_parsec <= 0:
            issues.append("max_distance_parsec must be > 0")
        if not (0.0 < self.field_of_view_deg < 180.0):
            issues.append("field_of_view_deg must be in (0, 180)")
        if not (0.0 <= self.cone_angle_deg < 180.0):
            issues.append("cone_angle_deg must be in [0, 180)")
        if self.near_clip_parsec < 0:
            issues.append("near_clip_parsec must be >= 0")
        if self.far_clip_parsec <= self.near_clip_parsec:
            issues.append("far_clip_parsec must be > near_clip_parsec")
        if self.max_visible_objects < 0:
            issues.append("max_visible_objects must be >= 0")
        if self.c4d_scale not in SCALE_MODES:
            issues.append(
                f"c4d_scale '{self.c4d_scale}' not in {sorted(SCALE_MODES.keys())}"
            )
        if not isinstance(self.selected_catalog_sources, list):
            issues.append("selected_catalog_sources must be a list")
        else:
            for s in self.selected_catalog_sources:
                if not isinstance(s, str) or not s:
                    issues.append(
                        f"selected_catalog_sources contains invalid entry: {s!r}"
                    )
                    break

        return issues

    def clamped(self) -> "NavigationParams":
        """Return a copy with invalid numeric fields clamped to safe
        ranges. Use this at the C4D boundary so a typo in the
        Attribute Manager doesn't break filtering."""
        out = NavigationParams(**self.to_dict())
        if out.max_distance_parsec <= 0:
            out.max_distance_parsec = DEFAULT_MAX_DISTANCE_PARSEC
        if not (0.0 < out.field_of_view_deg < 180.0):
            out.field_of_view_deg = DEFAULT_FIELD_OF_VIEW_DEG
        if not (0.0 <= out.cone_angle_deg < 180.0):
            out.cone_angle_deg = DEFAULT_CONE_ANGLE_DEG
        if out.near_clip_parsec < 0:
            out.near_clip_parsec = DEFAULT_NEAR_CLIP_PARSEC
        if out.far_clip_parsec <= out.near_clip_parsec:
            out.far_clip_parsec = max(
                out.near_clip_parsec + 1.0, DEFAULT_FAR_CLIP_PARSEC
            )
        if out.max_visible_objects < 0:
            out.max_visible_objects = 0
        if out.c4d_scale not in SCALE_MODES:
            out.c4d_scale = DEFAULT_C4D_SCALE
        if not isinstance(out.selected_catalog_sources, list):
            out.selected_catalog_sources = list(DEFAULT_SELECTED_SOURCES)
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_source_list(value: Any) -> List[str]:
    """Accept comma-separated strings, JSON-encoded lists, or actual
    lists; return a clean list of non-empty strings.
    """
    if isinstance(value, list):
        return [str(s) for s in value if isinstance(s, str) and s]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                v = json.loads(s)
                if isinstance(v, list):
                    return [str(x) for x in v if isinstance(x, str) and x]
            except (TypeError, ValueError):
                pass
        return [p.strip() for p in s.split(",") if p.strip()]
    return []


def sources_to_string(sources: List[str]) -> str:
    """Render a source list as a comma-separated user-data string."""
    return ",".join(s for s in sources if s)
