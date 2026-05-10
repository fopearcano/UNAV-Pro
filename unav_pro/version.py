"""UNAV Pro version metadata.

Single source of truth for the plugin's version string. The
dialog's status line, the diagnostics panel, the export
manifest, and the packaging script all read from this
module.

Bumped at each milestone tag. Format follows SemVer
(major.minor.patch). Pre-release suffixes (``"-rc1"``,
``"-dev"``) are allowed.

Stdlib-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

#: Plugin version string. Stamped into the export manifest,
#: surfaced in the dialog's title bar / status line, and
#: read by the packaging script when naming the zip.
PLUGIN_VERSION: str = "3.5.0"

#: Stable codename for the v3.5 milestone — surfaced in
#: release notes + the dialog's "About" log line.
PLUGIN_CODENAME: str = "Public Alpha"

#: Minimum Cinema 4D API the plugin supports. The
#: ``unav_plugin.pyp`` entry point also enforces this; the
#: number lives here so the diagnostics panel can render it
#: alongside the plugin version.
MIN_C4D_API: int = 26000


@dataclass(frozen=True)
class VersionInfo:
    """Structured version snapshot.

    The dialog renders this; tests assert the field shapes.
    """

    plugin_version: str = PLUGIN_VERSION
    codename: str = PLUGIN_CODENAME
    min_c4d_api: int = MIN_C4D_API

    def display_line(self) -> str:
        return (
            f"UNAV Pro v{self.plugin_version} "
            f"({self.codename}; requires C4D API ≥ {self.min_c4d_api})"
        )


def get_version_info() -> VersionInfo:
    """Return the canonical ``VersionInfo`` snapshot."""
    return VersionInfo()


def parse_version(value: str) -> Tuple[int, int, int]:
    """Parse a SemVer ``major.minor.patch`` string. Pre-
    release suffixes (after a dash) are stripped. Returns
    ``(0, 0, 0)`` on parse failure rather than raising —
    the dialog must never crash because a future hand-edited
    version string is malformed."""
    if not value:
        return (0, 0, 0)
    head = str(value).strip()
    if "-" in head:
        head = head.split("-", 1)[0]
    parts = head.split(".")
    out: list = [0, 0, 0]
    for i in range(min(3, len(parts))):
        try:
            out[i] = int(parts[i])
        except (TypeError, ValueError):
            return (0, 0, 0)
    return (out[0], out[1], out[2])
