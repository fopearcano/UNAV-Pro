"""v-integrated-external-tools subprocess runner.

Turns a :class:`~tools.tool_registry.ToolSpec` + a
dict of user-supplied values into a safe command
line, runs it in the **external** Python interpreter
via subprocess, streams the output back to the
dialog's diagnostics log, and reports a structured
result.

Design rules
------------

* **stdlib-only** — imports cleanly inside Cinema 4D.
  The heavy lifting happens in the spawned process,
  never in this module.
* **Never blocks indefinitely** — the default runner
  supports an optional ``timeout`` and a
  ``cancel_check`` placeholder. The dialog is meant
  to call :func:`run_tool` from a worker thread; this
  module stays agnostic about *how* it's threaded.
* **Injectable runner** — :func:`run_tool` accepts a
  ``runner`` callable ``(cmd) -> (returncode, stdout,
  stderr)`` so tests exercise the whole pipeline
  without spawning a real process.
* **Safe defaults** — optional inputs that carry a
  default (e.g. ``--limit``) are always emitted, so a
  fetch can't accidentally pull an unbounded
  download. No credentials are ever injected into the
  child environment.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .tool_registry import ToolInput, ToolSpec


# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------


#: Marker a tool may print so the runner can surface a
#: one-line human summary. Anything after the prefix
#: on that line becomes :attr:`ToolRunResult.summary`.
SUMMARY_PREFIX: str = "UNAV_SUMMARY:"

FAILURE_NONE: str = "none"
FAILURE_MISSING_PYTHON: str = "missing_python"
FAILURE_MISSING_SCRIPT: str = "missing_script"
FAILURE_DEPENDENCY: str = "dependency_error"
FAILURE_NETWORK: str = "network_error"
FAILURE_CANCELLED: str = "cancelled"
FAILURE_TIMEOUT: str = "timeout"
FAILURE_RUNTIME: str = "runtime_error"

#: All recognised failure kinds (handy for tests +
#: the panel's status mapping).
FAILURE_KINDS: Tuple[str, ...] = (
    FAILURE_NONE, FAILURE_MISSING_PYTHON, FAILURE_MISSING_SCRIPT,
    FAILURE_DEPENDENCY, FAILURE_NETWORK, FAILURE_CANCELLED,
    FAILURE_TIMEOUT, FAILURE_RUNTIME,
)


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------


def _truthy(value: object) -> bool:
    """Interpret a form value as a boolean for
    store_true flags."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def _is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


def _emit_input(inp: ToolInput, value: object, cmd: List[str]) -> None:
    """Append one input's CLI contribution to ``cmd``.

    store_true inputs emit only the bare flag when
    truthy; everything else emits ``flag value`` with
    the value stringified. Blank values emit nothing.
    """
    if inp.is_store_true():
        if _truthy(value):
            cmd.append(inp.flag)
        return
    if _is_blank(value):
        return
    cmd.extend([inp.flag, str(value).strip()])


def build_command(
    spec: ToolSpec,
    values: Optional[Dict[str, object]] = None,
    *,
    python_executable: str,
    repo_root: Optional[str] = None,
) -> List[str]:
    """Build the argv list for one tool invocation.

    ``values`` maps a :class:`ToolInput.flag` to the
    user-supplied value. Missing entries fall back to
    the input's ``default``; this is what makes the
    safe ``--limit`` default kick in automatically.

    Raises ``ValueError`` when the external Python
    isn't resolved or a required input is blank — both
    are caller errors the panel should have prevented.
    """
    if _is_blank(python_executable):
        raise ValueError("no external Python executable resolved")
    values = dict(values or {})

    script = spec.script_path
    if repo_root:
        script = os.path.join(repo_root, spec.script_path)
    cmd: List[str] = [str(python_executable), script]

    missing: List[str] = []
    for inp in spec.required_inputs:
        value = values.get(inp.flag, inp.default)
        if inp.is_store_true():
            _emit_input(inp, value, cmd)
            continue
        if _is_blank(value):
            missing.append(inp.flag)
            continue
        _emit_input(inp, value, cmd)
    if missing:
        raise ValueError(
            "missing required inputs: " + ", ".join(missing)
        )

    for inp in spec.optional_inputs:
        value = values.get(inp.flag, inp.default)
        _emit_input(inp, value, cmd)

    return cmd


def resolved_output_paths(
    spec: ToolSpec,
    values: Optional[Dict[str, object]] = None,
) -> Dict[str, str]:
    """Resolve the artefact paths a successful run will
    have produced, keyed by output flag.

    Used by the Dataset Manager integration to know
    *what* to register after the tool finishes.
    """
    values = dict(values or {})
    out: Dict[str, str] = {}
    for flag in spec.output_flags:
        inp = spec.input_for_flag(flag)
        value = values.get(flag, inp.default if inp else None)
        if _is_blank(value):
            continue
        out[flag] = os.path.expanduser(str(value).strip())
    return out


# ---------------------------------------------------------------------------
# Output parsing + failure classification
# ---------------------------------------------------------------------------


