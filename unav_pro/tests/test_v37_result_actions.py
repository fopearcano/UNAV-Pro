"""v3.7 result-action tests."""

from __future__ import annotations

import pytest

from data import CatalogObject
from query import (
    QueryResult,
    add_all_to_mission,
    add_all_to_route,
    add_to_mission_action,
    add_to_route_action,
    bookmark_action,
    bookmark_all,
    focus_navigator_action,
    inspect_action,
)


def _result(uid="x", **kw):
    base = dict(uid=uid)
    base.update(kw)
    return QueryResult(**base)


def _snapshot(uid="x", x=1.0, y=2.0, z=3.0):
    return CatalogObject(
        uid=uid, catalog_source="Test",
        object_type="star", ra_deg=0.0, dec_deg=0.0,
        cartesian_x=x, cartesian_y=y, cartesian_z=z,
    )


# ---------------------------------------------------------------------------
# focus_navigator_action
# ---------------------------------------------------------------------------


def test_focus_action_sets_uid():
    out = focus_navigator_action(_result(uid="a"))
    assert out.target_uid == "a"


def test_focus_action_pulls_position_from_snapshot():
    snap = _snapshot(x=5.0, y=6.0, z=7.0)
    r = _result(uid="a", snapshot=snap)
    out = focus_navigator_action(r)
    assert out.target_position_pc == (5.0, 6.0, 7.0)


def test_focus_action_handles_missing_snapshot():
    out = focus_navigator_action(_result(uid="a"))
    assert out.target_position_pc is None


def test_focus_action_uses_common_name_as_label():
    r = _result(uid="x", common_name="Sirius")
    assert focus_navigator_action(r).label == "Sirius"


def test_focus_action_rejects_none():
    with pytest.raises(ValueError):
        focus_navigator_action(None)


# ---------------------------------------------------------------------------
# bookmark_action
# ---------------------------------------------------------------------------


def test_bookmark_uses_common_name_when_present():
    r = _result(uid="x", common_name="Demo Star")
    delta = bookmark_action(r)
    assert delta.label == "Demo Star"
    assert delta.uid == "x"


def test_bookmark_falls_back_to_uid():
    r = _result(uid="x")
    delta = bookmark_action(r)
    assert delta.label == "x"


def test_bookmark_includes_source():
    r = _result(uid="x", catalog_source="Gaia DR3")
    delta = bookmark_action(r)
    assert delta.catalog_source == "Gaia DR3"


def test_bookmark_rejects_none():
    with pytest.raises(ValueError):
        bookmark_action(None)


# ---------------------------------------------------------------------------
# add_to_route_action
# ---------------------------------------------------------------------------


def test_route_delta_kind_is_object():
    delta = add_to_route_action(_result(uid="x"))
    assert delta.kind == "object"


def test_route_delta_label_uses_common_name():
    delta = add_to_route_action(_result(uid="x", common_name="Sirius"))
    assert delta.label == "Sirius"


def test_route_delta_rejects_none():
    with pytest.raises(ValueError):
        add_to_route_action(None)


# ---------------------------------------------------------------------------
# add_to_mission_action
# ---------------------------------------------------------------------------


def test_mission_delta_default_duration():
    delta = add_to_mission_action(_result(uid="x"))
    assert delta.duration_seconds == 4.0


def test_mission_delta_custom_duration():
    delta = add_to_mission_action(
        _result(uid="x"), duration_seconds=8.5,
    )
    assert delta.duration_seconds == 8.5


def test_mission_delta_negative_duration_rejected():
    with pytest.raises(ValueError):
        add_to_mission_action(
            _result(uid="x"), duration_seconds=-1.0,
        )


def test_mission_delta_orbital_kind_for_solar_system():
    for object_type in ("planet", "moon", "asteroid", "comet"):
        delta = add_to_mission_action(
            _result(uid="x", object_type=object_type),
        )
        assert delta.kind == "orbital"


def test_mission_delta_object_kind_for_stars():
    delta = add_to_mission_action(
        _result(uid="x", object_type="star"),
    )
    assert delta.kind == "object"


# ---------------------------------------------------------------------------
# inspect_action
# ---------------------------------------------------------------------------


def test_inspect_action_sets_uid_and_label():
    req = inspect_action(_result(uid="x", common_name="Sirius"))
    assert req.uid == "x"
    assert req.label == "Sirius"


def test_inspect_action_rejects_none():
    with pytest.raises(ValueError):
        inspect_action(None)


# ---------------------------------------------------------------------------
# Bulk variants
# ---------------------------------------------------------------------------


def test_bookmark_all():
    results = [_result(uid="a"), _result(uid="b")]
    deltas = bookmark_all(results)
    assert len(deltas) == 2
    assert {d.uid for d in deltas} == {"a", "b"}


def test_bookmark_all_skips_none_entries():
    results = [_result(uid="a"), None, _result(uid="b")]
    deltas = bookmark_all(results)
    assert len(deltas) == 2


def test_add_all_to_route():
    deltas = add_all_to_route([
        _result(uid="a"), _result(uid="b"),
    ])
    assert len(deltas) == 2
    assert all(d.kind == "object" for d in deltas)


def test_add_all_to_mission_uses_duration():
    deltas = add_all_to_mission(
        [_result(uid="a"), _result(uid="b")],
        duration_seconds=6.0,
    )
    assert all(d.duration_seconds == 6.0 for d in deltas)


# ---------------------------------------------------------------------------
# Short summaries
# ---------------------------------------------------------------------------


def test_focus_summary_includes_uid():
    out = focus_navigator_action(_result(uid="x"))
    assert "x" in out.short_summary()


def test_bookmark_summary_includes_label():
    out = bookmark_action(_result(uid="x", common_name="L"))
    assert "L" in out.short_summary()


def test_route_summary_includes_uid():
    out = add_to_route_action(_result(uid="x"))
    assert "x" in out.short_summary()


def test_mission_summary_starts_with_prefix():
    out = add_to_mission_action(_result(uid="x"))
    assert out.short_summary().startswith("mission+")


def test_inspect_summary_includes_uid():
    out = inspect_action(_result(uid="x"))
    assert "x" in out.short_summary()
