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
from data.connectors.redshift_distance import (
    DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
    HUBBLE_KM_S_MPC,
    SPEED_OF_LIGHT_KM_S,
    safe_redshift_to_distance_pc,
    stamp_proxy_metadata,
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

#: Human-readable label written into every emitted ``CatalogObject``.
#: The release token (``desi_edr`` / ``desi_dr1``) is preserved in
#: ``metadata_json``.
CATALOG_SOURCE_LABEL = "DESI"

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

# NOTE: ``HUBBLE_KM_S_MPC``, ``SPEED_OF_LIGHT_KM_S``, and
# ``DEFAULT_REDSHIFT_DISTANCE_MAX_Z`` are re-exported from
# ``redshift_distance`` for backwards compatibility with v0.3-era
# CLIs and tests.

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
    """Backwards-compatible facade over
    ``redshift_distance.safe_redshift_to_distance_pc``. ``z_err`` is
    accepted but unused (the linear inversion does not need it)."""
    return safe_redshift_to_distance_pc(
        z, zwarn=zwarn, max_z=max_z, h0_km_s_mpc=h0_km_s_mpc,
    )


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

    distance_pc = safe_redshift_to_distance_pc(
        z, zwarn=zwarn, max_z=redshift_max_z,
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
    if distance_pc is not None and z is not None:
        stamp_proxy_metadata(extra, z=z, max_z=redshift_max_z)

    return CatalogObject(
        uid=f"desi:{targetid}",
        catalog_source=CATALOG_SOURCE_LABEL,
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


# ---------------------------------------------------------------------------
# CLI-friendly one-shot
# ---------------------------------------------------------------------------


from dataclasses import dataclass as _dataclass, field as _field
from typing import List as _List


@_dataclass
class FetchAndWriteReport:
    """Outcome of ``fetch_normalize_and_write``."""

    output_path: str
    object_count: int = 0
    with_redshift: int = 0
    with_proxy_distance: int = 0
    warnings: _List[str] = _field(default_factory=list)
    index_path: Optional[str] = None
    index_total_objects: Optional[int] = None
    index_cell_count: Optional[int] = None


def fetch_normalize_and_write(
    query: DESIQuery,
    output_path: str,
    *,
    fetch_fn: Optional[FetchFn] = None,
    url: str = DESI_TAP_SYNC_URL,
    redshift_max_z: float = DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
    build_index_dir: Optional[str] = None,
    index_chunk_size: int = 5_000,
) -> FetchAndWriteReport:
    """End-to-end: fetch + normalize + write JSONL + optional spatial
    index. Mirrors the SDSS/JPL helpers so the CLIs look uniform."""
    objects = fetch_and_normalize(
        query, fetch_fn=fetch_fn, url=url, redshift_max_z=redshift_max_z,
    )

    from data.catalog_io import write_catalog

    write_catalog(objects, output_path, fmt="jsonl")

    with_z = sum(1 for o in objects if o.redshift is not None)
    with_d = sum(1 for o in objects if o.distance_parsec is not None)
    report = FetchAndWriteReport(
        output_path=output_path,
        object_count=len(objects),
        with_redshift=with_z,
        with_proxy_distance=with_d,
    )
    if not objects:
        report.warnings.append("query returned 0 usable rows")

    if build_index_dir and objects:
        from core.spatial_index import build_index

        index = build_index(
            objects, build_index_dir, chunk_size=index_chunk_size,
        )
        report.index_path = build_index_dir
        report.index_total_objects = index.total_objects
        report.index_cell_count = len(index.cells)
    return report
