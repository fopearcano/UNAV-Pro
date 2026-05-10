"""v3.7 query preset registry.

Eight named presets the *Advanced Query* panel
exposes so the artist doesn't have to fill every
filter by hand. Each preset is a small factory that
returns an ``AdvancedQuery`` populated with sensible
defaults; the dialog can override any field after.

* ``nearest_stars`` — closest stars to a reference
  point (typically the navigator's origin).
* ``brightest_stars`` — smallest apparent magnitude.
* ``nearby_gaia_objects`` — nearest Gaia-source
  rows.
* ``high_redshift_galaxies`` — z ≥ 1, type galaxy.
* ``high_redshift_quasars`` — z ≥ 1, type quasar.
* ``solar_system_at_epoch`` — JPL bodies at the
  active epoch (warns when no epoch).
* ``around_navigator`` — within the navigator's far
  clip.
* ``along_route`` — sentinel; the route-query module
  handles the heavy lifting.
* ``selected_dataset_summary`` — every object from
  one named source, capped.

Pure stdlib + dataclasses. No Cinema 4D imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .advanced_query import (
    AdvancedQuery,
    DEFAULT_MAX_RESULTS,
    QueryKind,
    SortOrder,
)


Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Preset descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryPresetDescriptor:
    """One row in the dialog's preset picker."""

    name: str
    label: str
    description: str
    builder: Callable[..., AdvancedQuery]
    requires_epoch: bool = False
    requires_route: bool = False


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def nearest_stars(
    *,
    reference_point_pc: Vec3 = (0.0, 0.0, 0.0),
    max_results: int = 25,
) -> AdvancedQuery:
    """Closest stars to ``reference_point_pc``."""
    return AdvancedQuery(
        kind=QueryKind.NEAREST,
        max_results=max_results,
        reference_point_pc=reference_point_pc,
        object_types=("star",),
    )


def brightest_stars(*, max_results: int = 25) -> AdvancedQuery:
    """Smallest apparent magnitude (brightest)."""
    return AdvancedQuery(
        kind=QueryKind.BRIGHTEST,
        max_results=max_results,
        object_types=("star",),
    )


def nearby_gaia_objects(
    *,
    reference_point_pc: Vec3 = (0.0, 0.0, 0.0),
    max_results: int = 50,
    distance_max_pc: Optional[float] = None,
) -> AdvancedQuery:
    """Closest Gaia-source rows."""
    return AdvancedQuery(
        kind=QueryKind.NEAREST,
        max_results=max_results,
        reference_point_pc=reference_point_pc,
        sources=("Gaia DR3", "Gaia DR3 (demo)"),
        distance_max_pc=distance_max_pc,
    )


def high_redshift_galaxies(
    *,
    redshift_min: float = 1.0,
    max_results: int = 50,
) -> AdvancedQuery:
    """Galaxies with z ≥ ``redshift_min``."""
    return AdvancedQuery(
        kind=QueryKind.HIGHEST_REDSHIFT,
        max_results=max_results,
        object_types=("galaxy",),
        redshift_min=redshift_min,
    )


def high_redshift_quasars(
    *,
    redshift_min: float = 1.0,
    max_results: int = 50,
) -> AdvancedQuery:
    """Quasars with z ≥ ``redshift_min``."""
    return AdvancedQuery(
        kind=QueryKind.HIGHEST_REDSHIFT,
        max_results=max_results,
        object_types=("quasar",),
        redshift_min=redshift_min,
    )


def solar_system_at_epoch(
    *,
    epoch_jd: Optional[float] = None,
    max_results: int = 25,
) -> AdvancedQuery:
    """JPL solar-system bodies at ``epoch_jd``.

    When ``epoch_jd`` is None the result still
    surfaces the bodies, but the engine warns that
    only stored coordinates are used."""
    return AdvancedQuery(
        kind=QueryKind.BY_TYPE,
        max_results=max_results,
        object_types=("planet", "moon", "asteroid", "comet"),
        sources=("JPL Horizons", "JPL Horizons (demo)"),
        epoch_jd=epoch_jd,
        interpolate_ephemeris=epoch_jd is not None,
    )


