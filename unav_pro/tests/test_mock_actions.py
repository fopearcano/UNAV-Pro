"""Tests for action handlers. Runs without Cinema 4D — handlers that
require c4d should report the limitation cleanly rather than raise."""

from __future__ import annotations

from core import mock_actions


def test_load_dataset_default_loads_bundled_sample():
    out = mock_actions.load_dataset()
    assert "Load Dataset" in out
    # The bundled sample contains 100 objects.
    assert "100" in out


def test_load_dataset_missing_path_reports_cleanly():
    out = mock_actions.load_dataset("/path/that/does/not/exist.jsonl")
    assert "Load Dataset" in out
    assert "not found" in out


def test_create_navigation_null_without_c4d_reports_cleanly():
    out = mock_actions.create_navigation_null()
    assert "Create Navigation Null" in out
    assert "Cinema 4D not available" in out


def test_generate_point_cloud_without_c4d_reports_cleanly():
    # Outside Cinema 4D the handler must not raise; it should say so.
    out = mock_actions.generate_point_cloud()
    assert "Generate Point Cloud" in out
    assert "Cinema 4D not available" in out


def test_clear_scene_without_c4d_reports_cleanly():
    out = mock_actions.clear_scene()
    assert "Clear Scene" in out
    assert "Cinema 4D not available" in out


def test_apply_view_filter_without_c4d_reports_cleanly():
    out = mock_actions.apply_view_filter()
    assert "Apply View Filter" in out
    assert "Cinema 4D not available" in out


def test_regenerate_visible_field_without_c4d_reports_cleanly():
    out = mock_actions.regenerate_visible_field()
    assert "Regenerate Visible Field" in out
    assert "Cinema 4D not available" in out


def test_sync_visible_sector_without_c4d_reports_cleanly():
    out = mock_actions.sync_visible_sector()
    assert "Sync Visible Sector" in out
    assert "Cinema 4D not available" in out


def test_toggle_debug_cone_without_c4d_reports_cleanly():
    out = mock_actions.toggle_debug_cone(True)
    assert "Debug Cone" in out
    assert "Cinema 4D not available" in out


# ---------------------------------------------------------------------------
# _active_document helper — refactor regression guard
# ---------------------------------------------------------------------------


def test_active_document_outside_c4d_returns_clear_error():
    """The helper that every scene-touching action shares must report
    'Cinema 4D not available' uniformly."""
    doc, err = mock_actions._active_document("do something")
    assert doc is None
    assert err is not None
    assert "Cinema 4D not available" in err
    # The verb is interpolated so the error mentions what the action
    # was trying to do.
    assert "do something" in err.lower()


def test_save_unav_state_without_c4d_reports_cleanly():
    out = mock_actions.save_unav_state()
    assert "Save UNAV State" in out
    assert "Cinema 4D not available" in out


def test_load_unav_state_without_c4d_reports_cleanly():
    out = mock_actions.load_unav_state()
    assert "Load UNAV State" in out
    assert "Cinema 4D not available" in out
