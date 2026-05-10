"""v3.7 query-preset tests."""

from __future__ import annotations

import pytest

from query import (
    AdvancedQuery,
    PRESET_REGISTRY,
    QueryKind,
    QueryPresetDescriptor,
    along_route,
    around_navigator,
    brightest_stars,
    get_preset,
    high_redshift_galaxies,
    high_redshift_quasars,
    list_presets,
    nearby_gaia_objects,
    nearest_stars,
    preset_names,
    selected_dataset_summary,
    solar_system_at_epoch,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_size():
    assert len(PRESET_REGISTRY) == 9


def test_registry_names_unique():
    names = [p.name for p in PRESET_REGISTRY]
    assert len(set(names)) == len(names)


def test_registry_includes_canonical_presets():
    expected = {
        "nearest_stars", "brightest_stars",
        "nearby_gaia_objects",
        "high_redshift_galaxies", "high_redshift_quasars",
        "solar_system_at_epoch",
        "around_navigator", "along_route",
        "selected_dataset_summary",
    }
    assert expected == set(p.name for p in PRESET_REGISTRY)


def test_list_presets_returns_list():
    out = list_presets()
    assert all(isinstance(p, QueryPresetDescriptor) for p in out)


def test_preset_names_returns_strings():
    names = preset_names()
    assert all(isinstance(n, str) for n in names)


def test_get_preset_known():
    p = get_preset("nearest_stars")
    assert p is not None
    assert p.name == "nearest_stars"


def test_get_preset_normalises_case_and_whitespace():
    p = get_preset("  Nearest_Stars  ")
    assert p is not None


def test_get_preset_unknown_returns_none():
    assert get_preset("nope") is None
    assert get_preset("") is None


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def test_nearest_stars_query_kind():
    q = nearest_stars(reference_point_pc=(1, 2, 3), max_results=10)
    assert q.kind is QueryKind.NEAREST
    assert q.reference_point_pc == (1, 2, 3)
    assert q.max_results == 10
    assert q.object_types == ("star",)


def test_brightest_stars_query_kind():
    q = brightest_stars(max_results=20)
    assert q.kind is QueryKind.BRIGHTEST
    assert q.object_types == ("star",)


def test_nearby_gaia_objects_filters_source():
    q = nearby_gaia_objects(
        reference_point_pc=(0, 0, 0),
        distance_max_pc=200.0,
    )
    assert q.kind is QueryKind.NEAREST
    assert "Gaia DR3" in q.sources
    assert q.distance_max_pc == 200.0


def test_high_redshift_galaxies_default():
    q = high_redshift_galaxies()
    assert q.kind is QueryKind.HIGHEST_REDSHIFT
    assert q.object_types == ("galaxy",)
    assert q.redshift_min == 1.0


def test_high_redshift_galaxies_custom_min():
    q = high_redshift_galaxies(redshift_min=2.5)
    assert q.redshift_min == 2.5


def test_high_redshift_quasars_default():
    q = high_redshift_quasars()
    assert q.kind is QueryKind.HIGHEST_REDSHIFT
    assert q.object_types == ("quasar",)


def test_solar_system_at_epoch_with_jd():
    q = solar_system_at_epoch(epoch_jd=2461041.5)
    assert q.kind is QueryKind.BY_TYPE
    assert q.epoch_jd == 2461041.5
    assert q.interpolate_ephemeris is True
    assert "planet" in q.object_types


def test_solar_system_at_epoch_without_jd():
    q = solar_system_at_epoch()
    assert q.epoch_jd is None
    assert q.interpolate_ephemeris is False


def test_around_navigator_caps_distance():
    q = around_navigator(far_clip_pc=750.0)
    assert q.distance_max_pc == 750.0
    assert q.kind is QueryKind.NEAREST


def test_along_route_is_sentinel_kind():
    q = along_route()
    assert q.kind is QueryKind.NEAR_ROUTE


def test_selected_dataset_summary_requires_source():
    with pytest.raises(ValueError):
        selected_dataset_summary(source="")


def test_selected_dataset_summary_filters_source():
    q = selected_dataset_summary(source="Gaia DR3")
    assert q.kind is QueryKind.BY_SOURCE
    assert q.sources == ("Gaia DR3",)


# ---------------------------------------------------------------------------
# Descriptor flags
# ---------------------------------------------------------------------------


def test_solar_system_descriptor_requires_epoch():
    p = get_preset("solar_system_at_epoch")
    assert p.requires_epoch is True


def test_along_route_descriptor_requires_route():
    p = get_preset("along_route")
    assert p.requires_route is True


def test_other_presets_do_not_require_context():
    for name in (
        "nearest_stars", "brightest_stars",
        "nearby_gaia_objects",
        "high_redshift_galaxies",
        "high_redshift_quasars",
        "around_navigator",
        "selected_dataset_summary",
    ):
        p = get_preset(name)
        assert p.requires_epoch is False
        assert p.requires_route is False


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_preset_builders_deterministic():
    a = nearest_stars(reference_point_pc=(0, 0, 0), max_results=10)
    b = nearest_stars(reference_point_pc=(0, 0, 0), max_results=10)
    assert a == b
