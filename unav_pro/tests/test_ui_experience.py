"""ui-experience-polish tests.

Pure-Python coverage for the shared UI foundation introduced by the
UI-experience pass: status/log/warning formatting, the canonical tab
registry (order + uniqueness), the Home dashboard composition, and the
destructive-action confirmation registry. No Cinema 4D needed.
"""

from __future__ import annotations

import pytest

from ui.ui_helpers import (
    Status,
    append_log_line,
    compact_separator,
    format_section_title,
    format_status_label,
    format_warning_box,
    normalize_button_label,
    status_prefix,
)
from ui.tab_registry import (
    TAB_ORDER,
    get_tab,
    index_of,
    ordered_tabs,
    tab_ids,
    tab_keys,
    tab_titles,
    validate_tabs,
)
from ui.home_dashboard import (
    HOME_ACTIONS,
    DashboardState,
    build_dashboard_text,
)
from ui.confirmations import (
    DESTRUCTIVE_ACTIONS,
    confirmation_message,
    confirmation_title,
    get_action,
    is_destructive,
)


# ---------------------------------------------------------------------------
# Status formatting
# ---------------------------------------------------------------------------


def test_status_prefix_known_tokens():
    assert status_prefix(Status.OK) == "[OK]"
    assert status_prefix(Status.WARN) == "[WARN]"
    assert status_prefix(Status.ERROR) == "[ERROR]"
    assert status_prefix(Status.MISSING) == "[MISSING]"
    assert status_prefix(Status.DISABLED) == "[DISABLED]"


def test_status_prefix_accepts_strings_case_insensitive():
    assert status_prefix("ok") == "[OK]"
    assert status_prefix("Warning") == "[WARN]"  # alias
    assert status_prefix("WARN") == "[WARN]"


def test_status_prefix_unknown_falls_back_to_info():
    assert status_prefix("banana") == "[INFO]"


def test_format_status_label_with_message():
    assert format_status_label(Status.OK, "ready") == "[OK] ready"
    assert format_status_label("error", "boom") == "[ERROR] boom"


def test_format_status_label_blank_message_is_bare_prefix():
    assert format_status_label(Status.WARN, "   ") == "[WARN]"
    assert format_status_label(Status.OK, "") == "[OK]"


def test_format_section_title_trims():
    assert format_section_title("  Datasets  ") == "Datasets"


def test_compact_separator_bounded():
    assert compact_separator(10) == "-" * 10
    assert len(compact_separator(9999)) == 200  # capped
    assert len(compact_separator(0)) == 1       # floored
    assert compact_separator(5, "=") == "====="


def test_format_warning_box_structure():
    box = format_warning_box("catalog missing")
    lines = box.split("\n")
    assert lines[0].startswith("[WARN]")
    assert lines[1] == "catalog missing"
    assert set(lines[2]) == {"-"}


def test_format_warning_box_empty_message():
    box = format_warning_box("")
    assert "(no detail)" in box


# ---------------------------------------------------------------------------
# Button-label normalisation
# ---------------------------------------------------------------------------


def test_normalize_button_collapses_spaces():
    assert normalize_button_label("  Sync   Visible  Sector ") == "Sync Visible Sector"


def test_normalize_button_ellipsis():
    assert normalize_button_label("Browse...") == "Browse…"
    assert normalize_button_label("Open…") == "Open…"


def test_normalize_button_empty():
    assert normalize_button_label("") == ""
    assert normalize_button_label(None) == ""


# ---------------------------------------------------------------------------
# append_log_line passthrough
# ---------------------------------------------------------------------------


def test_append_log_line_uses_log_buffer():
    from core.log_format import LogBuffer
    buf = LogBuffer()
    added = append_log_line(buf, "hello", level="WARNING")
    assert added == 1
    assert buf.snapshot() == ["[WARNING] hello"]


def test_append_log_line_multiline_counts_physical_lines():
    from core.log_format import LogBuffer
    buf = LogBuffer()
    assert append_log_line(buf, "a\nb\nc") == 3


# ---------------------------------------------------------------------------
# Tab registry
# ---------------------------------------------------------------------------


def test_tab_order_is_the_workflow_order():
    assert tab_keys() == [
        "home", "dataset", "navigator", "search", "voyage",
        "animation", "overlays", "tools", "diagnostics", "settings",
    ]


