"""NASA/JPL Horizons connector — single-body ephemeris at a given epoch.

Targets the public JPL Horizons web API
(``https://ssd.jpl.nasa.gov/api/horizons.api``) for one body at a
time. Stdlib-only: ``urllib`` for HTTP, ``json`` to unwrap the
response, ``re`` to extract labelled vector components from the
ephemeris text.

Scope
-----

  * **One body, one epoch.** The connector requests a single
    24-hour window with a one-day step so Horizons returns exactly
    one ephemeris row.
  * **Heliocentric ICRF Cartesian** (``CENTER='@10'``,
    ``REF_PLANE='FRAME'``, ``OUT_UNITS='AU-D'``). The plugin's
    canonical position is ICRS Cartesian; heliocentric is the
    smallest-error reference frame for solar-system bodies and lines
    up directly with the schema's ``cartesian_*`` columns after a
    units conversion.
  * **No live animation.** A static point at the requested epoch
    only; per-epoch sampling and SPK kernels are deferred (see
    ``UNAV_PRO_DATA_PIPELINE.md`` §5).
  * **Mock-friendly.** ``fetch_response(..., fetch_fn=...)`` accepts
    an injected fetcher so tests run without network access.

Output
------

One ``CatalogObject`` per call, with:

  * ``catalog_source = "jpl_horizons"``,
  * ``object_type`` from the caller (``planet``, ``moon``, ``asteroid``,
    ``comet``, ``spacecraft``),
  * ``ra_deg`` / ``dec_deg`` / ``distance_parsec`` derived from the
    heliocentric ICRF (X, Y, Z) vector,
  * ``metadata_json`` carrying the raw vector components, the epoch,
    the observer center, the body designation, and the Horizons
    API ``signature``/``version`` block when present.

The schema's ``compute_derived_fields`` will populate
``cartesian_*`` and ``c4d_*`` from the spherical fields at index /
load time, the same as for any other catalog row.

Failure modes
-------------

  * Network / HTTP error → ``JPLHorizonsError``.
  * Body designation matches multiple objects (Horizons returns a
    "Multiple matches" body block) → ``JPLHorizonsError`` with the
    list of candidates so the caller can re-query with a specific
    name.
  * Body has no ephemeris in the requested window (e.g. spacecraft
    after end-of-mission) → ``JPLHorizonsError`` with the Horizons
    error text.
  * Vector parse failure → ``JPLHorizonsError`` with the offending
    block.

The CLI catches all of the above and exits non-zero with a message.
"""

from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from core.logging_util import get_logger
from data.schema import CatalogObject, OBJECT_TYPES

_log = get_logger("data.connectors.jpl_horizons")

#: Public JPL Horizons web API endpoint.
JPL_HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

#: Catalog source recorded on every CatalogObject we emit.
SOURCE_NAME = "jpl_horizons"

#: Default observer center. ``@10`` is the Sun (heliocentric); ``@0``
#: is the Solar System Barycenter; ``500@399`` is Earth geocentric.
#: Heliocentric is the natural choice for static point generation —
#: distances are physically meaningful and the frame is stable across
#: bodies.
DEFAULT_CENTER = "@10"

#: Object types we recognize for ``--object-type``. The schema's full
#: list is broader; we restrict to the categories the CLI advertises.
ALLOWED_OBJECT_TYPES: Tuple[str, ...] = (
    "planet", "moon", "asteroid", "comet", "spacecraft",
)
DEFAULT_OBJECT_TYPE = "planet"

#: 1 astronomical unit in parsec. Definition value (IAU 2012 / 2015):
#: 1 pc = 648000/π AU ⇒ 1 AU = π/648000 pc ≈ 4.84813681e-6 pc.
_AU_PER_PC = 648_000.0 / math.pi
AU_TO_PC = 1.0 / _AU_PER_PC

_USER_AGENT = "UNAV-Pro/0.1 (+https://example.invalid/unav-pro)"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class JPLHorizonsError(Exception):
    """Raised for unrecoverable connector / archive errors."""


# ---------------------------------------------------------------------------
# Query model
# ---------------------------------------------------------------------------


