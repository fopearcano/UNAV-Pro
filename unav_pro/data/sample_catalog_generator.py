"""Generate a small synthetic catalog for development and tests.

The generator produces 100 fake astrophysical objects spanning four
object types (stars, galaxies, quasars, nebulae) with a realistic-ish
mix of distances, magnitudes, and spectral classes. It is intentionally
deterministic (default seed=42) so test assertions on the output are
stable.

This module replaces *no* real catalog ingestion. It is the seed file
that lets the plugin and tests exercise the full I/O + schema pipeline
before any Gaia/SDSS/DESI adapter exists.
"""

from __future__ import annotations

import json
import os
import random
from typing import List, Optional

from .catalog_io import default_sample_catalog_path, write_catalog
from .schema import CatalogObject

# Composition of the synthetic catalog (must sum to 100 by default).
_DEFAULT_MIX = (
    ("star", 60),
    ("galaxy", 25),
    ("quasar", 10),
    ("nebula", 5),
)

_SPECTRAL_CLASSES = ("O", "B", "A", "F", "G", "K", "M")
# Mass-function weighting: cool dwarfs are far more common than O/B stars.
_SPECTRAL_WEIGHTS = (1, 3, 8, 15, 25, 30, 40)

_NEBULA_NAMES = (
    "Veil", "Crab", "Helix", "Lagoon", "Eagle", "Trifid",
    "Orion", "Ring", "Cat's Eye", "Tarantula",
)


def _make_star(rng: random.Random, idx: int) -> CatalogObject:
    spec = rng.choices(_SPECTRAL_CLASSES, weights=_SPECTRAL_WEIGHTS, k=1)[0]
    subclass = rng.randint(0, 9)
    luminosity = rng.choice(("V", "IV", "III", "II", "I"))
    spectral_type = f"{spec}{subclass}{luminosity}"

    # Distances biased toward nearby stars but tail out to ~5 kpc.
    distance_pc = rng.lognormvariate(mu=4.0, sigma=1.2)
    distance_pc = max(1.0, min(distance_pc, 5000.0))
    parallax_mas = 1000.0 / distance_pc

    apparent_mag = rng.uniform(-1.5, 14.0)
    abs_mag = apparent_mag - 5.0 * (
        # log10(distance/10pc) — manual to avoid math import here.
        # Keep the math-free helper inline; we have math elsewhere if needed.
        # m - M = 5 log10(d/10 pc)
        _log10(distance_pc / 10.0)
    )

    color_index = rng.uniform(-0.3, 1.8)

    return CatalogObject(
        uid=f"sample-star-{idx:04d}",
        catalog_source="unav_sample",
        object_type="star",
        ra_deg=rng.uniform(0.0, 360.0),
        dec_deg=_uniform_sphere_dec(rng),
        distance_parsec=distance_pc,
        parallax_mas=parallax_mas,
        radial_velocity_kms=rng.gauss(0.0, 30.0),
        proper_motion_ra=rng.gauss(0.0, 50.0),
        proper_motion_dec=rng.gauss(0.0, 50.0),
        apparent_magnitude=apparent_mag,
        absolute_magnitude=abs_mag,
        color_index=color_index,
        spectral_type=spectral_type,
        name=f"SS-{idx:04d}",
        common_name=None,
        metadata_json=json.dumps({"synth": True, "kind": "star"}, sort_keys=True),
    )


def _make_galaxy(rng: random.Random, idx: int) -> CatalogObject:
    redshift = rng.uniform(0.001, 0.5)
    # Hubble-ish distance: d(Mpc) = c*z/H0; with H0=70 km/s/Mpc, c=3e5
    distance_mpc = 3.0e5 * redshift / 70.0
    distance_pc = distance_mpc * 1.0e6
    apparent_mag = rng.uniform(13.0, 21.0)
    abs_mag = apparent_mag - 5.0 * _log10(max(distance_pc / 10.0, 1e-9))

    return CatalogObject(
        uid=f"sample-galaxy-{idx:04d}",
        catalog_source="unav_sample",
        object_type="galaxy",
        ra_deg=rng.uniform(0.0, 360.0),
        dec_deg=_uniform_sphere_dec(rng),
        distance_parsec=distance_pc,
        redshift=redshift,
        radial_velocity_kms=redshift * 3.0e5,
        apparent_magnitude=apparent_mag,
        absolute_magnitude=abs_mag,
        color_index=rng.uniform(0.4, 1.2),
        name=f"SG-{idx:04d}",
        metadata_json=json.dumps(
            {"synth": True, "kind": "galaxy", "morphology": rng.choice(("E", "S", "Irr"))},
            sort_keys=True,
        ),
    )


