"""v3.4 reset-tools tests."""

from __future__ import annotations

import pytest

from core.reset_tools import (
    GeneratedObjectPlan,
    HierarchyRebuildPlan,
    ResetReport,
    UIStateSnapshot,
    clear_cache_references,
    clear_generated_objects_report,
    plan_clear_generated_objects,
    plan_rebuild_hierarchy,
    rebuild_hierarchy_report,
    reset_ui_state,
    reset_workspace_state,
)
from core.state_manager import (
    current_workspace,
    set_current_workspace,
)


# ---------------------------------------------------------------------------
# ResetReport
# ---------------------------------------------------------------------------


def test_report_short_summary_includes_counts():
    rep = ResetReport(
        operation="x", cleared=["a", "b"], skipped=["c"],
    )
    assert "cleared 2" in rep.short_summary()


def test_report_render_lists_each_action():
    rep = ResetReport(
        operation="x", cleared=["a"], skipped=["b"],
        warnings=["c"],
    )
    text = rep.render()
    assert "cleared: a" in text
    assert "skipped: b" in text
    assert "warning: c" in text


def test_report_is_clean_when_no_warnings():
    rep = ResetReport(operation="x", cleared=["a"])
    assert rep.is_clean()


def test_report_not_clean_with_warnings():
    rep = ResetReport(operation="x", warnings=["bad"])
    assert not rep.is_clean()


# ---------------------------------------------------------------------------
# reset_ui_state
# ---------------------------------------------------------------------------


def test_reset_ui_state_clears_populated_snapshot():
    state = UIStateSnapshot(
        selected_uid="x",
        selected_mission_id="m1",
        selected_step_id="s1",
        selected_dataset_name="ds",
        expanded_sections=["a", "b"],
        last_search_query="query",
        log_lines_count=100,
    )
    fresh, report = reset_ui_state(state)
    assert fresh.selected_uid == ""
    assert fresh.selected_mission_id == ""
    assert fresh.expanded_sections == []
    assert len(report.cleared) >= 6


def test_reset_ui_state_handles_none():
    fresh, report = reset_ui_state(None)
    assert isinstance(fresh, UIStateSnapshot)
    assert fresh.selected_uid == ""
    assert "no UI state" in report.skipped[0]


def test_reset_ui_state_idempotent_on_blank_snapshot():
    state = UIStateSnapshot()
    _, report = reset_ui_state(state)
    assert report.cleared == []


# ---------------------------------------------------------------------------
# reset_workspace_state
# ---------------------------------------------------------------------------


def test_reset_workspace_state_clears_active(monkeypatch):
    class FakeWorkspace:
        root = "/tmp/fake-ws"
    set_current_workspace(FakeWorkspace())
    try:
        report = reset_workspace_state()
    finally:
        set_current_workspace(None)
    assert any("active workspace" in c for c in report.cleared)


def test_reset_workspace_state_idempotent():
    set_current_workspace(None)
    report = reset_workspace_state()
    assert "no active workspace" in report.skipped[0]


def test_reset_workspace_state_does_not_touch_disk(tmp_path):
    """Confirm reset_workspace_state never deletes files
    on disk — it only drops the in-memory pointer."""
    class FakeWorkspace:
        root = str(tmp_path)
    set_current_workspace(FakeWorkspace())
    f = tmp_path / "marker.txt"
    f.write_text("kept", encoding="utf-8")
    try:
        reset_workspace_state()
    finally:
        set_current_workspace(None)
    assert f.read_text(encoding="utf-8") == "kept"


# ---------------------------------------------------------------------------
# plan_clear_generated_objects
# ---------------------------------------------------------------------------


def test_plan_clear_preserves_project_root():
    plan = plan_clear_generated_objects(
        existing_root_names=["UNAV_Project", "UNAV_Starfield"],
    )
    assert "UNAV_Project" in plan.preserve_groups
    assert "UNAV_Starfield" in plan.remove_root_names


def test_plan_clear_removes_legacy_roots():
    plan = plan_clear_generated_objects(
        existing_root_names=[
            "UNAV_Starfield", "UNAV_Overlays",
            "UNAV_ScienceLayers", "UNAV_DebugCone",
        ],
    )
    for name in (
        "UNAV_Starfield", "UNAV_Overlays",
        "UNAV_ScienceLayers", "UNAV_DebugCone",
    ):
        assert name in plan.remove_root_names


