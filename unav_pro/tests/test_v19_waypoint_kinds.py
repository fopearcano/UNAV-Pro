"""v1.9 waypoint extensions — new kinds + new fields."""

from __future__ import annotations

import pytest

from voyage import (
    MISSION_WAYPOINT_KINDS,
    PATH_CONTRIBUTING_KINDS,
    Mission,
    MissionWaypoint,
    build_camera_path,
)


# ---------------------------------------------------------------------------
# New kinds + path-contributing predicate
# ---------------------------------------------------------------------------


def test_v19_kinds_present():
    for k in ("search_result", "orbital", "annotation"):
        assert k in MISSION_WAYPOINT_KINDS


def test_annotation_not_in_path_contributing_kinds():
    assert "annotation" not in PATH_CONTRIBUTING_KINDS
    assert "object" in PATH_CONTRIBUTING_KINDS
    assert "search_result" in PATH_CONTRIBUTING_KINDS
    assert "orbital" in PATH_CONTRIBUTING_KINDS


def test_annotation_waypoint_skipped_in_camera_path():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
        MissionWaypoint(kind="annotation", label="note"),
        MissionWaypoint(kind="coordinate", x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m)
    # The annotation contributes nothing.
    assert path.waypoint_count() == 2


def test_search_result_requires_uid():
    with pytest.raises(ValueError):
        MissionWaypoint(kind="search_result")


def test_orbital_requires_uid():
    with pytest.raises(ValueError):
        MissionWaypoint(kind="orbital")


def test_annotation_requires_label_or_notes():
    with pytest.raises(ValueError):
        MissionWaypoint(kind="annotation")


def test_annotation_with_only_notes_ok():
    wp = MissionWaypoint(kind="annotation", notes="some prose")
    assert wp.kind == "annotation"


# ---------------------------------------------------------------------------
# camera_offset
# ---------------------------------------------------------------------------


def test_camera_offset_shifts_path_position():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate",
                        x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        camera_offset=(5.0, 0.0, 0.0)),
        MissionWaypoint(kind="coordinate",
                        x_c4d=10.0, y_c4d=0.0, z_c4d=0.0),
    ])
    path = build_camera_path(m)
    # First sample lands at the offset position, not the bare anchor.
    a = path.sample(0.0)
    assert a.x == pytest.approx(5.0)


def test_camera_offset_invalid_tuple_rejected():
    with pytest.raises(ValueError):
        MissionWaypoint(
            kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
            camera_offset=(1.0, 2.0),  # 2-tuple
        )


# ---------------------------------------------------------------------------
# Tags + serialization round-trip
# ---------------------------------------------------------------------------


def test_tags_lower_cased_on_construction():
    wp = MissionWaypoint(
        kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
        tags=["Solar", " STAR ", "  "],
    )
    assert wp.tags == ["solar", "star"]


def test_has_tag_predicate():
    wp = MissionWaypoint(
        kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
        tags=["solar"],
    )
    assert wp.has_tag("solar") is True
    assert wp.has_tag("Solar") is True  # case-insensitive
    assert wp.has_tag("missing") is False
    assert wp.has_tag("") is False


def test_v19_fields_round_trip():
    m = Mission(waypoints=[
        MissionWaypoint(
            kind="search_result",
            uid="gaia:42",
            search_query="Sirius",
            x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
            tags=["star", "search"],
            camera_offset=(1.0, 2.0, 3.0),
        ),
    ])
    rt = Mission.from_json(m.to_json()).waypoints[0]
    assert rt.kind == "search_result"
    assert rt.uid == "gaia:42"
    assert rt.search_query == "Sirius"
    assert rt.tags == ["star", "search"]
    assert rt.camera_offset == (1.0, 2.0, 3.0)


def test_default_v19_fields_omitted_on_roundtrip():
    """A waypoint with no v1.9 extensions serialises byte-
    identical to v1.4: tags / camera_offset / search_query
    fields are absent."""
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate",
                        x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
    ])
    out = m.to_dict()["waypoints"][0]
    assert "tags" not in out
    assert "camera_offset" not in out
    assert "search_query" not in out


# ---------------------------------------------------------------------------
# Display labels for the new kinds
# ---------------------------------------------------------------------------


def test_search_result_display_uses_uid():
    wp = MissionWaypoint(
        kind="search_result", uid="gaia:42",
        x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
    )
    assert wp.display_label() == "gaia:42"


def test_orbital_display_prefixes_uid():
    wp = MissionWaypoint(kind="orbital", uid="jpl:Mars:2026")
    assert wp.display_label() == "orbital:jpl:Mars:2026"


def test_annotation_default_label():
    wp = MissionWaypoint(kind="annotation", notes="xyz")
    assert wp.display_label() == "annotation"
