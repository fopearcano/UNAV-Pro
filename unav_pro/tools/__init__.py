"""UNAV Pro integrated external-tools layer.

The plugin's heavy preprocessing scripts (Gaia /
JPL / SDSS / DESI fetch, spatial index, DB import,
dataset audit, binary export) live in the repo's
top-level ``tools/`` directory and run in a
**separate external Python environment** — never
inside Cinema 4D's embedded interpreter.

This package is the **lightweight bridge**: it
describes the tools (``tool_registry``), locates +
validates the external Python (``python_env``), and
runs the scripts via subprocess while streaming
logs back to the dialog (``tool_runner``).

Everything here is **stdlib-only** so it imports
cleanly inside Cinema 4D. The heavy work happens in
the subprocess, not in this package.
"""

from __future__ import annotations

import os as _os

# In the source/dev checkout the repository also has a top-level
# ``tools/`` directory holding the *external* preprocessing scripts
# (fetch_gaia_region.py, import_catalog_to_db.py, …). Those scripts are
# run via subprocess in production, never imported — but the test suite
# imports a few of them as ``from tools import fetch_sdss_region``. Now
# that this package owns the ``tools`` name on ``sys.path`` it would
# otherwise shadow them. Extend ``__path__`` to also cover the repo-root
# ``tools/`` so both resolve. In a shipped C4D install that sibling dir
# doesn't exist, so this is a harmless no-op there.
_repo_tools = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "tools",
)
if _os.path.isdir(_repo_tools) and _repo_tools not in __path__:
    __path__.append(_repo_tools)

from .tool_registry import (
    REGISTRY,
    RUNTIME_CLASSES,
    TOOL_CATEGORIES,
    DependencyProfile,
    ToolInput,
    ToolSpec,
    get_tool,
    list_tools,
    tools_in_category,
)
from .python_env import (
    PYTHON_ENV_CONFIG_KEY,
    PythonEnvStatus,
    detect_default_python,
    resolve_external_python,
    validate_python,
)
from .tool_runner import (
    ToolRunRequest,
    ToolRunResult,
    build_command,
    classify_run_failure,
    parse_summary_line,
    run_tool,
)

__all__ = [
    # registry
    "ToolSpec", "ToolInput", "DependencyProfile",
    "REGISTRY", "RUNTIME_CLASSES", "TOOL_CATEGORIES",
    "get_tool", "list_tools", "tools_in_category",
    # python env
    "PythonEnvStatus", "PYTHON_ENV_CONFIG_KEY",
    "detect_default_python", "resolve_external_python",
    "validate_python",
    # runner
    "ToolRunRequest", "ToolRunResult",
    "build_command", "run_tool",
    "parse_summary_line", "classify_run_failure",
]
