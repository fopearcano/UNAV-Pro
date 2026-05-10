"""v3.45 deterministic naming policy.

Pre-v3.45 each builder coined object / track / marker
names ad-hoc:

* `point_cloud_builder` named visible-sector children
  by uid;
* `path_preview` named the spline ``UNAV_Mission_Preview``;
* `timeline_keys` named tracks via the C4D constant ID;
* `timeline_markers` prefixed markers with ``UNAV:``.

v3.45 documents the **single naming policy** every
builder reads from. Two goals:

1. **Determinism.** The same input always produces the
   same name. Re-baking a mission rewrites the same
   tracks; re-syncing a sector reuses the same
   children.
2. **Discoverability.** Every UNAV-owned scene object,
   track, or marker carries the ``UNAV_`` / ``UNAV:``
   prefix so cleanup / scene walks can find them
   without metadata reads.

Pure stdlib; no Cinema 4D imports. Tested without a
host.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Prefixes
# ---------------------------------------------------------------------------


#: Top-level scene objects use ``UNAV_`` (with an
#: underscore) so the name doubles as a Cinema-4D-
#: friendly identifier.
SCENE_OBJECT_PREFIX: str = "UNAV_"

#: Timeline markers + tag-named keys use ``UNAV:`` (with
#: a colon) so they sort distinctly inside the timeline.
#: Mirrors the v2.2 marker convention.
TIMELINE_TOKEN_PREFIX: str = "UNAV:"

#: Marker kinds emitted into the timeline. The v2.2
#: ``timeline_markers`` module recognises these tokens.
MARKER_KIND_WAYPOINT: str = "waypoint"
MARKER_KIND_EPOCH: str = "epoch"
MARKER_KIND_SYNC: str = "sync"
MARKER_KIND_SCIENCE: str = "science"
MARKER_KIND_PRESENTATION: str = "presentation"

MARKER_KINDS: tuple = (
    MARKER_KIND_WAYPOINT, MARKER_KIND_EPOCH,
    MARKER_KIND_SYNC, MARKER_KIND_SCIENCE,
    MARKER_KIND_PRESENTATION,
)


#: Bake-track suffixes the v1.8 timeline writer attaches
#: to the camera + navigator nulls. Tests assert these
#: names are stable across runs.
TRACK_SUFFIX_CAMERA_PSR: str = "PSR"
TRACK_SUFFIX_CAMERA_FOV: str = "FOV"
TRACK_SUFFIX_NAV_CONE: str = "Cone"
TRACK_SUFFIX_NAV_FAR: str = "Far"
TRACK_SUFFIX_NAV_NEAR: str = "Near"


# ---------------------------------------------------------------------------
# Sanitisation
# ---------------------------------------------------------------------------


_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._\-:+]+")


def safe_token(value: str, *, max_len: int = 80) -> str:
    """Map a free-form string to a name-safe token.

    Non-alphanumeric runs collapse to ``_``; leading /
    trailing dots and underscores are stripped; an
    empty result becomes ``_``. Length is capped at
    ``max_len`` so a very long uid doesn't blow up
    Cinema 4D's name-display widget.
    """
    s = _UNSAFE_RE.sub("_", str(value or "")).strip("._")
    if not s:
        s = "_"
    if len(s) > max_len:
        s = s[:max_len].rstrip("._") or "_"
    return s


# ---------------------------------------------------------------------------
# Scene object names
# ---------------------------------------------------------------------------


def visible_sector_child_name(
    uid: str, *, label: Optional[str] = None,
) -> str:
    """Name the v0.1 visible-sector point cloud uses
    for one materialised object.

    Format: ``UNAV_Star_<safe-uid>`` for star uids;
    ``UNAV_Object_<safe-uid>`` for non-star uids.
    A non-empty ``label`` becomes the suffix instead so
    the artist sees recognisable names in the OM.
    """
    base = safe_token(uid)
    if label:
        return f"{SCENE_OBJECT_PREFIX}{safe_token(label)}__{base}"
    return f"{SCENE_OBJECT_PREFIX}Object_{base}"


def overlay_object_name(kind: str) -> str:
    """Name the v2.0 overlays builder uses for one
    overlay null. ``kind`` is one of the v2.0
    overlay tokens (``grid``, ``galactic_plane`` …)."""
    return f"{SCENE_OBJECT_PREFIX}Overlay_{safe_token(kind)}"


def science_layer_object_name(kind: str) -> str:
    """Name the v2.1 science-layer builder uses."""
    return f"{SCENE_OBJECT_PREFIX}Science_{safe_token(kind)}"


def mission_preview_name(mission_id: str) -> str:
    """Name the v1.4 mission preview spline. The
    mission id is included so two mission previews
    can coexist in one document without clashing."""
    return f"{SCENE_OBJECT_PREFIX}Mission_{safe_token(mission_id)}_Preview"


def waypoint_null_name(
    mission_id: str, index: int, label: Optional[str] = None,
) -> str:
    """Name the v1.4 waypoint helper null."""
    suffix = safe_token(label) if label else f"WP{int(index):03d}"
    return (
        f"{SCENE_OBJECT_PREFIX}Mission_{safe_token(mission_id)}_"
        f"WP{int(index):03d}_{suffix}"
    )


def annotation_object_name(index: int, label: str) -> str:
    """Name the v1.9 scene-annotation null."""
    return (
        f"{SCENE_OBJECT_PREFIX}Annotation_"
        f"{int(index):03d}_{safe_token(label)}"
    )


# ---------------------------------------------------------------------------
# Timeline tokens
# ---------------------------------------------------------------------------


def marker_token(kind: str, payload: str = "") -> str:
    """Compose a v2.2 timeline marker name.

    Format: ``UNAV:<kind>:<safe-payload>`` (the payload
    suffix is omitted when empty)."""
    if kind not in MARKER_KINDS:
        raise ValueError(
            f"unknown marker kind: {kind!r}; valid: {MARKER_KINDS}"
        )
    base = f"{TIMELINE_TOKEN_PREFIX}{kind}"
    if not payload:
        return base
    return f"{base}:{safe_token(payload)}"


def parse_marker_token(name: str) -> Optional[tuple]:
    """Inverse of ``marker_token``. Returns
    ``(kind, payload)`` for a UNAV-owned marker name,
    or ``None`` for foreign markers."""
    if not isinstance(name, str):
        return None
    if not name.startswith(TIMELINE_TOKEN_PREFIX):
        return None
    rest = name[len(TIMELINE_TOKEN_PREFIX):]
    if not rest:
        return None
    parts = rest.split(":", 1)
    kind = parts[0]
    if kind not in MARKER_KINDS:
        return None
    payload = parts[1] if len(parts) > 1 else ""
    return (kind, payload)


def is_unav_owned_name(name: str) -> bool:
    """True iff ``name`` matches one of UNAV's prefixes."""
    if not isinstance(name, str):
        return False
    return (
        name.startswith(SCENE_OBJECT_PREFIX)
        or name.startswith(TIMELINE_TOKEN_PREFIX)
    )


