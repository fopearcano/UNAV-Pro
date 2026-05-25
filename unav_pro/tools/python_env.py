"""v-integrated-external-tools external Python env.

The external preprocessing tools run in a **separate
Python interpreter** — never Cinema 4D's embedded
one. This module locates + validates that
interpreter and persists the user's choice in the
UNAV config.

Why a separate interpreter?

* Cinema 4D ships a fixed embedded Python the user
  can't `pip install` into without surgery.
* The fetch tools want network + (for the user's
  own extensions) potentially heavy packages.
* Keeping the heavy environment external means the
  plugin ships without forcing any C4D-side
  installs.

This module is **stdlib-only** + safe to import
inside Cinema 4D. It runs ``python --version`` via
subprocess to validate a candidate interpreter; it
never imports the heavy packages itself.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple


#: UnavConfig field that stores the user's chosen
#: external Python executable.
PYTHON_ENV_CONFIG_KEY: str = "external_python_path"

#: Timeout (seconds) for the ``python --version``
#: probe. Validation must never hang the dialog.
VALIDATE_TIMEOUT_SECONDS: float = 10.0

#: Minimum Python the tools support.
MIN_PYTHON: Tuple[int, int] = (3, 10)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


#: Candidate executable names to probe when no
#: explicit path is configured. Ordered most-
#: specific → least.
_CANDIDATE_NAMES: Tuple[str, ...] = (
    "python3.13", "python3.12", "python3.11",
    "python3.10", "python3", "python",
)


def detect_default_python() -> Optional[str]:
    """Best-effort: find a system Python ≥ 3.10 on
    PATH that is **not** the Cinema 4D embedded
    interpreter.

    Returns the absolute path, or ``None`` when
    nothing suitable is found. Pure ``shutil.which``
    lookups + a guard against returning the running
    (possibly C4D-embedded) interpreter.
    """
    running = os.path.realpath(sys.executable) if sys.executable else ""
    for name in _CANDIDATE_NAMES:
        found = shutil.which(name)
        if not found:
            continue
        real = os.path.realpath(found)
        # Skip the interpreter we're running under —
        # inside Cinema 4D that's the embedded
        # Python, which is exactly what we want to
        # avoid.
        if real == running and _looks_like_c4d(real):
            continue
        return found
    return None


def _looks_like_c4d(path: str) -> bool:
    """Heuristic: does this interpreter path look
    like it lives inside a Cinema 4D install?"""
    lowered = path.lower()
    return (
        "cinema 4d" in lowered
        or "maxon" in lowered
        or "c4dpy" in lowered
    )


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_external_python(
    *,
    configured_path: Optional[str] = None,
) -> Optional[str]:
    """Resolve the external Python to use.

    Order of precedence:
      1. an explicit ``configured_path`` (from the
         UNAV config), if it exists on disk;
      2. the detected default (``detect_default_python``).

    Returns ``None`` when neither resolves — the
    dialog then prompts the user to pick one.
    """
    if configured_path:
        candidate = os.path.expanduser(str(configured_path).strip())
        if candidate and os.path.isfile(candidate):
            return candidate
    return detect_default_python()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class PythonEnvStatus:
    """Outcome of validating a candidate Python."""

    executable: str
    valid: bool
    version: str = ""
    version_tuple: Tuple[int, int, int] = (0, 0, 0)
    meets_minimum: bool = False
    error: str = ""

    def short_summary(self) -> str:
        if not self.valid:
            return f"Python: invalid ({self.error or 'no version'})"
        warn = "" if self.meets_minimum else (
            f" — below the {MIN_PYTHON[0]}.{MIN_PYTHON[1]} minimum"
        )
        return f"Python {self.version} @ {self.executable}{warn}"


_VERSION_RE = re.compile(r"Python\s+(\d+)\.(\d+)\.(\d+)")


def _parse_version(text: str) -> Tuple[int, int, int]:
    match = _VERSION_RE.search(text or "")
    if not match:
        return (0, 0, 0)
    return (
        int(match.group(1)), int(match.group(2)), int(match.group(3)),
    )


def validate_python(
    executable: Optional[str],
    *,
    runner=None,
) -> PythonEnvStatus:
    """Run ``<executable> --version`` and parse the
    result.

    ``runner`` is an injectable callable
    ``(cmd: List[str]) -> (returncode, stdout,
    stderr)`` so tests can validate without
    spawning a real process. When ``None`` the real
    ``subprocess`` is used.

    Never raises: a missing executable / timeout /
    crash all map to ``valid=False`` with a reason.
    """
    if not executable:
        return PythonEnvStatus(
            executable="", valid=False,
            error="no Python executable configured",
        )
    exe = os.path.expanduser(str(executable).strip())
    if runner is None and not os.path.isfile(exe):
        return PythonEnvStatus(
            executable=exe, valid=False,
            error=f"executable not found: {exe}",
        )
    runner_fn = runner if runner is not None else _default_version_runner
    try:
        code, out, err = runner_fn([exe, "--version"])
    except Exception as exc:  # noqa: BLE001 — boundary
        return PythonEnvStatus(
            executable=exe, valid=False,
            error=f"probe failed: {exc}",
        )
    if code != 0:
        return PythonEnvStatus(
            executable=exe, valid=False,
            error=f"`python --version` exited {code}: "
                  f"{(err or out).strip()[:200]}",
        )
    # Some Python builds print to stdout, others to
    # stderr — check both.
    combined = (out or "") + "\n" + (err or "")
    version_tuple = _parse_version(combined)
    if version_tuple == (0, 0, 0):
        return PythonEnvStatus(
            executable=exe, valid=False,
            error=f"could not parse version from: "
                  f"{combined.strip()[:200]}",
        )
    version_str = ".".join(str(x) for x in version_tuple)
    meets_min = version_tuple[:2] >= MIN_PYTHON
    return PythonEnvStatus(
        executable=exe, valid=True,
        version=version_str,
        version_tuple=version_tuple,
        meets_minimum=meets_min,
    )


def _default_version_runner(
    cmd: List[str],
) -> Tuple[int, str, str]:
    """Real subprocess version probe. Bounded by
    ``VALIDATE_TIMEOUT_SECONDS`` so it can't hang
    the dialog."""
    proc = subprocess.run(  # noqa: S603 — controlled command
        cmd,
        capture_output=True,
        text=True,
        timeout=VALIDATE_TIMEOUT_SECONDS,
    )
    return proc.returncode, proc.stdout, proc.stderr
