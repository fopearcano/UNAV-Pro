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

import csv
import io
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from core.logging_util import get_logger
from data.schema import CatalogObject

_log = get_logger("data.connectors.sdss")

#: Default SDSS SkyServer SQL endpoint (DR18).
SDSS_SQL_URL = "https://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch"

DEFAULT_SDSS_RELEASE = "sdss_dr18"
_RELEASE_TO_ENDPOINT = {
    "sdss_dr18": "https://skyserver.sdss.org/dr18/SkyServerWS/SearchTools/SqlSearch",
    "sdss_dr17": "https://skyserver.sdss.org/dr17/SkyServerWS/SearchTools/SqlSearch",
}

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

#: Hubble constant assumed by ``safe_redshift_to_distance`` (km/s/Mpc).
HUBBLE_KM_S_MPC = 70.0
SPEED_OF_LIGHT_KM_S = 299_792.458
#: Above this z the naive Hubble inversion is meaningless; we leave
#: ``distance_parsec`` as None and let the schema's placeholder sphere
#: take over.
DEFAULT_REDSHIFT_DISTANCE_MAX_Z = 0.1


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

    SkyServer prepends a comment line beginning with ``#`` to many
    responses; ``csv.DictReader`` handles that as a header row, so we
    strip leading ``#``-only lines first.
    """
    if not body:
        return iter([])
    # Drop leading comment lines that aren't valid CSV headers.
    lines = body.splitlines()
    while lines and lines[0].lstrip().startswith("#"):
        lines.pop(0)
    if not lines:
        return iter([])
    cleaned = "\n".join(lines)
    reader = csv.DictReader(io.StringIO(cleaned))
    if reader.fieldnames is None:
        return iter([])
    return reader


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def _to_float(s: Any) -> Optional[float]:
    if s is None:
        return None
    if isinstance(s, float):
        return s
    text = str(s).strip()
    if not text or text.lower() in {"null", "nan", "none"}:
        return None
    try:
        v = float(text)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    return v


def _to_int(s: Any) -> Optional[int]:
    f = _to_float(s)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError, OverflowError):
        return None


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
    """Coarse Hubble-law distance in parsec.

    Only returns a number when ``0 < z <= max_z`` (Hubble's law is a
    poor approximation past ~ 0.1 in z); otherwise returns ``None``
    and the schema's placeholder-sphere fallback applies.

    Beyond ``max_z`` the right answer is a cosmology-aware comoving
    distance; that is a future-tightening (a Bayesian / FlatLambdaCDM
    integrator), not an MVP feature.
    """
    if z is None or z <= 0.0:
        return None
    if z > max_z:
        return None
    distance_mpc = SPEED_OF_LIGHT_KM_S * z / h0_km_s_mpc
    return distance_mpc * 1.0e6  # Mpc → pc


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
    distance_pc = safe_redshift_to_distance(spec_z, spec_zerr, max_z=redshift_max_z)

    # SDSS ``r``-band model magnitude is the most stable single-band
    # tracer across the survey; use it as ``apparent_magnitude``.
    mag_r = _to_float(row.get("modelMag_r"))
    mag_g = _to_float(row.get("modelMag_g"))
    color_g_r: Optional[float] = None
    if mag_g is not None and mag_r is not None:
        color_g_r = mag_g - mag_r

    extra: Dict[str, Any] = {
        "objid": objid,
        "release": release,
        "spec_class": spec_class,
        "spec_subclass": (row.get("spec_subclass") or "").strip() or None,
        "specobjid": (row.get("specObjID") or "").strip() or None,
        "spec_zerr": spec_zerr,
        "modelMag_u": _to_float(row.get("modelMag_u")),
        "modelMag_g": mag_g,
        "modelMag_r": mag_r,
        "modelMag_i": _to_float(row.get("modelMag_i")),
        "modelMag_z": _to_float(row.get("modelMag_z")),
        "photo_type": photo_type,
    }

    return CatalogObject(
        uid=f"{release}:{objid}",
        catalog_source=release,
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
