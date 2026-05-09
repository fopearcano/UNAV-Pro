"""v2.1 science-layer orchestrator.

Wraps the per-layer builders in ``overlay_layers`` behind a
single ``ScienceLayerSettings`` dataclass + a single
``build_science_bundle`` entry point.

The dialog calls one function:

    settings = ScienceLayerSettings(...)
    bundle = build_science_bundle(settings, objects=catalog_rows)
    apply_science_bundle(bundle)   # c4d-bound applier

Pure stdlib. No Cinema 4D, no DB, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Dict, Iterable, List, Optional

from procedural.overlays import OverlayBundle, OverlayLabel, OverlayPolyline

from .overlay_layers import (
    CatalogSourceRegionSettings,
    ConstellationBoundarySettings,
    DistanceShellSettings,
    LAYER_CATALOG_SOURCE_REGIONS,
    LAYER_CONSTELLATION_BOUNDARIES,
    LAYER_DISTANCE_SHELLS,
    LAYER_MAGNITUDE_SHELLS,
    LAYER_MOTION_VECTORS,
    LAYER_OBJECT_DENSITY_VOLUME,
    LAYER_REDSHIFT_SHELLS,
    LAYER_SOLAR_SYSTEM_ORBITS,
    LayerBuildResult,
    MagnitudeShellSettings,
    MotionVectorSettings,
    ObjectDensityVolumeSettings,
    RedshiftShellSettings,
    SCIENCE_LAYER_IDS,
    SolarSystemOrbitSettings,
    build_catalog_source_regions,
    build_constellation_boundaries,
    build_distance_shells,
    build_magnitude_shells,
    build_motion_vectors,
    build_object_density_volume,
    build_redshift_shells,
    build_solar_system_orbits,
)


# ---------------------------------------------------------------------------
# Per-layer support map (which catalog sources each layer
# benefits from). Populated for diagnostics; the layer
# builders are dataset-tolerant (they emit warnings, not
# exceptions, when the dataset doesn't carry the right
# fields).
# ---------------------------------------------------------------------------


LAYER_SUPPORTED_SOURCES: Dict[str, tuple] = {
    LAYER_DISTANCE_SHELLS:        ("Gaia DR3", "SDSS", "DESI", "JPL Horizons"),
    LAYER_REDSHIFT_SHELLS:        ("SDSS", "DESI"),
    LAYER_MAGNITUDE_SHELLS:       ("Gaia DR3", "SDSS", "DESI"),
    LAYER_MOTION_VECTORS:         ("Gaia DR3",),
    LAYER_CATALOG_SOURCE_REGIONS: ("Gaia DR3", "SDSS", "DESI", "JPL Horizons"),
    LAYER_SOLAR_SYSTEM_ORBITS:    ("JPL Horizons",),
    LAYER_CONSTELLATION_BOUNDARIES: (),  # data-driven once IAU set lands
    LAYER_OBJECT_DENSITY_VOLUME:  ("Gaia DR3", "SDSS", "DESI", "JPL Horizons"),
}


@dataclass
class ScienceLayerSettings:
    """Bundle of per-layer settings.

    Persisted via the v0.x project_state sidecar. The dialog's
    "Save UNAV State" / "Load UNAV State" buttons round-trip
    the entire ``ScienceLayerSettings`` instance under the
    ``science_layers`` key on ``ProjectState``.
    """

    distance_shells: DistanceShellSettings = field(default_factory=DistanceShellSettings)
    redshift_shells: RedshiftShellSettings = field(default_factory=RedshiftShellSettings)
    magnitude_shells: MagnitudeShellSettings = field(default_factory=MagnitudeShellSettings)
    motion_vectors: MotionVectorSettings = field(default_factory=MotionVectorSettings)
    catalog_source_regions: CatalogSourceRegionSettings = field(default_factory=CatalogSourceRegionSettings)
    solar_system_orbits: SolarSystemOrbitSettings = field(default_factory=SolarSystemOrbitSettings)
    constellation_boundaries: ConstellationBoundarySettings = field(default_factory=ConstellationBoundarySettings)
    object_density_volume: ObjectDensityVolumeSettings = field(default_factory=ObjectDensityVolumeSettings)

    def any_enabled(self) -> bool:
        return any(getattr(self, f.name).enabled for f in fields(self))

    def enabled_layer_ids(self) -> List[str]:
        out: List[str] = []
        for sub in fields(self):
            sub_settings = getattr(self, sub.name)
            if not sub_settings.enabled:
                continue
            # Each sub-settings name matches its layer id.
            out.append(sub.name)
        return out

    # ------------------------------------------------------------ (de)ser
    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for f in fields(self):
            sub = getattr(self, f.name)
            entry: Dict[str, Any] = {}
            for sf in fields(sub):
                value = getattr(sub, sf.name)
                entry[sf.name] = list(value) if isinstance(value, list) else value
            out[f.name] = entry
        return out

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "ScienceLayerSettings":
        d = d or {}
        # Build each sub-settings independently so a corrupt
        # entry only resets that one layer's settings.
        bag: Dict[str, Any] = {}
        for f in fields(cls):
            sub_cls = f.default_factory().__class__  # type: ignore[union-attr]
            try:
                bag[f.name] = sub_cls(**(d.get(f.name) or {}))
            except (TypeError, ValueError):
                bag[f.name] = sub_cls()
        try:
            return cls(**bag)
        except (TypeError, ValueError):
            return cls()


@dataclass
class ScienceBundle:
    """Aggregate output of every enabled layer.

    The C4D applier walks ``per_layer`` (preserving layer
    grouping in the scene tree) and reads ``warnings`` for
    the dialog log.
    """

    per_layer: List[LayerBuildResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def empty(self) -> bool:
        return not any(
            r.polylines or r.labels for r in self.per_layer
        )

    def total_polylines(self) -> int:
        return sum(len(r.polylines) for r in self.per_layer)

    def total_labels(self) -> int:
        return sum(len(r.labels) for r in self.per_layer)

    def by_layer(self, layer_id: str) -> Optional[LayerBuildResult]:
        for r in self.per_layer:
            if r.layer_id == layer_id:
                return r
        return None


def build_science_bundle(
    settings: ScienceLayerSettings,
    *,
    objects: Optional[Iterable[Any]] = None,
) -> ScienceBundle:
    """Build a ``ScienceBundle`` from settings + an optional
    catalog row sequence. Layers that need rows (motion
    vectors, source regions, solar-system orbits) emit a
    warning when the rows are missing or empty; the bundle
    still builds, just without those layers.

    Same input → byte-identical output.
    """
    bundle = ScienceBundle()
    rows = list(objects or ())

    # Layers that don't consume the dataset.
    bundle.per_layer.append(build_distance_shells(settings.distance_shells))
    bundle.per_layer.append(build_redshift_shells(settings.redshift_shells))
    bundle.per_layer.append(build_magnitude_shells(settings.magnitude_shells))

    # Layers that benefit from the dataset.
    bundle.per_layer.append(build_motion_vectors(
        settings.motion_vectors, objects=rows,
    ))
    bundle.per_layer.append(build_catalog_source_regions(
        settings.catalog_source_regions, objects=rows,
    ))
    bundle.per_layer.append(build_solar_system_orbits(
        settings.solar_system_orbits, objects=rows,
    ))

    # Placeholders.
    bundle.per_layer.append(build_constellation_boundaries(
        settings.constellation_boundaries,
    ))
    bundle.per_layer.append(build_object_density_volume(
        settings.object_density_volume,
    ))

    # Hoist warnings.
    for r in bundle.per_layer:
        bundle.warnings.extend(r.warnings)
    return bundle


def to_overlay_bundle(bundle: ScienceBundle) -> OverlayBundle:
    """Flatten a ``ScienceBundle`` into a v2.0 ``OverlayBundle``
    for code paths that already consume v2.0 bundles. Loses
    per-layer grouping; use only when the caller wants the
    raw polyline / label set."""
    flat = OverlayBundle()
    for r in bundle.per_layer:
        flat.polylines.extend(r.polylines)
        flat.labels.extend(r.labels)
    return flat


def render_warnings(bundle: ScienceBundle) -> str:
    """Multi-line plain-text rendering of the bundle's
    warnings. The dialog drops this into its log so the
    artist can see why a layer is empty."""
    if not bundle.warnings:
        return ""
    lines = ["=== Science layer warnings ==="]
    for w in bundle.warnings:
        lines.append(f"  ! {w}")
    return "\n".join(lines)