@dataclass
class JPLBodyQuery:
    """Single-body, single-epoch ephemeris request."""

    body: str
    epoch: str  # ISO-8601 date ("2026-01-01") or anything Horizons accepts
    center: str = DEFAULT_CENTER
    object_type: str = DEFAULT_OBJECT_TYPE
    stop_epoch: Optional[str] = None
    step_size: str = "1d"

    def __post_init__(self) -> None:
        if not self.body or not self.body.strip():
            raise ValueError("body must be a non-empty designation")
        if not self.epoch or not self.epoch.strip():
            raise ValueError("epoch must be a non-empty time string")
        if self.object_type not in ALLOWED_OBJECT_TYPES:
            raise ValueError(
                f"object_type '{self.object_type}' not in "
                f"{ALLOWED_OBJECT_TYPES}"
            )
        if self.object_type not in OBJECT_TYPES:
            # Defensive: if the schema is later trimmed, surface it here.
            raise ValueError(
                f"object_type '{self.object_type}' is not declared in "
                f"the local schema's OBJECT_TYPES"
            )
        if not self.center or not self.center.strip():
            raise ValueError("center must be a non-empty designation")

    def effective_stop(self) -> str:
        """Stop time defaults to the start time + 1 day (Horizons
        rejects equal start/stop). Callers that want a custom stop
        can set ``stop_epoch`` explicitly."""
        if self.stop_epoch:
            return self.stop_epoch
        # Horizons accepts a "JD + N" expression; this also works for
        # named days. We use a literal "+1d" suffix so we don't have
        # to parse arbitrary calendar formats.
        return f"{self.epoch} +1d"


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------


def _q(value: str) -> str:
    """Wrap a Horizons string parameter in single quotes."""
    return f"'{value}'"


def build_request_params(query: JPLBodyQuery) -> Dict[str, str]:
    """Return the GET params Horizons expects for one VECTORS query."""
    return {
        "format": "json",
        "COMMAND": _q(query.body),
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "VECTORS",
        "CENTER": _q(query.center),
        "START_TIME": _q(query.epoch),
        "STOP_TIME": _q(query.effective_stop()),
        "STEP_SIZE": _q(query.step_size),
        "OUT_UNITS": _q("AU-D"),
        "REF_PLANE": _q("FRAME"),     # ICRF (J2000), not ecliptic
        "VEC_LABELS": "YES",
        "VEC_TABLE": "2",             # state vector + LT/range
    }


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------


FetchFn = Callable[[str, Dict[str, str]], str]


def _http_fetch(url: str, params: Dict[str, str]) -> str:
    """Default fetcher: GET to Horizons. Returns the raw body."""
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        full,
        method="GET",
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status != 200:
                raise JPLHorizonsError(
                    f"Horizons HTTP {resp.status}: {body[:300]!r}"
                )
            return body
    except urllib.error.HTTPError as exc:
        try:
            payload = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            payload = "<unreadable>"
        raise JPLHorizonsError(
            f"Horizons HTTP {exc.code}: {payload[:300]!r}"
        ) from exc
    except urllib.error.URLError as exc:
        raise JPLHorizonsError(
            f"Horizons network error: {exc.reason!r}"
        ) from exc


