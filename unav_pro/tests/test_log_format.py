"""log_format tests.

Pure-Python helper tests for the fix introduced by
``fix-log-newline-formatting``: every log entry must
render on its own line and every multi-line message
must split into one buffer element per physical line.
"""

from __future__ import annotations

import re

import pytest

from core.log_format import (
    DEFAULT_LOG_BUFFER_LINES,
    DEFAULT_LOG_LEVEL,
    KNOWN_LOG_LEVELS,
    LogBuffer,
    format_log_entry,
    normalize_line_endings,
    utc_timestamp,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_default_buffer_lines_reasonable():
    assert 100 <= DEFAULT_LOG_BUFFER_LINES <= 10_000


def test_default_level_constant():
    assert DEFAULT_LOG_LEVEL == "INFO"


def test_known_log_levels_present():
    for token in ("DEBUG", "INFO", "WARNING", "ERROR"):
        assert token in KNOWN_LOG_LEVELS


# ---------------------------------------------------------------------------
# normalize_line_endings
# ---------------------------------------------------------------------------


def test_normalize_crlf_to_lf():
    assert normalize_line_endings("a\r\nb") == "a\nb"


def test_normalize_lone_cr_to_lf():
    assert normalize_line_endings("a\rb") == "a\nb"


def test_normalize_already_lf_unchanged():
    assert normalize_line_endings("a\nb") == "a\nb"


def test_normalize_handles_none():
    assert normalize_line_endings(None) == ""


def test_normalize_coerces_non_string():
    assert normalize_line_endings(42) == "42"


# ---------------------------------------------------------------------------
# format_log_entry
# ---------------------------------------------------------------------------


def test_format_single_line_no_level():
    out = format_log_entry("hello")
    assert out == ["hello"]


def test_format_with_level_prefix():
    out = format_log_entry("hello", level="info")
    assert out == ["[INFO] hello"]


def test_format_with_timestamp_and_level():
    out = format_log_entry("hello", level="INFO", timestamp="12:34:56")
    assert out == ["12:34:56 [INFO] hello"]


def test_format_with_timestamp_only():
    out = format_log_entry("hello", timestamp="12:34:56")
    assert out == ["12:34:56 hello"]


def test_format_multiline_splits_lines():
    out = format_log_entry("first\nsecond\nthird")
    assert out == ["first", "second", "third"]


def test_format_multiline_with_level_prefixes_each_line():
    out = format_log_entry("first\nsecond", level="ERROR")
    assert out == ["[ERROR] first", "[ERROR] second"]


def test_format_normalises_crlf_before_splitting():
    out = format_log_entry("first\r\nsecond\r\nthird")
    assert out == ["first", "second", "third"]


def test_format_strips_leading_and_trailing_newlines():
    """Don't produce phantom blank entries from
    incoming text that's wrapped in newlines."""
    out = format_log_entry("\n\nhello\n\n")
    assert out == ["hello"]


def test_format_empty_message_returns_empty_list():
    assert format_log_entry("") == []
    assert format_log_entry("   \n\n") == []
    assert format_log_entry(None) == []


def test_format_level_normalised_to_uppercase():
    out = format_log_entry("x", level="warning")
    assert out == ["[WARNING] x"]


def test_format_level_whitespace_only_dropped():
    out = format_log_entry("x", level="   ")
    assert out == ["x"]


# ---------------------------------------------------------------------------
# LogBuffer — basic
# ---------------------------------------------------------------------------


def test_buffer_default_state_empty():
    buf = LogBuffer()
    assert len(buf) == 0
    assert buf.render() == ""
    assert buf.render_for_export() == ""


def test_buffer_rejects_zero_max_lines():
    with pytest.raises(ValueError):
        LogBuffer(max_lines=0)


def test_buffer_append_single_line():
    buf = LogBuffer()
    added = buf.append("hello")
    assert added == 1
    assert buf.snapshot() == ["hello"]


def test_buffer_append_returns_added_count():
    buf = LogBuffer()
    assert buf.append("first") == 1
    assert buf.append("a\nb\nc") == 3
    assert buf.append("") == 0


def test_buffer_append_with_level():
    buf = LogBuffer()
    buf.append("hello", level="WARNING")
    assert buf.snapshot() == ["[WARNING] hello"]


def test_buffer_clear():
    buf = LogBuffer()
    buf.append("a")
    buf.append("b")
    buf.clear()
    assert len(buf) == 0
    assert buf.render() == ""


# ---------------------------------------------------------------------------
# LogBuffer — newline preservation (the bug under fix)
# ---------------------------------------------------------------------------


def test_repeated_appends_keep_entries_on_separate_lines():
    """The core regression test: two appends in a row
    must NOT collapse into a single line."""
    buf = LogBuffer()
    buf.append("[INFO] Loaded dataset")
    buf.append("[INFO] Created navigator")
    buf.append("[WARNING] Missing metadata")
    rendered = buf.render()
    # Each entry on its own line in the rendered output.
    lines = rendered.rstrip("\n").split("\n")
    assert lines == [
        "[INFO] Loaded dataset",
        "[INFO] Created navigator",
        "[WARNING] Missing metadata",
    ]
    # Crucially, the rendered text contains explicit "\n"
    # separators between every pair of entries.
    assert rendered.count("\n") == 3   # 2 separators + trailing


def test_render_ends_with_trailing_newline():
    buf = LogBuffer()
    buf.append("hello")
    assert buf.render().endswith("\n")


def test_render_for_export_no_trailing_blank_line():
    buf = LogBuffer()
    buf.append("a")
    buf.append("b")
    text = buf.render_for_export()
    assert text == "a\nb"
    assert not text.endswith("\n")


def test_multiline_message_stays_multiline_in_render():
    buf = LogBuffer()
    buf.append("first\nsecond", level="ERROR")
    rendered = buf.render()
    assert "[ERROR] first" in rendered
    assert "[ERROR] second" in rendered
    # The continuation line keeps its own newline.
    assert rendered.count("\n") == 2   # 1 separator + trailing


def test_append_normalises_crlf():
    buf = LogBuffer()
    buf.append("a\r\nb\r\nc")
    assert buf.snapshot() == ["a", "b", "c"]


def test_repeated_appends_dont_duplicate_separators():
    """A rendered buffer should never contain ``\\n\\n``
    between entries (which would indicate a duplicated
    separator)."""
    buf = LogBuffer()
    for i in range(10):
        buf.append(f"entry {i}")
    rendered = buf.render()
    # Allow one trailing \n; any "\n\n" in the body is
    # a duplication bug.
    body = rendered.rstrip("\n")
    assert "\n\n" not in body


# ---------------------------------------------------------------------------
# LogBuffer — bounded capacity
# ---------------------------------------------------------------------------


def test_buffer_caps_at_max_lines():
    buf = LogBuffer(max_lines=5)
    for i in range(20):
        buf.append(f"entry {i}")
    assert len(buf) == 5
    # The kept lines are the most recent.
    assert buf.snapshot() == [f"entry {i}" for i in range(15, 20)]


def test_buffer_cap_one():
    buf = LogBuffer(max_lines=1)
    buf.append("a")
    buf.append("b")
    assert buf.snapshot() == ["b"]


def test_buffer_default_cap_documented():
    """The buffer's max_lines defaults to the
    documented constant so a tweak there is visible
    in every test."""
    buf = LogBuffer()
    assert buf.max_lines == DEFAULT_LOG_BUFFER_LINES


# ---------------------------------------------------------------------------
# LogBuffer — determinism
# ---------------------------------------------------------------------------


def test_buffer_render_deterministic():
    a = LogBuffer()
    b = LogBuffer()
    for msg in ("alpha", "beta", "gamma"):
        a.append(msg, level="INFO")
        b.append(msg, level="INFO")
    assert a.render() == b.render()


def test_buffer_snapshot_is_a_copy():
    buf = LogBuffer()
    buf.append("a")
    snap = buf.snapshot()
    snap.clear()
    assert len(buf) == 1


# ---------------------------------------------------------------------------
# utc_timestamp
# ---------------------------------------------------------------------------


def test_utc_timestamp_shape():
    ts = utc_timestamp()
    assert re.match(r"^\d{2}:\d{2}:\d{2}$", ts), ts


# ---------------------------------------------------------------------------
# Issue-bundle integration: snapshot is per-line
# ---------------------------------------------------------------------------


def test_snapshot_compatible_with_issue_report_log_tail():
    """The v3.5 issue-report bundler takes
    ``log_tail: Sequence[str]`` — one entry per line.
    LogBuffer.snapshot() returns exactly that
    shape."""
    from core.issue_report import trim_log_tail
    buf = LogBuffer()
    buf.append("[INFO] one")
    buf.append("[WARNING] two")
    buf.append("multi-line\ntrace", level="ERROR")
    trimmed = trim_log_tail(buf.snapshot(), max_lines=10)
    # Every element is a single physical line.
    assert all("\n" not in line for line in trimmed)
    assert "[INFO] one" in trimmed
    assert "[WARNING] two" in trimmed
    assert "[ERROR] multi-line" in trimmed
    assert "[ERROR] trace" in trimmed
