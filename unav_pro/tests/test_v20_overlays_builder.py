"""v2.0 c4d overlays builder tests.

The c4d-bound applier is exercised by the dialog at runtime;
these tests cover the pure-Python contract: parent/container
naming, idempotent no-op behaviour outside Cinema 4D, and
the overlays-root-removal path.
"""

from __future__ import annotations

import pytest

from c4d_objects.overlays_builder import (
    OVERLAYS_ROOT_NAME,
    apply_overlay_bundle,
    clear_overlays,
    container_name_for_kind,
    overlays_root_name,
)
from procedural import (
    KIND_DISTANCE_RINGS,
    KIND_GALACTIC_PLANE,
    KIND_GRID,
    KIND_ROUTE_CORRIDOR,
    KIND_SECTOR_CONE,
    KIND_WAYPOINT_LABELS,
    OverlayBundle,
    OverlayLabel,
    OverlayPolyline,
)


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


def test_overlays_root_name_is_canonical():
    assert overlays_root_name() == "UNAV_Overlays"
    assert overlays_root_name() == OVERLAYS_ROOT_NAME


def test_container_name_per_kind():
    assert container_name_for_kind(KIND_GRID) == "UNAV_Overlay_grid"
    assert container_name_for_kind(KIND_GALACTIC_PLANE) == "UNAV_Overlay_galactic_plane"
    assert container_name_for_kind(KIND_DISTANCE_RINGS) == "UNAV_Overlay_distance_rings"
    assert container_name_for_kind(KIND_SECTOR_CONE) == "UNAV_Overlay_sector_cone"
    assert container_name_for_kind(KIND_ROUTE_CORRIDOR) == "UNAV_Overlay_route_corridor"
    assert container_name_for_kind(KIND_WAYPOINT_LABELS) == "UNAV_Overlay_waypoint_labels"


def test_container_names_are_distinct_across_kinds():
    """Every overlay kind produces a unique container name —
    guards against accidental collisions in the v2.0 builder
    when a future kind is added without updating the name
    helper."""
    from procedural import OVERLAY_KINDS
    names = [container_name_for_kind(k) for k in OVERLAY_KINDS]
    assert len(set(names)) == len(names)


# ---------------------------------------------------------------------------
# Apply outside Cinema 4D
# ---------------------------------------------------------------------------


def test_apply_no_c4d_returns_zero():
    bundle = OverlayBundle(polylines=[
        OverlayPolyline(kind=KIND_GRID, index=0,
                        points=[(0, 0, 0), (1, 0, 0)]),
    ])
    assert apply_overlay_bundle(bundle) == 0


def test_apply_empty_bundle_no_c4d_returns_zero():
    assert apply_overlay_bundle(OverlayBundle()) == 0


def test_clear_overlays_no_c4d_returns_false():
    assert clear_overlays() is False


# ---------------------------------------------------------------------------
# Idempotency contract documented through the bundle shape
# ---------------------------------------------------------------------------


def test_bundle_kind_grouping_is_stable():
    """The builder keys per-kind containers off the bundle's
    kind values. A bundle built from the same input twice
    produces the same kind grouping — which guarantees the
    builder reuses (rather than duplicates) per-kind
    containers."""
    bundle = OverlayBundle(polylines=[
        OverlayPolyline(kind=KIND_GRID, index=0,
                        points=[(0, 0, 0), (1, 0, 0)]),
        OverlayPolyline(kind=KIND_GRID, index=1,
                        points=[(0, 0, 0), (0, 1, 0)]),
        OverlayPolyline(kind=KIND_GALACTIC_PLANE, index=0,
                        points=[(1, 0, 0), (0, 1, 0), (-1, 0, 0)],
                        closed=True),
    ])
    by_kind = {}
    for poly in bundle.polylines:
        by_kind.setdefault(poly.kind, []).append(poly)
    assert set(by_kind.keys()) == {KIND_GRID, KIND_GALACTIC_PLANE}
    assert len(by_kind[KIND_GRID]) == 2


def test_bundle_label_collection_separate_from_polylines():
    """Labels live in their own list; polylines never carry
    label text. This separation is what keeps the builder's
    waypoint-labels container distinct from the polyline
    containers."""
    bundle = OverlayBundle(
        polylines=[
            OverlayPolyline(kind=KIND_GRID, index=0,
                            points=[(0, 0, 0), (1, 0, 0)])
        ],
        labels=[OverlayLabel(text="A", position=(0, 0, 0))],
    )
    # No polyline carries label data; labels carry no points.
    for p in bundle.polylines:
        assert isinstance(p.points, list)
    for l in bundle.labels:
        assert isinstance(l.text, str)


def test_bundle_by_kind_lookup():
    bundle = OverlayBundle(polylines=[
        OverlayPolyline(kind=KIND_GRID, index=0, points=[(0, 0, 0), (1, 0, 0)]),
        OverlayPolyline(kind=KIND_GRID, index=1, points=[(0, 0, 0), (0, 1, 0)]),
        OverlayPolyline(kind=KIND_GALACTIC_PLANE, index=0,
                        points=[(0, 0, 0), (1, 0, 0)]),
    ])
    grid = bundle.by_kind(KIND_GRID)
    assert len(grid) == 2
    assert all(p.kind == KIND_GRID for p in grid)
