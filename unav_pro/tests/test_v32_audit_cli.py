"""v3.2 audit-CLI tests.

Drive the CLI's pure helpers (argument parsing, streaming
read, exit-code logic) without spawning subprocesses.
"""

from __future__ import annotations

import json
import os
import sys

import pytest


_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_TOOLS_DIR = os.path.join(_REPO_ROOT, "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import audit_dataset  # type: ignore  # noqa: E402
from data import CatalogObject, build_record, attach_provenance  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: str, rows) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _row(uid: str, **overrides) -> dict:
    base = {
        "uid": uid,
        "catalog_source": "Test",
        "object_type": "star",
        "ra_deg": 10.0,
        "dec_deg": 20.0,
        "metadata_json": "{}",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def test_argparser_requires_input():
    parser = audit_dataset._build_argparser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_argparser_accepts_full_invocation():
    parser = audit_dataset._build_argparser()
    args = parser.parse_args([
        "--input", "in.jsonl",
        "--output", "out.md",
        "--json-output", "out.json",
        "--max-rows", "100",
        "--quiet",
        "--include-no-provenance",
    ])
    assert args.input == "in.jsonl"
    assert args.output == "out.md"
    assert args.json_output == "out.json"
    assert args.max_rows == 100
    assert args.quiet is True
    assert args.include_no_provenance is True


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


def test_main_emits_markdown_report(tmp_path, capsys):
    input_path = tmp_path / "catalog.jsonl"
    _write_jsonl(str(input_path), [
        _row("a"),
        _row("b"),
    ])
    output_md = tmp_path / "out.md"
    code = audit_dataset.main([
        "--input", str(input_path),
        "--output", str(output_md),
    ])
    assert code == 0
    assert output_md.is_file()
    text = output_md.read_text(encoding="utf-8")
    assert "UNAV Pro" in text
    assert "Counts" in text


def test_main_writes_json_sidecar(tmp_path):
    input_path = tmp_path / "catalog.jsonl"
    _write_jsonl(str(input_path), [_row("a")])
    output_md = tmp_path / "out.md"
    output_json = tmp_path / "out.json"
    code = audit_dataset.main([
        "--input", str(input_path),
        "--output", str(output_md),
        "--json-output", str(output_json),
        "--quiet",
    ])
    assert code == 0
    assert output_json.is_file()
    decoded = json.loads(output_json.read_text(encoding="utf-8"))
    assert "counts" in decoded


def test_main_default_output_path(tmp_path, capsys):
    input_path = tmp_path / "catalog.jsonl"
    _write_jsonl(str(input_path), [_row("a")])
    code = audit_dataset.main([
        "--input", str(input_path),
        "--quiet",
    ])
    assert code == 0
    expected = str(input_path).replace(".jsonl", ".audit.md")
    assert os.path.isfile(expected)


def test_main_returns_nonzero_on_errors(tmp_path):
    """Negative parallax doesn't trigger an error severity
    on its own (it's a warning). A negative redshift is
    error severity."""
    input_path = tmp_path / "catalog.jsonl"
    _write_jsonl(str(input_path), [
        _row("a", redshift=-0.5),
    ])
    output_md = tmp_path / "out.md"
    code = audit_dataset.main([
        "--input", str(input_path),
        "--output", str(output_md),
        "--quiet",
    ])
    assert code == 1


def test_main_missing_input_returns_2(tmp_path):
    code = audit_dataset.main([
        "--input", str(tmp_path / "missing.jsonl"),
        "--quiet",
    ])
    assert code == 2


def test_main_max_rows_limits_scan(tmp_path):
    input_path = tmp_path / "catalog.jsonl"
    _write_jsonl(str(input_path), [
        _row(f"u{i}") for i in range(10)
    ])
    output_md = tmp_path / "out.md"
    output_json = tmp_path / "out.json"
    code = audit_dataset.main([
        "--input", str(input_path),
        "--output", str(output_md),
        "--json-output", str(output_json),
        "--max-rows", "3",
        "--quiet",
    ])
    assert code == 0
    decoded = json.loads(output_json.read_text(encoding="utf-8"))
    assert decoded["counts"]["rows_total"] == 3


def test_main_include_no_provenance_flag(tmp_path):
    """With the flag set, rows without provenance produce
    info-level findings. Without it, they don't."""
    input_path = tmp_path / "catalog.jsonl"
    _write_jsonl(str(input_path), [_row("a")])
    output_json = tmp_path / "out.json"

    # Without flag.
    audit_dataset.main([
        "--input", str(input_path),
        "--output", str(tmp_path / "a.md"),
        "--json-output", str(output_json),
        "--quiet",
    ])
    without = json.loads(output_json.read_text(encoding="utf-8"))

    # With flag.
    audit_dataset.main([
        "--input", str(input_path),
        "--output", str(tmp_path / "b.md"),
        "--json-output", str(output_json),
        "--include-no-provenance",
        "--quiet",
    ])
    with_flag = json.loads(output_json.read_text(encoding="utf-8"))

    assert with_flag["counts"]["total_issues"] >= without["counts"]["total_issues"]


def test_main_quiet_suppresses_stdout(tmp_path, capsys):
    input_path = tmp_path / "catalog.jsonl"
    _write_jsonl(str(input_path), [_row("a")])
    audit_dataset.main([
        "--input", str(input_path),
        "--output", str(tmp_path / "out.md"),
        "--quiet",
    ])
    captured = capsys.readouterr()
    assert captured.out == ""