def parse_summary_line(text: Optional[str]) -> str:
    """Extract a human-readable one-liner from tool
    output.

    Prefers the last line tagged with
    :data:`SUMMARY_PREFIX`; falls back to the last
    non-empty physical line. Returns ``""`` for empty
    output.
    """
    if not text:
        return ""
    lines = [
        ln.strip()
        for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if ln.strip()
    ]
    if not lines:
        return ""
    for ln in reversed(lines):
        if ln.upper().startswith(SUMMARY_PREFIX):
            return ln[len(SUMMARY_PREFIX):].strip()
    return lines[-1]


def classify_run_failure(
    returncode: int,
    stderr: Optional[str],
    *,
    exception: Optional[BaseException] = None,
) -> str:
    """Map a (returncode, stderr, exception) tuple to a
    :data:`FAILURE_KINDS` token.

    The classification is best-effort + string-based:
    it reads the child's stderr for the well-known
    signatures (``ModuleNotFoundError``, name-
    resolution failures, etc.) so the panel can show a
    targeted hint instead of a raw traceback.
    """
    if isinstance(exception, FileNotFoundError):
        # subprocess couldn't find the interpreter.
        return FAILURE_MISSING_PYTHON
    if isinstance(exception, subprocess.TimeoutExpired):
        return FAILURE_TIMEOUT
    if returncode == 0 and exception is None:
        return FAILURE_NONE

    text = (stderr or "").lower()
    if (
        "no module named" in text
        or "modulenotfounderror" in text
        or "importerror" in text
    ):
        return FAILURE_DEPENDENCY
    if (
        "can't open file" in text
        or "cannot find" in text
        or ("no such file or directory" in text and ".py" in text)
    ):
        return FAILURE_MISSING_SCRIPT
    if any(
        sig in text
        for sig in (
            "urlerror", "connectionerror", "connection refused",
            "timed out", "timeout", "temporary failure in name resolution",
            "max retries exceeded", "httperror", "ssl",
            "name or service not known",
        )
    ):
        return FAILURE_NETWORK
    return FAILURE_RUNTIME


# ---------------------------------------------------------------------------
# Run request / result
# ---------------------------------------------------------------------------


@dataclass
class ToolRunRequest:
    """Everything needed to launch one tool."""

    spec: ToolSpec
    python_executable: str
    values: Dict[str, object] = field(default_factory=dict)
    repo_root: Optional[str] = None
    timeout: Optional[float] = None
    #: Extra env vars to overlay on the inherited
    #: environment. Intentionally *never* used to pass
    #: credentials — the fetch tools hit public,
    #: anonymous endpoints.
    extra_env: Optional[Dict[str, str]] = None

    def command(self) -> List[str]:
        return build_command(
            self.spec, self.values,
            python_executable=self.python_executable,
            repo_root=self.repo_root,
        )


@dataclass
class ToolRunResult:
    """Structured outcome of one tool invocation."""

    tool_id: str
    command: List[str]
    returncode: int = -1
    ok: bool = False
    stdout: str = ""
    stderr: str = ""
    summary: str = ""
    failure_kind: str = FAILURE_NONE
    error: str = ""
    output_paths: Dict[str, str] = field(default_factory=dict)

    def short_summary(self) -> str:
        if self.ok:
            return self.summary or f"{self.tool_id}: done"
        hint = self.error or self.failure_kind
        return f"{self.tool_id}: failed ({hint})"


# ---------------------------------------------------------------------------
# Default subprocess runner (real process; streams lines)
# ---------------------------------------------------------------------------


