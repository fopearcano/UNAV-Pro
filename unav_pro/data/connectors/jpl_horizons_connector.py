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
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from core.logging_util import get_logger
from data.schema import CatalogObject, OBJECT_TYPES

_log = get_logger("data.connectors.jpl_horizons")

#: Public JPL Horizons web API endpoint.
JPL_HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

#: Internal release token. Kept for the metadata blob even though
#: the catalog_source label is human-readable.
SOURCE_NAME = "jpl_horizons"

#: Human-readable label written into every emitted ``CatalogObject``.
#: Distinct from ``SOURCE_NAME`` (the internal token, preserved in
#: ``metadata_json``) so the inspector and dataset manager show
#: "JPL Horizons" rather than ``jpl_horizons``.
CATALOG_SOURCE_LABEL = "JPL Horizons"

#: Default observer center. ``@10`` is the Sun (heliocentric); ``@0``
#: is the Solar System Barycenter; ``500@399`` is Earth geocentric.
#: Heliocentric is the natural choice for static point generation —
#: distances are physically meaningful and the frame is stable across
#: bodies. ``500@10`` is an alias for the Sun.
DEFAULT_CENTER = "@10"

#: Object types we recognize for ``--object-type``. The schema's full
#: list is broader; we restrict to the categories the CLI advertises.
ALLOWED_OBJECT_TYPES: Tuple[str, ...] = (
    "planet", "moon", "asteroid", "comet", "spacecraft", "unknown",
)
DEFAULT_OBJECT_TYPE = "planet"

