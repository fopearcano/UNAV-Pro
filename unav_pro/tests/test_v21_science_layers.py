"""v2.1 science-layer tests.

Cover:
* Per-layer settings serialization round-trip.
* Distance / redshift / magnitude shell generation.
* Motion vector calculation + cap behaviour.
* Dataset-specific availability (Gaia / SDSS / DESI / JPL).
* Idempotent rebuild contract (bundle structure stable).
* Placeholder layers fail gracefully with warnings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pytest

from astro import (
    LAYER_CATALOG_SOURCE_REGIONS,
    LAYER_CONSTELLATION_BOUNDARIES,
    LAYER_DISTANCE_SHELLS,
    LAYER_MAGNITUDE_SHELLS,
    LAYER_MOTION_VECTORS,
    LAYER_OBJECT_DENSITY_VOLUME,
    LAYER_REDSHIFT_SHELLS,
    LAYER_SOLAR_SYSTEM_ORBITS,
    LAYER_SUPPORTED_SOURCES,
    MAX_MOTION_VECTORS,
    SCIENCE_LAYER_IDS,
    CatalogSourceRegionSettings,
    ConstellationBoundarySettings,
    DistanceShellSettings,
    MagnitudeShellSettings,
    MotionVectorSettings,
    ObjectDensityVolumeSettings,
    RedshiftShellSettings,
    ScienceLayerSettings,
    SolarSystemOrbitSettings,
    build_catalog_source_regions,
    build_distance_shells,
    build_magnitude_shells,
    build_motion_vectors,
    build_redshift_shells,
    build_science_bundle,
    build_solar_system_orbits,
    render_warnings,
    to_overlay_bundle,
)


@dataclass
class _Row:
    uid: str = "x:1"
    catalog_source: str = "Gaia DR3"
    object_type: Optional[str] = "star"
    cartesian_x: Optional[float] = 0.0
    cartesian_y: Optional[float] = 0.0
    cartesian_z: Optional[float] = 0.0
    proper_motion_ra: Optional[float] = None
    proper_motion_dec: Optional[float] = None
    radial_velocity_kms: Optional[float] = None


# ---------------------------------------------------------------------------
# Constants + registry
# ---------------------------------------------------------------------------


def test_layer_ids_include_every_expected_kind():
    expected = {
        "distance_shells", "redshift_shells", "magnitude_shells",
        "motion_vectors", "catalog_source_regions",
        "solar_system_orbits", "constellation_boundaries",
        "object_density_volume",
    }
    assert set(SCIENCE_LAYER_IDS) == expected


def test_supported_sources_map_covers_every_layer():
    for layer_id in SCIENCE_LAYER_IDS:
        assert layer_id in LAYER_SUPPORTED_SOURCES


# ---------------------------------------------------------------------------
# Per-layer settings validation
# ---------------------------------------------------------------------------


def test_distance_shell_settings_drop_invalid():
    s = DistanceShellSettings(radii_pc=[10.0, -5.0, 0.0, 50.0, 50.0, "bad"])  # type: ignore[list-item]
    assert s.radii_pc == [10.0, 50.0]


def test_distance_shell_settings_default_when_empty():
    s = DistanceShellSettings(radii_pc=[])
    assert s.radii_pc == [100.0]


def test_redshift_shell_settings_drop_negative_z():
    s = RedshiftShellSettings(redshifts=[-0.1, 0.0, 0.5, 0.5])
    assert s.redshifts == [0.5]


def test_motion_vector_settings_clamp_max():
    s = MotionVectorSettings(max_vectors=10_000_000)
    assert s.max_vectors == MAX_MOTION_VECTORS


def test_motion_vector_settings_reject_zero_scale():
    with pytest.raises(ValueError):
        MotionVectorSettings(scale_pc_per_masyr=0.0)


# ---------------------------------------------------------------------------
# ScienceLayerSettings round-trip
# ---------------------------------------------------------------------------


def test_science_layer_settings_default_disabled():
    s = ScienceLayerSettings()
    assert s.any_enabled() is False
    assert s.enabled_layer_ids() == []


def test_science_layer_settings_round_trip():
    s = ScienceLayerSettings(
        distance_shells=DistanceShellSettings(enabled=True, radii_pc=[10.0, 100.0]),
        motion_vectors=MotionVectorSettings(enabled=True, min_pm_masyr=5.0),
    )
    rt = ScienceLayerSettings.from_dict(s.to_dict())
    assert rt.distance_shells.enabled is True
    assert rt.distance_shells.radii_pc == [10.0, 100.0]
    assert rt.motion_vectors.enabled is True
    assert rt.motion_vectors.min_pm_masyr == 5.0


def test_science_layer_settings_corrupt_falls_through():
    """A malformed entry for one layer must not corrupt the
    other layers — each sub-settings instance is built
    independently."""
    s = ScienceLayerSettings.from_dict({
        "distance_shells": {"enabled": True, "radii_pc": [10.0]},
        "motion_vectors": {"scale_pc_per_masyr": -1.0},  # invalid
    })
    assert s.distance_shells.enabled is True
    # Bad sub-settings → defaults for that layer only.
    assert s.motion_vectors.scale_pc_per_masyr > 0


def test_science_layer_settings_enabled_layer_ids():
    s = ScienceLayerSettings(
        distance_shells=DistanceShellSettings(enabled=True),
        redshift_shells=RedshiftShellSettings(enabled=True),
    )
    ids = set(s.enabled_layer_ids())
    assert ids == {"distance_shells", "redshift_shells"}


# ---------------------------------------------------------------------------
# Distance shells
# ---------------------------------------------------------------------------


def test_distance_shells_three_planes_per_radius():
    res = build_distance_shells(DistanceShellSettings(
        enabled=True, radii_pc=[10.0, 50.0],
    ))
    assert res.layer_id == LAYER_DISTANCE_SHELLS
    # 2 radii × 3 planes = 6 polylines.
    assert len(res.polylines) == 6
    assert all(p.kind == LAYER_DISTANCE_SHELLS for p in res.polylines)
    assert all(p.closed for p in res.polylines)
    assert res.item_count == 2


def test_distance_shells_radius_correct():
    res = build_distance_shells(DistanceShellSettings(
        enabled=True, radii_pc=[42.0],
    ))
    for poly in res.polylines:
        for (x, y, z) in poly.points:
            r = math.sqrt(x * x + y * y + z * z)
            assert abs(r - 42.0) < 1e-3


def test_distance_shells_disabled_returns_empty():
    res = build_distance_shells(DistanceShellSettings(enabled=False))
    assert res.polylines == []


# ---------------------------------------------------------------------------
# Redshift shells
# ---------------------------------------------------------------------------


def test_redshift_shells_emit_proxy_warning():
    res = build_redshift_shells(RedshiftShellSettings(
        enabled=True, redshifts=[0.1],
    ))
    assert any("Hubble" in w for w in res.warnings)
    assert len(res.polylines) == 3


def test_redshift_shells_radius_increases_with_z():
    res = build_redshift_shells(RedshiftShellSettings(
        enabled=True, redshifts=[0.01, 0.5],
    ))
    # 2 redshifts × 3 planes = 6.
    assert len(res.polylines) == 6
    # The first three polylines (z=0.01) sit at smaller radius
    # than the next three (z=0.5).
    r_small = math.sqrt(sum(c * c for c in res.polylines[0].points[0]))
    r_big = math.sqrt(sum(c * c for c in res.polylines[3].points[0]))
    assert r_small < r_big


# ---------------------------------------------------------------------------
# Magnitude shells
# ---------------------------------------------------------------------------


def test_magnitude_shells_emit_cosmetic_warning():
    res = build_magnitude_shells(MagnitudeShellSettings(
        enabled=True, magnitudes=[5.0, 8.0],
    ))
    assert any("cosmetic" in w for w in res.warnings)
    assert len(res.polylines) == 6  # 2 mags × 3 planes


def test_magnitude_shells_radius_increases_with_mag():
    res = build_magnitude_shells(MagnitudeShellSettings(
        enabled=True, magnitudes=[5.0, 11.0],
    ))
    r_bright = math.sqrt(sum(c * c for c in res.polylines[0].points[0]))
    r_dim = math.sqrt(sum(c * c for c in res.polylines[3].points[0]))
    assert r_bright < r_dim


# ---------------------------------------------------------------------------
# Motion vectors
# ---------------------------------------------------------------------------


def test_motion_vectors_disabled_no_polylines():
    res = build_motion_vectors(
        MotionVectorSettings(enabled=False),
        objects=[_Row(proper_motion_ra=10.0)],
    )
    assert res.polylines == []


def test_motion_vectors_proper_motion_emits_one_line_per_row():
    rows = [
        _Row(uid="g:1", cartesian_x=10.0, cartesian_y=0.0, cartesian_z=0.0,
             proper_motion_ra=5.0, proper_motion_dec=-3.0),
        _Row(uid="g:2", cartesian_x=0.0, cartesian_y=10.0, cartesian_z=0.0,
             proper_motion_ra=2.0, proper_motion_dec=1.0),
    ]
    res = build_motion_vectors(
        MotionVectorSettings(enabled=True), objects=rows,
    )
    assert len(res.polylines) == 2
    for poly in res.polylines:
        # Each is a 2-point segment.
        assert len(poly.points) == 2


def test_motion_vectors_skip_rows_without_position():
    rows = [
        _Row(uid="g:1", cartesian_x=None, cartesian_y=None, cartesian_z=None,
             proper_motion_ra=5.0, proper_motion_dec=-3.0),
    ]
    res = build_motion_vectors(
        MotionVectorSettings(enabled=True), objects=rows,
    )
    assert res.polylines == []


def test_motion_vectors_min_pm_filter():
    rows = [
        _Row(uid="g:slow", cartesian_x=10.0, cartesian_y=0.0, cartesian_z=0.0,
             proper_motion_ra=0.5, proper_motion_dec=0.5),
        _Row(uid="g:fast", cartesian_x=10.0, cartesian_y=0.0, cartesian_z=0.0,
             proper_motion_ra=50.0, proper_motion_dec=50.0),
    ]
    res = build_motion_vectors(
        MotionVectorSettings(enabled=True, min_pm_masyr=10.0),
        objects=rows,
    )
    # Only the fast row passes the filter.
    assert len(res.polylines) == 1


def test_motion_vectors_cap_truncates_extras():
    rows = [
        _Row(uid=f"g:{i}", cartesian_x=10.0, cartesian_y=0.0, cartesian_z=0.0,
             proper_motion_ra=5.0, proper_motion_dec=-3.0)
        for i in range(20)
    ]
    res = build_motion_vectors(
        MotionVectorSettings(enabled=True, max_vectors=5),
        objects=rows,
    )
    assert len(res.polylines) == 5
    assert any("capped" in w for w in res.warnings)


def test_motion_vectors_radial_velocity():
    rows = [
        _Row(uid="g:rv", cartesian_x=10.0, cartesian_y=0.0, cartesian_z=0.0,
             radial_velocity_kms=20.0),
    ]
    res = build_motion_vectors(
        MotionVectorSettings(
            enabled=True, show_proper_motion=False, show_radial_velocity=True,
        ),
        objects=rows,
    )
    assert len(res.polylines) == 1


# ---------------------------------------------------------------------------
# Catalog source regions
# ---------------------------------------------------------------------------


def test_catalog_source_regions_one_per_source():
    rows = [
        _Row(catalog_source="Gaia DR3", cartesian_x=1.0, cartesian_y=0.0, cartesian_z=0.0),
        _Row(catalog_source="Gaia DR3", cartesian_x=2.0, cartesian_y=0.0, cartesian_z=0.0),
        _Row(catalog_source="SDSS", cartesian_x=10.0, cartesian_y=10.0, cartesian_z=0.0),
    ]
    res = build_catalog_source_regions(
        CatalogSourceRegionSettings(enabled=True), objects=rows,
    )
    # 2 sources × 3 planes = 6 polylines + 2 labels.
    assert len(res.polylines) == 6
    assert len(res.labels) == 2


def test_catalog_source_regions_warning_when_no_positions():
    rows = [_Row(catalog_source="Gaia DR3", cartesian_x=None, cartesian_y=None, cartesian_z=None)]
    res = build_catalog_source_regions(
        CatalogSourceRegionSettings(enabled=True), objects=rows,
    )
    assert any("nothing to draw" in w for w in res.warnings)


# ---------------------------------------------------------------------------
# Solar System orbits
# ---------------------------------------------------------------------------


def test_solar_system_orbits_only_jpl_rows():
    rows = [
        _Row(uid="jpl:Mars:2026", catalog_source="JPL Horizons",
             cartesian_x=1.5e-5, cartesian_y=0.0, cartesian_z=0.0),
        _Row(uid="gaia:1", catalog_source="Gaia DR3",
             cartesian_x=10.0, cartesian_y=0.0, cartesian_z=0.0),
    ]
    res = build_solar_system_orbits(
        SolarSystemOrbitSettings(enabled=True), objects=rows,
    )
    assert len(res.polylines) == 1
    assert res.polylines[0].label.startswith("Mars")


def test_solar_system_orbits_empty_when_no_jpl_rows():
    rows = [_Row(catalog_source="Gaia DR3", cartesian_x=10.0, cartesian_y=0.0, cartesian_z=0.0)]
    res = build_solar_system_orbits(
        SolarSystemOrbitSettings(enabled=True), objects=rows,
    )
    assert res.polylines == []
    assert any("no JPL Horizons" in w for w in res.warnings)


def test_solar_system_orbits_dedup_by_body():
    """Same body at multiple epochs (different uids) should
    only produce one orbit ring."""
    rows = [
        _Row(uid="jpl:Mars:2026", catalog_source="JPL Horizons",
             cartesian_x=1.5e-5, cartesian_y=0.0, cartesian_z=0.0),
        _Row(uid="jpl:Mars:2027", catalog_source="JPL Horizons",
             cartesian_x=1.6e-5, cartesian_y=0.0, cartesian_z=0.0),
    ]
    res = build_solar_system_orbits(
        SolarSystemOrbitSettings(enabled=True), objects=rows,
    )
    assert len(res.polylines) == 1


# ---------------------------------------------------------------------------
# Placeholder layers
# ---------------------------------------------------------------------------


def test_constellation_boundaries_placeholder_emits_warning():
    s = ConstellationBoundarySettings(enabled=True)
    from astro import build_constellation_boundaries
    res = build_constellation_boundaries(s)
    assert res.polylines == []
    assert any("placeholder" in w for w in res.warnings)


def test_object_density_volume_placeholder_emits_warning():
    s = ObjectDensityVolumeSettings(enabled=True)
    from astro import build_object_density_volume
    res = build_object_density_volume(s)
    assert res.polylines == []
    assert any("placeholder" in w for w in res.warnings)


# ---------------------------------------------------------------------------
# Bundle aggregation + idempotency
# ---------------------------------------------------------------------------


def _bundle_with_two_layers(rows=None):
    settings = ScienceLayerSettings(
        distance_shells=DistanceShellSettings(enabled=True, radii_pc=[10.0, 50.0]),
        catalog_source_regions=CatalogSourceRegionSettings(enabled=True),
    )
    return build_science_bundle(settings, objects=rows or [])


def test_build_science_bundle_groups_per_layer():
    rows = [_Row(catalog_source="Gaia DR3", cartesian_x=10.0, cartesian_y=0.0, cartesian_z=0.0)]
    bundle = _bundle_with_two_layers(rows)
    layer_ids = [r.layer_id for r in bundle.per_layer]
    assert LAYER_DISTANCE_SHELLS in layer_ids
    assert LAYER_CATALOG_SOURCE_REGIONS in layer_ids


def test_build_science_bundle_is_idempotent():
    """Re-running with the same input produces byte-identical
    bundle structure (counts + kinds match)."""
    rows = [
        _Row(uid="g:1", catalog_source="Gaia DR3",
             cartesian_x=10.0, cartesian_y=0.0, cartesian_z=0.0,
             proper_motion_ra=5.0, proper_motion_dec=-3.0),
    ]
    settings = ScienceLayerSettings(
        distance_shells=DistanceShellSettings(enabled=True),
        motion_vectors=MotionVectorSettings(enabled=True),
        catalog_source_regions=CatalogSourceRegionSettings(enabled=True),
    )
    a = build_science_bundle(settings, objects=rows)
    b = build_science_bundle(settings, objects=rows)
    assert a.total_polylines() == b.total_polylines()
    assert a.total_labels() == b.total_labels()
    for ra, rb in zip(a.per_layer, b.per_layer):
        assert ra.layer_id == rb.layer_id
        assert len(ra.polylines) == len(rb.polylines)


def test_science_bundle_empty_when_nothing_enabled():
    bundle = build_science_bundle(ScienceLayerSettings(), objects=[])
    assert bundle.empty()


def test_to_overlay_bundle_flattens():
    rows = [_Row(catalog_source="Gaia DR3", cartesian_x=10.0, cartesian_y=0.0, cartesian_z=0.0)]
    bundle = _bundle_with_two_layers(rows)
    flat = to_overlay_bundle(bundle)
    assert flat.polylines  # not empty


def test_render_warnings_includes_warnings():
    bundle = build_science_bundle(
        ScienceLayerSettings(
            redshift_shells=RedshiftShellSettings(enabled=True, redshifts=[0.1]),
        ),
    )
    text = render_warnings(bundle)
    assert "Hubble" in text


def test_render_warnings_empty_when_no_warnings():
    bundle = build_science_bundle(ScienceLayerSettings(), objects=[])
    assert render_warnings(bundle) == ""


# ---------------------------------------------------------------------------
# Dataset awareness
# ---------------------------------------------------------------------------


def test_motion_vectors_warns_when_dataset_lacks_pm():
    rows = [_Row(catalog_source="SDSS", cartesian_x=1.0, cartesian_y=0.0, cartesian_z=0.0)]
    res = build_motion_vectors(
        MotionVectorSettings(enabled=True), objects=rows,
    )
    assert any("no rows in active dataset carry" in w for w in res.warnings)


def test_solar_orbits_layer_only_lists_jpl_in_supported():
    assert LAYER_SUPPORTED_SOURCES[LAYER_SOLAR_SYSTEM_ORBITS] == ("JPL Horizons",)


def test_redshift_supported_sources_extragalactic():
    assert "SDSS" in LAYER_SUPPORTED_SOURCES[LAYER_REDSHIFT_SHELLS]
    assert "DESI" in LAYER_SUPPORTED_SOURCES[LAYER_REDSHIFT_SHELLS]


def test_motion_supported_sources_gaia_only():
    assert LAYER_SUPPORTED_SOURCES[LAYER_MOTION_VECTORS] == ("Gaia DR3",)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_distance_shells_deterministic():
    s = DistanceShellSettings(enabled=True, radii_pc=[10.0, 25.0])
    a = build_distance_shells(s)
    b = build_distance_shells(s)
    for pa, pb in zip(a.polylines, b.polylines):
        assert pa.points == pb.points