# ---------------------------------------------------------------------------
# Bake-track naming
# ---------------------------------------------------------------------------


def baked_track_name(*, target: str, suffix: str) -> str:
    """Name the v1.8 baked CTrack the timeline writer
    attaches to ``target`` (camera or navigator).

    Format: ``UNAV:Bake:<target>:<suffix>`` so the
    timeline groups them under a single
    ``UNAV:Bake:*`` namespace.
    """
    target_token = safe_token(target)
    suffix_token = safe_token(suffix)
    return f"{TIMELINE_TOKEN_PREFIX}Bake:{target_token}:{suffix_token}"


def is_baked_track_name(name: str) -> bool:
    """True iff ``name`` was emitted by ``baked_track_name``."""
    if not isinstance(name, str):
        return False
    return name.startswith(f"{TIMELINE_TOKEN_PREFIX}Bake:")


# ---------------------------------------------------------------------------
# Display label (Object Manager)
# ---------------------------------------------------------------------------


@dataclass
class DisplayLabel:
    """A name + secondary annotation pair the OM cell
    renders. Pure data; the C4D-bound builder writes
    the primary string to ``BaseObject.SetName`` and
    the annotation to a UNAV marker container the
    inspector reads."""

    name: str
    annotation: str = ""

    def render(self) -> str:
        if self.annotation:
            return f"{self.name}  ·  {self.annotation}"
        return self.name


def display_label_for_visible(
    *, uid: str, common_name: Optional[str] = None,
    catalog_source: Optional[str] = None,
) -> DisplayLabel:
    """Compose the OM cell text for a v0.1 visible-
    sector point. Used by the v3.45 builder so the
    artist sees a friendly name plus a discreet source
    tag."""
    primary = visible_sector_child_name(uid, label=common_name)
    annotation = (
        f"({catalog_source})" if catalog_source else ""
    )
    return DisplayLabel(name=primary, annotation=annotation)
