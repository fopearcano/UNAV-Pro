"""Cinema 4D host version check.

Cinema 4D's API version numbering changed across releases:

  - R26 (Cinema 4D 2023) reports 26000 from ``c4d.GetC4DVersion()``.
  - Cinema 4D 2024 reports 2024xxx.
  - Cinema 4D 2025 reports 2025xxx.

We accept either scheme. Anything below 26000 is considered too old and
the plugin refuses to register.

This module is intentionally importable without ``c4d``; it is also
called by tests with a synthetic version int.
"""

from __future__ import annotations

from typing import Optional, Tuple

# Minimum supported API version. C4D 2023 == 26000.
MIN_VERSION = 26000


def is_supported(version: int, minimum: int = MIN_VERSION) -> bool:
    """Return True if ``version`` meets the minimum supported version."""
    if not isinstance(version, int):
        return False
    return version >= minimum


def describe(version: int) -> str:
    """Render a Cinema 4D API version int as a human-readable string."""
    if version >= 2023000:
        # Cinema 4D 2024+ scheme: 2024xxx, 2025xxx, ...
        major = version // 1000
        minor = version % 1000
        return f"Cinema 4D {major} (build {minor})"
    if version >= 26000:
        # R26 is C4D 2023.
        major = version // 1000
        minor = version % 1000
        return f"Cinema 4D R{major} (build {minor})"
    return f"Cinema 4D (legacy version {version})"


def check_host(version: Optional[int] = None) -> Tuple[bool, str]:
    """Check the host version. Returns (ok, message).

    If ``version`` is None, attempts to import ``c4d`` and call
    ``GetC4DVersion()``. When ``c4d`` is not available (e.g. unit tests
    outside C4D) the function returns (False, reason) without raising.
    """
    if version is None:
        try:
            import c4d  # type: ignore
        except ImportError:
            return False, "Cinema 4D module not available (running outside C4D)."
        try:
            version = c4d.GetC4DVersion()
        except Exception as exc:  # defensive: API errors must not crash
            return False, f"Failed to read C4D version: {exc!r}"

    if not is_supported(version):
        return False, (
            f"Unsupported host: {describe(version)}. "
            f"UNAV Pro requires Cinema 4D 2023 or later (API >= {MIN_VERSION})."
        )
    return True, f"Host OK: {describe(version)}."
