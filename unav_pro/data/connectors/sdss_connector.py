"""SDSS connector — cone search against the public SkyServer.

Targets the SDSS DR18 SkyServer SQL search endpoint:
``https://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch``.
Stdlib-only: ``urllib`` for HTTP, ``csv`` for the response, the local
schema for canonical output. No third-party scientific packages.

This module is shipped as a **stub**: the function signatures, the
SQL surface, the column mapping, and the test surface are all
production-shaped, but the live HTTP path is exercised only against
mocked responses in this MVP. Once we have artist demand the same
``fetch_fn``-injected design lets ``_http_fetch`` go live without any
caller-visible change.

Scope
-----

  * **Cone search** around (RA, Dec) with a row cap.
  * **Photometric backbone with optional spectro join.** The default
    SQL hits ``PhotoObj`` and left-joins ``SpecObj`` so rows that
    happen to have a spectrum carry redshift; rows that do not still
    flow through with photometry only.
  * **Object types covered:** stars, galaxies, quasars (via the
    spectroscopic ``class`` field; photometric ``type`` provides a
    coarser fallback).
  * **Mock-friendly.** ``fetch_rows(..., fetch_fn=...)`` accepts an
    injected fetcher so tests run without network access.

The full pipeline schema is in ``docs/UNAV_PRO_DATA_PIPELINE.md`` §4.
This connector populates the local-format subset in
``unav_pro/data/schema.py`` and tags every row with
``catalog_source = "sdss_dr18"`` (or whichever release the caller
chose).

See ``docs/SDSS_CONNECTOR.md`` for the full SQL strategy, column
mapping, and known limitations.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from core.logging_util import get_logger
from data.connectors._normalize import (
    parse_csv as _parse_csv_base,
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

_log = get_logger("data.connectors.sdss")

#: Default SDSS SkyServer SQL endpoint (DR18).
SDSS_SQL_URL = "https://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch"

DEFAULT_SDSS_RELEASE = "sdss_dr18"
_RELEASE_TO_ENDPOINT = {
    "sdss_dr18": "https://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch",
    "sdss_dr17": "https://skyserver.sdss.org/dr17/SkyServerWS/SearchTools/SqlSearch",
}

#: Human-readable label written into every emitted ``CatalogObject``.
#: Distinct from the per-release token (``sdss_dr18`` / ``sdss_dr17``)
#: which is preserved in ``metadata_json``. The dataset manager and
#: inspector show this label.
CATALOG_SOURCE_LABEL = "SDSS"

#: Hard ceiling on row count.
MAX_ROW_LIMIT = 100_000

#: Hard ceiling on cone radius (degrees). SkyServer accepts arcmin in
#: ``fGetNearbyObjEq`` so we convert; a 30° cone at the resolution of
#: SDSS is far beyond what makes sense for a single query anyway.
MAX_RADIUS_DEG = 30.0

_USER_AGENT = "UNAV-Pro/0.1 (+https://example.invalid/unav-pro)"

#: Photometric-type integer → UNAV object_type. SDSS uses small
#: integers in ``PhotoObj.type``: 3 = galaxy, 6 = star.
_PHOTO_TYPE_MAP: Dict[int, str] = {
    3: "galaxy",
    6: "star",
}

#: Spectroscopic ``SpecObj.class`` strings → UNAV object_type. When
#: present, this overrides the photometric guess (galaxies that are
#: actually QSOs, etc.).
_SPEC_CLASS_MAP: Dict[str, str] = {
    "GALAXY": "galaxy",
    "QSO": "quasar",
    "QUASAR": "quasar",
    "STAR": "star",
}

# NOTE: ``HUBBLE_KM_S_MPC``, ``SPEED_OF_LIGHT_KM_S``, and
# ``DEFAULT_REDSHIFT_DISTANCE_MAX_Z`` are re-exported from
# ``redshift_distance`` for backwards compatibility with the v0.4-era
# CLIs and tests that import them off this module.


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SDSSQueryError(Exception):
    """Raised for unrecoverable SDSS connector / archive errors."""


# ---------------------------------------------------------------------------
# Query model
# ---------------------------------------------------------------------------


@dataclass
class SDSSQuery:
    """SDSS cone query parameters."""

    ra_deg: float
    dec_deg: float
    radius_deg: float
    limit: int = 5_000
    release: str = DEFAULT_SDSS_RELEASE
    include_spectro: bool = True

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
        if self.release not in _RELEASE_TO_ENDPOINT:
            raise ValueError(
                f"unknown release '{self.release}'; "
                f"valid: {', '.join(_RELEASE_TO_ENDPOINT.keys())}"
            )


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------


_PHOTO_COLUMNS = (
    "p.objID",
    "p.ra", "p.dec", "p.type",
    "p.modelMag_u", "p.modelMag_g", "p.modelMag_r",
    "p.modelMag_i", "p.modelMag_z",
)
_SPEC_COLUMNS = (
    "s.specObjID",
    "s.z AS spec_z", "s.zErr AS spec_zerr",
    "s.class AS spec_class", "s.subClass AS spec_subclass",
)


def build_sql(query: SDSSQuery) -> str:
    """Render the SkyServer SQL cone query.

    Uses ``dbo.fGetNearbyObjEq(ra, dec, r_arcmin)`` — the canonical
    SDSS table-valued function for cone search. Joins ``SpecObj`` for
    redshift / class when ``include_spectro`` is true (default).
    """
    radius_arcmin = query.radius_deg * 60.0
    cols = list(_PHOTO_COLUMNS)
    join = ""
    if query.include_spectro:
        cols.extend(_SPEC_COLUMNS)
        join = "LEFT JOIN SpecObj s ON s.bestObjID = p.objID"
    select = ", ".join(cols)
    return (
        f"SELECT TOP {query.limit} {select} "
        f"FROM PhotoObj p {join} "
        f"JOIN dbo.fGetNearbyObjEq({query.ra_deg}, {query.dec_deg}, {radius_arcmin}) n "
        f"ON p.objID = n.objID "
        f"ORDER BY p.modelMag_r ASC"
    )


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------


FetchFn = Callable[[str, Dict[str, str]], str]


def _http_fetch(url: str, params: Dict[str, str]) -> str:
    """Default fetcher: synchronous GET to the SkyServer SQL endpoint."""
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        full,
        method="GET",
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/csv",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status != 200:
                raise SDSSQueryError(
                    f"SkyServer HTTP {resp.status}: {body[:300]!r}"
                )
            return body
    except urllib.error.HTTPError as exc:
        raise SDSSQueryError(
            f"SkyServer HTTP {exc.code}: {exc.read()[:300]!r}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SDSSQueryError(
            f"SkyServer network error: {exc.reason!r}"
        ) from exc


def fetch_rows(
    query: SDSSQuery,
    fetch_fn: Optional[FetchFn] = None,
    url: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Run ``query`` against SkyServer and return raw CSV rows."""
    fetcher = fetch_fn or _http_fetch
    endpoint = url or _RELEASE_TO_ENDPOINT[query.release]
    sql = build_sql(query)
    params = {"cmd": sql, "format": "csv"}
    _log.info(
        "SDSS cone query: ra=%.4f dec=%.4f radius=%.3f limit=%d release=%s",
        query.ra_deg, query.dec_deg, query.radius_deg, query.limit, query.release,
    )
    body = fetcher(endpoint, params)
    return list(_parse_csv(body))


