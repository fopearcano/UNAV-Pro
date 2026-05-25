"""integrated-external-tools-ui tests.

Covers the lightweight bridge that lets the dialog launch the heavy
preprocessing tools in a separate external Python:

  * the tool registry (descriptions / lookup / categories)
  * external-Python detection + validation (injectable runner)
  * command construction + subprocess result parsing (injectable runner)
  * failure classification (missing python / script / dependency / net)
  * dataset-manager registration of a successful run

Everything here is pure-Python — no subprocess is ever spawned and
Cinema 4D is never imported.
"""

from __future__ import annotations

import os

import pytest

from tools.tool_registry import (
    CATEGORY_EXPORT,
    CATEGORY_FETCH,
    CATEGORY_PROCESSING,
    REGISTRY,
    TOOL_CATEGORIES,
    DependencyProfile,
    InputKind,
    ToolInput,
    ToolSpec,
    get_tool,
    list_tools,
    tools_in_category,
)
from tools.python_env import (
    MIN_PYTHON,
    PYTHON_ENV_CONFIG_KEY,
    PythonEnvStatus,
    detect_default_python,
    resolve_external_python,
    validate_python,
)
from tools.tool_runner import (
    FAILURE_CANCELLED,
    FAILURE_DEPENDENCY,
    FAILURE_MISSING_PYTHON,
    FAILURE_MISSING_SCRIPT,
    FAILURE_NETWORK,
    FAILURE_NONE,
    FAILURE_RUNTIME,
    SUMMARY_PREFIX,
    ToolRunRequest,
    ToolRunResult,
    build_command,
    classify_run_failure,
    parse_summary_line,
    resolved_output_paths,
    run_tool,
    should_warn_before_run,
    warning_text_for,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_non_empty_and_unique_ids():
    ids = [s.tool_id for s in list_tools()]
    assert ids
    assert len(ids) == len(set(ids)), "tool_id collision"


def test_registry_covers_all_categories():
    seen = {s.category for s in REGISTRY}
    assert seen == set(TOOL_CATEGORIES)


def test_get_tool_known_and_unknown():
    assert get_tool("fetch_gaia") is not None
    assert get_tool("fetch_gaia").display_name == "Fetch Gaia Region"
    assert get_tool("does-not-exist") is None
    assert get_tool("") is None
    # Lookup is case-insensitive / whitespace-tolerant.
    assert get_tool("  FETCH_GAIA ") is not None


def test_tools_in_category_partitions_registry():
    total = 0
    for cat in TOOL_CATEGORIES:
        total += len(tools_in_category(cat))
    assert total == len(REGISTRY)


def test_fetch_tools_are_network_and_unsafe_in_c4d():
    for spec in tools_in_category(CATEGORY_FETCH):
        assert spec.dependency_profile is DependencyProfile.NETWORK
        assert spec.safe_to_run_inside_c4d is False


def test_processing_and_export_are_stdlib():
    for spec in tools_in_category(CATEGORY_PROCESSING) + tools_in_category(
        CATEGORY_EXPORT
    ):
        assert spec.dependency_profile is DependencyProfile.STDLIB


def test_toolspec_input_helpers():
    spec = get_tool("fetch_gaia")
    flags = {i.flag for i in spec.all_inputs()}
    assert {"--ra", "--dec", "--radius-deg", "--output"} <= flags
    assert spec.input_for_flag("--ra").kind is InputKind.FLOAT
    assert spec.input_for_flag("--nope") is None


def test_fetch_tools_carry_a_safe_limit_default():
    # Every cone-search fetch must default --limit so a run can't pull
    # an unbounded download.
    for tid in ("fetch_gaia", "fetch_sdss", "fetch_desi"):
        spec = get_tool(tid)
        limit = spec.input_for_flag("--limit")
        assert limit is not None
        assert isinstance(limit.default, int) and limit.default > 0


def test_store_true_input_detection():
    spec = get_tool("import_db")
    replace = spec.input_for_flag("--replace")
    assert replace is not None
    assert replace.is_store_true()


# ---------------------------------------------------------------------------
# Python environment
# ---------------------------------------------------------------------------


def _runner_ok(version="3.11.4"):
    def runner(cmd):
        return (0, f"Python {version}\n", "")
    return runner


def test_validate_python_valid():
    status = validate_python("/usr/bin/python3", runner=_runner_ok("3.12.1"))
    assert status.valid
    assert status.version == "3.12.1"
    assert status.version_tuple == (3, 12, 1)
    assert status.meets_minimum


def test_validate_python_below_minimum():
    status = validate_python("/usr/bin/python3", runner=_runner_ok("3.8.10"))
    assert status.valid
    assert not status.meets_minimum
    assert "below" in status.short_summary()


def test_validate_python_version_on_stderr():
    def runner(cmd):
        # Older builds print --version to stderr.
        return (0, "", "Python 3.10.6\n")
    status = validate_python("/usr/bin/python3", runner=runner)
    assert status.valid
    assert status.version_tuple == (3, 10, 6)


def test_validate_python_nonzero_exit():
    def runner(cmd):
        return (1, "", "boom")
    status = validate_python("/usr/bin/python3", runner=runner)
    assert not status.valid
    assert "exited 1" in status.error


def test_validate_python_unparseable():
    def runner(cmd):
        return (0, "not a version", "")
    status = validate_python("/usr/bin/python3", runner=runner)
    assert not status.valid


def test_validate_python_empty_executable():
    status = validate_python("", runner=_runner_ok())
    assert not status.valid
    assert "no Python" in status.error


def test_validate_python_runner_raises_is_caught():
    def runner(cmd):
        raise OSError("cannot spawn")
    status = validate_python("/usr/bin/python3", runner=runner)
    assert not status.valid
    assert "probe failed" in status.error


def test_resolve_prefers_configured_path(tmp_path):
    fake = tmp_path / "python3"
    fake.write_text("#!/bin/sh\n")
    resolved = resolve_external_python(configured_path=str(fake))
    assert resolved == str(fake)


def test_resolve_falls_back_to_detected(monkeypatch):
    # A configured path that doesn't exist falls through to detection.
    resolved = resolve_external_python(configured_path="/no/such/python")
    # detection may legitimately return None in odd environments; the
    # contract is only that it doesn't return the bogus path.
    assert resolved != "/no/such/python"


def test_config_key_constant():
    assert PYTHON_ENV_CONFIG_KEY == "external_python_path"


def test_min_python_is_310_or_higher():
    assert MIN_PYTHON >= (3, 10)


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


def test_build_command_required_and_default_optionals():
    spec = get_tool("fetch_gaia")
    cmd = build_command(
        spec,
        {"--ra": 56.75, "--dec": 24.12, "--radius-deg": 1.0,
         "--output": "/tmp/out.jsonl"},
        python_executable="/usr/bin/python3",
        repo_root="/repo",
    )
    assert cmd[0] == "/usr/bin/python3"
    assert cmd[1] == os.path.join("/repo", "tools/fetch_gaia_region.py")
    assert "--ra" in cmd and "56.75" in cmd
    # The safe default --limit must be emitted even though the caller
    # didn't supply one.
    assert "--limit" in cmd
    assert "5000" in cmd


def test_build_command_missing_required_raises():
    spec = get_tool("fetch_gaia")
    with pytest.raises(ValueError) as exc:
        build_command(
            spec, {"--ra": 1.0},  # missing dec/radius/output
            python_executable="/usr/bin/python3",
        )
    assert "missing required inputs" in str(exc.value)


def test_build_command_missing_python_raises():
    spec = get_tool("audit_dataset")
    with pytest.raises(ValueError):
        build_command(
            spec, {"--input": "/a.jsonl", "--output": "/r.md"},
            python_executable="",
        )


def test_build_command_store_true_emits_bare_flag_when_truthy():
    spec = get_tool("import_db")
    cmd = build_command(
        spec,
        {"--input": "/a.jsonl", "--db": "/a.db", "--replace": True},
        python_executable="py",
    )
    # store_true: the flag appears with no value after it.
    assert "--replace" in cmd
    assert cmd[cmd.index("--replace") - 1] != "--replace"
    # And the next token is not a value for --replace.
    pos = cmd.index("--replace")
    assert pos == len(cmd) - 1 or cmd[pos + 1].startswith("--")


def test_build_command_store_true_omitted_when_falsey():
    spec = get_tool("import_db")
    cmd = build_command(
        spec,
        {"--input": "/a.jsonl", "--db": "/a.db", "--replace": False},
        python_executable="py",
    )
    assert "--replace" not in cmd


def test_build_command_blank_optional_skipped():
    spec = get_tool("fetch_gaia")
    cmd = build_command(
        spec,
        {"--ra": 1.0, "--dec": 2.0, "--radius-deg": 1.0,
         "--output": "/o.jsonl", "--build-index": ""},
        python_executable="py",
    )
    assert "--build-index" not in cmd


def test_resolved_output_paths():
    spec = get_tool("fetch_gaia")
    outs = resolved_output_paths(
        spec, {"--output": "~/cat.jsonl", "--build-index": "/idx"},
    )
    assert outs["--output"] == os.path.expanduser("~/cat.jsonl")
    assert outs["--build-index"] == "/idx"


# ---------------------------------------------------------------------------
# Summary parsing + failure classification
# ---------------------------------------------------------------------------


def test_parse_summary_prefers_marker():
    text = "doing things\n" + SUMMARY_PREFIX + " wrote 5000 rows\n"
    assert parse_summary_line(text) == "wrote 5000 rows"


def test_parse_summary_falls_back_to_last_line():
    assert parse_summary_line("a\nb\nc\n") == "c"


def test_parse_summary_empty():
    assert parse_summary_line("") == ""
    assert parse_summary_line(None) == ""


def test_classify_success():
    assert classify_run_failure(0, "") == FAILURE_NONE


def test_classify_dependency_error():
    err = "Traceback ...\nModuleNotFoundError: No module named 'requests'"
    assert classify_run_failure(1, err) == FAILURE_DEPENDENCY


def test_classify_missing_python_via_exception():
    kind = classify_run_failure(-1, "", exception=FileNotFoundError("py"))
    assert kind == FAILURE_MISSING_PYTHON


def test_classify_missing_script():
    err = "python: can't open file '/repo/tools/x.py': No such file"
    assert classify_run_failure(2, err) == FAILURE_MISSING_SCRIPT


def test_classify_network_error():
    err = "urllib.error.URLError: <urlopen error timed out>"
    assert classify_run_failure(1, err) == FAILURE_NETWORK


def test_classify_generic_runtime():
    assert classify_run_failure(1, "ValueError: bad radius") == FAILURE_RUNTIME


# ---------------------------------------------------------------------------
# run_tool (injectable runner)
# ---------------------------------------------------------------------------


def _audit_request(tmp_path):
    spec = get_tool("audit_dataset")
    return ToolRunRequest(
        spec=spec,
        python_executable="/usr/bin/python3",
        values={"--input": str(tmp_path / "in.jsonl"),
                "--output": str(tmp_path / "report.md")},
        repo_root=None,
    )


def test_run_tool_success_streams_and_summarises():
    spec = get_tool("audit_dataset")
    req = ToolRunRequest(
        spec=spec, python_executable="py",
        values={"--input": "/a.jsonl", "--output": "/r.md"},
    )
    lines = []

    def runner(cmd):
        return (0, "scanning\n" + SUMMARY_PREFIX + " ok 10 objects\n", "")

    result = run_tool(req, runner=runner, log=lines.append)
    assert result.ok
    assert result.returncode == 0
    assert result.failure_kind == FAILURE_NONE
    assert result.summary == "ok 10 objects"
    # The command line + each output line was streamed to the log.
    assert any("scanning" in ln for ln in lines)


def test_run_tool_dependency_failure():
    spec = get_tool("fetch_gaia")
    req = ToolRunRequest(
        spec=spec, python_executable="py",
        values={"--ra": 1.0, "--dec": 2.0, "--radius-deg": 1.0,
                "--output": "/o.jsonl"},
    )

    def runner(cmd):
        return (1, "", "ModuleNotFoundError: No module named 'numpy'")

    result = run_tool(req, runner=runner)
    assert not result.ok
    assert result.failure_kind == FAILURE_DEPENDENCY
    assert "dependency" in result.error.lower()


def test_run_tool_missing_python_maps_to_failure():
    spec = get_tool("audit_dataset")
    req = ToolRunRequest(
        spec=spec, python_executable="py",
        values={"--input": "/a.jsonl", "--output": "/r.md"},
    )

    def runner(cmd):
        raise FileNotFoundError("py")

    result = run_tool(req, runner=runner)
    assert not result.ok
    assert result.failure_kind == FAILURE_MISSING_PYTHON


def test_run_tool_missing_required_input_is_clean_failure():
    spec = get_tool("audit_dataset")
    req = ToolRunRequest(
        spec=spec, python_executable="py", values={},  # nothing
    )
    result = run_tool(req, runner=lambda cmd: (0, "", ""))
    assert not result.ok
    assert "missing required" in result.error


def test_run_tool_cancellation_placeholder():
    spec = get_tool("fetch_gaia")
    req = ToolRunRequest(
        spec=spec, python_executable="py",
        values={"--ra": 1.0, "--dec": 2.0, "--radius-deg": 1.0,
                "--output": "/o.jsonl"},
    )
    called = []

    def runner(cmd):
        called.append(cmd)
        return (0, "", "")

    result = run_tool(req, runner=runner, cancel_check=lambda: True)
    assert not result.ok
    assert result.failure_kind == FAILURE_CANCELLED
    assert called == [], "runner must not be invoked when cancelled pre-launch"


def test_run_tool_default_runner_missing_script(tmp_path):
    # With no injected runner, a non-existent script is caught before
    # spawning anything.
    spec = get_tool("audit_dataset")
    req = ToolRunRequest(
        spec=spec,
        python_executable="/usr/bin/python3",
        values={"--input": str(tmp_path / "in.jsonl"),
                "--output": str(tmp_path / "r.md")},
        repo_root=str(tmp_path),  # tools/ doesn't exist here
    )
    result = run_tool(req)
    assert not result.ok
    assert result.failure_kind == FAILURE_MISSING_SCRIPT


# ---------------------------------------------------------------------------
# Pre-launch advisories
# ---------------------------------------------------------------------------


def test_should_warn_for_network_tools():
    assert should_warn_before_run(get_tool("fetch_gaia"))
    assert "network" in warning_text_for(get_tool("fetch_gaia")).lower()


def test_short_stdlib_tool_no_warning():
    spec = get_tool("audit_dataset")  # short + stdlib
    assert not should_warn_before_run(spec)
    assert warning_text_for(spec) == ""


# ---------------------------------------------------------------------------
# Dataset-manager registration
# ---------------------------------------------------------------------------


_SAMPLE_ROW = (
    '{"uid": "demo:1", "catalog_source": "UNAV Demo", "object_type": '
    '"star", "ra_deg": 0.0, "dec_deg": 0.0, "distance_parsec": 1.0, '
    '"apparent_magnitude": 1.0, "name": "Origin", "metadata_json": "{}"}'
)


def _empty_controller(tmp_path):
    from core.dataset_registry import DatasetRegistry
    from ui.dataset_manager import DatasetManagerController
    reg = DatasetRegistry()
    return DatasetManagerController(
        registry=reg, registry_path=str(tmp_path / "datasets.json"),
    )


def test_register_fetch_output(tmp_path):
    cat = tmp_path / "gaia.jsonl"
    cat.write_text(_SAMPLE_ROW + "\n")
    ctrl = _empty_controller(tmp_path)
    spec = get_tool("fetch_gaia")
    result = ToolRunResult(
        tool_id="fetch_gaia", command=[], ok=True,
        output_paths={"--output": str(cat)},
    )
    msg = ctrl.register_tool_output(spec, result, {"--output": str(cat)})
    assert "registered" in msg
    assert ctrl.registry.find(os.path.splitext(os.path.basename(str(cat)))[0])


def test_register_fetch_attaches_index(tmp_path):
    cat = tmp_path / "gaia.jsonl"
    cat.write_text(_SAMPLE_ROW + "\n")
    idx = tmp_path / "gaia_index"
    idx.mkdir()
    ctrl = _empty_controller(tmp_path)
    spec = get_tool("fetch_gaia")
    result = ToolRunResult(
        tool_id="fetch_gaia", command=[], ok=True,
        output_paths={"--output": str(cat), "--build-index": str(idx)},
    )
    ctrl.register_tool_output(
        spec, result, {"--output": str(cat), "--build-index": str(idx)},
    )
    entry = ctrl.registry.entries[-1]
    assert entry.index_path == os.path.abspath(str(idx))


def test_register_build_index_attaches_to_existing(tmp_path):
    cat = tmp_path / "gaia.jsonl"
    cat.write_text(_SAMPLE_ROW + "\n")
    ctrl = _empty_controller(tmp_path)
    # Pre-register the source catalog.
    ctrl.registry.add_path(str(cat), name="src")
    idx = tmp_path / "idx"
    idx.mkdir()
    spec = get_tool("build_index")
    result = ToolRunResult(
        tool_id="build_index", command=[], ok=True,
        output_paths={"--output": str(idx)},
    )
    msg = ctrl.register_tool_output(
        spec, result, {"--input": str(cat), "--output": str(idx)},
    )
    assert "index attached" in msg
    assert ctrl.registry.find("src").index_path == os.path.abspath(str(idx))


def test_register_failed_result_is_noop(tmp_path):
    ctrl = _empty_controller(tmp_path)
    spec = get_tool("fetch_gaia")
    result = ToolRunResult(
        tool_id="fetch_gaia", command=[], ok=False,
        failure_kind=FAILURE_RUNTIME, error="boom",
    )
    msg = ctrl.register_tool_output(spec, result, {})
    assert "did not finish" in msg
    assert len(ctrl.registry) == 0


def test_register_audit_tool_is_noop(tmp_path):
    cat = tmp_path / "x.jsonl"
    cat.write_text(_SAMPLE_ROW + "\n")
    ctrl = _empty_controller(tmp_path)
    spec = get_tool("audit_dataset")  # produces neither dataset/index/db
    result = ToolRunResult(
        tool_id="audit_dataset", command=[], ok=True,
        output_paths={"--output": str(tmp_path / "r.md")},
    )
    msg = ctrl.register_tool_output(
        spec, result, {"--input": str(cat), "--output": str(tmp_path / "r.md")},
    )
    assert "no registerable dataset" in msg
    assert len(ctrl.registry) == 0


# ---------------------------------------------------------------------------
# Panel controller (pure half)
# ---------------------------------------------------------------------------


def test_panel_controller_sections_and_run(tmp_path):
    from core.config import UnavConfig
    from ui.tools_panel import ToolsPanelController
    cfg = UnavConfig(external_python_path="/usr/bin/python3")
    ctrl = ToolsPanelController(
        config=cfg, repo_root="/repo",
        config_path=str(tmp_path / "config.json"),
    )
    cats = [c for c, _l, _s in ctrl.sections()]
    assert cats == [CATEGORY_FETCH, CATEGORY_PROCESSING, CATEGORY_EXPORT]

    # A full run through the controller using an injected runner.
    def runner(cmd):
        assert cmd[0] == "/usr/bin/python3"
        return (0, SUMMARY_PREFIX + " done\n", "")

    result = ctrl.run(
        "audit_dataset",
        {"--input": "/a.jsonl", "--output": "/r.md"},
        runner=runner,
    )
    assert result.ok
    assert result.summary == "done"


def test_panel_controller_run_without_python(tmp_path):
    from core.config import UnavConfig
    from ui.tools_panel import ToolsPanelController
    cfg = UnavConfig(external_python_path="/definitely/not/here/python")
    ctrl = ToolsPanelController(
        config=cfg, repo_root="/repo",
        config_path=str(tmp_path / "config.json"),
    )
    # Force resolve to None by also blocking detection via a bogus value
    # — if the environment has a system python, resolve() will find it,
    # so only assert the happy contract: build_request raises when no
    # python resolves. We emulate that by checking the explicit error
    # path through a tool with an unresolved interpreter.
    import tools.python_env as pe
    original = pe.detect_default_python
    pe.detect_default_python = lambda: None
    try:
        ctrl_no_py = ToolsPanelController(
            config=UnavConfig(external_python_path=None),
            repo_root="/repo",
            config_path=str(tmp_path / "c2.json"),
        )
        result = ctrl_no_py.run("audit_dataset", {"--input": "/a", "--output": "/b"})
        assert not result.ok
        assert "external Python" in result.error
    finally:
        pe.detect_default_python = original


def test_panel_controller_persists_python_path(tmp_path):
    from core.config import UnavConfig, load_config
    from ui.tools_panel import ToolsPanelController
    cfg_path = str(tmp_path / "config.json")
    ctrl = ToolsPanelController(
        config=UnavConfig(), repo_root="/repo", config_path=cfg_path,
    )
    ctrl.set_python_path("/opt/py/bin/python3")
    # Re-read from disk: the override persisted.
    reloaded = load_config(cfg_path)
    assert reloaded.external_python_path == "/opt/py/bin/python3"
