"""Tests for core.route. Pure CPython, no Cinema 4D."""

from __future__ import annotations

import json
import math

import pytest

from core.metadata_lookup import MetadataLookup
from core.route import (
    ROUTE_SCHEMA_VERSION,
    ResolvedPosition,
    Route,
    RouteSegment,
    RouteSummary,
    Waypoint,
    compute_route,
    make_lookup_resolver,
    passthrough_resolver,
    render_summary,
)
from data.schema import CatalogObject


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _coord_wp(x, y, z, label="cp"):
    return Waypoint(
        kind="coordinate", label=label,
        x_c4d=float(x), y_c4d=float(y), z_c4d=float(z),
    )


def _full_obj_wp(uid="demo:1", label="Alpha", **overrides):
    base = dict(
        kind="object", label=label, uid=uid,
        catalog_source="unav_sample", object_type="star",
        x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
        x_pc=10.0, y_pc=0.0, z_pc=0.0,
    )
    base.update(overrides)
    return Waypoint(**base)


# ---------------------------------------------------------------------------
# Waypoint validation
# ---------------------------------------------------------------------------


def test_waypoint_rejects_unknown_kind():
    with pytest.raises(ValueError, match="kind"):
        Waypoint(kind="warp")


def test_object_waypoint_requires_uid():
    with pytest.raises(ValueError, match="uid"):
        Waypoint(kind="object", uid="")


def test_coordinate_waypoint_requires_position():
    with pytest.raises(ValueError, match="x/y/z_c4d"):
        Waypoint(kind="coordinate", label="incomplete")


def test_named_waypoint_allows_no_position():
    wp = Waypoint(kind="named", label="Sgr A*")
    assert wp.kind == "named"
    assert not wp.has_c4d_position()
    assert not wp.has_pc_position()


def test_object_waypoint_position_is_optional():
    wp = Waypoint(kind="object", uid="x:1", label="X")
    assert wp.kind == "object"
    assert not wp.has_c4d_position()


# ---------------------------------------------------------------------------
# display_label
# ---------------------------------------------------------------------------


def test_display_label_prefers_explicit_label():
    wp = _full_obj_wp(uid="u:1", label="Alpha")
    assert wp.display_label() == "Alpha"


def test_display_label_falls_back_to_uid_for_objects():
    wp = Waypoint(kind="object", uid="u:7")
    assert wp.display_label() == "u:7"


def test_display_label_kind_marker_for_named():
    wp = Waypoint(kind="named")
    assert "named" in wp.display_label()


# ---------------------------------------------------------------------------
# Waypoint serialization
# ---------------------------------------------------------------------------


def test_waypoint_to_dict_drops_none_fields():
    wp = Waypoint(kind="named", label="Earth")
    d = wp.to_dict()
    assert d == {"kind": "named", "label": "Earth"}


def test_waypoint_round_trip_object_with_full_position():
    wp = _full_obj_wp()
    out = Waypoint.from_dict(wp.to_dict())
    assert out == wp


def test_waypoint_round_trip_coordinate():
    wp = _coord_wp(1, 2, 3, label="origin")
    out = Waypoint.from_dict(wp.to_dict())
    assert out == wp


def test_waypoint_from_dict_drops_unknown_keys():
    out = Waypoint.from_dict({
        "kind": "named", "label": "Earth", "warp_drive": True,
    })
    assert out.kind == "named"
    assert out.label == "Earth"


# ---------------------------------------------------------------------------
# Route container
# ---------------------------------------------------------------------------


def test_route_starts_empty():
    r = Route()
    assert len(r) == 0
    assert r.last() is None


def test_route_add_and_clear():
    r = Route()
    r.add(_coord_wp(0, 0, 0))
    r.add(_coord_wp(1, 0, 0))
    assert len(r) == 2
    n = r.clear()
    assert n == 2
    assert len(r) == 0


def test_route_remove_at_returns_waypoint():
    r = Route()
    a = r.add(_coord_wp(0, 0, 0, label="a"))
    b = r.add(_coord_wp(1, 0, 0, label="b"))
    out = r.remove_at(0)
    assert out is a
    assert r.waypoints == [b]


def test_route_remove_at_out_of_range():
    r = Route()
    r.add(_coord_wp(0, 0, 0))
    assert r.remove_at(99) is None


def test_route_last_returns_most_recent():
    r = Route()
    r.add(_coord_wp(0, 0, 0, label="first"))
    last = r.add(_coord_wp(1, 0, 0, label="second"))
    assert r.last() is last