def _parse_csv(body: str) -> Iterable[Dict[str, str]]:
    """Parse a SkyServer CSV response.

    SkyServer prepends a banner comment beginning with ``#`` to many
    responses; the shared parser strips those before reading the
    real header row.
    """
    return _parse_csv_base(body, strip_leading_comments=True)


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def _resolve_object_type(
    photo_type: Optional[int], spec_class: Optional[str]
) -> str:
    """Spectroscopic class beats photometric type when both available."""
    if spec_class:
        cls = str(spec_class).strip().upper()
        if cls in _SPEC_CLASS_MAP:
            return _SPEC_CLASS_MAP[cls]
    if photo_type is not None and photo_type in _PHOTO_TYPE_MAP:
        return _PHOTO_TYPE_MAP[photo_type]
    return "unknown"


def safe_redshift_to_distance(
    z: Optional[float],
    z_err: Optional[float] = None,
    max_z: float = DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
    h0_km_s_mpc: float = HUBBLE_KM_S_MPC,
) -> Optional[float]:
    """Backwards-compatible facade over
    ``redshift_distance.safe_redshift_to_distance_pc``. ``z_err`` is
    accepted for API symmetry with v0.3-era callers but is unused —
    the underlying mapping is linear in ``z``."""
    return safe_redshift_to_distance_pc(z, max_z=max_z, h0_km_s_mpc=h0_km_s_mpc)