def _make_quasar(rng: random.Random, idx: int) -> CatalogObject:
    redshift = rng.uniform(0.5, 4.0)
    distance_mpc = 3.0e5 * redshift / 70.0
    distance_pc = distance_mpc * 1.0e6
    apparent_mag = rng.uniform(16.0, 22.0)
    abs_mag = apparent_mag - 5.0 * _log10(max(distance_pc / 10.0, 1e-9))

    return CatalogObject(
        uid=f"sample-quasar-{idx:04d}",
        catalog_source="unav_sample",
        object_type="quasar",
        ra_deg=rng.uniform(0.0, 360.0),
        dec_deg=_uniform_sphere_dec(rng),
        distance_parsec=distance_pc,
        redshift=redshift,
        radial_velocity_kms=redshift * 3.0e5,
        apparent_magnitude=apparent_mag,
        absolute_magnitude=abs_mag,
        name=f"SQ-{idx:04d}",
        metadata_json=json.dumps({"synth": True, "kind": "quasar"}, sort_keys=True),
    )


def _make_nebula(rng: random.Random, idx: int) -> CatalogObject:
    name = rng.choice(_NEBULA_NAMES)
    distance_pc = rng.uniform(200.0, 5000.0)
    apparent_mag = rng.uniform(5.0, 11.0)

    return CatalogObject(
        uid=f"sample-nebula-{idx:04d}",
        catalog_source="unav_sample",
        object_type="nebula",
        ra_deg=rng.uniform(0.0, 360.0),
        dec_deg=_uniform_sphere_dec(rng),
        distance_parsec=distance_pc,
        apparent_magnitude=apparent_mag,
        name=f"SN-{idx:04d}",
        common_name=f"Synth {name} Nebula",
        metadata_json=json.dumps({"synth": True, "kind": "nebula"}, sort_keys=True),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uniform_sphere_dec(rng: random.Random) -> float:
    """Draw a declination uniformly on the celestial sphere (so cos(dec)
    weights latitude correctly)."""
    import math
    u = rng.uniform(-1.0, 1.0)
    return math.degrees(math.asin(u))


def _log10(x: float) -> float:
    import math
    return math.log10(x)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_objects(
    n: int = 100,
    seed: Optional[int] = 42,
) -> List[CatalogObject]:
    """Build ``n`` synthetic ``CatalogObject``s with the default mix.

    For ``n == 100`` the mix is exactly ``_DEFAULT_MIX``. For other
    counts the mix is scaled proportionally and any rounding deficit is
    absorbed by stars (the most common type).
    """
    rng = random.Random(seed)

    counts: dict[str, int] = {}
    for kind, share in _DEFAULT_MIX:
        counts[kind] = int(round(n * share / 100))
    delta = n - sum(counts.values())
    counts["star"] = max(0, counts["star"] + delta)

    out: List[CatalogObject] = []
    idx = 0
    for kind, k in counts.items():
        for _ in range(k):
            if kind == "star":
                out.append(_make_star(rng, idx))
            elif kind == "galaxy":
                out.append(_make_galaxy(rng, idx))
            elif kind == "quasar":
                out.append(_make_quasar(rng, idx))
            elif kind == "nebula":
                out.append(_make_nebula(rng, idx))
            idx += 1
    rng.shuffle(out)
    return out


def write_sample_catalog(
    path: Optional[str] = None,
    n: int = 100,
    seed: Optional[int] = 42,
    fmt: str = "auto",
) -> str:
    """Generate and write a sample catalog. Returns the absolute path."""
    target = path or default_sample_catalog_path()
    objects = generate_objects(n=n, seed=seed)
    write_catalog(objects, target, fmt=fmt)
    return os.path.abspath(target)


if __name__ == "__main__":  # pragma: no cover — CLI convenience
    out = write_sample_catalog()
    print(f"Wrote sample catalog to {out}")
