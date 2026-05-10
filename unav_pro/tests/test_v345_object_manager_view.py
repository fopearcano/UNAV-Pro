"""v3.45 Object-Manager-view tests."""

from __future__ import annotations

import pytest

from c4d_objects.object_manager_view import (
    DuplicateRootReport,
    FlatNode,
    ObjectNode,
    OrphanReport,
    UNAVObjectCounts,
    count_unav_objects,
    find_duplicate_roots,
    find_orphans,
    flatten_unav_tree,
    render_object_manager_view,
)
from c4d_objects.scene_structure import (
    CANONICAL_CHILD_GROUPS,
    DEBUG_GROUP_NAME,
    MISSIONS_GROUP_NAME,
    NAVIGATION_GROUP_NAME,
    OVERLAYS_GROUP_NAME,
    PROJECT_ROOT_NAME,
    SCIENCE_LAYERS_GROUP_NAME,
    VISIBLE_SECTOR_GROUP_NAME,
)


# ---------------------------------------------------------------------------
# ObjectNode
# ---------------------------------------------------------------------------


def test_descendants_walks_full_tree():
    leaf = ObjectNode("leaf")
    mid = ObjectNode("mid", children=[leaf])
    root = ObjectNode("root", children=[mid])
    desc = root.descendants()
    names = [n.name for n in desc]
    assert names == ["mid", "leaf"]


def test_descendants_returns_empty_for_leaf():
    leaf = ObjectNode("x")
    assert leaf.descendants() == []


# ---------------------------------------------------------------------------
# count_unav_objects
# ---------------------------------------------------------------------------


def _project_node(*, children=()):
    return ObjectNode(PROJECT_ROOT_NAME, children=list(children))


def test_count_no_project_root_returns_blank():
    counts = count_unav_objects([ObjectNode("Camera")])
    assert counts.project_root_present is False
    assert counts.total_unav_owned == 0


def test_count_canonical_children_each_count_one():
    project = _project_node(children=[
        ObjectNode(name) for name in CANONICAL_CHILD_GROUPS
    ])
    counts = count_unav_objects([project])
    assert counts.project_root_present
    assert counts.total_unav_owned == 6
    assert counts.by_category["navigation"] == 1
    assert counts.by_category["debug"] == 1


def test_count_includes_unav_descendants():
    overlays = ObjectNode(OVERLAYS_GROUP_NAME, children=[
        ObjectNode("UNAV_Overlay_grid"),
        ObjectNode("UNAV_Overlay_galactic_plane"),
    ])
    project = _project_node(children=[overlays])
    counts = count_unav_objects([project])
    assert counts.by_category["overlays"] == 3  # null + 2 children


def test_count_skips_non_unav_descendants():
    overlays = ObjectNode(OVERLAYS_GROUP_NAME, children=[
        ObjectNode("ArtistNull"),
    ])
    project = _project_node(children=[overlays])
    counts = count_unav_objects([project])
    # Just the OVERLAYS root null counts; ArtistNull is
    # artist content.
    assert counts.by_category["overlays"] == 1


def test_count_short_summary_no_root():
    counts = UNAVObjectCounts()
    assert "no UNAV_Project root" in counts.short_summary()


def test_count_short_summary_present_no_children():
    project = _project_node()
    counts = count_unav_objects([project])
    assert "no children" in counts.short_summary()


def test_count_short_summary_with_data():
    project = _project_node(children=[
        ObjectNode(NAVIGATION_GROUP_NAME),
    ])
    counts = count_unav_objects([project])
    assert "navigation=1" in counts.short_summary()


# ---------------------------------------------------------------------------
# flatten_unav_tree
# ---------------------------------------------------------------------------


def test_flatten_skips_non_unav_roots():
    rows = flatten_unav_tree([ObjectNode("Camera")])
    assert rows == []


def test_flatten_walks_tree_depth_first():
    overlays = ObjectNode(OVERLAYS_GROUP_NAME, children=[
        ObjectNode("UNAV_Overlay_grid"),
    ])
    project = _project_node(children=[overlays])
    rows = flatten_unav_tree([project])
    names = [r.name for r in rows]
    assert names == [
        PROJECT_ROOT_NAME, OVERLAYS_GROUP_NAME, "UNAV_Overlay_grid",
    ]


