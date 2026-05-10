"""v3.5 issue-report tests."""

from __future__ import annotations

import json
import os

import pytest

from core.issue_report import (
    DEFAULT_LOG_TAIL_LINES,
    ISSUE_REPORT_SCHEMA_VERSION,
    MAX_LOG_BYTES,
    DatasetStatus,
    HealthSnapshot,
    HostEnvironment,
    IssueReport,
    WorkspaceStatus,
    build_issue_report,
    probe_dataset_status,
    probe_health_snapshot,
    probe_host_environment,
    probe_workspace_status,
    trim_log_tail,
    write_issue_report,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_schema_version_is_one():
    assert ISSUE_REPORT_SCHEMA_VERSION == 1


def test_default_log_tail_is_reasonable():
    assert 10 <= DEFAULT_LOG_TAIL_LINES <= 1000


def test_max_log_bytes_capped():
    assert MAX_LOG_BYTES <= 256 * 1024


# ---------------------------------------------------------------------------
# trim_log_tail
# ---------------------------------------------------------------------------


def test_trim_log_tail_returns_last_n_lines():
    out = trim_log_tail(["a", "b", "c", "d", "e"], max_lines=3)
    assert out == ["c", "d", "e"]


def test_trim_log_tail_handles_empty():
    assert trim_log_tail([]) == []


def test_trim_log_tail_caps_total_bytes():
    big = ["x" * 1000 for _ in range(50)]
    out = trim_log_tail(big, max_lines=50, max_bytes=2500)
    joined = "\n".join(out).encode("utf-8")
    assert len(joined) <= 2500


def test_trim_log_tail_no_byte_cap_when_zero():
    big = ["xxxxx" for _ in range(20)]
    out = trim_log_tail(big, max_lines=20, max_bytes=0)
    assert len(out) == 20


# ---------------------------------------------------------------------------
# Probes (defensive)
# ---------------------------------------------------------------------------


def test_probe_host_environment_returns_dataclass():
    env = probe_host_environment()
    assert isinstance(env, HostEnvironment)
    assert env.python_version


def test_probe_workspace_status_no_active_workspace():
    """Outside any active workspace, the probe reports
    inactive without raising."""
    from core.state_manager import set_current_workspace
    set_current_workspace(None)
    status = probe_workspace_status()
    assert isinstance(status, WorkspaceStatus)
    assert status.active is False


def test_probe_workspace_status_with_active_workspace(tmp_path):
    from core.state_manager import set_current_workspace
    from project import create_workspace
    ws = create_workspace(str(tmp_path / "ws"))
    set_current_workspace(ws)
    try:
        status = probe_workspace_status()
    finally:
        set_current_workspace(None)
    assert status.active is True
    assert status.intact is True


def test_probe_dataset_status_returns_record():
    status = probe_dataset_status()
    assert isinstance(status, DatasetStatus)


def test_probe_health_snapshot_returns_text():
    snap = probe_health_snapshot()
    assert isinstance(snap, HealthSnapshot)


# ---------------------------------------------------------------------------
# render() outputs
# ---------------------------------------------------------------------------


def test_host_env_render_includes_python_version():
    env = HostEnvironment(
        plugin_version="3.5.0",
        plugin_codename="Public Alpha",
        python_version="3.11.5",
        platform_string="macOS-15.0",
        machine="arm64",
        inside_c4d=False,
    )
    text = env.render()
    assert "3.11.5" in text
    assert "Public Alpha" in text
    assert "not running" in text


def test_workspace_status_render_inactive():
    text = WorkspaceStatus().render()
    assert "not active" in text


def test_workspace_status_render_intact():
    text = WorkspaceStatus(
        active=True, root="/tmp/ws", intact=True, project_name="Voyager",
    ).render()
    assert "intact" in text
    assert "Voyager" in text


def test_workspace_status_render_broken():
    text = WorkspaceStatus(
        active=True, root="/tmp/ws", intact=False,
    ).render()
    assert "missing" in text


def test_dataset_status_render_empty():
    text = DatasetStatus().render()
    assert "empty" in text


def test_dataset_status_render_with_data():
    text = DatasetStatus(total=3, enabled=2, indexed=1).render()
    assert "2/3" in text
    assert "1 indexed" in text


# ---------------------------------------------------------------------------
# build_issue_report
# ---------------------------------------------------------------------------


def test_build_report_returns_markdown_doc():
    report = build_issue_report(
        host_env=HostEnvironment(
            plugin_version="3.5.0",
            python_version="3.11",
            platform_string="Linux",
        ),
        workspace_status=WorkspaceStatus(),
        dataset_status=DatasetStatus(),
        health_snapshot=HealthSnapshot(overall="Health: OK (14)"),
        log_tail=["line one", "line two"],
    )
    assert isinstance(report, IssueReport)
    body = report.to_markdown()
    assert "# UNAV Pro Issue Report" in body
    assert "Environment" in body
    assert "State" in body
    assert "Health check" in body
    assert "Recent status log" in body
    assert "line one" in body
    assert "line two" in body
    assert "Boundary reminder" in body


def test_build_report_includes_user_summary_when_provided():
    report = build_issue_report(
        user_summary="Crashes on Sync Visible Sector",
        host_env=HostEnvironment(),
    )
    assert "Crashes on Sync Visible Sector" in report.body


def test_build_report_handles_empty_log_tail():
    report = build_issue_report(
        host_env=HostEnvironment(),
        workspace_status=WorkspaceStatus(),
        dataset_status=DatasetStatus(),
        health_snapshot=HealthSnapshot(),
        log_tail=[],
    )
    assert "no log lines captured" in report.body


def test_build_report_handles_no_health_snapshot():
    report = build_issue_report(
        host_env=HostEnvironment(),
        workspace_status=WorkspaceStatus(),
        dataset_status=DatasetStatus(),
        health_snapshot=HealthSnapshot(),
    )
    assert "no health check captured" in report.body


def test_build_report_stamps_timestamp():
    report = build_issue_report(
        host_env=HostEnvironment(),
    )
    assert report.generated_at_iso
    # ISO8601-ish: contains a 'T' separator + 'Z' suffix.
    assert "T" in report.generated_at_iso


def test_build_report_does_not_include_paths_outside_safe_set():
    """The bundle must only mention the paths it explicitly
    surfaces — never random scene-file paths."""
    report = build_issue_report(
        host_env=HostEnvironment(),
        workspace_status=WorkspaceStatus(
            active=True, root="/safe/workspace", intact=True,
        ),
        log_tail=["status: ok"],
    )
    # Allowed mentions: workspace root + cwd-style log lines.
    # Reject obviously sensitive substrings.
    body_lower = report.body.lower()
    assert "passwd" not in body_lower
    assert "credentials" not in body_lower


def test_build_report_includes_boundary_reminder():
    report = build_issue_report(host_env=HostEnvironment())
    assert "single-threaded" in report.body
    assert "ROADMAP.md" in report.body


# ---------------------------------------------------------------------------
# write_issue_report
# ---------------------------------------------------------------------------


def test_write_issue_report_atomic(tmp_path):
    report = build_issue_report(host_env=HostEnvironment())
    path = tmp_path / "report.md"
    written = write_issue_report(report, str(path))
    assert os.path.isfile(written)
    contents = path.read_text(encoding="utf-8")
    assert contents == report.body
    # No leftover temp file.
    assert not (tmp_path / "report.md.tmp").exists()


def test_write_issue_report_creates_parent_dir(tmp_path):
    report = build_issue_report(host_env=HostEnvironment())
    path = tmp_path / "subdir" / "report.md"
    written = write_issue_report(report, str(path))
    assert os.path.isfile(written)


# ---------------------------------------------------------------------------
# IssueReport
# ---------------------------------------------------------------------------


def test_issue_report_to_markdown_alias_matches_body():
    report = IssueReport(body="hello\n")
    assert report.to_markdown() == "hello\n"