def test_route_iteration_yields_waypoints():
    r = Route()
    r.add(_coord_wp(0, 0, 0, label="a"))
    r.add(_coord_wp(1, 0, 0, label="b"))
    labels = [wp.label for wp in r]
    assert labels == ["a", "b"]


# ---------------------------------------------------------------------------
# Route serialization
# ---------------------------------------------------------------------------


def test_route_to_dict_includes_schema_version():
    r = Route()
    r.add(_coord_wp(0, 0, 0))
    d = r.to_dict()
    assert d["schema_version"] == ROUTE_SCHEMA_VERSION
    assert d["name"] == "UNAV Route"
    assert len(d["waypoints"]) == 1


def test_route_round_trip_dict():
    r = Route(name="Galactic Tour")
    r.add(_coord_wp(0, 0, 0, label="origin"))
    r.add(_full_obj_wp(uid="x:1"))
    out = Route.from_dict(r.to_dict())
    assert out.name == "Galactic Tour"
    assert len(out.waypoints) == 2
    assert out.waypoints[0].label == "origin"
    assert out.waypoints[1].uid == "x:1"


def test_route_round_trip_json():
    r = Route()
    r.add(_full_obj_wp())
    out = Route.from_json(r.to_json())
    assert len(out.waypoints) == 1
    assert out.waypoints[0].uid == "demo:1"


def test_route_from_json_handles_garbage():
    out = Route.from_json("{not json")
    assert isinstance(out, Route)
    assert len(out) == 0


def test_route_from_dict_handles_none():
    out = Route.from_dict(None)  # type: ignore[arg-type]
    assert isinstance(out, Route)
    assert len(out) == 0


# ---------------------------------------------------------------------------
# passthrough_resolver
# ---------------------------------------------------------------------------


def test_passthrough_resolver_returns_position_when_present():
    wp = _full_obj_wp()
    pos = passthrough_resolver(wp)
    assert pos is not None
    assert pos.x_c4d == 10.0
    assert pos.has_pc()


def test_passthrough_resolver_returns_none_for_named_without_position():
    wp = Waypoint(kind="named", label="Earth")
    assert passthrough_resolver(wp) is None


def test_passthrough_resolver_handles_partial_pc():
    wp = _coord_wp(0, 0, 0)
    pos = passthrough_resolver(wp)
    assert pos is not None
    assert not pos.has_pc()


# ---------------------------------------------------------------------------
# make_lookup_resolver
# ---------------------------------------------------------------------------


def _catalog_obj(uid="cat:1") -> CatalogObject:
    return CatalogObject(
        uid=uid,
        catalog_source="unav_sample",
        object_type="star",
        ra_deg=0.0, dec_deg=0.0,
        distance_parsec=10.0,
    )


def test_lookup_resolver_fills_pc_from_catalog():
    obj = _catalog_obj()
    lk = MetadataLookup([obj])
    resolver = make_lookup_resolver(lk)

    wp = Waypoint(
        kind="object", uid=obj.uid, label="X",
        x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
    )
    pos = resolver(wp)
    assert pos is not None
    assert pos.has_pc()
    assert pos.x_pc == pytest.approx(10.0)


def test_lookup_resolver_falls_back_when_uid_missing_from_lookup():
    lk = MetadataLookup()  # empty
    resolver = make_lookup_resolver(lk)
    wp = _full_obj_wp(uid="absent:1")
    pos = resolver(wp)
    # The cached coords on the waypoint are still returned.
    assert pos is not None
    assert pos.x_c4d == 10.0


def test_lookup_resolver_returns_none_for_unresolvable_named():
    resolver = make_lookup_resolver(MetadataLookup())
    wp = Waypoint(kind="named", label="Earth")
    assert resolver(wp) is None


# ---------------------------------------------------------------------------
# compute_route — distances
# ---------------------------------------------------------------------------


def test_compute_route_empty_returns_zero():
    summary = compute_route(Route())
    assert summary.waypoint_count == 0
    assert summary.resolved_count == 0
    assert summary.total_distance_c4d == 0.0
    assert summary.total_distance_pc is None
    assert summary.segments == []


def test_compute_route_single_waypoint_no_segments():
    r = Route()
    r.add(_full_obj_wp())
    summary = compute_route(r)
    assert summary.waypoint_count == 1
    assert summary.resolved_count == 1
    assert summary.segments == []
    assert summary.total_distance_c4d == 0.0


