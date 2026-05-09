"""v1.9 voyage template tests."""

from __future__ import annotations

import pytest

from voyage import (
    Mission,
    NEAREST_STARS,
    REDSHIFT_ANCHORS,
    SOLAR_SYSTEM_BODIES,
    TEMPLATE_REGISTRY,
    empty_voyage,
    get_template,
    list_templates,
    nearest_stars_tour,
    redshift_tour,
    selected_objects_tour,
    solar_system_tour,
)


def test_solar_system_tour_has_eight_planets():
    m = solar_system_tour()
    assert len(m.waypoints) == len(SOLAR_SYSTEM_BODIES) == 8
    labels = [w.label for w in m.waypoints]
    assert labels[0] == "Mercury"
    assert labels[-1] == "Neptune"


def test_solar_system_waypoints_are_orbital_kind():
    m = solar_system_tour()
    assert all(w.kind == "orbital" for w in m.waypoints)


def test_solar_system_template_carries_template_tag():
    m = solar_system_tour()
    assert "template" in m.tags
    assert "solar-system" in m.tags


def test_solar_system_template_is_editable():
    """Templates return mutable Missions; the dialog can rename
    / reorder / extend them freely."""
    m = solar_system_tour()
    m.title = "My Solar System Cinematic"
    m.add(m.waypoints[0])  # duplicate the first stop
    assert m.title == "My Solar System Cinematic"
    assert len(m.waypoints) == 9


def test_nearest_stars_template_includes_origin():
    m = nearest_stars_tour()
    assert m.waypoints[0].label == "Sun (origin)"
    # Plus the catalogue.
    assert len(m.waypoints) == 1 + len(NEAREST_STARS)


def test_nearest_stars_have_cached_pc_positions():
    """Cached pc positions let the path render without an
    active metadata lookup."""
    m = nearest_stars_tour()
    for w in m.waypoints:
        assert w.has_pc_position()


def test_redshift_tour_anchors_in_increasing_distance():
    m = redshift_tour()
    distances = [w.x_pc for w in m.waypoints]
    assert distances == sorted(distances)
    assert len(m.waypoints) == len(REDSHIFT_ANCHORS)


def test_redshift_tour_carries_approximate_tag():
    m = redshift_tour()
    assert "approximate" in m.tags
    for w in m.waypoints:
        assert "approximate" in w.tags


def test_empty_voyage_has_zero_waypoints():
    m = empty_voyage()
    assert isinstance(m, Mission)
    assert len(m.waypoints) == 0


def test_empty_voyage_carries_custom_title():
    m = empty_voyage(title="Custom", description="x", tags=["a", "b"])
    assert m.title == "Custom"
    assert m.description == "x"
    assert m.tags == ["a", "b"]


def test_selected_objects_tour_filters_blanks():
    m = selected_objects_tour(["gaia:1", "", "gaia:2", "  "])
    assert len(m.waypoints) == 2
    assert m.waypoints[0].uid == "gaia:1"
    assert m.waypoints[1].uid == "gaia:2"


def test_selected_objects_tour_empty_input():
    m = selected_objects_tour([])
    assert len(m.waypoints) == 0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_template_registry_lists_five_entries():
    assert len(TEMPLATE_REGISTRY) == 5
    names = {t.name for t in TEMPLATE_REGISTRY}
    assert names == {
        "solar_system_tour", "nearest_stars_tour",
        "redshift_tour", "empty_voyage", "selected_objects_tour",
    }


def test_get_template_resolves_by_name():
    assert get_template("solar_system_tour") is not None
    assert get_template("redshift_tour") is not None
    assert get_template("nope") is None
    assert get_template("") is None


def test_get_template_is_case_insensitive():
    assert get_template("Solar_System_Tour") is not None


def test_list_templates_returns_descriptors():
    descriptors = list_templates()
    assert len(descriptors) == 5
    for d in descriptors:
        assert d.name and d.label and d.description and d.builder


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_template_missions_round_trip_through_json():
    m = solar_system_tour()
    rt = Mission.from_json(m.to_json())
    assert rt.title == m.title
    assert len(rt.waypoints) == len(m.waypoints)
    assert rt.tags == m.tags