def _default_subprocess_runner(
    cmd: List[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    on_line: Optional[Callable[[str], None]] = None,
) -> Tuple[int, str, str]:
    """Spawn ``cmd`` for real, streaming each stdout
    line through ``on_line`` as it arrives. stderr is
    merged into stdout so the live log is ordered the
    way a terminal would show it; the merged text is
    returned as both ``stdout`` and ``stderr`` so
    classification still sees error signatures."""
    proc = subprocess.Popen(  # noqa: S603 — controlled argv
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    captured: List[str] = []
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            captured.append(line)
            if on_line is not None:
                on_line(line)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
    combined = "\n".join(captured)
    return proc.returncode, combined, combined


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_tool(
    request: ToolRunRequest,
    *,
    runner: Optional[Callable[..., Tuple[int, str, str]]] = None,
    log: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> ToolRunResult:
    """Run one tool + return a structured result.

    ``runner`` is the injection seam. When ``None`` the
    real streaming subprocess runner is used. Tests
    pass a callable taking ``cmd`` (and ignoring the
    rest) returning ``(returncode, stdout, stderr)``.

    ``log`` receives each output line for the
    diagnostics panel. ``cancel_check`` is the
    cancellation placeholder: if it returns ``True``
    *before* the process starts, the run is reported as
    cancelled without spawning anything. (In-flight
    cancellation is a future enhancement; the seam is
    here so callers can wire it up.)

    Never raises: every failure path maps to a
    ``ToolRunResult`` with ``ok=False`` + a
    ``failure_kind``.
    """
    spec = request.spec
    output_paths = resolved_output_paths(spec, request.values)

    # --- Cancellation placeholder (pre-launch) -------------------------
    if cancel_check is not None and cancel_check():
        return ToolRunResult(
            tool_id=spec.tool_id,
            command=[],
            returncode=-1,
            ok=False,
            failure_kind=FAILURE_CANCELLED,
            error="cancelled before launch",
            output_paths=output_paths,
        )

    # --- Build the command --------------------------------------------
    try:
        cmd = request.command()
    except ValueError as exc:
        return ToolRunResult(
            tool_id=spec.tool_id,
            command=[],
            returncode=-1,
            ok=False,
            failure_kind=FAILURE_RUNTIME,
            error=str(exc),
            output_paths=output_paths,
        )

    # --- Guard: script must exist (clear error pre-spawn) -------------
    script_path = cmd[1] if len(cmd) > 1 else ""
    if runner is None and script_path and not os.path.isfile(script_path):
        return ToolRunResult(
            tool_id=spec.tool_id,
            command=cmd,
            returncode=-1,
            ok=False,
            failure_kind=FAILURE_MISSING_SCRIPT,
            error=f"tool script not found: {script_path}",
            output_paths=output_paths,
        )

    if log is not None:
        log(f"$ {' '.join(cmd)}")

    # --- Execute -------------------------------------------------------
    env = None
    if request.extra_env:
        env = dict(os.environ)
        env.update(request.extra_env)

    exception: Optional[BaseException] = None
    returncode, stdout, stderr = -1, "", ""
    try:
        if runner is None:
            returncode, stdout, stderr = _default_subprocess_runner(
                cmd,
                cwd=request.repo_root,
                env=env,
                timeout=request.timeout,
                on_line=log,
            )
        else:
            returncode, stdout, stderr = runner(cmd)
            # Replay captured output into the log so the
            # injected-runner path still streams.
            if log is not None and stdout:
                for line in stdout.replace("\r\n", "\n").split("\n"):
                    if line:
                        log(line)
    except FileNotFoundError as exc:
        exception = exc
    except subprocess.TimeoutExpired as exc:
        exception = exc
    except Exception as exc:  # noqa: BLE001 — boundary
        exception = exc

    # --- Classify ------------------------------------------------------
    diag_text = stderr if stderr else stdout
    failure_kind = classify_run_failure(
        returncode, diag_text, exception=exception,
    )
    ok = failure_kind == FAILURE_NONE

    error = ""
    if not ok:
        if exception is not None:
            error = f"{type(exception).__name__}: {exception}"
        else:
            error = _failure_hint(failure_kind, diag_text)

    return ToolRunResult(
        tool_id=spec.tool_id,
        command=cmd,
        returncode=returncode,
        ok=ok,
        stdout=stdout,
        stderr=stderr,
        summary=parse_summary_line(stdout) if ok else "",
        failure_kind=failure_kind,
        error=error,
        output_paths=output_paths,
    )


def _failure_hint(failure_kind: str, diag_text: str) -> str:
    """Build a short, actionable error string for a
    non-zero exit without dumping the whole traceback."""
    tail = (diag_text or "").strip().splitlines()
    last = tail[-1] if tail else ""
    if failure_kind == FAILURE_DEPENDENCY:
        return (
            "missing Python dependency — run the env setup "
            f"(requirements-tools.txt). {last}"[:300]
        )
    if failure_kind == FAILURE_NETWORK:
        return f"network error reaching the data service. {last}"[:300]
    if failure_kind == FAILURE_MISSING_SCRIPT:
        return last or "tool script not found"
    if failure_kind == FAILURE_MISSING_PYTHON:
        return "external Python interpreter not found"
    return last[:300] if last else "tool exited with a non-zero status"


# ---------------------------------------------------------------------------
# Pre-launch safety advisories (consumed by the panel)
# ---------------------------------------------------------------------------


def should_warn_before_run(spec: ToolSpec) -> bool:
    """True when the panel should confirm before
    launching: anything that hits the network or is
    slower than ``short`` gets a heads-up so the artist
    isn't surprised by a long-running fetch."""
    from .tool_registry import DependencyProfile
    if spec.dependency_profile is DependencyProfile.NETWORK:
        return True
    return spec.estimated_runtime_class != "short"


def warning_text_for(spec: ToolSpec) -> str:
    """Human-readable advisory string for the confirm
    dialog. Empty when no warning is needed."""
    if not should_warn_before_run(spec):
        return ""
    bits = []
    from .tool_registry import DependencyProfile
    if spec.dependency_profile is DependencyProfile.NETWORK:
        bits.append("downloads data over the network")
    if spec.estimated_runtime_class != "short":
        bits.append(f"may run for a {spec.estimated_runtime_class} time")
    joined = " and ".join(bits) if bits else "may take a while"
    return (
        f"'{spec.display_name}' {joined}. It runs in the external "
        "Python process and won't freeze Cinema 4D. Continue?"
    )