#: Above this many bodies in a batch fetch the CLI prints a soft
#: warning. The hard ceiling is enforced separately at the CLI; this
#: is advisory.
SOFT_BATCH_WARNING = 25

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
    # Approximate distance in km, useful for the inspector and any
    # downstream tools that prefer SI units. 1 AU = 1.49597870700e8 km.
    distance_km = math.sqrt(x_au * x_au + y_au * y_au + z_au * z_au) * 1.495978707e8

    extra: Dict[str, Any] = {
        "release": SOURCE_NAME,
        "body": query.body,
        "epoch": query.epoch,
        "center": query.center,
        "ref_plane": "ICRF",
        "vector_au": {"X": x_au, "Y": y_au, "Z": z_au},
        "vector_pc": {"X": x_pc, "Y": y_pc, "Z": z_pc},
        "out_units": "AU-D",
        "distance_au": math.sqrt(x_au * x_au + y_au * y_au + z_au * z_au),
        "distance_km": distance_km,
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
    obj = CatalogObject(
        uid=uid,
        catalog_source=CATALOG_SOURCE_LABEL,
        object_type=query.object_type,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        distance_parsec=distance_pc if distance_pc > 0.0 else None,
        name=query.body,
        common_name=query.body,
        metadata_json=json.dumps(extra, sort_keys=True),
    )
    # Populate cartesian + c4d fields directly from the Horizons
    # vector so the streaming pipeline does not have to round-trip
    # through ra/dec/distance. Default scale is "pc" — c4d_x/y/z
    # equal cartesian_x/y/z. The visible-sector builder recomputes
    # for non-pc scale_modes via ``compute_derived_fields``.
    obj.cartesian_x, obj.cartesian_y, obj.cartesian_z = x_pc, y_pc, z_pc
    obj.c4d_x, obj.c4d_y, obj.c4d_z = x_pc, y_pc, z_pc
    return obj


def _uid_segment(value: str) -> str:
    """Slug a single uid segment: replace whitespace and slashes with
    underscores. Keeps colons / dots / dashes / underscores so an
    ISO epoch like ``2026-01-01T00:00:00`` survives unchanged."""
    cleaned = re.sub(r"[\s/]+", "_", (value or "").strip())
    cleaned = re.sub(r"[^A-Za-z0-9._:_-]+", "_", cleaned)
    return cleaned.strip("_") or "x"


def _make_uid(query: JPLBodyQuery) -> str:
    """``jpl:{body}:{epoch}`` — release-agnostic, registry-namespaced
    later. Both segments are lightly slugged so whitespace becomes
    ``_`` but ISO timestamps' colons survive."""
    return f"jpl:{_uid_segment(query.body)}:{_uid_segment(query.epoch)}"


def fetch_and_normalize(
    query: JPLBodyQuery,
    fetch_fn: Optional[FetchFn] = None,
    url: str = JPL_HORIZONS_URL,
) -> CatalogObject:
    """Convenience: ``fetch_response`` + ``parse_response`` in one call."""
    response = fetch_response(query, fetch_fn=fetch_fn, url=url)
    return parse_response(response, query)


# ---------------------------------------------------------------------------
# Batch — one epoch, many bodies
# ---------------------------------------------------------------------------


from dataclasses import field as _field
from typing import List as _List


@dataclass
class BatchBodyRequest:
    """One row in a batch request: a body and its UNAV object_type tag."""

    body: str
    object_type: str = DEFAULT_OBJECT_TYPE


@dataclass
class BatchResult:
    """Outcome of ``fetch_batch_and_normalize``.

    Per-body errors do not abort the batch; they are recorded in
    ``errors`` so the CLI can surface them and continue writing the
    objects that did succeed.
    """

    objects: _List[CatalogObject] = _field(default_factory=list)
    errors: _List[Tuple[str, str]] = _field(default_factory=list)
    warnings: _List[str] = _field(default_factory=list)

    @property
    def kept(self) -> int:
        return len(self.objects)

    @property
    def failed(self) -> int:
        return len(self.errors)

    def short_summary(self) -> str:
        parts = [f"kept {self.kept}"]
        if self.failed:
            parts.append(f"{self.failed} failed")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return ", ".join(parts)


def fetch_batch_and_normalize(
    requests: Sequence[BatchBodyRequest],
    epoch: str,
    *,
    center: str = DEFAULT_CENTER,
    fetch_fn: Optional[FetchFn] = None,
    url: str = JPL_HORIZONS_URL,
) -> BatchResult:
    """Fetch every body in ``requests`` at the same ``epoch``.

    Per-body failures are recorded in ``BatchResult.errors`` and
    skipped; the remaining bodies still flow through. Returns the
    merged result.

    The batch runs sequentially — Horizons's web API is one body per
    call, and the public archive is rate-sensitive. For a typical
    "Sun + 8 planets + Moon" batch this takes ~20 seconds against
    the live endpoint.
    """
    out = BatchResult()
    if len(requests) > SOFT_BATCH_WARNING:
        out.warnings.append(
            f"batch contains {len(requests)} bodies (above the "
            f"{SOFT_BATCH_WARNING} soft threshold); the public Horizons "
            "archive may be slow. Consider splitting into smaller batches."
        )
    for req in requests:
        try:
            query = JPLBodyQuery(
                body=req.body, epoch=epoch, center=center,
                object_type=req.object_type,
            )
        except ValueError as exc:
            out.errors.append((req.body, f"invalid query: {exc}"))
            continue
        try:
            obj = fetch_and_normalize(query, fetch_fn=fetch_fn, url=url)
        except JPLHorizonsError as exc:
            out.errors.append((req.body, str(exc)))
            _log.warning("Batch: %s failed: %s", req.body, exc)
            continue
        out.objects.append(obj)
    return out


# ---------------------------------------------------------------------------
# CLI-friendly one-shot
# ---------------------------------------------------------------------------


@dataclass
class FetchAndWriteReport:
    """Outcome of ``fetch_normalize_and_write``."""

    output_path: str
    object_count: int = 0
    failed: int = 0
    warnings: _List[str] = _field(default_factory=list)
    errors: _List[Tuple[str, str]] = _field(default_factory=list)
    index_path: Optional[str] = None
    index_total_objects: Optional[int] = None
    index_cell_count: Optional[int] = None


def fetch_single_normalize_and_write(
    query: JPLBodyQuery,
    output_path: str,
    *,
    fetch_fn: Optional[FetchFn] = None,
    url: str = JPL_HORIZONS_URL,
    build_index_dir: Optional[str] = None,
    index_chunk_size: int = 1_000,
) -> FetchAndWriteReport:
    """End-to-end single-body: fetch + normalize + write JSONL +
    optionally build the spatial index. Mirrors the Gaia connector's
    matching helper so the CLIs look uniform."""
    obj = fetch_and_normalize(query, fetch_fn=fetch_fn, url=url)

    from data.catalog_io import write_catalog

    write_catalog([obj], output_path, fmt="jsonl", compute_derived=False)

    report = FetchAndWriteReport(output_path=output_path, object_count=1)
    if build_index_dir:
        from core.spatial_index import build_index

        index = build_index(
            [obj], build_index_dir, chunk_size=index_chunk_size,
        )
        report.index_path = build_index_dir
        report.index_total_objects = index.total_objects
        report.index_cell_count = len(index.cells)
    return report


def fetch_batch_normalize_and_write(
    requests: Sequence[BatchBodyRequest],
    epoch: str,
    output_path: str,
    *,
    center: str = DEFAULT_CENTER,
    fetch_fn: Optional[FetchFn] = None,
    url: str = JPL_HORIZONS_URL,
    build_index_dir: Optional[str] = None,
    index_chunk_size: int = 1_000,
) -> FetchAndWriteReport:
    """End-to-end batch: fetch every body in ``requests`` at the
    same epoch, write the merged JSONL, optionally build the
    spatial index. Partial failure is recorded in
    ``report.errors`` — the bodies that did succeed still get
    written and indexed."""
    batch = fetch_batch_and_normalize(
        requests, epoch, center=center, fetch_fn=fetch_fn, url=url,
    )

    from data.catalog_io import write_catalog

    write_catalog(batch.objects, output_path, fmt="jsonl", compute_derived=False)

    report = FetchAndWriteReport(
        output_path=output_path,
        object_count=batch.kept,
        failed=batch.failed,
        warnings=list(batch.warnings),
        errors=list(batch.errors),
    )

    if build_index_dir and batch.objects:
        from core.spatial_index import build_index

        index = build_index(
            batch.objects, build_index_dir, chunk_size=index_chunk_size,
        )
        report.index_path = build_index_dir
        report.index_total_objects = index.total_objects
        report.index_cell_count = len(index.cells)
    return report
