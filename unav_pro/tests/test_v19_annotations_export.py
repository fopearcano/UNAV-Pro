"""v1.9 annotations + exports tests."""

from __future__ import annotations

import csv
import io
import json
import os

import pytest

from voyage import (
    Mission,
    MissionWaypoint,
    SceneAnnotation,
    add_scene_annotation,
    build_mission_annotations,
    derive_notes,
    get_scene_annotations,
    mission_to_csv,
    mission_to_json_file,
    mission_to_markdown,
    remove_scene_annotation_at,
    write_csv,
    write_markdown,
)


# ---------------------------------------------------------------------------
# SceneAnnotation
# ---------------------------------------------------------------------------


def test_scene_annotation_requires_label():
    with pytest.raises(ValueError):
        SceneAnnotation(label="")


def test_scene_annotation_round_trip_dict():
    a = SceneAnnotation(label="Sun", x_c4d=1.0, y_c4d=2.0, z_c4d=3.0,
                        notes="origin", tags=["star", "Center"])
    rt = SceneAnnotation.from_dict(a.to_dict())
    assert rt.label == "Sun"
    assert rt.tags == ["star", "center"]  # lowercased
    assert rt.x_c4d == 1.0


def test_add_and_remove_scene_annotation_on_mission():
    m = Mission()
    add_scene_annotation(m, SceneAnnotation(label="A"))
    add_scene_annotation(m, SceneAnnotation(label="B"))
    annotations = get_scene_annotations(m)
    assert [a.label for a in annotations] == ["A", "B"]
    assert remove_scene_annotation_at(m, 0) is True
    assert remove_scene_annotation_at(m, 99) is False
    assert [a.label for a in get_scene_annotations(m)] == ["B"]


def test_mission_serialises_scene_annotations():
    m = Mission()
    add_scene_annotation(m, SceneAnnotation(label="Origin"))
    rt = Mission.from_json(m.to_json())
    annotations = get_scene_annotations(rt)
    assert len(annotations) == 1
    assert annotations[0].label == "Origin"


def test_mission_omits_scene_annotations_when_empty():
    m = Mission()
    assert "scene_annotations" not in m.to_dict()


# ---------------------------------------------------------------------------
# derive_notes
# ---------------------------------------------------------------------------


def test_derive_notes_includes_catalog_and_uid():
    wp = MissionWaypoint(
        kind="object", uid="gaia:1",
        catalog_source="Gaia DR3", object_type="star",
        epoch_jd=2451545.0,
    )
    notes = derive_notes(wp)
    assert any("Gaia DR3" in n for n in notes)
    assert any("uid: gaia:1" in n for n in notes)
    assert any("epoch: JD" in n for n in notes)


def test_derive_notes_search_query():
    wp = MissionWaypoint(
        kind="search_result", uid="gaia:1",
        search_query="Sirius",
    )
    notes = derive_notes(wp)
    assert any("found via search: Sirius" in n for n in notes)


def test_derive_notes_camera_offset():
    wp = MissionWaypoint(
        kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
        camera_offset=(1.0, 2.0, 3.0),
    )
    notes = derive_notes(wp)
    assert any("camera offset" in n for n in notes)


# ---------------------------------------------------------------------------
# build_mission_annotations
# ---------------------------------------------------------------------------


def test_build_mission_annotations_includes_derived_by_default():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="gaia:1",
                        catalog_source="Gaia DR3"),
    ])
    rpt = build_mission_annotations(m)
    wa = rpt.waypoint_annotations[0]
    assert wa.derived  # non-empty


def test_build_mission_annotations_can_skip_derived():
    m = Mission(waypoints=[
        MissionWaypoint(kind="object", uid="gaia:1",
                        catalog_source="Gaia DR3"),
    ])
    rpt = build_mission_annotations(m, include_derived=False)
    assert rpt.waypoint_annotations[0].derived == []


def test_render_text_lists_waypoints_and_scene_annotations():
    m = Mission(title="Tour", description="hi")
    m.waypoints.append(
        MissionWaypoint(kind="object", uid="gaia:1", notes="bright"),
    )
    add_scene_annotation(m, SceneAnnotation(label="Origin"))
    text = build_mission_annotations(
        m, scene_annotations=m.scene_annotations,
    ).render_text()
    assert "Tour" in text
    assert "hi" in text
    assert "bright" in text  # waypoint notes
    assert "Origin" in text


