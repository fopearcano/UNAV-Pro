"""Gaia connector — fetch a small sky region and normalize to UNAV.

Targets the public Gaia ESA archive's TAP (Table Access Protocol)
sync endpoint with an ADQL cone-search query. Stdlib-only:
``urllib`` for HTTP, ``csv`` for the response, the local schema
module for the canonical output. No ``astroquery``, no ``astropy``,
no credentials required.

Scope
-----

  * **Read-only.** Cone queries with a row cap.
  * **Small regions.** The CLI default is 1°/5 000 rows; the
    connector itself enforces an upper bound so a typo cannot pull
    millions of rows.
  * **Single source release.** Defaults to ``gaiadr3.gaia_source``.
    Any future release is a one-line constant change.
  * **Local sample / mock-friendly.** ``fetch_rows(..., fetch_fn=...)``
    accepts an injected fetcher so tests run without network access.

Coordinate / unit handling
--------------------------

Gaia returns parallax in milliarcseconds (mas). UNAV's canonical
schema expects ``parallax_mas`` in mas and ``distance_parsec`` in pc.
Distance is derived only when the parallax is positive and meets a
caller-configurable signal-to-noise floor (default 5.0). All other
cases leave ``distance_parsec`` as ``None``; the schema then falls
back to the placeholder sphere at compute-derived time, which keeps
the rest of the pipeline well-defined for noisy rows.

Failure modes
-------------

  * Network errors → raised as ``GaiaQueryError`` with the original
    URL + status. The CLI catches them and exits non-zero.
  * Parse errors on individual rows → counted, logged, skipped. A
    handful of bad rows must not abort a 5 000-row query.
  * The Gaia archive rate-limiting → respect HTTP 429 / 503 by
    surfacing them in the exception. The MVP does not retry; let
    the operator wait and rerun.

The full canonical pipeline schema is in
``docs/UNAV_PRO_DATA_PIPELINE.md`` §4. This connector populates a
strict subset (the local-format schema in
``unav_pro/data/schema.py``).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from core.logging_util import get_logger
from data.connectors._normalize import parse_csv as _parse_csv, to_float as _to_float
from data.schema import CatalogObject

_log = get_logger("data.connectors.gaia")

#: Public ESA Gaia archive TAP endpoint (synchronous).
GAIA_TAP_SYNC_URL = "https://gea.esac.esa.int/tap-server/tap/sync"

#: Default release the connector queries.
DEFAULT_GAIA_RELEASE = "gaia_dr3"
_RELEASE_TO_TABLE = {
    "gaia_dr3": "gaiadr3.gaia_source",
    "gaia_dr2": "gaiadr2.gaia_source",
}

#: Hard ceiling on row count, regardless of what the caller asks for.
#: A polite limit on the public archive and a guardrail against typo'd
#: --limit values.
MAX_ROW_LIMIT = 100_000

#: Hard ceiling on cone radius (degrees). Beyond this the caller
#: should be using HEALPix tiling, not single-region queries.
MAX_RADIUS_DEG = 30.0

#: Default parallax signal-to-noise floor. Below this we leave
#: ``distance_parsec`` as None; the row still flows through.
DEFAULT_PARALLAX_SNR_MIN = 5.0

_USER_AGENT = "UNAV-Pro/0.1 (+https://example.invalid/unav-pro)"

#: Columns we ask Gaia to return. Keep the list short and explicit so
#: a schema change in the archive surfaces here, not in the
#: normalizer.
_GAIA_COLUMNS: tuple = (
    "source_id",
    "ra", "dec",
    "parallax", "parallax_error",
    "pmra", "pmdec",
    "radial_velocity",
    "phot_g_mean_mag",
    "bp_rp",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GaiaQueryError(Exception):
    """Raised for unrecoverable network / archive errors."""


# ---------------------------------------------------------------------------
# Query model
# ---------------------------------------------------------------------------


@dataclass
class GaiaQuery:
    """Cone query parameters. Validated at construction."""

    ra_deg: float
    dec_deg: float
    radius_deg: float
    limit: int = 5_000
    release: str = DEFAULT_GAIA_RELEASE

    def __post_init__(self) -> None:
        if not (0.0 <= self.ra_deg < 360.0):
            raise ValueError(f"ra_deg out of range [0, 360): {self.ra_deg}")
        if not (-90.0 <= self.dec_deg <= 90.0):
            raise ValueError(f"dec_deg out of range [-90, 90]: {self.dec_deg}")
        if not (0.0 < self.radius_deg <= MAX_RADIUS_DEG):
            raise ValueError(
                f"radius_deg out of range (0, {MAX_RADIUS_DEG}]: {self.radius_deg}"
            )
        if not (0 < self.limit <= MAX_ROW_LIMIT):
            raise ValueError(
                f"limit out of range (0, {MAX_ROW_LIMIT}]: {self.limit}"
            )
        if self.release not in _RELEASE_TO_TABLE:
            raise ValueError(
                f"unknown release '{self.release}'; "
                f"valid: {', '.join(_RELEASE_TO_TABLE.keys())}"
            )


# ---------------------------------------------------------------------------
# ADQL
# ---------------------------------------------------------------------------


def build_adql(query: GaiaQuery) -> str:
    """Render the ADQL cone query Gaia's TAP endpoint will execute.

    Brightest objects first so a user-supplied ``--limit`` is biased
    toward visible stars rather than the noise floor.
    """
    table = _RELEASE_TO_TABLE[query.release]
    cols = ", ".join(_GAIA_COLUMNS)
    return (
        f"SELECT TOP {query.limit} {cols} "
        f"FROM {table} "
        f"WHERE 1=CONTAINS("
        f"POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {query.ra_deg}, {query.dec_deg}, {query.radius_deg})"
        f") "
        f"ORDER BY phot_g_mean_mag ASC"
    )


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


FetchFn = Callable[[str, Dict[str, str]], str]


def _http_fetch(url: str, params: Dict[str, str]) -> str:
    """Default fetcher: synchronous POST to the TAP sync endpoint.

    Returns the response body as a CSV string. Raises
    ``GaiaQueryError`` on any network or HTTP-status failure.
    """
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/csv",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status != 200:
                raise GaiaQueryError(
                    f"Gaia TAP returned HTTP {resp.status}: {body[:300]!r}"
                )
            return body
    except urllib.error.HTTPError as exc:
        raise GaiaQueryError(
            f"Gaia TAP HTTP {exc.code} for {url}: {exc.read()[:300]!r}"
        ) from exc
    except urllib.error.URLError as exc:
        raise GaiaQueryError(f"Gaia TAP network error: {exc.reason!r}") from exc


def fetch_rows(
    query: GaiaQuery,
    fetch_fn: Optional[FetchFn] = None,
    url: str = GAIA_TAP_SYNC_URL,
) -> List[Dict[str, str]]:
    """Run ``query`` against the Gaia archive and return raw rows.

    Each row is a ``{column_name: cell_string}`` dict; numeric
    conversion happens later in ``normalize_rows`` so this function's
    behavior is deterministic for tests.

    ``fetch_fn`` is injectable: pass a callable
    ``(url, params) -> csv_text`` to bypass the network in tests.
    """
    fetcher = fetch_fn or _http_fetch
    adql = build_adql(query)
    params = {
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": adql,
    }
    _log.info(
        "Gaia TAP query: ra=%.4f dec=%.4f radius=%.3f limit=%d release=%s",
        query.ra_deg, query.dec_deg, query.radius_deg, query.limit, query.release,
    )
    body = fetcher(url, params)
    return list(_parse_csv(body))


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def safe_parallax_to_distance(
    parallax_mas: Optional[float],
    parallax_error_mas: Optional[float] = None,
    snr_min: float = DEFAULT_PARALLAX_SNR_MIN,
    distance_pc_max: float = 1.0e5,
) -> Optional[float]:
    """Convert parallax to distance only when the result is trustworthy.

    Returns ``None`` if any of these hold:

      * parallax is missing or ≤ 0 (negative-parallax noise);
      * parallax error is provided and ``parallax / error < snr_min``;
      * the implied distance exceeds ``distance_pc_max`` (Bayesian
        priors dominate beyond this and a naive ``1000/parallax`` is
        misleading).

    Otherwise returns ``1000.0 / parallax_mas`` in pc.
    """
    if parallax_mas is None or parallax_mas <= 0.0:
        return None
    if parallax_error_mas is not None and parallax_error_mas > 0.0:
        if (parallax_mas / parallax_error_mas) < snr_min:
            return None
    distance = 1000.0 / parallax_mas
    if distance > distance_pc_max:
        return None
    return distance


def _row_to_object(
    row: Dict[str, str],
    release: str,
    parallax_snr_min: float,
) -> Optional[CatalogObject]:
    """Map one Gaia row to a UNAV ``CatalogObject``. Returns None for
    fundamentally unusable rows (missing source_id / ra / dec)."""
    source_id = (row.get("source_id") or "").strip()
    ra = _to_float(row.get("ra"))
    dec = _to_float(row.get("dec"))
    if not source_id or ra is None or dec is None:
        return None
    if not (0.0 <= ra < 360.0) or not (-90.0 <= dec <= 90.0):
        return None

    parallax = _to_float(row.get("parallax"))
    parallax_err = _to_float(row.get("parallax_error"))
    distance_pc = safe_parallax_to_distance(
        parallax, parallax_err, snr_min=parallax_snr_min,
    )

    extra = {
        "source_id": source_id,
        "release": release,
        "parallax_error_mas": parallax_err,
    }

    return CatalogObject(
        uid=f"{release}:{source_id}",
        catalog_source=release,
        object_type="star",
        ra_deg=ra,
        dec_deg=dec,
        distance_parsec=distance_pc,
        parallax_mas=parallax,
        radial_velocity_kms=_to_float(row.get("radial_velocity")),
        proper_motion_ra=_to_float(row.get("pmra")),
        proper_motion_dec=_to_float(row.get("pmdec")),
        apparent_magnitude=_to_float(row.get("phot_g_mean_mag")),
        color_index=_to_float(row.get("bp_rp")),
        name=source_id,
        metadata_json=json.dumps(extra, sort_keys=True),
    )


def normalize_rows(
    rows: Sequence[Dict[str, str]],
    release: str = DEFAULT_GAIA_RELEASE,
    parallax_snr_min: float = DEFAULT_PARALLAX_SNR_MIN,
) -> List[CatalogObject]:
    """Convert raw Gaia CSV rows into UNAV ``CatalogObject``s.

    Bad rows (missing identifier / position) are counted in the log
    and skipped — a single corrupt cell must not abort the import.
    """
    out: List[CatalogObject] = []
    skipped = 0
    for raw in rows:
        obj = _row_to_object(raw, release=release, parallax_snr_min=parallax_snr_min)
        if obj is None:
            skipped += 1
            continue
        out.append(obj)
    if skipped:
        _log.warning("Skipped %d unusable Gaia rows during normalization.", skipped)
    return out


# ---------------------------------------------------------------------------
# One-shot helper
# ---------------------------------------------------------------------------


def fetch_and_normalize(
    query: GaiaQuery,
    fetch_fn: Optional[FetchFn] = None,
    url: str = GAIA_TAP_SYNC_URL,
    parallax_snr_min: float = DEFAULT_PARALLAX_SNR_MIN,
) -> List[CatalogObject]:
    """Convenience: ``fetch_rows`` + ``normalize_rows`` in one call."""
    rows = fetch_rows(query, fetch_fn=fetch_fn, url=url)
    return normalize_rows(
        rows, release=query.release, parallax_snr_min=parallax_snr_min,
    )
