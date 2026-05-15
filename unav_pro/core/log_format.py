"""v3.x log-line formatting helpers.

Why this module exists
----------------------

The dialog's *Status Log* widget used to maintain its
state inside Cinema 4D's ``MultiLineEditText``: every
``_append_log(...)`` call read the widget back with
``GetString``, appended the new line, and set the
result back via ``SetString``.

This was buggy. Cinema 4D's ``MultiLineEditText``
**does not reliably preserve ``\\n``** when its
contents are round-tripped through ``GetString`` —
the exact behaviour depends on the host build /
platform / OS line-ending convention. When the
newline gets dropped on the round-trip, the next
append concatenates against the previous entry +
the log degenerates to:

::

    [INFO] Loaded dataset[INFO] Created navigator[WARN] Missing metadata

The fix:

* Maintain the buffer **Python-side** (``List[str]``).
* Never read state back from the widget.
* Re-render the widget via ``SetString`` at every
  append, joining the buffer with ``"\\n"``.
* Cap the buffer at a sensible length so a long
  session doesn't balloon memory.

This module is the **pure** half of the fix — the
parsing / normalisation / capping math. The
``_append_log`` method in ``ui/main_dialog.py``
calls into these helpers + then forwards the
rendered text to ``SetString``. Tests exercise
this module directly without booting Cinema 4D.

Stdlib-only; no Cinema 4D, no network, no PRNG.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


#: Maximum number of lines kept in the in-memory
#: status-log buffer. Beyond this the oldest lines
#: are dropped FIFO. Sized so a busy session doesn't
#: balloon memory (500 lines × ~120 chars/line ≈ 60 KB).
DEFAULT_LOG_BUFFER_LINES: int = 500

#: Default level token used by ``append_entry`` when the
#: caller doesn't supply one.
DEFAULT_LOG_LEVEL: str = "INFO"

#: Canonical level tokens. Anything else is accepted
#: but uppercased before rendering.
KNOWN_LOG_LEVELS = ("DEBUG", "INFO", "WARN", "WARNING", "ERROR")


# ---------------------------------------------------------------------------
# Single-entry formatting
# ---------------------------------------------------------------------------


def normalize_line_endings(text: str) -> str:
    """Map ``\\r\\n`` / ``\\r`` line endings to ``\\n``.

    Strings the dialog receives can arrive from a
    mix of platforms (offline-CLI output, mission
    JSONs hand-edited on Windows, etc.). Normalising
    upfront means the rest of the helper sees one
    consistent newline shape."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def format_log_entry(
    message: str,
    *,
    level: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> List[str]:
    """Produce a list of *physical lines* for one log
    entry.

    A single ``message`` can contain embedded newlines
    (e.g. a multi-line traceback). Each physical line
    is returned separately so the buffer stores one
    line per entry — never a single string with
    embedded newlines that the widget might collapse.

    Empty / whitespace-only messages produce an empty
    list (the caller drops them).

    ``level`` (case-insensitive) prefixes every
    physical line with ``[LEVEL]`` so a multi-line
    traceback's continuation lines stay tagged with
    their severity.

    ``timestamp`` is prepended verbatim before the
    level prefix when supplied. The caller is in
    charge of formatting (e.g. ``"HH:MM:SS"``); the
    helper doesn't impose a clock convention.
    """
    if message is None:
        return []
    text = normalize_line_endings(str(message)).strip("\n")
    # Drop whitespace-only entries entirely (e.g. a
    # caller that hands in ``"   "`` or ``"\n\n"``);
    # such entries are UI artefacts, not real log
    # content + would otherwise produce a phantom
    # blank line in the rendered buffer.
    if not text or not text.strip():
        return []
    raw_lines = text.split("\n")
    prefix_parts: List[str] = []
    if timestamp:
        prefix_parts.append(str(timestamp).strip())
    if level:
        level_token = str(level).upper().strip()
        if level_token:
            prefix_parts.append(f"[{level_token}]")
    prefix = (" ".join(prefix_parts) + " ") if prefix_parts else ""
    return [prefix + line if prefix else line for line in raw_lines]


# ---------------------------------------------------------------------------
# Buffer
# ---------------------------------------------------------------------------


@dataclass
class LogBuffer:
    """Pure-Python status-log buffer.

    The dialog owns one instance and re-renders the
    Cinema 4D widget after every change. Tests drive
    this dataclass directly without a host.
    """

    max_lines: int = DEFAULT_LOG_BUFFER_LINES
    lines: List[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.lines)

    def __post_init__(self) -> None:
        if self.max_lines < 1:
            raise ValueError("max_lines must be >= 1")

    # ------------------------------------------------------- mutate
    def append(
        self,
        message: str,
        *,
        level: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> int:
        """Append one entry. Returns the number of
        *physical lines* added (0 when the message
        was empty)."""
        entries = format_log_entry(
            message, level=level, timestamp=timestamp,
        )
        if not entries:
            return 0
        self.lines.extend(entries)
        if len(self.lines) > self.max_lines:
            # Drop oldest. Slicing is O(N) but the
            # cap is small + this only runs after the
            # buffer fills.
            self.lines = self.lines[-self.max_lines:]
        return len(entries)

    def clear(self) -> None:
        self.lines.clear()

    # ------------------------------------------------------- render
    def render(self) -> str:
        """Render the buffer for display. Lines are
        joined with ``\\n`` and the result ends with
        a trailing ``\\n`` so the widget's cursor
        sits on a fresh blank line (which most C4D
        builds auto-scroll to)."""
        if not self.lines:
            return ""
        return "\n".join(self.lines) + "\n"

    def render_for_export(self) -> str:
        """Same shape as ``render`` but without the
        trailing blank line — exported logs shouldn't
        carry a stray empty final line.

        Used by the v3.5 issue-report bundler + the
        diagnostics panel's *Copy* button so the
        clipboard contents match what the user sees
        in the panel."""
        return "\n".join(self.lines)

    # ------------------------------------------------------- snapshot
    def snapshot(self) -> List[str]:
        """Return a copy of the line list. Safe to
        iterate while the buffer is being mutated."""
        return list(self.lines)


# ---------------------------------------------------------------------------
# Convenience timestamp helper
# ---------------------------------------------------------------------------


def utc_timestamp() -> str:
    """``HH:MM:SS`` UTC timestamp. Used by the
    dialog when the caller doesn't supply one."""
    return time.strftime("%H:%M:%S", time.gmtime())
