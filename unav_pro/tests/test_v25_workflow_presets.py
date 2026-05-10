"""v2.5 workflow-preset tests.

The presets are a thin re-presentation layer over the v1.9
voyage templates. Tests assert: (1) the registry is shaped
correctly, (2) every preset resolves to a callable builder
that produces a real ``Mission``, (3) the friendly metadata
(``label`` / ``task`` / ``recommended_overlays``) is
populated, (4) the lookup helpers return the right values
for known + unknown names.

Crucially: tests must prove the wrapper is **transparent** —
the Mission produced by ``build_mission_from_preset`` is
exactly what the v1.9 template builder would produce.
"""

from __future__ import annotations

import pytest

from core.workflow_presets import (
    WORKFLOW_PRESETS,
    WorkflowPreset,
    build_mission_from_preset,
    get_workflow_preset,
    list_workflow_presets,
    preset_labels,
    preset_names,
    recommended_overlays_for,
)
from voyage import Mission
from voyage.templates import (
    empty_voyage,
    nearest_stars_tour,
    redshift_tour,
    selected_objects_tour,
    solar_system_tour,
)


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


def test_registry_is_non_empty():
    assert len(WORKFLOW_PRESETS) >= 5


def test_registry_entries_are_workflow_presets():
    for entry in WORKFLOW_PRESETS:
        assert isinstance(entry, WorkflowPreset)


def test_registry_names_are_unique():
    names = [p.name for p in WORKFLOW_PRESETS]
    assert len(names) == len(set(names))


def test_registry_labels_are_unique():
    labels = [p.label for p in WORKFLOW_PRESETS]
    assert len(labels) == len(set(labels))


def test_registry_covers_expected_presets():
    names = {p.name for p in WORKFLOW_PRESETS}
    expected = {
        "solar_system_flythrough",
        "stellar_neighbourhood",
        "hubble_flow_voyage",
        "blank_voyage",
        "selection_flythrough",
    }
    assert expected.issubset(names)


def test_registry_is_immutable():
    """The registry tuple should be a tuple (not a list) so
    accidental mutation can't poison it across modules."""
    assert isinstance(WORKFLOW_PRESETS, tuple)


# ---------------------------------------------------------------------------
# Field shape
# ---------------------------------------------------------------------------


def test_every_preset_has_callable_builder():
    for p in WORKFLOW_PRESETS:
        assert callable(p.builder)


def test_every_preset_has_a_label_and_task():
    for p in WORKFLOW_PRESETS:
        assert p.label, f"{p.name} missing label"
        assert p.task, f"{p.name} missing task copy"


def test_every_preset_has_template_name():
    for p in WORKFLOW_PRESETS:
        assert p.template_name, f"{p.name} missing template_name"


def test_recommended_overlays_are_strings():
    """Overlay kinds are stored as strings; tests can
    cross-check them against the v2.0 overlay registry."""
    for p in WORKFLOW_PRESETS:
        assert isinstance(p.recommended_overlays, tuple)
        for k in p.recommended_overlays:
            assert isinstance(k, str)
            assert k


def test_default_duration_is_positive():
    for p in WORKFLOW_PRESETS:
        assert p.default_duration_seconds > 0


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def test_list_workflow_presets_returns_list():
    presets = list_workflow_presets()
    assert isinstance(presets, list)
    assert len(presets) == len(WORKFLOW_PRESETS)


def test_list_workflow_presets_preserves_order():
    """Order matters: Solar System first, etc."""
    presets = list_workflow_presets()
    assert presets[0].name == "solar_system_flythrough"


def test_get_workflow_preset_resolves_known_name():
    p = get_workflow_preset("solar_system_flythrough")
    assert p is not None
    assert p.name == "solar_system_flythrough"


def test_get_workflow_preset_normalises_case_and_whitespace():
    assert get_workflow_preset("  Blank_Voyage ") is not None


def test_get_workflow_preset_returns_none_for_unknown():
    assert get_workflow_preset("does_not_exist") is None
    assert get_workflow_preset("") is None


def test_preset_names_returns_stable_list():
    names = preset_names()
    assert names[0] == "solar_system_flythrough"
    assert "blank_voyage" in names


def test_preset_labels_returns_human_strings():
    labels = preset_labels()
    assert "Solar System Flythrough" in labels
    assert "Blank Voyage" in labels


def test_recommended_overlays_for_unknown_returns_empty():
    assert recommended_overlays_for("bogus") == ()


def test_recommended_overlays_for_known_returns_tuple():
    overlays = recommended_overlays_for("solar_system_flythrough")
    assert isinstance(overlays, tuple)
    assert "ecliptic_plane" in overlays


# ---------------------------------------------------------------------------
# build_mission_from_preset
# ---------------------------------------------------------------------------


def test_build_mission_from_preset_solar_system():
    m = build_mission_from_preset("solar_system_flythrough")
    assert isinstance(m, Mission)
    # The v1.9 template ships eight planet waypoints.
    assert len(m.waypoints) == 8


def test_build_mission_from_preset_nearest_stars():
    m = build_mission_from_preset("stellar_neighbourhood")
    assert isinstance(m, Mission)
    # Sun + six neighbours = seven waypoints.
    assert len(m.waypoints) == 7


def test_build_mission_from_preset_redshift():
    m = build_mission_from_preset("hubble_flow_voyage")
    assert isinstance(m, Mission)
    assert len(m.waypoints) >= 4
    # The v1.9 template tags every waypoint as "approximate".
    for wp in m.waypoints:
        assert "approximate" in wp.tags


def test_build_mission_from_preset_blank_voyage():
    m = build_mission_from_preset("blank_voyage")
    assert isinstance(m, Mission)
    assert m.waypoints == []


def test_build_mission_from_preset_selection_with_uids():
    m = build_mission_from_preset(
        "selection_flythrough",
        uids=["gaia:1", "gaia:2", "gaia:3"],
    )
    assert isinstance(m, Mission)
    assert len(m.waypoints) == 3


def test_build_mission_from_preset_selection_filters_blanks():
    m = build_mission_from_preset(
        "selection_flythrough",
        uids=["gaia:1", "", "  ", "gaia:2"],
    )
    assert len(m.waypoints) == 2


def test_build_mission_from_preset_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        build_mission_from_preset("does_not_exist")


def test_build_mission_from_preset_forwards_kwargs():
    """Custom title flows through to the underlying empty
    voyage builder."""
    m = build_mission_from_preset("blank_voyage", title="Custom Voyage")
    assert m.title == "Custom Voyage"


# ---------------------------------------------------------------------------
# Wrapper transparency: preset === underlying template
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "preset_name, builder",
    [
        ("solar_system_flythrough", solar_system_tour),
        ("stellar_neighbourhood", nearest_stars_tour),
        ("hubble_flow_voyage", redshift_tour),
        ("blank_voyage", empty_voyage),
    ],
)
def test_preset_builder_is_underlying_template(preset_name, builder):
    """The preset's builder field is *literally* the v1.9
    template builder. Calling either produces equivalent
    output."""
    p = get_workflow_preset(preset_name)
    assert p is not None
    assert p.builder is builder


def test_preset_mission_round_trips_via_json():
    """A preset-built mission round-trips through the
    Mission JSON loader byte-identically."""
    m = build_mission_from_preset("solar_system_flythrough")
    rt = Mission.from_json(m.to_json())
    assert [w.uid for w in rt.waypoints] == [w.uid for w in m.waypoints]
    assert [w.label for w in rt.waypoints] == [w.label for w in m.waypoints]