def _row_to_object(
    row: Dict[str, str],
    release: str,
    redshift_max_z: float,
) -> Optional[CatalogObject]:
    objid = (row.get("objID") or row.get("objid") or "").strip()
    ra = _to_float(row.get("ra"))
    dec = _to_float(row.get("dec"))
    if not objid or ra is None or dec is None:
        return None
    if not (0.0 <= ra < 360.0) or not (-90.0 <= dec <= 90.0):
        return None

    photo_type = _to_int(row.get("type"))
    spec_class = (row.get("spec_class") or row.get("class") or "").strip() or None
    object_type = _resolve_object_type(photo_type, spec_class)

    spec_z = _to_float(row.get("spec_z") or row.get("z"))
    spec_zerr = _to_float(row.get("spec_zerr") or row.get("zErr") or row.get("zerr"))
    distance_pc = safe_redshift_to_distance_pc(spec_z, max_z=redshift_max_z)

    # SDSS ``r``-band model magnitude is the most stable single-band
    # tracer across the survey; use it as ``apparent_magnitude``.
    mag_r = _to_float(row.get("modelMag_r"))
    mag_g = _to_float(row.get("modelMag_g"))
    color_g_r: Optional[float] = None
    if mag_g is not None and mag_r is not None:
        color_g_r = mag_g - mag_r

    specobjid = (row.get("specObjID") or "").strip() or None
    extra: Dict[str, Any] = {
        "objid": objid,
        "release": release,
        "spec_class": spec_class,
        "spec_subclass": (row.get("spec_subclass") or "").strip() or None,
        "specobjid": specobjid,
        "spec_zerr": spec_zerr,
        "modelMag_u": _to_float(row.get("modelMag_u")),
        "modelMag_g": mag_g,
        "modelMag_r": mag_r,
        "modelMag_i": _to_float(row.get("modelMag_i")),
        "modelMag_z": _to_float(row.get("modelMag_z")),
        "photo_type": photo_type,
    }
    if distance_pc is not None and spec_z is not None:
        stamp_proxy_metadata(extra, z=spec_z, max_z=redshift_max_z)

    # uid prefix is the connector token (``sdss``), release token lives
    # in metadata_json. Prefer specObjID when present (canonical pointer
    # for redshift catalogs); fall back to photometric objID.
    uid_segment = specobjid or objid
    return CatalogObject(
        uid=f"sdss:{uid_segment}",
        catalog_source=CATALOG_SOURCE_LABEL,
        object_type=object_type,
        ra_deg=ra,
        dec_deg=dec,
        distance_parsec=distance_pc,
        redshift=spec_z,
        apparent_magnitude=mag_r,
        color_index=color_g_r,
        name=objid,
        metadata_json=json.dumps(extra, sort_keys=True),
    )


def normalize_rows(
    rows: Sequence[Dict[str, str]],
    release: str = DEFAULT_SDSS_RELEASE,
    redshift_max_z: float = DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
) -> List[CatalogObject]:
    """Convert raw SkyServer rows into UNAV ``CatalogObject``s."""
    out: List[CatalogObject] = []
    skipped = 0
    for raw in rows:
        obj = _row_to_object(raw, release=release, redshift_max_z=redshift_max_z)
        if obj is None:
            skipped += 1
            continue
        out.append(obj)
    if skipped:
        _log.warning("Skipped %d unusable SDSS rows during normalization.", skipped)
    return out


# ---------------------------------------------------------------------------
# One-shot helper
# ---------------------------------------------------------------------------


def fetch_and_normalize(
    query: SDSSQuery,
    fetch_fn: Optional[FetchFn] = None,
    url: Optional[str] = None,
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
    query: SDSSQuery,
    output_path: str,
    *,
    fetch_fn: Optional[FetchFn] = None,
    url: Optional[str] = None,
    redshift_max_z: float = DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
    build_index_dir: Optional[str] = None,
    index_chunk_size: int = 5_000,
) -> FetchAndWriteReport:
    """End-to-end: fetch + normalize + write JSONL + optional spatial
    index. Mirrors the v0.4 JPL helper so the CLIs look uniform."""
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