def test_flatten_assigns_categories_to_children():
    overlays = ObjectNode(OVERLAYS_GROUP_NAME, children=[
        ObjectNode("UNAV_Overlay_grid"),
    ])
    project = _project_node(children=[overlays])
    rows = flatten_unav_tree([project])
    by_name = {r.name: r.category for r in rows}
    assert by_name[OVERLAYS_GROUP_NAME] == "overlays"
    assert by_name["UNAV_Overlay_grid"] == "overlays"


def test_flat_node_render_indents_by_depth():
    fn = FlatNode(name="X", depth=2, category="overlays")
    text = fn.render()
    assert text.startswith("    X")
    assert "[overlays]" in text


def test_render_om_view_blank_when_no_unav():
    text = render_object_manager_view([ObjectNode("Camera")])
    assert "(no UNAV objects" in text


def test_render_om_view_lists_tree():
    project = _project_node(children=[ObjectNode(NAVIGATION_GROUP_NAME)])
    text = render_object_manager_view([project])
    assert PROJECT_ROOT_NAME in text
    assert NAVIGATION_GROUP_NAME in text


# ---------------------------------------------------------------------------
# find_duplicate_roots
# ---------------------------------------------------------------------------


def test_find_duplicates_clean_scene():
    rep = find_duplicate_roots([ObjectNode("Camera")])
    assert rep.is_clean()


def test_find_duplicates_detects_doubled_root():
    roots = [
        ObjectNode("UNAV_Project"),
        ObjectNode("UNAV_Project"),
    ]
    rep = find_duplicate_roots(roots)
    assert "UNAV_Project" in rep.duplicates


def test_find_duplicates_detects_legacy_roots():
    roots = [ObjectNode("UNAV_Starfield")]
    rep = find_duplicate_roots(roots)
    assert "UNAV_Starfield" in rep.legacy_roots


def test_find_duplicates_short_summary_clean():
    rep = DuplicateRootReport()
    assert "clean" in rep.short_summary()


def test_find_duplicates_short_summary_with_data():
    rep = DuplicateRootReport(duplicates=["UNAV_Project"])
    assert "duplicates" in rep.short_summary()


def test_find_duplicates_outputs_sorted():
    roots = [
        ObjectNode("UNAV_Z"),
        ObjectNode("UNAV_Z"),
        ObjectNode("UNAV_A"),
        ObjectNode("UNAV_A"),
    ]
    rep = find_duplicate_roots(roots)
    assert rep.duplicates == sorted(rep.duplicates)


# ---------------------------------------------------------------------------
# find_orphans
# ---------------------------------------------------------------------------


def test_find_orphans_clean_canonical():
    project = _project_node(children=[
        ObjectNode(name) for name in CANONICAL_CHILD_GROUPS
    ])
    rep = find_orphans([project])
    assert rep.is_clean()


def test_find_orphans_flags_non_canonical_unav_child():
    project = _project_node(children=[
        ObjectNode(NAVIGATION_GROUP_NAME),
        ObjectNode("UNAV_Experimental"),
    ])
    rep = find_orphans([project])
    orphan_names = [name for (name, _parent) in rep.orphans]
    assert "UNAV_Experimental" in orphan_names


def test_find_orphans_ignores_artist_content():
    project = _project_node(children=[
        ObjectNode(NAVIGATION_GROUP_NAME),
        ObjectNode("MyArtistNull"),
    ])
    rep = find_orphans([project])
    assert rep.is_clean()


def test_find_orphans_no_project_root():
    rep = find_orphans([ObjectNode("Camera")])
    assert rep.is_clean()


def test_orphan_report_summary():
    rep = OrphanReport()
    assert "no orphans" in rep.short_summary()
    rep.orphans = [("UNAV_X", "UNAV_Project")]
    assert "1 orphan" in rep.short_summary()
