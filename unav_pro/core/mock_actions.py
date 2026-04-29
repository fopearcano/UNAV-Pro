"""Mock action handlers for the MVP dialog.

These functions stand in for real engine calls so the UI can be exercised
end-to-end before any catalog data, spatial index, or particle generator
is wired up. Each returns a short status string that the dialog appends
to its log area. Failures are reported as strings — they never raise out
to the C4D event loop.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from .logging_util import get_logger

_log = get_logger("mock")


def _safe(label: str, fn, *args, **kwargs) -> str:
    """Run ``fn`` and return a status line; turn exceptions into messages."""
    started = time.monotonic()
    try:
        result = fn(*args, **kwargs)
        elapsed_ms = (time.monotonic() - started) * 1000.0
        msg = f"{label}: {result} ({elapsed_ms:.1f} ms)"
        _log.info(msg)
        return msg
    except Exception as exc:  # noqa: BLE001 — boundary handler
        msg = f"{label} FAILED: {exc!r}"
        _log.exception(msg)
        return msg


def load_dataset(path: Optional[str] = None) -> str:
    """Pretend to load a dataset from ``path``.

    With the path missing or non-existent we still succeed (mock mode);
    we just report which fallback we took. This mirrors the eventual
    real behavior where a missing cache triggers a clear, actionable
    error rather than a stack trace.
    """

    def _do() -> str:
        if path is None or path == "":
            return "no path provided; using built-in mock dataset 'gaia_demo'"
        if not os.path.exists(path):
            return f"path not found ({path}); using built-in mock dataset 'gaia_demo'"
        return f"mock-loaded dataset from {path}"

    return _safe("Load Dataset", _do)


def create_navigation_null() -> str:
    """Pretend to create the navigation null in the active scene."""

    def _do() -> str:
        # Real implementation will instantiate a c4d.BaseObject(c4d.Onull),
        # name it "UNAV Navigator", insert it into the active document,
        # and tag it with our navigator tag.
        return "mock navigation null 'UNAV Navigator' would be inserted into active doc"

    return _safe("Create Navigation Null", _do)


def generate_point_cloud(point_count: int = 10000) -> str:
    """Pretend to generate a point cloud of ``point_count`` synthetic stars."""

    def _do() -> str:
        if point_count <= 0:
            raise ValueError("point_count must be > 0")
        # Real implementation will pull from the spatial index and push
        # a buffer to the viewport particle layer.
        return f"mock point cloud generated with {point_count} synthetic points"

    return _safe("Generate Point Cloud", _do)


def clear_scene() -> str:
    """Pretend to remove all UNAV Pro objects from the active scene."""

    def _do() -> str:
        # Real implementation will walk the active doc, find UNAV-tagged
        # objects, and remove them inside an undo block.
        return "mock clear: would remove all UNAV objects from active doc"

    return _safe("Clear Scene", _do)
