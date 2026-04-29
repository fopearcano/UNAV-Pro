"""Shared CSV / null-handling helpers for catalog connectors.

Every connector (Gaia, SDSS, DESI, …) parses raw archive responses
that carry numeric and integer columns with archive-specific
"missing" sentinels (``""``, ``"null"``, ``"NaN"``, ``"None"``) and
plain CSV bodies (sometimes with a leading ``#``-prefixed banner
line). Repeating the same coercion + parsing code in every
connector was the biggest source of duplicated logic in the data
layer; this module is the single source of truth.

No c4d dependency. Pure CPython, fully unit-tested.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, Iterable, Optional

#: String tokens connectors accept as "this cell is missing." Treated
#: case-insensitively. Empty string (``""``) is always missing too.
NULL_TOKENS = frozenset({"null", "nan", "none"})


def to_float(value: Any) -> Optional[float]:
    """Coerce a CSV cell into a Python float, or ``None`` if missing.

    Accepts empty strings, archive-specific ``"null"`` / ``"NaN"`` /
    ``"None"`` tokens (case-insensitive), and NaN floats. Anything
    that does not parse as a finite number returns ``None`` rather
    than raising — connectors must never abort an import because of
    a single corrupt cell.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, float):
        # NaN is "missing" by convention.
        return None if value != value else value
    if isinstance(value, int):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in NULL_TOKENS:
        return None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


def to_int(value: Any) -> Optional[int]:
    """Coerce a CSV cell into a Python int, or ``None`` if missing.

    Accepts everything ``to_float`` accepts and truncates toward zero.
    Returns ``None`` for un-parseable, missing, or overflowing values.
    """
    parsed = to_float(value)
    if parsed is None:
        return None
    try:
        return int(parsed)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_csv(
    body: str,
    *,
    strip_leading_comments: bool = False,
) -> Iterable[Dict[str, str]]:
    """Parse a CSV response body into ``{column: value}`` dict rows.

    With ``strip_leading_comments=True`` (used by SDSS SkyServer),
    any leading ``#``-prefixed lines are dropped before parsing; the
    real header row is whichever line follows the banner.

    Returns an empty iterator (never raises) for empty bodies or
    bodies that ``csv.DictReader`` can't find a header in. Connectors
    that need archive-specific recovery should call this and layer
    their own retry logic above.
    """
    if not body:
        return iter([])
    if strip_leading_comments:
        lines = body.splitlines()
        while lines and lines[0].lstrip().startswith("#"):
            lines.pop(0)
        if not lines:
            return iter([])
        body = "\n".join(lines)
    reader = csv.DictReader(io.StringIO(body))
    if reader.fieldnames is None:
        return iter([])
    return reader
