"""Python ↔ native C++ bridge — file-based protocol (v0.9).

The v0.9 milestone wires the Python plugin to the native C++ point
viewer through three small JSON files in the user's UNAV cache
directory:

  * **request.json** — Python side writes "load this binary file";
    the native plugin reads it and refreshes its buffer.
  * **status.json**  — native plugin writes after each load
    attempt: success / failure, point count, file size, load
    time.
  * **selection.json** — native plugin writes when the user
    clicks a point in the viewport: ``uid_hash`` + the resolved
    point index + a timestamp so Python can avoid stale reads.

This is intentionally a file-based bus, not a shared-memory or
pybind11 binding:

  * Zero coupling. The file format the C++ side reads is the same
    binary visible-sector file the Python exporter has produced
    since v0.8; no ABI surface to negotiate.
  * Cross-platform without a build harness. The bridge works
    identically on Windows / macOS / Linux because the shared
    surface is JSON on disk.
  * Safe at the boundary. Each side validates its inputs and
    falls back gracefully if the file is missing / corrupt /
    stale.

A future v0.10+ milestone may layer a faster (shared-memory or
direct extension) bridge on top, but the file protocol stays as
the always-on fallback.

No c4d dependency. Fully unit-tested.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional

from core.config import default_config_dir
from core.logging_util import get_logger

_log = get_logger("core.native_bridge")

#: Schema version for the request / status / selection JSON files.
#: Each side rejects any version it does not understand.
BRIDGE_SCHEMA_VERSION = 1

#: Filenames inside the bridge directory.
REQUEST_FILENAME = "native_request.json"
STATUS_FILENAME = "native_status.json"
SELECTION_FILENAME = "native_selection.json"

#: Default visible-sector binary file the native plugin loads.
DEFAULT_VISIBLE_SECTOR_FILENAME = "visible_sector.bin"

#: Default metadata sidecar (the JSONL of the rows whose uids the
#: binary file references).
DEFAULT_SIDECAR_FILENAME = "visible_sector.jsonl"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def default_bridge_dir() -> str:
    """Per-user bridge directory. Lives next to ``config.json`` /
    ``bookmarks.json`` under ``~/.unav_pro/``."""
    return os.path.join(default_config_dir(), "native_bridge")


def default_visible_sector_path() -> str:
    return os.path.join(default_bridge_dir(), DEFAULT_VISIBLE_SECTOR_FILENAME)


def default_sidecar_path() -> str:
    return os.path.join(default_bridge_dir(), DEFAULT_SIDECAR_FILENAME)


def default_request_path() -> str:
    return os.path.join(default_bridge_dir(), REQUEST_FILENAME)


def default_status_path() -> str:
    return os.path.join(default_bridge_dir(), STATUS_FILENAME)


def default_selection_path() -> str:
    return os.path.join(default_bridge_dir(), SELECTION_FILENAME)


def _ensure_bridge_dir(path: Optional[str] = None) -> str:
    target = path or default_bridge_dir()
    os.makedirs(target, exist_ok=True)
    return target


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class NativeBridgeError(Exception):
    """Raised for unrecoverable bridge protocol errors."""


# ---------------------------------------------------------------------------
# Request — Python → native
# ---------------------------------------------------------------------------


@dataclass
class NativeRequest:
    """Payload Python writes to ask the native plugin to load a
    binary file. The native plugin polls the request file and
    refreshes its buffer when the timestamp changes."""

    schema_version: int = BRIDGE_SCHEMA_VERSION
    action: str = "load"  # "load" | "clear" | "noop"
    binary_path: str = ""
    sidecar_path: str = ""
    requested_at_iso: str = ""
    request_id: str = ""
    max_points: int = 0  # 0 = native plugin uses its own cap

    def __post_init__(self) -> None:
        if not self.requested_at_iso:
            self.requested_at_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not self.request_id:
            self.request_id = f"req_{int(time.time() * 1000)}"
        if self.action not in ("load", "clear", "noop"):
            raise ValueError(
                f"unknown bridge action '{self.action}'; "
                "valid: load / clear / noop"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "NativeRequest":
        d = d or {}
        version = int(d.get("schema_version", 0))
        if version != BRIDGE_SCHEMA_VERSION:
            raise NativeBridgeError(
                f"unsupported request schema_version {version}; "
                f"this build understands {BRIDGE_SCHEMA_VERSION}"
            )
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in d.items() if k in known}
        return cls(**clean)


def write_request(
    request: NativeRequest, path: Optional[str] = None,
) -> str:
    """Persist ``request`` to ``path`` (or the default). Returns the
    full path written. Failures raise ``NativeBridgeError``."""
    target = path or default_request_path()
    _ensure_bridge_dir(os.path.dirname(target))
    try:
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(request.to_dict(), fh, indent=2, sort_keys=True)
    except OSError as exc:
        raise NativeBridgeError(
            f"could not write request to {target}: {exc}"
        ) from exc
    return target


def read_request(path: Optional[str] = None) -> Optional[NativeRequest]:
    """Read the active request, or ``None`` if no request file
    exists. Corrupt / unsupported requests raise
    ``NativeBridgeError``."""
    target = path or default_request_path()
    if not os.path.isfile(target):
        return None
    try:
        with open(target, "r", encoding="utf-8") as fh:
            return NativeRequest.from_dict(json.load(fh))
    except (OSError, ValueError, TypeError) as exc:
        raise NativeBridgeError(
            f"could not read request {target}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Status — native → Python
# ---------------------------------------------------------------------------


@dataclass
class NativeStatus:
    """Payload the native plugin writes after each load attempt.

    v1.0 added the GPU-buffer fields. Older statuses (v0.9) lack
    them and default to safe values, so the dialog can still
    parse them without complaining.
    """

    schema_version: int = BRIDGE_SCHEMA_VERSION
    engine_version: str = "1.0.0"
    engine_available: bool = False
    last_request_id: str = ""
    last_load_iso: str = ""
    binary_path: str = ""
    point_count: int = 0
    file_size_bytes: int = 0
    load_seconds: float = 0.0
    error: str = ""
    # v1.0 — GPU buffer stats. The C++ side populates these; older
    # v0.9 status files leave them at the defaults.
    gpu_uploaded: bool = False
    gpu_bytes: int = 0
    estimated_gpu_bytes: int = 0
    gpu_backend: str = ""
    format_version: int = 0  # 1 or 2 once a load has happened

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "NativeStatus":
        d = d or {}
        version = int(d.get("schema_version", BRIDGE_SCHEMA_VERSION))
        if version != BRIDGE_SCHEMA_VERSION:
            raise NativeBridgeError(
                f"unsupported status schema_version {version}; "
                f"this build understands {BRIDGE_SCHEMA_VERSION}"
            )
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in d.items() if k in known}
        return cls(**clean)

    def short_summary(self) -> str:
        if self.error:
            return f"native: error — {self.error}"
        if not self.engine_available:
            return "native: not loaded (Python fallback)"
        gpu_part = ""
        if self.gpu_uploaded:
            gpu_part = f", GPU {self.gpu_backend or 'on'}"
        elif self.estimated_gpu_bytes:
            gpu_part = (
                f", GPU CPU-fallback "
                f"(~{self.estimated_gpu_bytes / (1024 * 1024):.1f} MB)"
            )
        v_part = (
            f" v{self.format_version}"
            if self.format_version else ""
        )
        return (
            f"native v{self.engine_version}: {self.point_count} points "
            f"(file{v_part} {self.file_size_bytes} bytes, "
            f"{self.load_seconds * 1000:.0f} ms{gpu_part})"
        )

    def detailed_lines(self) -> list:
        """Multi-line breakdown the v1.0 dialog surfaces in its
        Native Point Viewer strip. Always returns at least one
        line so the panel never goes blank."""
        if self.error:
            return [f"native: error — {self.error}"]
        if not self.engine_available:
            return ["native: not loaded (Python fallback)"]
        lines = [
            f"engine    : v{self.engine_version}"
            + (f" (format v{self.format_version})" if self.format_version else ""),
            f"file      : {self.binary_path or '(none)'}",
            f"points    : {self.point_count:,}",
            f"file size : {self.file_size_bytes:,} bytes",
            f"load time : {self.load_seconds * 1000:.1f} ms",
        ]
        if self.gpu_uploaded:
            lines.append(
                f"GPU       : {self.gpu_backend or 'uploaded'} "
                f"({self.gpu_bytes:,} bytes)"
            )
        elif self.estimated_gpu_bytes:
            lines.append(
                f"GPU       : CPU fallback "
                f"(would use ~{self.estimated_gpu_bytes:,} bytes)"
            )
        if self.last_load_iso:
            lines.append(f"last load : {self.last_load_iso}")
        return lines


def write_status(
    status: NativeStatus, path: Optional[str] = None,
) -> str:
    """Persist ``status`` to ``path`` (or the default). Used by the
    native plugin and by the Python fallback that reports
    "not loaded" when the native plugin is missing."""
    target = path or default_status_path()
    _ensure_bridge_dir(os.path.dirname(target))
    try:
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(status.to_dict(), fh, indent=2, sort_keys=True)
    except OSError as exc:
        raise NativeBridgeError(
            f"could not write status to {target}: {exc}"
        ) from exc
    return target


def read_status(path: Optional[str] = None) -> Optional[NativeStatus]:
    """Read the most recent status. Returns ``None`` if the native
    plugin has not written anything yet (i.e. it is not loaded
    into the host)."""
    target = path or default_status_path()
    if not os.path.isfile(target):
        return None
    try:
        with open(target, "r", encoding="utf-8") as fh:
            return NativeStatus.from_dict(json.load(fh))
    except (OSError, ValueError, TypeError) as exc:
        raise NativeBridgeError(
            f"could not read status {target}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Selection — native → Python
# ---------------------------------------------------------------------------


@dataclass
class NativeSelection:
    """Payload the native plugin writes when the user picks a point.

    Both ``uid_hash`` and the position are recorded so the Python
    side can verify the pick before showing the inspector. The
    metadata sidecar (the JSONL referenced by the binary header)
    resolves ``uid_hash → uid``; the inspector then resolves
    ``uid → CatalogObject`` via the active ``MetadataLookup``.
    """

    schema_version: int = BRIDGE_SCHEMA_VERSION
    timestamp_iso: str = ""
    uid_hash: int = 0
    point_index: int = -1
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    source_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "NativeSelection":
        d = d or {}
        version = int(d.get("schema_version", BRIDGE_SCHEMA_VERSION))
        if version != BRIDGE_SCHEMA_VERSION:
            raise NativeBridgeError(
                f"unsupported selection schema_version {version}; "
                f"this build understands {BRIDGE_SCHEMA_VERSION}"
            )
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in d.items() if k in known}
        return cls(**clean)


def write_selection(
    selection: NativeSelection, path: Optional[str] = None,
) -> str:
    target = path or default_selection_path()
    _ensure_bridge_dir(os.path.dirname(target))
    if not selection.timestamp_iso:
        selection.timestamp_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(selection.to_dict(), fh, indent=2, sort_keys=True)
    except OSError as exc:
        raise NativeBridgeError(
            f"could not write selection to {target}: {exc}"
        ) from exc
    return target


def read_selection(path: Optional[str] = None) -> Optional[NativeSelection]:
    target = path or default_selection_path()
    if not os.path.isfile(target):
        return None
    try:
        with open(target, "r", encoding="utf-8") as fh:
            return NativeSelection.from_dict(json.load(fh))
    except (OSError, ValueError, TypeError) as exc:
        raise NativeBridgeError(
            f"could not read selection {target}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# uid_hash → uid resolution
# ---------------------------------------------------------------------------


def resolve_uid_from_hash(
    uid_hash: int, candidate_uids: List[str],
) -> Optional[str]:
    """Find the original UNAV uid whose BLAKE2b 64-bit digest
    matches ``uid_hash``. Returns ``None`` when no candidate
    matches. Caller passes the list of uids that were exported in
    the most recent visible sector (typically the
    ``MetadataLookup.uids()`` of the active dataset registry)."""
    from data.binary_export import compute_uid_hash
    target = int(uid_hash) & 0xFFFFFFFFFFFFFFFF
    for uid in candidate_uids:
        if compute_uid_hash(uid) == target:
            return uid
    return None


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def make_load_request(
    binary_path: str,
    *,
    sidecar_path: str = "",
    max_points: int = 0,
) -> NativeRequest:
    """Build a ``NativeRequest(action="load")`` with sensible
    defaults. The dialog uses this when the artist clicks the
    Sync / Reload Native Viewer buttons."""
    return NativeRequest(
        schema_version=BRIDGE_SCHEMA_VERSION,
        action="load",
        binary_path=binary_path,
        sidecar_path=sidecar_path,
        max_points=int(max_points),
    )


def make_clear_request() -> NativeRequest:
    """Build a ``NativeRequest(action="clear")`` so the artist can
    drop the native buffer without quitting C4D."""
    return NativeRequest(
        schema_version=BRIDGE_SCHEMA_VERSION,
        action="clear",
    )