def test_compute_route_total_c4d_distance():
    r = Route()
    r.add(_coord_wp(0, 0, 0, label="o"))
    r.add(_coord_wp(3, 4, 0, label="a"))
    r.add(_coord_wp(3, 4, 0, label="b"))  # zero-length segment
    summary = compute_route(r)
    assert summary.total_distance_c4d == pytest.approx(5.0)
    assert summary.segments[0].distance_c4d == pytest.approx(5.0)
    assert summary.segments[1].distance_c4d == pytest.approx(0.0)


def test_compute_route_total_pc_when_all_have_pc():
    r = Route()
    r.add(_full_obj_wp(uid="a", x_pc=0.0, y_pc=0.0, z_pc=0.0,
                       x_c4d=0.0, y_c4d=0.0, z_c4d=0.0))
    r.add(_full_obj_wp(uid="b", x_pc=3.0, y_pc=4.0, z_pc=0.0,
                       x_c4d=3.0, y_c4d=4.0, z_c4d=0.0))
    summary = compute_route(r)
    assert summary.total_distance_pc == pytest.approx(5.0)
    assert summary.incomplete_pc_segments == 0


def test_compute_route_pc_total_none_when_any_segment_missing_pc():
    r = Route()
    r.add(_full_obj_wp(uid="a"))                # has pc coords
    r.add(_coord_wp(20.0, 0.0, 0.0, label="b")) # no pc coords
    summary = compute_route(r)
    # C4D total still computed (10 → 20 = 10 units).
    assert summary.total_distance_c4d == pytest.approx(10.0)
    # PC total falls back to None because one endpoint lacks pc coords.
    assert summary.total_distance_pc is None
    assert summary.incomplete_pc_segments == 1
    # The segment is "complete" in c4d but not in pc.
    assert summary.segments[0].is_complete
    assert summary.segments[0].distance_pc is None


def test_compute_route_unresolvable_segment_counted_incomplete():
    """A waypoint that cannot resolve at all (named without coords)
    leaves the surrounding segment incomplete."""
    r = Route()
    r.add(_coord_wp(0, 0, 0, label="o"))
    r.add(Waypoint(kind="named", label="ghost"))    # unresolvable
    r.add(_coord_wp(3, 4, 0, label="a"))
    summary = compute_route(r)
    # Two segments, both touching the ghost waypoint -> both incomplete.
    assert summary.incomplete_segments == 2
    assert summary.total_distance_c4d == 0.0
    assert all(seg.distance_c4d is None for seg in summary.segments)


def test_compute_route_uses_custom_resolver():
    """A resolver that overrides positions can shape the totals."""

    def fixed(wp):
        return ResolvedPosition(0.0, 0.0, 0.0)  # collapse everything

    r = Route()
    r.add(_coord_wp(0, 0, 0))
    r.add(_coord_wp(100, 0, 0))
    summary = compute_route(r, resolver=fixed)
    assert summary.total_distance_c4d == 0.0


# ---------------------------------------------------------------------------
# render_summary
# ---------------------------------------------------------------------------


def test_render_summary_empty_route_friendly_message():
    text = render_summary(Route(), compute_route(Route()))
    assert "No waypoints yet" in text


def test_render_summary_includes_route_name_and_counts():
    r = Route(name="Local Cluster Tour")
    r.add(_coord_wp(0, 0, 0, label="o"))
    r.add(_coord_wp(3, 4, 0, label="a"))
    text = render_summary(r, compute_route(r))
    assert "Local Cluster Tour" in text
    assert "Waypoints       : 2" in text
    assert "Total (C4D)" in text


def test_render_summary_marks_incomplete_pc_total():
    r = Route()
    r.add(_coord_wp(0, 0, 0))
    r.add(_coord_wp(3, 4, 0))
    text = render_summary(r, compute_route(r))
    # Both endpoints are coordinate waypoints (no pc coords), so the
    # parsec total should be marked as missing.
    assert "Total (parsec)" in text
    assert "without parsec coords" in text


def test_render_summary_lists_waypoints_with_index_and_kind():
    r = Route()
    r.add(_full_obj_wp(uid="x:1", label="Alpha"))
    r.add(Waypoint(kind="named", label="Earth"))
    text = render_summary(r, compute_route(r))
    assert "[0] Alpha" in text
    assert "[1] Earth" in text
    assert "(object)" in text
    assert "(named)" in text