def test_tab_registry_validates_clean():
    report = validate_tabs()
    assert report["ok"], report
    assert report["count"] == 10
    assert report["duplicate_keys"] == []
    assert report["duplicate_ids"] == []
    assert report["duplicate_titles"] == []
    assert report["blank"] == []


def test_tab_ids_unique():
    ids = tab_ids()
    assert len(ids) == len(set(ids))


def test_tab_titles_unique():
    titles = tab_titles()
    assert len(titles) == len(set(titles))


def test_every_tab_has_summary():
    for t in TAB_ORDER:
        assert t.summary.strip()
        assert t.title.strip()
        assert t.key.strip()


def test_get_tab_and_index():
    assert get_tab("home").title == "Home"
    assert index_of("home") == 0
    assert index_of("settings") == 9
    assert index_of("nope") == -1


def test_get_tab_unknown_raises():
    with pytest.raises(KeyError):
        get_tab("does-not-exist")


def test_ordered_tabs_is_a_copy():
    a = ordered_tabs()
    a.clear()
    assert len(ordered_tabs()) == 10


def test_settings_marked_advanced():
    assert get_tab("settings").advanced is True
    assert get_tab("home").advanced is False


# ---------------------------------------------------------------------------
# Home dashboard
# ---------------------------------------------------------------------------


def test_dashboard_empty_state_is_safe():
    text = build_dashboard_text(DashboardState())
    # No exceptions, and missing things are flagged rather than blank.
    assert "[MISSING] Workspace" in text
    assert "[MISSING] Datasets" in text
    assert "[MISSING] Navigator" in text
    assert "Visible sector: not synced" in text
    assert "Health check: not run" in text


def test_dashboard_full_state():
    state = DashboardState(
        plugin_version="3.9.0", codename="Integrated External Tools",
        workspace_path="/proj/ws", dataset_count=3, enabled_dataset_count=2,
        navigator_present=True, navigator_name="Nav",
        visible_sector_synced=True, visible_sector_count=500,
        active_mission="Tour A", health_ok=True, health_summary="6/6 ok",
    )
    text = build_dashboard_text(state)
    assert "[OK] UNAV Pro v3.9.0 — Integrated External Tools" in text
    assert "[OK] Workspace: /proj/ws" in text
    assert "2 enabled of 3 registered" in text
    assert "[OK] Navigator: Nav" in text
    assert "Visible sector: 500 objects" in text
    assert "[OK] Mission: Tour A" in text
    assert "[OK] Health: 6/6 ok" in text


def test_dashboard_health_failure():
    text = build_dashboard_text(DashboardState(health_ok=False))
    assert "[ERROR] Health: issues found" in text


def test_dashboard_datasets_registered_but_none_enabled_warns():
    text = build_dashboard_text(
        DashboardState(dataset_count=2, enabled_dataset_count=0),
    )
    assert "[WARN] Datasets: 0 enabled of 2 registered" in text


def test_home_actions_set():
    keys = [k for k, _label in HOME_ACTIONS]
    assert keys == [
        "create_navigator", "register_dataset", "sync_sector",
        "open_sample", "run_health_check",
    ]


# ---------------------------------------------------------------------------
# Confirmations
# ---------------------------------------------------------------------------


def test_destructive_actions_present():
    for aid in (
        "clear_scene", "reset_workspace", "reset_preferences",
        "delete_mission", "delete_dataset", "clear_route",
        "clear_keyframes", "clear_cache_references",
    ):
        assert is_destructive(aid), aid


def test_confirmation_message_for_known_action():
    msg = confirmation_message("delete_mission")
    assert "mission" in msg.lower()
    assert confirmation_title("delete_mission") == "Delete Mission"


def test_confirmation_message_unknown_is_generic_but_guards():
    # Unknown ids still produce a cautionary prompt so nothing slips
    # through unguarded.
    msg = confirmation_message("brand_new_thing")
    assert "cannot be undone" in msg.lower()
    assert not is_destructive("brand_new_thing")


def test_get_action_roundtrip():
    a = get_action("clear_scene")
    assert a is not None
    assert a.title == "Clear Scene"
    assert get_action("nope") is None


def test_delete_dataset_message_reassures_file_untouched():
    msg = confirmation_message("delete_dataset")
    assert "left untouched" in msg.lower() or "untouched" in msg.lower()
