"""v2.0 dataset-derived helper tests."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pytest

from procedural import (
    DEFAULT_SHELL_REDSHIFTS,
    BoundingSphere,
    DensityHeatmap,
    RedshiftShells,
    SourceDistribution,
    compute_bounding_sphere,
    compute_density_heatmap_placeholder,
    compute_redshift_shells_placeholder,
    compute_source_distribution,
)


@dataclass
class _Obj:
    """Minimal stand-in for ``CatalogObject`` — the helpers
    only read ``cartesian_*`` / ``catalog_source`` /
    ``object_type``."""

    cartesian_x: Optional[float] = None
    cartesian_y: Optional[float] = None
    cartesian_z: Optional[float] = None
    catalog_source: Optional[str] = None
    object_type: Optional[str] = None


# ---------------------------------------------------------------------------
# Bounding sphere
# ---------------------------------------------------------------------------


def test_bounding_sphere_empty_input():
    s = compute_bounding_sphere([])
    assert s.count == 0
    assert s.radius_pc == 0.0
    assert s.centre_pc == (0.0, 0.0, 0.0)


def test_bounding_sphere_single_point():
    s = compute_bounding_sphere([_Obj(1.0, 2.0, 3.0)])
    assert s.count == 1
    assert s.centre_pc == (1.0, 2.0, 3.0)
    assert s.radius_pc == 0.0


def test_bounding_sphere_two_points():
    s = compute_bounding_sphere([
        _Obj(0.0, 0.0, 0.0),
        _Obj(2.0, 0.0, 0.0),
    ])
    assert s.count == 2
    assert s.centre_pc == (1.0, 0.0, 0.0)
    assert s.radius_pc == pytest.approx(1.0)


def test_bounding_sphere_skips_objects_without_position():
    s = compute_bounding_sphere([
        _Obj(0.0, 0.0, 0.0),
        _Obj(None, None, None),
        _Obj(2.0, 0.0, 0.0),
    ])
    assert s.count == 2


def test_bounding_sphere_three_dimensional():
    s = compute_bounding_sphere([
        _Obj(1.0, 0.0, 0.0),
        _Obj(0.0, 1.0, 0.0),
        _Obj(0.0, 0.0, 1.0),
    ])
    # Centroid = (1/3, 1/3, 1/3); radius = farthest point.
    assert s.count == 3
    assert s.centre_pc[0] == pytest.approx(1.0 / 3.0)
    expected_r = math.sqrt(
        (1.0 - 1.0 / 3.0) ** 2 + (1.0 / 3.0) ** 2 + (1.0 / 3.0) ** 2
    )
    assert s.radius_pc == pytest.approx(expected_r)


# ---------------------------------------------------------------------------
# Source distribution
# ---------------------------------------------------------------------------


def test_source_distribution_counts():
    objs = [
        _Obj(catalog_source="Gaia DR3", object_type="star"),
        _Obj(catalog_source="Gaia DR3", object_type="star"),
        _Obj(catalog_source="SDSS", object_type="galaxy"),
        _Obj(catalog_source=None, object_type=None),
    ]
    rep = compute_source_distribution(objs)
    assert rep.total == 4
    assert rep.by_catalog_source.get("Gaia DR3") == 2
    assert rep.by_catalog_source.get("SDSS") == 1
    assert rep.by_catalog_source.get("<unspecified>") == 1
    assert rep.by_object_type.get("star") == 2
    assert rep.by_object_type.get("galaxy") == 1


def test_source_distribution_render_text_for_empty():
    rep = compute_source_distribution([])
    assert "No objects" in rep.render_text()


def test_source_distribution_render_text_lists_counts():
    rep = compute_source_distribution([
        _Obj(catalog_source="Gaia DR3", object_type="star"),
    ])
    text = rep.render_text()
    assert "Dataset summary" in text
    assert "Gaia DR3" in text
    assert "star" in text


# ---------------------------------------------------------------------------
# Density heatmap placeholder
# ---------------------------------------------------------------------------


def test_density_heatmap_size_matches_bins():
    h = compute_density_heatmap_placeholder([], bins=4, extent_pc=10.0)
    assert h.bins == 4
    assert len(h.cells) == 4 ** 3
    assert all(c == 0.0 for c in h.cells)
    assert h.is_placeholder is True


def test_density_heatmap_clamps_bins():
    big = compute_density_heatmap_placeholder([], bins=10_000)
    assert big.bins == 64  # cap


def test_density_heatmap_floor_extent():
    h = compute_density_heatmap_placeholder([], extent_pc=-1.0)
    assert h.extent_pc == 1.0


def test_density_heatmap_cell_index():
    h = compute_density_heatmap_placeholder([], bins=4)
    # Index of (0,0,0) → 0; (3,3,3) → 4*4*4 - 1 = 63.
    assert h.cell_index(0, 0, 0) == 0
    assert h.cell_index(3, 3, 3) == 63


# ---------------------------------------------------------------------------
# Redshift shell placeholder
# ---------------------------------------------------------------------------


def test_redshift_shells_default_uses_bundled_ladder():
    s = compute_redshift_shells_placeholder()
    assert len(s.shells) == len(DEFAULT_SHELL_REDSHIFTS)
    # Radii are monotonically increasing with z.
    radii = [r for _, r in s.shells]
    assert radii == sorted(radii)


def test_redshift_shells_drops_negative_z():
    s = compute_redshift_shells_placeholder([0.1, -0.5, 0.0, 0.5])
    zs = [z for z, _ in s.shells]
    assert 0.1 in zs
    assert 0.5 in zs
    assert -0.5 not in zs
    assert 0.0 not in zs


def test_redshift_shells_render_text_includes_proxy_caveat():
    s = compute_redshift_shells_placeholder([0.1])
    text = s.render_text()
    assert "Hubble proxy" in text
    assert "0.100" in text


def test_redshift_shells_empty_render():
    s = RedshiftShells()
    assert "No redshift shells" in s.render_text()
