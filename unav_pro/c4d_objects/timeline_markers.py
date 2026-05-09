"""v2.2 Cinema 4D timeline-marker helpers.

Two halves:

* ``MarkerRecord`` + ``build_marker_records`` — pure-Python
  data layer the dialog (and tests) consume to know "this
  frame should carry a UNAV waypoint marker called X".
* ``apply_markers`` / ``clear_markers`` — c4d-bound applier
  that drops Cinema 4D timeline markers via
  ``c4d.documents.AddMarker`` and removes them safely on
  rebuild.

Markers are tagged with a stable name prefix
(``UNAV_MARKER_PREFIX``) so the C4D-side cleanup walk can
find + remove the previous build's markers without touching
markers the artist (or another plugin) has placed by hand.

Pure-Python data layer is tested without Cinema 4D; the c4d
applier is a thin wrapper that no-ops outside the host.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from animation.animated_state import AnimatedTimeline
from c4d_objects.timeline_keys import BakeRange
from core.logging_util import get_logger

_log = get_logger("c4d_objects.timeline_markers")


#: Stable prefix every UNAV-managed timeline marker name
#: starts with. The C4D-side cleanup walk keys off this
#: prefix; markers without it are left untouched.
UNAV_MARKER_PREFIX: str = "UNAV:"

#: Per-kind marker prefix. The ``apply_markers`` applier
#: keys off these prefixes when scrubbing previous markers
#: so the artist can clear "just the waypoint markers" or
#: "just the sync markers" if a future v2.x dialog exposes
#: per-kind clears.
KIND_WAYPOINT: str = "waypoint"
KIND_EPOCH: str = "epoch"
KIND_SYNC: str = "sync"
KIND_SCIENCE: str = "science"

MARKER_KINDS: tuple = (KIND_WAYPOINT, KIND_EPOCH, KIND_SYNC, KIND_SCIENCE)


#: Hard cap on UNAV-managed markers per build. Above this
#: the pure-Python builder logs a warning + truncates.
MAX_MARKERS_PER_BAKE: int = 4096


# ---------------------------------------------------------------------------
# Pure-Python data layer
# ---------------------------------------------------------------------------


@dataclass
class MarkerRecord:
    """One row of marker data the C4D applier consumes.

    ``frame`` is the integer C4D frame; ``kind`` is one of
    ``MARKER_KINDS``; ``label`` is the human-readable text
    that ends up in the marker's name (after the
    ``UNAV_MARKER_PREFIX`` and ``kind`` prefix).
    """

    frame: int
    kind: str
    label: str = ""

    def display_name(self) -> str:
        """Stable on-marker display name. The applier uses
        this; the cleanup walk matches against the prefix."""
        body = self.label or self.kind
        return f"{UNAV_MARKER_PREFIX}{self.kind}:{body}"


@dataclass
class MarkerBundle:
    """Aggregate of every marker the v2.2 evaluator wants
    materialised for a baked timeline."""

    records: List[MarkerRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.records

    def by_kind(self, kind: str) -> List[MarkerRecord]:
        return [r for r in self.records if r.kind == kind]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_marker_bundle(
    timeline: AnimatedTimeline,
    *,
    waypoint_labels: Optional[Sequence[str]] = None,
    sync_label: str = "sync",
    science_layer_frames: Optional[Sequence[int]] = None,
) -> MarkerBundle:
    """Build a ``MarkerBundle`` from a v2.2 ``AnimatedTimeline``.

    The bundle's ``records`` list contains:

    * one ``waypoint`` marker per frame in
      ``timeline.waypoint_arrival_frames``,
    * one ``epoch`` marker per frame in
      ``timeline.epoch_change_frames``,
    * one ``sync`` marker per frame in
      ``timeline.sync_marker_frames``,
    * (optionally) one ``science`` marker per frame in
      ``science_layer_frames``.

    ``waypoint_labels`` is an optional iterable of label
    strings; the builder pairs them with
    ``waypoint_arrival_frames`` in order. Extra arrivals
    fall back to ``waypoint #N`` labels.
    """
    bundle = MarkerBundle()

    labels = list(waypoint_labels or ())
    for i, frame in enumerate(timeline.waypoint_arrival_frames):
        label = labels[i] if i < len(labels) else f"waypoint #{i}"
        bundle.records.append(MarkerRecord(
            frame=int(frame), kind=KIND_WAYPOINT, label=label,
        ))

    for i, frame in enumerate(timeline.epoch_change_frames):
        bundle.records.append(MarkerRecord(
            frame=int(frame), kind=KIND_EPOCH,
            label=f"epoch change #{i}",
        ))

    for i, frame in enumerate(timeline.sync_marker_frames):
        bundle.records.append(MarkerRecord(
            frame=int(frame), kind=KIND_SYNC,
            label=f"{sync_label} #{i}",
        ))

    for i, frame in enumerate(science_layer_frames or ()):
        bundle.records.append(MarkerRecord(
            frame=int(frame), kind=KIND_SCIENCE,
            label=f"science refresh #{i}",
        ))

    # Cap.
    if len(bundle.records) > MAX_MARKERS_PER_BAKE:
        bundle.warnings.append(
            f"timeline markers: capped at "
            f"{MAX_MARKERS_PER_BAKE} (input had {len(bundle.records)})."
        )
        bundle.records = bundle.records[:MAX_MARKERS_PER_BAKE]

    return bundle


# ---------------------------------------------------------------------------
# C4D applier
# ---------------------------------------------------------------------------


def apply_markers(
    bundle: MarkerBundle,
    *,
    doc=None,
    fps: Optional[int] = None,
) -> int:
    """Drop every marker in ``bundle`` onto Cinema 4D's
    timeline. Existing UNAV-managed markers (those whose
    name starts with ``UNAV_MARKER_PREFIX``) are removed
    first so a re-bake replaces in place; markers placed by
    other tools or by the artist are left untouched.

    Returns the number of markers actually inserted (or 0
    when Cinema 4D isn't available)."""
    if not _C4D_AVAILABLE:
        return 0
    if doc is None:
        try:
            from c4d import documents  # type: ignore
            doc = documents.GetActiveDocument()
        except Exception:  # noqa: BLE001
            return 0
    if doc is None:
        return 0
    # Always scrub previous UNAV markers — even when the new
    # bundle is empty we want a clean re-build.
    _clear_unav_markers(doc)
    if bundle.is_empty():
        try:
            c4d.EventAdd()
        except Exception:  # noqa: BLE001
            pass
        return 0

    f = int(fps) if fps else int(doc.GetFps() or 30)
    written = 0
    for rec in bundle.records:
        try:
            btime = c4d.BaseTime(int(rec.frame), f)
            marker = c4d.documents.AddMarker(doc, None, btime, rec.display_name())
            if marker is not None:
                written += 1
        except Exception as exc:  # noqa: BLE001 — c4d boundary
            _log.warning(
                "timeline markers: failed to add marker at frame %s: %s",
                rec.frame, exc,
            )
    try:
        c4d.EventAdd()
    except Exception:  # noqa: BLE001
        pass
    return written


def clear_markers(*, doc=None) -> int:
    """Remove every UNAV-managed marker from the active
    document. Returns the number actually removed (or 0
    when Cinema 4D isn't available)."""
    if not _C4D_AVAILABLE:
        return 0
    if doc is None:
        try:
            from c4d import documents  # type: ignore
            doc = documents.GetActiveDocument()
        except Exception:  # noqa: BLE001
            return 0
    if doc is None:
        return 0
    n = _clear_unav_markers(doc)
    try:
        c4d.EventAdd()
    except Exception:  # noqa: BLE001
        pass
    return n


def _clear_unav_markers(doc) -> int:
    """Walk every marker in ``doc`` and remove the ones whose
    name starts with ``UNAV_MARKER_PREFIX``. Returns the
    removed count."""
    if not _C4D_AVAILABLE or doc is None:
        return 0
    removed = 0
    try:
        marker = c4d.documents.GetFirstMarker(doc)
    except Exception:  # noqa: BLE001
        return 0
    to_remove = []
    while marker is not None:
        try:
            name = marker.GetName() or ""
        except Exception:  # noqa: BLE001
            name = ""
        if name.startswith(UNAV_MARKER_PREFIX):
            to_remove.append(marker)
        try:
            marker = marker.GetNext()
        except Exception:  # noqa: BLE001
            break
    for m in to_remove:
        try:
            m.Remove()
            removed += 1
        except Exception:  # noqa: BLE001
            _log.warning("timeline markers: failed to remove marker.")
    return removed


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def render_marker_summary(bundle: MarkerBundle) -> str:
    """Plain-text summary the dialog log appends after a
    marker bake."""
    if bundle.is_empty():
        return "No timeline markers to insert."
    lines = [f"=== UNAV markers ({len(bundle.records)}) ==="]
    for kind in MARKER_KINDS:
        n = sum(1 for r in bundle.records if r.kind == kind)
        if n:
            lines.append(f"  {kind:10}: {n}")
    for w in bundle.warnings:
        lines.append(f"  ! {w}")
    return "\n".join(lines)