def around_navigator(
    *,
    reference_point_pc: Vec3 = (0.0, 0.0, 0.0),
    far_clip_pc: float = 500.0,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> AdvancedQuery:
    """Objects inside the navigator's far clip."""
    return AdvancedQuery(
        kind=QueryKind.NEAREST,
        max_results=max_results,
        reference_point_pc=reference_point_pc,
        distance_max_pc=far_clip_pc,
    )


def along_route(
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> AdvancedQuery:
    """Sentinel for route-aware discovery. The actual
    work is done by :mod:`route_query`; this preset
    just carries the ``NEAR_ROUTE`` kind so the panel
    can route the call appropriately."""
    return AdvancedQuery(
        kind=QueryKind.NEAR_ROUTE,
        max_results=max_results,
    )


def selected_dataset_summary(
    *,
    source: str,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> AdvancedQuery:
    """Every object from one named ``source``,
    capped."""
    if not source:
        raise ValueError("source is required")
    return AdvancedQuery(
        kind=QueryKind.BY_SOURCE,
        max_results=max_results,
        sources=(source,),
        sort_order=SortOrder.UID_ASC,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


PRESET_REGISTRY: Tuple[QueryPresetDescriptor, ...] = (
    QueryPresetDescriptor(
        name="nearest_stars",
        label="Nearest Stars",
        description="Closest stars to a reference point.",
        builder=nearest_stars,
    ),
    QueryPresetDescriptor(
        name="brightest_stars",
        label="Brightest Stars",
        description="Stars sorted by apparent magnitude (brightest first).",
        builder=brightest_stars,
    ),
    QueryPresetDescriptor(
        name="nearby_gaia_objects",
        label="Nearby Gaia Objects",
        description="Closest Gaia-source rows to a reference point.",
        builder=nearby_gaia_objects,
    ),
    QueryPresetDescriptor(
        name="high_redshift_galaxies",
        label="High-redshift Galaxies",
        description="Galaxies with z ≥ 1.0; tagged 'approximate' due to v0.5 redshift→distance proxy.",
        builder=high_redshift_galaxies,
    ),
    QueryPresetDescriptor(
        name="high_redshift_quasars",
        label="High-redshift Quasars",
        description="Quasars with z ≥ 1.0; same caveats as the galaxy preset.",
        builder=high_redshift_quasars,
    ),
    QueryPresetDescriptor(
        name="solar_system_at_epoch",
        label="Solar System at Epoch",
        description="JPL solar-system bodies at the active time-navigator epoch.",
        builder=solar_system_at_epoch,
        requires_epoch=True,
    ),
    QueryPresetDescriptor(
        name="around_navigator",
        label="Around Navigator",
        description="Objects inside the navigator's far clip.",
        builder=around_navigator,
    ),
    QueryPresetDescriptor(
        name="along_route",
        label="Along Route",
        description="Objects close to the active route's polyline (route-aware).",
        builder=along_route,
        requires_route=True,
    ),
    QueryPresetDescriptor(
        name="selected_dataset_summary",
        label="Selected Dataset Summary",
        description="Every object from one catalog source, capped.",
        builder=selected_dataset_summary,
    ),
)


def get_preset(name: str) -> Optional[QueryPresetDescriptor]:
    """Look up a preset by its stable ``name``. Returns
    ``None`` for unknown values so the dialog can
    surface the failure cleanly."""
    if not name:
        return None
    target = name.strip().lower()
    for entry in PRESET_REGISTRY:
        if entry.name == target:
            return entry
    return None


def list_presets() -> List[QueryPresetDescriptor]:
    """Return the registry in display order."""
    return list(PRESET_REGISTRY)


def preset_names() -> List[str]:
    return [p.name for p in PRESET_REGISTRY]
