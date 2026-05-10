"""v3.45 scene-lifecycle tests."""

from __future__ import annotations

import pytest

from c4d_objects.lifecycle import (
    VALID_EVENTS,
    DocumentScope,
    LifecycleActionPlan,
    LifecycleEvent,
    MultiDocumentReport,
    build_multi_document_report,
    plan_for_event,
)


# ---------------------------------------------------------------------------
# LifecycleEvent
# ---------------------------------------------------------------------------


def test_valid_events_include_all_five():
    expected = {
        LifecycleEvent.OPENED, LifecycleEvent.CLOSED,
        LifecycleEvent.SWITCHED, LifecycleEvent.RELOADED,
        LifecycleEvent.SAVED,
    }
    assert expected == set(VALID_EVENTS)


def test_event_str_value():
    assert LifecycleEvent.OPENED.value == "opened"
    assert LifecycleEvent.CLOSED.value == "closed"
    assert LifecycleEvent.SWITCHED.value == "switched"


# ---------------------------------------------------------------------------
# plan_for_event
# ---------------------------------------------------------------------------


def test_opened_event_full_rebind():
    plan = plan_for_event(LifecycleEvent.OPENED)
    assert plan.rebind_state_manager
    assert plan.rediscover_scene_objects
    assert plan.reset_caches
    assert not plan.is_noop()


def test_opened_with_workspace_reloads_workspace():
    plan = plan_for_event(LifecycleEvent.OPENED, workspace_active=True)
    assert plan.reload_workspace is True


def test_opened_without_workspace_skips_reload():
    plan = plan_for_event(LifecycleEvent.OPENED, workspace_active=False)
    assert plan.reload_workspace is False


def test_closed_event_flushes_workspace():
    plan = plan_for_event(LifecycleEvent.CLOSED, workspace_active=True)
    assert plan.flush_workspace
    assert plan.rebind_state_manager
    assert plan.reset_caches


def test_closed_without_workspace_no_flush():
    plan = plan_for_event(LifecycleEvent.CLOSED)
    assert not plan.flush_workspace


def test_switched_event_rebinds():
    plan = plan_for_event(LifecycleEvent.SWITCHED)
    assert plan.rebind_state_manager
    assert plan.reset_caches


def test_switched_with_multi_doc_rediscovers():
    plan = plan_for_event(
        LifecycleEvent.SWITCHED, multi_document_open=True,
    )
    assert plan.rediscover_scene_objects


def test_switched_single_doc_skips_rediscover():
    plan = plan_for_event(
        LifecycleEvent.SWITCHED, multi_document_open=False,
    )
    assert plan.rediscover_scene_objects is False


def test_reloaded_event_full_rebind():
    plan = plan_for_event(LifecycleEvent.RELOADED, workspace_active=True)
    assert plan.rebind_state_manager
    assert plan.reload_workspace
    assert plan.rediscover_scene_objects
    assert plan.reset_caches


def test_saved_event_is_minimal():
    plan = plan_for_event(LifecycleEvent.SAVED)
    assert plan.is_noop()


def test_saved_with_workspace_emits_note():
    plan = plan_for_event(LifecycleEvent.SAVED, workspace_active=True)
    assert any("workspace" in n for n in plan.notes)


# ---------------------------------------------------------------------------
# Plan summary
# ---------------------------------------------------------------------------


def test_plan_short_summary_describes_event():
    plan = plan_for_event(LifecycleEvent.OPENED)
    assert "[opened]" in plan.short_summary()


def test_plan_short_summary_no_op():
    plan = LifecycleActionPlan(event=LifecycleEvent.SAVED)
    assert "no-op" in plan.short_summary()


def test_plan_short_summary_lists_actions():
    plan = plan_for_event(LifecycleEvent.OPENED, workspace_active=True)
    text = plan.short_summary()
    assert "rebind" in text
    assert "workspace" in text


# ---------------------------------------------------------------------------
# DocumentScope
# ---------------------------------------------------------------------------


def test_document_scope_short_summary_marks_active():
    d = DocumentScope(
        doc_id="x", title="Voyager", is_active=True, has_unav_state=True,
    )
    s = d.short_summary()
    assert s.startswith("*")
    assert "Voyager" in s
    assert "[UNAV]" in s


def test_document_scope_inactive_no_marker():
    d = DocumentScope(doc_id="x", title="X", is_active=False)
    s = d.short_summary()
    assert s.startswith(" ")


# ---------------------------------------------------------------------------
# MultiDocumentReport
# ---------------------------------------------------------------------------


def test_build_report_marks_active():
    docs = [
        DocumentScope(doc_id="a", title="A", is_active=True),
        DocumentScope(doc_id="b", title="B", is_active=False),
    ]
    rep = build_multi_document_report(docs)
    assert rep.count == 2
    assert rep.active_doc_id == "a"
    assert rep.active().doc_id == "a"


def test_build_report_dedupes_doc_ids():
    docs = [
        DocumentScope(doc_id="a", title="A"),
        DocumentScope(doc_id="a", title="A duplicate"),
    ]
    rep = build_multi_document_report(docs)
    assert rep.count == 1


def test_build_report_drops_empty_doc_ids():
    docs = [
        DocumentScope(doc_id="", title="empty"),
        DocumentScope(doc_id="a", title="A"),
    ]
    rep = build_multi_document_report(docs)
    assert rep.count == 1


def test_report_short_summary_no_docs():
    rep = MultiDocumentReport()
    assert "no documents" in rep.short_summary()


def test_report_short_summary_with_docs():
    docs = [DocumentScope(doc_id="a", title="A", is_active=True)]
    rep = build_multi_document_report(docs)
    assert "1 document" in rep.short_summary()


def test_report_render_lists_each_document():
    docs = [
        DocumentScope(doc_id="a", title="A", is_active=True),
        DocumentScope(doc_id="b", title="B"),
    ]
    rep = build_multi_document_report(docs)
    text = rep.render()
    assert "A" in text
    assert "B" in text
