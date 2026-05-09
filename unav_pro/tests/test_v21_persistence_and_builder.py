"""v2.1 persistence + c4d builder contract tests.

The c4d-bound applier (``apply_science_bundle``) is exercised
by the dialog at runtime; these tests cover the pure-Python
contracts: parent/container naming, no-c4d safety, project
state round-trip.
"""

from __future__ import annotations

import pytest

from astro import (
    DistanceShellSettings,
    MotionVectorSettings,
    RedshiftShellSettings,
    ScienceLayerSettings,
    build_science_bundle,
)
from c4d_objects.overlays_builder import (
    SCIENCE_LAYERS_ROOT_NAME,
    apply_science_bundle,
    clear_science_layers,
    container_name_for_layer,
    science_layers_root_name,
)
from core.project_state import ProjectState


# ---------------------------------------------------------------------------
# C4D builder contract — pure-Python helpers
# ---------------------------------------------------------------------------


def test_science_layers_root_name_canonical():
    assert science_layers_root_name() == "UNAV_ScienceLayers"
    assert science_layers_root_name() == SCIENCE_LAYERS_ROOT_NAME


def test_science_layers_root_distinct_from_overlays_root():
    """Critical: v2.1 must not collide with v2.0's
    ``UNAV_Overlays`` root. Otherwise one builder would
    delete the other's children on every rebuild."""
    from c4d_objects.overlays_builder import OVERLAYS_ROOT_NAME
    assert SCIENCE_LAYERS_ROOT_NAME != OVERLAYS_ROOT_NAME


def test_science_container_name_per_layer_id():
    assert container_name_for_layer("distance_shells") == "UNAV_ScienceLayer_distance_shells"
    assert container_name_for_layer("motion_vectors") == "UNAV_ScienceLayer_motion_vectors"


def test_science_container_prefix_distinct_from_v20():
    """v2.0 containers use ``UNAV_Overlay_<kind>``; v2.1 uses
    ``UNAV_ScienceLayer_<kind>``. The distinct prefixes keep
    the per-layer cleanup walks independent."""
    from c4d_objects.overlays_builder import container_name_for_kind
    assert container_name_for_kind("grid").startswith("UNAV_Overlay_")
    assert container_name_for_layer("distance_shells").startswith("UNAV_ScienceLayer_")


def test_apply_science_bundle_no_c4d_returns_zero():
    bundle = build_science_bundle(
        ScienceLayerSettings(
            distance_shells=DistanceShellSettings(enabled=True),
        ),
    )
    assert apply_science_bundle(bundle) == 0


def test_apply_science_bundle_empty_no_c4d_returns_zero():
    bundle = build_science_bundle(ScienceLayerSettings(), objects=[])
    assert apply_science_bundle(bundle) == 0


def test_clear_science_layers_no_c4d_returns_false():
    assert clear_science_layers() is False


# ---------------------------------------------------------------------------
# ProjectState carries the science_layers dict
# ---------------------------------------------------------------------------


def test_project_state_default_science_layers_empty():
    ps = ProjectState()
    assert ps.science_layers == {}


def test_project_state_round_trip_with_science_layers():
    settings = ScienceLayerSettings(
        distance_shells=DistanceShellSettings(enabled=True, radii_pc=[5.0, 10.0]),
        motion_vectors=MotionVectorSettings(enabled=True, min_pm_masyr=2.5),
    )
    ps = ProjectState(science_layers=settings.to_dict())
    rt = ProjectState.from_dict(ps.to_dict())
    assert "distance_shells" in rt.science_layers
    rebuilt = ScienceLayerSettings.from_dict(rt.science_layers)
    assert rebuilt.distance_shells.enabled is True
    assert rebuilt.distance_shells.radii_pc == [5.0, 10.0]
    assert rebuilt.motion_vectors.enabled is True
    assert rebuilt.motion_vectors.min_pm_masyr == 2.5


def test_project_state_handles_missing_science_layers_key():
    """Loading a v2.0 project_state file (without the new
    ``science_layers`` key) must not raise."""
    legacy = {
        "schema_version": 1,
        "saved_at_iso": None,
        "navigator": {},
        "route": {},
        "visual_encoding": {},
        "config": None,
        "overlays": {},
    }
    ps = ProjectState.from_dict(legacy)
    assert ps.science_layers == {}


def test_project_state_carries_overlays_and_science_layers_independently():
    overlays = {"show_grid": True, "radius_pc": 50.0}
    settings = ScienceLayerSettings(
        redshift_shells=RedshiftShellSettings(enabled=True),
    )
    ps = ProjectState(
        overlays=overlays,
        science_layers=settings.to_dict(),
    )
    rt = ProjectState.from_dict(ps.to_dict())
    assert rt.overlays.get("show_grid") is True
    assert "redshift_shells" in rt.science_layers


# ---------------------------------------------------------------------------
# Bundle structure stability across repeated builds
# ---------------------------------------------------------------------------


def test_bundle_per_layer_count_matches_eight_layer_set():
    """``build_science_bundle`` always emits exactly eight
    per-layer results (one per kind), even when most are
    disabled."""
    bundle = build_science_bundle(ScienceLayerSettings(), objects=[])
    assert len(bundle.per_layer) == 8


def test_repeated_build_preserves_layer_order():
    s = ScienceLayerSettings(
        distance_shells=DistanceShellSettings(enabled=True),
    )
    a = build_science_bundle(s)
    b = build_science_bundle(s)
    assert [r.layer_id for r in a.per_layer] == [r.layer_id for r in b.per_layer]
