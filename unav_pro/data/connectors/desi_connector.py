"""DESI connector — cone search against the public DESI EDR / DR1.

Targets the NOIRLab Astro Data Lab TAP service:
``https://datalab.noirlab.edu/tap/sync``. The DESI Early Data Release
is exposed there as ``desi_edr.zpix`` (and ``desi_edr.zall_pix``),
addressable with standard ADQL cone queries.

Stdlib-only: ``urllib`` for HTTP, ``csv`` for the response, the local
schema for canonical output. Stub status — the live HTTP path is in
place but only exercised against mocked responses in this MVP.

Scope
-----

  * **Cone search** around (RA, Dec) with a row cap.
  * **Redshift catalog.** ``zpix`` is the per-target best-redshift
    table; this is what scenes will visualize. Photometric merger
    with imaging surveys (Legacy, BASS, MzLS) is reserved for the
    production crossmatch stage.
  * **Object types covered:** galaxies, quasars, stars (the
    ``SPECTYPE`` column has values ``GALAXY``, ``QSO``, ``STAR``).
  * **Survey metadata.** ``SURVEY``, ``PROGRAM``, and
    ``DESI_TARGET`` are preserved verbatim in ``metadata_json`` so a
    future filter can gate by survey phase (`sv1`, `sv3`, `main`)
    or by target class.
  * **Mock-friendly.** ``fetch_rows(..., fetch_fn=...)`` accepts an
    injected fetcher so tests run without network access.

The full pipeline schema is in ``docs/UNAV_PRO_DATA_PIPELINE.md`` §4.
This connector populates the local-format subset in
``unav_pro/data/schema.py`` and tags every row with
``catalog_source = "desi_edr"`` (or whichever release the caller
chose).

See ``docs/DESI_CONNECTOR.md`` for the full ADQL strategy, target-
bit decoding, and known limitations.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from core.logging_util import get_logger
from data.connectors._normalize import (
    parse_csv as _parse_csv,
    to_float as _to_float,
    to_int as _to_int,
)
from data.schema import CatalogObject

_log = get_logger("data.connectors.desi")

#: Default DESI TAP endpoint via NOIRLab Astro Data Lab.
DESI_TAP_SYNC_URL = "https://datalab.noirlab.edu/tap/sync"

DEFAULT_DESI_RELEASE = "desi_edr"
_RELEASE_TO_TABLE = {
    "desi_edr": "desi_edr.zpix",
    "desi_dr1": "desi_dr1.zpix",
}

MAX_ROW_LIMIT = 100_000
MAX_RADIUS_DEG = 30.0

_USER_AGENT = "UNAV-Pro/0.1 (+https://example.invalid/unav-pro)"

#: DESI ``SPECTYPE`` → UNAV object_type. Anything else falls through
#: to ``"unknown"``.
_SPECTYPE_MAP: Dict[str, str] = {
    "GALAXY": "galaxy",
    "QSO": "quasar",
    "QUASAR": "quasar",
    "STAR": "star",
}

#: Hubble constant for the coarse redshift→distance fallback. Same
#: caveats as the SDSS connector — this is a stand-in for the real
#: cosmology-aware comoving distance.
HUBBLE_KM_S_MPC = 70.0
SPEED_OF_LIGHT_KM_S = 299_792.458
DEFAULT_REDSHIFT_DISTANCE_MAX_Z = 0.1

#: Fields we ask DESI for. ``healpix`` is recorded so a future tile
#: layer can fold these rows into the same HEALPix index used by Gaia.
_DESI_COLUMNS = (
    "targetid",
    "target_ra", "target_dec",
    "z", "zerr", "zwarn",
    "spectype", "subtype",
    "desi_target",
    "survey", "program",
    "healpix",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DESIQueryError(Exception):
    """Raised for unrecoverable DESI connector / archive errors."""


# ---------------------------------------------------------------------------
# Query model
# ---------------------------------------------------------------------------


@dataclass
class DESIQuery:
    ra_deg: float
    dec_deg: float
    radius_deg: float
    limit: int = 5_000
    release: str = DEFAULT_DESI_RELEASE
    spectype: Optional[str] = None  # e.g. "GALAXY" / "QSO" / "STAR"

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
        if self.spectype is not None:
            up = str(self.spectype).strip().upper()
            if up not in _SPECTYPE_MAP and up != "":
                raise ValueError(
                    f"spectype '{self.spectype}' not in "
                    f"{sorted(_SPECTYPE_MAP)}"
                )
            self.spectype = up or None


# ---------------------------------------------------------------------------
# ADQL
# ---------------------------------------------------------------------------


def build_adql(query: DESIQuery) -> str:
    """Render the ADQL cone query for the DESI TAP endpoint."""
    table = _RELEASE_TO_TABLE[query.release]
    cols = ", ".join(_DESI_COLUMNS)
    where = (
        f"1=CONTAINS("
        f"POINT('ICRS', target_ra, target_dec), "
        f"CIRCLE('ICRS', {query.ra_deg}, {query.dec_deg}, {query.radius_deg})"
        f")"
    )
    if query.spectype:
        where += f" AND spectype = '{query.spectype}'"
    return (
        f"SELECT TOP {query.limit} {cols} "
        f"FROM {table} "
        f"WHERE {where} "
        f"ORDER BY z ASC"
    )


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------


FetchFn = Callable[[str, Dict[str, str]], str]


def _http_fetch(url: str, params: Dict[str, str]) -> str:
    """Default fetcher: synchronous POST to the TAP sync endpoint."""
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
                raise DESIQueryError(
                    f"DESI TAP HTTP {resp.status}: {body[:300]!r}"
                )
            return body
    except urllib.error.HTTPError as exc:
        raise DESIQueryError(
            f"DESI TAP HTTP {exc.code}: {exc.read()[:300]!r}"
        ) from exc
    except urllib.error.URLError as exc:
        raise DESIQueryError(
            f"DESI TAP network error: {exc.reason!r}"
        ) from exc


def fetch_rows(
    query: DESIQuery,
    fetch_fn: Optional[FetchFn] = None,
    url: str = DESI_TAP_SYNC_URL,
) -> List[Dict[str, str]]:
    """Run ``query`` against the DESI archive and return raw CSV rows."""
    fetcher = fetch_fn or _http_fetch
    adql = build_adql(query)
    params = {
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": adql,
    }
    _log.info(
        "DESI TAP query: ra=%.4f dec=%.4f radius=%.3f limit=%d release=%s spectype=%s",
        query.ra_deg, query.dec_deg, query.radius_deg, query.limit,
        query.release, query.spectype or "*",
    )
    body = fetcher(url, params)
    return list(_parse_csv(body))


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def safe_redshift_to_distance(
    z: Optional[float],
    z_err: Optional[float] = None,
    zwarn: Optional[int] = None,
    max_z: float = DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
    h0_km_s_mpc: float = HUBBLE_KM_S_MPC,
) -> Optional[float]:
    """Coarse Hubble-law distance in parsec, only when safe.

    Returns ``None`` if:
      * ``z`` is missing or ≤ 0;
      * ``z`` exceeds ``max_z`` (naive Hubble breaks down);
      * ``zwarn`` is non-zero (DESI quality bitmask: any flag means
        the redshift fit is suspect).
    """
    if z is None or z <= 0.0:
        return None
    if zwarn is not None and zwarn != 0:
        return None
    if z > max_z:
        return None
    distance_mpc = SPEED_OF_LIGHT_KM_S * z / h0_km_s_mpc
    return distance_mpc * 1.0e6


def _resolve_object_type(spectype: Optional[str]) -> str:
    if not spectype:
        return "unknown"
    return _SPECTYPE_MAP.get(spectype.strip().upper(), "unknown")


def _row_to_object(
    row: Dict[str, str],
    release: str,
    redshift_max_z: float,
) -> Optional[CatalogObject]:
    targetid = (row.get("targetid") or row.get("TARGETID") or "").strip()
    ra = _to_float(row.get("target_ra") or row.get("TARGET_RA"))
    dec = _to_float(row.get("target_dec") or row.get("TARGET_DEC"))
    if not targetid or ra is None or dec is None:
        return None
    if not (0.0 <= ra < 360.0) or not (-90.0 <= dec <= 90.0):
        return None

    z = _to_float(row.get("z") or row.get("Z"))
    zerr = _to_float(row.get("zerr") or row.get("ZERR"))
    zwarn = _to_int(row.get("zwarn") or row.get("ZWARN"))

    spectype = (row.get("spectype") or row.get("SPECTYPE") or "").strip() or None
    object_type = _resolve_object_type(spectype)

    distance_pc = safe_redshift_to_distance(
        z, z_err=zerr, zwarn=zwarn, max_z=redshift_max_z,
    )

    extra: Dict[str, Any] = {
        "targetid": targetid,
        "release": release,
        "spectype": spectype,
        "subtype": (row.get("subtype") or row.get("SUBTYPE") or "").strip() or None,
        "zerr": zerr,
        "zwarn": zwarn,
        "desi_target": (
            row.get("desi_target") or row.get("DESI_TARGET") or ""
        ).strip() or None,
        "survey": (row.get("survey") or row.get("SURVEY") or "").strip() or None,
        "program": (row.get("program") or row.get("PROGRAM") or "").strip() or None,
        "healpix": _to_int(row.get("healpix") or row.get("HEALPIX")),
    }

    return CatalogObject(
        uid=f"{release}:{targetid}",
        catalog_source=release,
        object_type=object_type,
        ra_deg=ra,
        dec_deg=dec,
        distance_parsec=distance_pc,
        redshift=z,
        name=targetid,
        metadata_json=json.dumps(extra, sort_keys=True),
    )


def normalize_rows(
    rows: Sequence[Dict[str, str]],
    release: str = DEFAULT_DESI_RELEASE,
    redshift_max_z: float = DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
) -> List[CatalogObject]:
    """Convert raw DESI rows into UNAV ``CatalogObject``s."""
    out: List[CatalogObject] = []
    skipped = 0
    for raw in rows:
        obj = _row_to_object(raw, release=release, redshift_max_z=redshift_max_z)
        if obj is None:
            skipped += 1
            continue
        out.append(obj)
    if skipped:
        _log.warning("Skipped %d unusable DESI rows during normalization.", skipped)
    return out


# ---------------------------------------------------------------------------
# One-shot helper
# ---------------------------------------------------------------------------


def fetch_and_normalize(
    query: DESIQuery,
    fetch_fn: Optional[FetchFn] = None,
    url: str = DESI_TAP_SYNC_URL,
    redshift_max_z: float = DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
) -> List[CatalogObject]:
    rows = fetch_rows(query, fetch_fn=fetch_fn, url=url)
    return normalize_rows(rows, release=query.release, redshift_max_z=redshift_max_z)
