"""v2.5 workflow presets.

A thin, artist-facing wrapper over the v1.9 voyage templates
(:mod:`unav_pro.voyage.templates`). Templates are the
underlying machinery — Python builders that emit a
:class:`~unav_pro.voyage.mission.Mission` seeded with
waypoints. *Workflow presets* are the same builders dressed
up with:

* a short, friendly preset name ("Solar System Flythrough"),
* a one-line task description ("Drop the inner-to-outer
  planets and bake to the timeline"),
* an optional cinematic-ready default duration so the
  artist can hit *Bake* immediately,
* a small group of recommended overlays the dialog can
  toggle on alongside the mission.

This module is **strictly a re-presentation of v1.9 data**.
It introduces no new state, no Cinema 4D dependency, no
network calls. Every preset still resolves to a v1.9
template builder, so the on-disk Mission JSON is identical
to what the existing template path produces. Removing this
module would only cost the friendly labels — no data
would be lost.

Five presets cover the bulk of artist requests:

* ``solar_system_flythrough`` → ``solar_system_tour``
* ``stellar_neighbourhood``   → ``nearest_stars_tour``
* ``hubble_flow_voyage``      → ``redshift_tour``
* ``blank_voyage``             → ``empty_voyage``
* ``selection_flythrough``     → ``selected_objects_tour``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Tuple

from voyage.mission import Mission
from voyage.templates import (
    empty_voyage,
    nearest_stars_tour,
    redshift_tour,
    selected_objects_tour,
    solar_system_tour,
)


# ---------------------------------------------------------------------------
# Preset descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkflowPreset:
    """One row in the workflow preset picker.

    Attributes:
        name:           Stable identifier (snake_case).
        label:          Human label shown in the dialog.
        task:           One-line "what this gets you" copy.
        template_name:  The underlying v1.9 template name.
        builder:        The v1.9 template builder. Returning
                        the builder by reference makes the
                        wrapper completely transparent — call
                        ``preset.builder(**kwargs)`` and the
                        result is byte-identical to the
                        template path.
        recommended_overlays: Procedural-overlay kinds the
                        dialog should auto-enable when the
                        artist picks this preset. Purely
                        advisory — the artist can still
                        toggle them off.
        default_duration_seconds: Pre-tuned per-waypoint
                        duration that produces a watchable
                        cinematic at 24 fps.
    """

    name: str
    label: str
    task: str
    template_name: str
    builder: Callable[..., Mission]
    recommended_overlays: Tuple[str, ...] = field(default_factory=tuple)
    default_duration_seconds: float = 4.0


# ---------------------------------------------------------------------------
# Preset registry
# ---------------------------------------------------------------------------


WORKFLOW_PRESETS: Tuple[WorkflowPreset, ...] = (
    WorkflowPreset(
        name="solar_system_flythrough",
        label="Solar System Flythrough",
        task=(
            "Drop the eight planets at a default epoch and "
            "bake a quick fly-through. Great first cinematic."
        ),
        template_name="solar_system_tour",
        builder=solar_system_tour,
        recommended_overlays=("ecliptic_plane", "distance_rings"),
        default_duration_seconds=4.0,
    ),
    WorkflowPreset(
        name="stellar_neighbourhood",
        label="Stellar Neighbourhood",
        task=(
            "Sun + the closest stars with cached parsec "
            "positions so the path renders without an active "
            "metadata lookup."
        ),
        template_name="nearest_stars_tour",
        builder=nearest_stars_tour,
        recommended_overlays=("galactic_plane", "distance_rings"),
        default_duration_seconds=4.0,
    ),
    WorkflowPreset(
        name="hubble_flow_voyage",
        label="Hubble Flow Voyage",
        task=(
            "Increasing-redshift extragalactic anchors. "
            "Distances are coarse Hubble-law proxies — "
            "tagged 'approximate'; not cosmology-grade."
        ),
        template_name="redshift_tour",
        builder=redshift_tour,
        recommended_overlays=("distance_rings",),
        default_duration_seconds=5.0,
    ),
    WorkflowPreset(
        name="blank_voyage",
        label="Blank Voyage",
        task=(
            "Zero waypoints — start from a clean mission "
            "with just a title and tags."
        ),
        template_name="empty_voyage",
        builder=empty_voyage,
        recommended_overlays=(),
        default_duration_seconds=4.0,
    ),
    WorkflowPreset(
        name="selection_flythrough",
        label="Selection Flythrough",
        task=(
            "Build a mission from the UIDs you already have "
            "selected (bookmarks or search results)."
        ),
        template_name="selected_objects_tour",
        builder=selected_objects_tour,
        recommended_overlays=("waypoint_labels",),
        default_duration_seconds=4.0,
    ),
)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def list_workflow_presets() -> List[WorkflowPreset]:
    """Return the full preset registry in display order.

    The dialog's "New from Preset" picker iterates this list
    verbatim. Order matters — the most common workflow
    (Solar System) is listed first.
    """
    return list(WORKFLOW_PRESETS)


def get_workflow_preset(name: str) -> Optional[WorkflowPreset]:
    """Look up a preset by its stable ``name``.

    Returns ``None`` for unknown names so the dialog can
    surface a friendly error rather than crash. ``name`` is
    lower-cased before comparison so artist-typed or
    pickle-loaded values match.
    """
    if not name:
        return None
    target = name.strip().lower()
    for entry in WORKFLOW_PRESETS:
        if entry.name == target:
            return entry
    return None


def build_mission_from_preset(
    name: str,
    /,
    **kwargs: object,
) -> Mission:
    """Build a fresh :class:`Mission` from the named preset.

    Forwards ``kwargs`` to the underlying v1.9 template
    builder unchanged. If the preset doesn't accept a kwarg
    a clear ``TypeError`` propagates from the builder, which
    is the right failure mode for a programming error.

    Raises ``KeyError`` when ``name`` doesn't resolve so
    callers (the dialog, the API) can surface "preset not
    found" cleanly without an opaque ``AttributeError`` from
    a ``None`` lookup.
    """
    preset = get_workflow_preset(name)
    if preset is None:
        raise KeyError(f"unknown workflow preset: {name!r}")
    return preset.builder(**kwargs)


def preset_names() -> List[str]:
    """Return the stable names in display order. Useful for
    serialisation, tests, and dialog enumeration."""
    return [p.name for p in WORKFLOW_PRESETS]


def preset_labels() -> List[str]:
    """Return the human labels in display order. The dialog
    uses this list to populate the picker."""
    return [p.label for p in WORKFLOW_PRESETS]


def recommended_overlays_for(name: str) -> Tuple[str, ...]:
    """Return the overlay kinds the dialog should toggle on
    when the artist picks ``name``. Empty tuple for unknown
    presets — the dialog never crashes on a missing preset."""
    preset = get_workflow_preset(name)
    if preset is None:
        return ()
    return preset.recommended_overlays