def test_render_text_empty_mission_says_so():
    m = Mission()
    text = build_mission_annotations(m).render_text()
    assert "no annotations" in text


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def _two_wp_mission():
    return Mission(title="Tour", description="A short test tour.", waypoints=[
        MissionWaypoint(
            kind="object", uid="gaia:1", label="Sirius",
            catalog_source="Gaia DR3", object_type="star",
            x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
            x_pc=0.0, y_pc=0.0, z_pc=0.0,
        ),
        MissionWaypoint(
            kind="object", uid="gaia:2", label="Vega",
            catalog_source="Gaia DR3", object_type="star",
            x_c4d=10.0, y_c4d=0.0, z_c4d=0.0,
            x_pc=10.0, y_pc=0.0, z_pc=0.0,
        ),
    ])


def test_markdown_starts_with_h1_title():
    text = mission_to_markdown(_two_wp_mission())
    assert text.startswith("# Tour")


def test_markdown_lists_waypoints_table():
    text = mission_to_markdown(_two_wp_mission())
    assert "| Sirius" in text
    assert "| Vega" in text
    assert "| 0 |" in text  # row indices
    assert "| 1 |" in text


def test_markdown_includes_route_analytics_when_eligible():
    text = mission_to_markdown(_two_wp_mission())
    assert "Route Analytics" in text
    assert "Total (parsec)" in text


def test_markdown_skips_analytics_for_single_waypoint_mission():
    m = Mission(title="Solo", waypoints=[
        MissionWaypoint(kind="coordinate", x_c4d=0.0, y_c4d=0.0, z_c4d=0.0),
    ])
    text = mission_to_markdown(m)
    assert "Route Analytics" not in text


def test_markdown_escapes_pipe_characters():
    m = Mission(title="x", waypoints=[
        MissionWaypoint(kind="coordinate",
                        x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        label="weird|label"),
    ])
    text = mission_to_markdown(m)
    assert "weird\\|label" in text


def test_markdown_includes_scene_annotations_section():
    m = _two_wp_mission()
    add_scene_annotation(m, SceneAnnotation(label="Origin"))
    text = mission_to_markdown(m)
    assert "Scene Annotations" in text
    assert "Origin" in text


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def test_csv_header_matches_csv_fields():
    from voyage import CSV_FIELDS
    rows = list(csv.reader(io.StringIO(mission_to_csv(_two_wp_mission()))))
    assert tuple(rows[0]) == tuple(CSV_FIELDS)


def test_csv_row_per_waypoint():
    rows = list(csv.reader(io.StringIO(mission_to_csv(_two_wp_mission()))))
    # Header + two waypoints.
    assert len(rows) == 3
    assert rows[1][2] == "Sirius"
    assert rows[2][2] == "Vega"


def test_csv_tags_joined_with_semicolon():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate",
                        x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        tags=["solar", "demo"]),
    ])
    rows = list(csv.reader(io.StringIO(mission_to_csv(m))))
    # Find the tags column.
    from voyage import CSV_FIELDS
    tag_idx = list(CSV_FIELDS).index("tags")
    assert rows[1][tag_idx] == "solar; demo"


def test_csv_strips_newlines_in_notes():
    m = Mission(waypoints=[
        MissionWaypoint(kind="coordinate",
                        x_c4d=0.0, y_c4d=0.0, z_c4d=0.0,
                        notes="line1\nline2"),
    ])
    text = mission_to_csv(m)
    # No raw newline mid-notes (the notes field itself).
    assert "line1 line2" in text


# ---------------------------------------------------------------------------
# Atomic file writes
# ---------------------------------------------------------------------------


def test_write_markdown_atomic(tmp_path):
    target = str(tmp_path / "out.md")
    ok = write_markdown(_two_wp_mission(), target)
    assert ok == target
    with open(target, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert text.startswith("# Tour")


def test_write_csv_atomic(tmp_path):
    target = str(tmp_path / "out.csv")
    ok = write_csv(_two_wp_mission(), target)
    assert ok == target
    with open(target, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "Sirius" in text


def test_mission_to_json_file_atomic(tmp_path):
    target = str(tmp_path / "out.json")
    ok = mission_to_json_file(_two_wp_mission(), target)
    assert ok == target
    with open(target, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["title"] == "Tour"