def test_plan_clear_leaves_user_content_alone():
    plan = plan_clear_generated_objects(
        existing_root_names=["MyArtistNull", "Camera", "Lights"],
    )
    assert plan.remove_root_names == []
    assert plan.preserve_groups == []


def test_plan_clear_notes_unfamiliar_unav_root():
    plan = plan_clear_generated_objects(
        existing_root_names=["UNAV_Experimental"],
    )
    assert plan.remove_root_names == []
    assert any(
        "UNAV_Experimental" in n for n in plan.notes
    )


def test_plan_clear_dedupes_repeat_names():
    plan = plan_clear_generated_objects(
        existing_root_names=["UNAV_Starfield", "UNAV_Starfield"],
    )
    assert plan.remove_root_names == ["UNAV_Starfield"]


def test_plan_clear_is_noop_for_blank_scene():
    plan = plan_clear_generated_objects(existing_root_names=[])
    assert plan.is_noop()


def test_clear_generated_objects_report_shape():
    rep = clear_generated_objects_report(
        existing_root_names=["UNAV_Starfield", "UNAV_Project"],
    )
    assert rep.operation == "clear_generated_objects"
    assert "UNAV_Starfield" in rep.cleared
    assert any("UNAV_Project" in s for s in rep.skipped)


# ---------------------------------------------------------------------------
# clear_cache_references
# ---------------------------------------------------------------------------


def test_clear_cache_references_runs_without_error():
    rep = clear_cache_references()
    assert rep.operation == "cache_references"
    # The cache + timing log should always be clearable
    # (their modules are part of the package).
    assert len(rep.cleared) >= 1


def test_clear_cache_references_clears_timing_log():
    from db.spatial_query import GLOBAL_QUERY_TIMING_LOG
    GLOBAL_QUERY_TIMING_LOG.record(
        candidate_rows=1, kept_rows=1,
        bbox_elapsed_ms=1.0, refine_elapsed_ms=1.0,
    )
    assert len(GLOBAL_QUERY_TIMING_LOG) > 0
    clear_cache_references()
    assert len(GLOBAL_QUERY_TIMING_LOG) == 0


# ---------------------------------------------------------------------------
# plan_rebuild_hierarchy
# ---------------------------------------------------------------------------


def test_plan_rebuild_handles_empty_scene():
    plan = plan_rebuild_hierarchy(
        existing_root_names=[],
    )
    assert plan.project_root_name == "UNAV_Project"
    assert len(plan.canonical_children) == 6
    assert len(plan.missing_children) == 6


def test_plan_rebuild_handles_complete_scene():
    from c4d_objects.scene_structure import (
        CANONICAL_CHILD_GROUPS, PROJECT_ROOT_NAME,
    )
    plan = plan_rebuild_hierarchy(
        existing_root_names=[PROJECT_ROOT_NAME],
        existing_project_children=tuple(CANONICAL_CHILD_GROUPS),
    )
    assert plan.is_noop()


def test_plan_rebuild_flags_legacy_roots_for_migration():
    from c4d_objects.scene_structure import (
        CANONICAL_CHILD_GROUPS, PROJECT_ROOT_NAME,
    )
    plan = plan_rebuild_hierarchy(
        existing_root_names=[
            PROJECT_ROOT_NAME, "UNAV_Starfield",
        ],
        existing_project_children=tuple(CANONICAL_CHILD_GROUPS),
    )
    pairs = dict(plan.legacy_to_migrate)
    assert "UNAV_Starfield" in pairs


def test_rebuild_hierarchy_report_shape():
    rep = rebuild_hierarchy_report(
        existing_root_names=[],
    )
    assert rep.operation == "rebuild_hierarchy"
    assert any("create" in c for c in rep.cleared)


# ---------------------------------------------------------------------------
# Plan summaries
# ---------------------------------------------------------------------------


def test_generated_object_plan_summary_when_empty():
    plan = GeneratedObjectPlan()
    assert "nothing to remove" in plan.short_summary()


def test_generated_object_plan_summary_with_actions():
    plan = GeneratedObjectPlan(
        remove_root_names=["UNAV_Starfield"],
    )
    assert "remove 1" in plan.short_summary()


def test_hierarchy_rebuild_summary_canonical():
    plan = HierarchyRebuildPlan()
    assert "canonical" in plan.short_summary()


def test_hierarchy_rebuild_summary_with_work():
    plan = HierarchyRebuildPlan(
        missing_children=["UNAV_Navigation"],
    )
    assert "create" in plan.short_summary()
