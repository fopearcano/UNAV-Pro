"""v3.45 document-summary tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import pytest

from c4d_objects.object_manager_view import (
    ObjectNode,
    count_unav_objects,
)
from c4d_objects.scene_structure import (
    NAVIGATION_GROUP_NAME,
    OVERLAYS_GROUP_NAME,
    PROJECT_ROOT_NAME,
)
from core.diagnostics import (
    DocumentSummary,
    build_document_summary,
)


# ---------------------------------------------------------------------------
# Empty summary
# ---------------------------------------------------------------------------


def test_empty_summary_short_text():
    summary = build_document_summary()
    text = summary.short_summary()
    assert "no UNAV root" in text


def test_empty_summary_render():
    summary = build_document_summary()
    text = summary.render()
    assert "Document" in text
    assert "missing" in text


# ---------------------------------------------------------------------------
# With object counts
# ---------------------------------------------------------------------------


def test_summary_with_counts_reports_categories():
    project = ObjectNode(PROJECT_ROOT_NAME, children=[
        ObjectNode(NAVIGATION_GROUP_NAME),
        ObjectNode(OVERLAYS_GROUP_NAME, children=[
            ObjectNode("UNAV_Overlay_grid"),
        ]),
    ])
    counts = count_unav_objects([project])
    summary = build_document_summary(
        document_title="Voyager",
        object_counts=counts,
    )
    assert summary.project_root_present
    assert summary.total_unav_objects > 0
    text = summary.render()
    assert "Voyager" in text
    assert "navigation" in text
    assert "overlays" in text


def test_summary_short_summary_includes_count():
    project = ObjectNode(PROJECT_ROOT_NAME, children=[
        ObjectNode(NAVIGATION_GROUP_NAME),
    ])
    counts = count_unav_objects([project])
    summary = build_document_summary(
        document_title="X",
        object_counts=counts,
    )
    s = summary.short_summary()
    assert "UNAV object" in s


# ---------------------------------------------------------------------------
# With active mission
# ---------------------------------------------------------------------------


@dataclass
class FakeMission:
    title: str = "FakeMission"
    waypoints: List[object] = field(default_factory=list)


def test_summary_includes_active_mission_title():
    mission = FakeMission(
        title="Voyager Tour",
        waypoints=[1, 2, 3],
    )
    summary = build_document_summary(
        document_title="X",
        active_mission=mission,
    )
    text = summary.render()
    assert "Voyager Tour" in text
    assert "3 waypoint" in text


def test_summary_handles_none_mission():
    summary = build_document_summary(active_mission=None)
    assert summary.active_mission_title == ""
    assert summary.active_mission_waypoint_count == 0


def test_summary_handles_mission_without_waypoints_attr():
    """Defensive: a duck-typed mission missing
    `waypoints` shouldn't crash the summary."""
    @dataclass
    class WeirdMission:
        title: str = "x"
    summary = build_document_summary(
        active_mission=WeirdMission(),
    )
    assert summary.active_mission_title == "x"


# ---------------------------------------------------------------------------
# With workspace
# ---------------------------------------------------------------------------


@dataclass
class FakeWorkspace:
    root: str = "/tmp/ws"


def test_summary_includes_workspace_root():
    summary = build_document_summary(
        document_title="X",
        workspace=FakeWorkspace(root="/path/to/ws"),
    )
    assert summary.workspace_root == "/path/to/ws"
    assert "ws" in summary.render()


# ---------------------------------------------------------------------------
# Defensive surface
# ---------------------------------------------------------------------------


def test_summary_robust_against_minimal_inputs():
    summary = build_document_summary(
        document_title="",
        object_counts=None,
        active_mission=None,
        workspace=None,
    )
    assert isinstance(summary, DocumentSummary)
    assert summary.short_summary()