def fetch_response(
    query: JPLBodyQuery,
    fetch_fn: Optional[FetchFn] = None,
    url: str = JPL_HORIZONS_URL,
) -> Dict[str, Any]:
    """Run ``query`` against Horizons and return the parsed JSON dict.

    The returned object includes a ``"result"`` key whose value is
    Horizons's free-form text ephemeris; downstream code parses that
    to extract the state vector.
    """
    fetcher = fetch_fn or _http_fetch
    params = build_request_params(query)
    _log.info(
        "JPL Horizons query: body=%r epoch=%r center=%r",
        query.body, query.epoch, query.center,
    )
    body = fetcher(url, params)
    try:
        return json.loads(body)
    except (TypeError, ValueError) as exc:
        raise JPLHorizonsError(
            f"Horizons response is not valid JSON: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


_MULTIPLE_MATCH_MARKERS = (
    "Multiple major-bodies match",
    "Multiple major-body matches",
    "Multiple matching small-bodies",
    "Matching small-bodies",
)


def _detect_multiple_matches(text: str) -> Optional[str]:
    """Return the candidates block if Horizons returned an ambiguous
    match list, else None."""
    for marker in _MULTIPLE_MATCH_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            return text[idx:idx + 1500]
    return None


def _detect_no_matches(text: str) -> bool:
    return "No matches found" in text or "No such body" in text


_SOE = "$$SOE"
_EOE = "$$EOE"


def _extract_ephem_block(text: str) -> str:
    soe = text.find(_SOE)
    eoe = text.find(_EOE)
    if soe == -1 or eoe == -1 or eoe <= soe:
        raise JPLHorizonsError(
            "Horizons response did not contain a $$SOE/$$EOE block"
        )
    return text[soe + len(_SOE):eoe]


_LABEL_RE = re.compile(r"(?<![A-Za-z_])([A-Z]{1,3})\s*=\s*([-+0-9.Ee]+)")


def _parse_labels(block: str) -> Dict[str, float]:
    """Pull every ``LABEL = NUMBER`` pair out of a vectors block."""
    out: Dict[str, float] = {}
    for m in _LABEL_RE.finditer(block):
        try:
            out[m.group(1)] = float(m.group(2))
        except (TypeError, ValueError):
            continue
    return out


def _xyz_pc_from_au(x_au: float, y_au: float, z_au: float) -> Tuple[float, float, float]:
    return x_au * AU_TO_PC, y_au * AU_TO_PC, z_au * AU_TO_PC


def _ra_dec_distance_pc(x_pc: float, y_pc: float, z_pc: float) -> Tuple[float, float, float]:
    distance = math.sqrt(x_pc * x_pc + y_pc * y_pc + z_pc * z_pc)
    if distance == 0.0:
        return 0.0, 0.0, 0.0
    dec_deg = math.degrees(math.asin(z_pc / distance))
    ra_deg = math.degrees(math.atan2(y_pc, x_pc)) % 360.0
    return ra_deg, dec_deg, distance


# ---------------------------------------------------------------------------
# Top-level normalize
# ---------------------------------------------------------------------------


def parse_response(
    response: Dict[str, Any], query: JPLBodyQuery,
) -> CatalogObject:
    """Convert a Horizons JSON response into one ``CatalogObject``."""
    text = response.get("result")
    if not isinstance(text, str) or not text:
        raise JPLHorizonsError("Horizons response has no 'result' text")

    multiple = _detect_multiple_matches(text)
    if multiple:
        raise JPLHorizonsError(
            f"Horizons body designation '{query.body}' is ambiguous; "
            f"refine the name or pass a NAIF ID. Candidates excerpt: "
            f"{multiple[:500]!r}"
        )
    if _detect_no_matches(text):
        raise JPLHorizonsError(
            f"Horizons found no body matching '{query.body}'."
        )

    block = _extract_ephem_block(text)
    labels = _parse_labels(block)
    for required in ("X", "Y", "Z"):
        if required not in labels:
            raise JPLHorizonsError(
                f"Horizons vectors block missing '{required}': "
                f"block excerpt {block[:400]!r}"
            )

    x_au, y_au, z_au = labels["X"], labels["Y"], labels["Z"]
    x_pc, y_pc, z_pc = _xyz_pc_from_au(x_au, y_au, z_au)
    ra_deg, dec_deg, distance_pc = _ra_dec_distance_pc(x_pc, y_pc, z_pc)

    extra: Dict[str, Any] = {
        "body": query.body,
        "epoch": query.epoch,
        "center": query.center,
        "ref_plane": "ICRF",
        "vector_au": {"X": x_au, "Y": y_au, "Z": z_au},
        "out_units": "AU-D",
    }
    # Optional extras — keep whatever Horizons handed us.
    for key in ("VX", "VY", "VZ", "LT", "RG", "RR"):
        if key in labels:
            extra[f"{key.lower()}_au_per_d" if key.startswith("V") else key.lower()] = labels[key]
    sig = response.get("signature")
    if isinstance(sig, dict):
        extra["horizons_signature"] = {
            k: sig[k] for k in ("source", "version") if k in sig
        }

    uid = _make_uid(query)
    return CatalogObject(
        uid=uid,
        catalog_source=SOURCE_NAME,
        object_type=query.object_type,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        distance_parsec=distance_pc if distance_pc > 0.0 else None,
        name=query.body,
        common_name=query.body,
        metadata_json=json.dumps(extra, sort_keys=True),
    )


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s.strip()).strip("_") or "body"


def _make_uid(query: JPLBodyQuery) -> str:
    return f"{SOURCE_NAME}:{_slug(query.body)}@{_slug(query.epoch)}"


def fetch_and_normalize(
    query: JPLBodyQuery,
    fetch_fn: Optional[FetchFn] = None,
    url: str = JPL_HORIZONS_URL,
) -> CatalogObject:
    """Convenience: ``fetch_response`` + ``parse_response`` in one call."""
    response = fetch_response(query, fetch_fn=fetch_fn, url=url)
    return parse_response(response, query)
