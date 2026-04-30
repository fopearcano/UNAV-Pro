"""Redshift → proxy distance helper.

Isolated so the SDSS and DESI connectors share **one** definition of
the naive Hubble-law conversion, and so the metadata inspector can
reliably detect that a row's ``distance_parsec`` came from this path
(via the ``distance_method`` tag this module stamps into
``metadata_json``).

This module is intentionally **not** a cosmology engine. It is a
linear ``d ≈ c·z / H₀`` mapping with a hard ``z ≤ z_max`` cutoff
and a hard ``zwarn == 0`` requirement (when the caller chooses to
pass it). Above ``z_max`` the conversion is silently refused —
``compute_derived_fields`` will then place the object on the
schema's placeholder sphere, and the inspector flags it.

See ``docs/REDSHIFT_DISTANCE_LIMITATIONS.md`` for the full caveat
list and the upgrade path to a cosmology-aware comoving integrator.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

#: Hubble constant assumed by the linear inversion (km/s/Mpc).
HUBBLE_KM_S_MPC = 70.0
#: Speed of light, exact (km/s).
SPEED_OF_LIGHT_KM_S = 299_792.458

#: Above this redshift the linear Hubble inversion is meaningless;
#: the helper returns ``None`` and the schema's placeholder-sphere
#: fallback applies. Cosmology-grade comoving distance is reserved
#: for a future tightening (a Bayesian / FlatLambdaCDM integrator).
DEFAULT_REDSHIFT_DISTANCE_MAX_Z = 0.1

#: Tag written into ``metadata_json["distance_method"]`` whenever the
#: helper returned a real proxy distance. The inspector keys off this
#: token to surface the "approximate distance" warning. Distinct from
#: the schema's ``placeholder_sphere`` tag.
DISTANCE_METHOD_REDSHIFT_PROXY = "redshift_hubble_proxy"

#: Human-readable warning included alongside the tag, so it travels
#: with the row when the metadata blob is copied / inspected.
DISTANCE_PROXY_WARNING_TEXT = (
    "Distance derived from naive Hubble's law (d = c·z / H0) at "
    "z <= 0.1; approximate, not cosmology-grade."
)


def safe_redshift_to_distance_pc(
    z: Optional[float],
    *,
    zwarn: Optional[int] = None,
    max_z: float = DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
    h0_km_s_mpc: float = HUBBLE_KM_S_MPC,
) -> Optional[float]:
    """Linear Hubble-law distance in parsec, or ``None`` if unsafe.

    Returns ``None`` when:

    * ``z`` is missing or non-positive,
    * ``zwarn`` (when provided) is non-zero (DESI-style quality flag),
    * ``z`` exceeds ``max_z`` (the cutoff above which the linear
      inversion is meaningless and we defer to the placeholder sphere).

    The conversion is::

        d_Mpc = (c [km/s] * z) / H0 [km/s/Mpc]
        d_pc  = d_Mpc * 1e6
    """
    if z is None or z <= 0.0:
        return None
    if zwarn is not None and zwarn != 0:
        return None
    if z > max_z:
        return None
    distance_mpc = SPEED_OF_LIGHT_KM_S * float(z) / float(h0_km_s_mpc)
    return distance_mpc * 1.0e6


def stamp_proxy_metadata(
    extra: Dict[str, Any],
    *,
    z: float,
    h0_km_s_mpc: float = HUBBLE_KM_S_MPC,
    max_z: float = DEFAULT_REDSHIFT_DISTANCE_MAX_Z,
) -> Dict[str, Any]:
    """Add the ``distance_method`` / warning fields onto an extras
    dict in place. Caller invokes this only when
    ``safe_redshift_to_distance_pc`` returned a non-None value, so the
    tag is never stamped on rows whose distance was rejected. Returns
    the same dict for chaining."""
    extra["distance_method"] = DISTANCE_METHOD_REDSHIFT_PROXY
    extra["distance_proxy_warning"] = DISTANCE_PROXY_WARNING_TEXT
    extra["distance_proxy_z"] = float(z)
    extra["distance_proxy_h0_km_s_mpc"] = float(h0_km_s_mpc)
    extra["distance_proxy_max_z"] = float(max_z)
    return extra


def is_proxy_distance(metadata_blob: Optional[Dict[str, Any]]) -> bool:
    """Inspector-side predicate: does this metadata_json blob carry a
    redshift-proxy distance? Tolerates ``None`` and non-dict input."""
    if not isinstance(metadata_blob, dict):
        return False
    return metadata_blob.get("distance_method") == DISTANCE_METHOD_REDSHIFT_PROXY
