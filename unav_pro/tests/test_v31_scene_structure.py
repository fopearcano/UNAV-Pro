"""v3.1 scene-structure planning tests.

Pure helpers only (no Cinema 4D). The c4d-bound builders
raise ``RuntimeError`` outside the host, which is the
right behaviour for the test suite.
"""

from __future__ import annotations

import pytest

from c4d_objects.scene_structure import (
    CANONICAL_CHILD_GROUPS,
    DEBUG_GROUP_NAME,
    LEGACY_ROOT_TO_CANONICAL,
    MISSIONS_GROUP_NAME,
    NAVIGATION_GROUP_NAME,
    OVERLAYS_GROUP_NAME,
    PROJECT_ROOT_NAME,
    SCIENCE_LAYERS_GROUP_NAME,
    VISIBLE_SECTOR_GROUP_NAME,
    CleanupPlan,
    HierarchyDiff,
    HierarchyPlan,
    cleanup_project_structure,
    diff_hierarchy,
    ensure_project_structure,
    is_canonical_name,
    plan_cleanup,
    plan_hierarchy,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_canonical_children_count_is_six():
    assert len(CANONICAL_CHILD_GROUPS) == 6


def test_canonical_children_are_unique():
    assert len(set(CANONICAL_CHILD_GROUPS)) == 6


def test_canonical_names_are_documented():
    expected = {
        NAVIGATION_GROUP_NAME, VISIBLE_SECTOR_GROUP_NAME,
        OVERLAYS_GROUP_NAME, SCIENCE_LAYERS_GROUP_NAME,
        MISSIONS_GROUP_NAME, DEBUG_GROUP_NAME,
    }
    assert set(CANONICAL_CHILD_GROUPS) == expected


def test_legacy_map_has_starfield():
    assert "UNAV_Starfield" in LEGACY_ROOT_TO_CANONICAL
    assert LEGACY_ROOT_TO_CANONICAL["UNAV_Starfield"] == VISIBLE_SECTOR_GROUP_NAME


def test_is_canonical_name():
    assert is_canonical_name(PROJECT_ROOT_NAME)
    for name in CANONICAL_CHILD_GROUPS:
        assert is_canonical_name(name)
    assert not is_canonical_name("UNAV_Starfield")  # legacy
    assert not is_canonical_name("Random")


# ---------------------------------------------------------------------------
# plan_hierarchy
# ---------------------------------------------------------------------------


def test_plan_hierarchy_returns_full_tree():
    plan = plan_hierarchy()
    assert isinstance(plan, HierarchyPlan)
    assert plan.root.name == PROJECT_ROOT_NAME
    assert plan.child_names() == list(CANONICAL_CHILD_GROUPS)


def test_plan_has_child():
    plan = plan_hierarchy()
    for name in CANONICAL_CHILD_GROUPS:
        assert plan.has_child(name)
    assert not plan.has_child("UNAV_Random")


# ---------------------------------------------------------------------------
# diff_hierarchy
# ---------------------------------------------------------------------------


def test_diff_blank_scene_lists_all_missing_children():
    diff = diff_hierarchy(
        existing_root_names=[],
        existing_project_children=(),
    )
    assert isinstance(diff, HierarchyDiff)
    assert set(diff.missing_children) == set(CANONICAL_CHILD_GROUPS)
    assert diff.legacy_to_migrate == []
    assert diff.is_clean() is False


def test_diff_complete_project_is_clean():
    diff = diff_hierarchy(
        existing_root_names=[PROJECT_ROOT_NAME],
        existing_project_children=tuple(CANONICAL_CHILD_GROUPS),
    )
    assert diff.is_clean()
    assert "matches" in diff.short_summary().lower()


def test_diff_legacy_starfield_is_flagged_for_migration():
    diff = diff_hierarchy(
        existing_root_names=["UNAV_Starfield", "UNAV_Project"],
        existing_project_children=tuple(CANONICAL_CHILD_GROUPS),
    )
    pairs = dict(diff.legacy_to_migrate)
    assert pairs["UNAV_Starfield"] == VISIBLE_SECTOR_GROUP_NAME


def test_diff_extra_unav_groups_logged_but_not_migrated():
    diff = diff_hierarchy(
        existing_root_names=["UNAV_Project", "UNAV_FutureExperiment"],
        existing_project_children=tuple(CANONICAL_CHILD_GROUPS),
    )
    assert "UNAV_FutureExperiment" in diff.extra_unav_groups
    assert diff.legacy_to_migrate == []


def test_diff_short_summary_describes_actions():
    diff = diff_hierarchy(
        existing_root_names=["UNAV_Starfield"],
        existing_project_children=(),
    )
    text = diff.short_summary()
    assert "create" in text
    assert "migrate" in text


# ---------------------------------------------------------------------------
# plan_cleanup
# ---------------------------------------------------------------------------


def test_plan_cleanup_keeps_canonical_children():
    plan = plan_cleanup(
        project_children=list(CANONICAL_CHILD_GROUPS),
    )
    assert set(plan.keep_groups) == set(CANONICAL_CHILD_GROUPS)
    assert plan.remove_groups == []


def test_plan_cleanup_removes_non_canonical_unav_groups():
    plan = plan_cleanup(
        project_children=list(CANONICAL_CHILD_GROUPS) + ["UNAV_Random"],
    )
    assert "UNAV_Random" in plan.remove_groups


def test_plan_cleanup_leaves_user_groups_alone():
    """Anything not UNAV-prefixed is artist content; the
    cleanup must not touch it."""
    plan = plan_cleanup(
        project_children=list(CANONICAL_CHILD_GROUPS) + ["MyCustomNull"],
    )
    assert "MyCustomNull" not in plan.remove_groups
    assert "MyCustomNull" not in plan.keep_groups


def test_plan_cleanup_flags_orphan_uids():
    plan = plan_cleanup(
        project_children=list(CANONICAL_CHILD_GROUPS),
        enabled_dataset_uids=["a", "b"],
        materialised_uids=["a", "b", "c", "d"],
    )
    assert set(plan.orphan_uids) == {"c", "d"}


def test_plan_cleanup_is_noop_when_clean():
    plan = plan_cleanup(
        project_children=list(CANONICAL_CHILD_GROUPS),
        enabled_dataset_uids=["a"],
        materialised_uids=["a"],
    )
    assert plan.is_noop()


def test_plan_cleanup_handles_empty_uids():
    plan = plan_cleanup(
        project_children=list(CANONICAL_CHILD_GROUPS),
        materialised_uids=["", "x"],
        enabled_dataset_uids=[],
    )
    # Empty uid is dropped; "x" is the only orphan.
    assert plan.orphan_uids == ["x"]


# ---------------------------------------------------------------------------
# C4D-bound builders raise outside the host
# ---------------------------------------------------------------------------


def test_ensure_project_structure_requires_c4d():
    with pytest.raises(RuntimeError):
        ensure_project_structure(None)  # type: ignore[arg-type]


def test_cleanup_project_structure_requires_c4d():
    with pytest.raises(RuntimeError):
        cleanup_project_structure(None, plan=CleanupPlan())  # type: ignore[arg-type]
