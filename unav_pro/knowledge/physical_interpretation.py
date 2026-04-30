"""Astrophysical interpretation helpers for the v1.3 knowledge layer.

Pure functions that turn raw catalog fields into short, careful
plain-language notes. Everything here is deterministic and
hedged — when the input doesn't carry enough signal, the
function returns ``None`` (or an explicit "unknown" string) and
the caller decides whether to render anything.

What lives here:

* ``spectral_class_hint`` — turn a Morgan-Keenan letter into a
  rough temperature / luminosity-class description.
* ``distance_quality`` — explain *how* the distance was derived
  (explicit, parallax inversion, redshift proxy, placeholder
  sphere) and how trustworthy it is.
* ``motion_summary`` — describe a star's annual drift in
  human-friendly units (mas/yr → "fast / moderate / slow").

None of these functions invent facts. They take what the
connector provided and apply a small set of reference tables.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Spectral class
# ---------------------------------------------------------------------------

#: Coarse description per Morgan-Keenan letter. Temperatures are
#: rough mid-class values from any introductory astronomy text.
#: Stars at the boundaries are ~one class off — that's fine for an
#: inspector hint.
_SPECTRAL_CLASS_DESCRIPTIONS = {
    "O": ("very hot blue main-sequence star", 30_000, 50_000),
    "B": ("hot blue-white main-sequence star", 10_000, 30_000),
    "A": ("white main-sequence star",          7_500, 10_000),
    "F": ("yellow-white main-sequence star",   6_000,  7_500),
    "G": ("yellow main-sequence star",         5_200,  6_000),
    "K": ("orange main-sequence star",         3_700,  5_200),
    "M": ("cool red main-sequence star",       2_400,  3_700),
    "L": ("brown dwarf (L type)",              1_300,  2_400),
    "T": ("cool brown dwarf (T type)",           500,  1_300),
}


def spectral_class_hint(spectral_type: Optional[str]) -> Optional[str]:
    """Translate a spectral-type string into a one-line hint.

    Examples:

        ``"G2V"`` → ``"yellow main-sequence star, ~5,200–6,000 K
        (Sun-like)"``.
        ``"M5III"`` → ``"cool red main-sequence star, ~2,400–
        3,700 K"``  (with a luminosity-class note when the
        roman-numeral suffix is present).

    Returns ``None`` when the spectral type is empty or its
    leading letter is unknown.
    """
    if not spectral_type:
        return None
    s = spectral_type.strip().upper()
    if not s:
        return None
    letter = s[0]
    entry = _SPECTRAL_CLASS_DESCRIPTIONS.get(letter)
    if entry is None:
        return None
    description, t_lo, t_hi = entry

    extras = []
    if letter == "G" and s.startswith("G2"):
        extras.append("Sun-like")
    if "I" in s[1:]:
        # Crude luminosity-class detection. Real MK classification
        # is more nuanced; this catches the giants/supergiants tail.
        if "III" in s:
            extras.append("giant")
        elif "II" in s:
            extras.append("bright giant")
        elif "Ia" in s or "Ib" in s:
            extras.append("supergiant")
    summary = f"{description}, ~{t_lo:,}–{t_hi:,} K"
    if extras:
        summary += " (" + ", ".join(extras) + ")"
    return summary


# ---------------------------------------------------------------------------
# Distance quality
# ---------------------------------------------------------------------------


def distance_quality(
    *,
    distance_parsec: Optional[float],
    parallax_mas: Optional[float],
    distance_method: Optional[str],
    parallax_error_mas: Optional[float] = None,
) -> Tuple[str, str]:
    """Categorise how a distance was determined.

    Returns ``(label, note)`` where ``label`` is a short tag
    suitable for the inspector header (one of ``"explicit"``,
    ``"parallax"``, ``"redshift_proxy"``, ``"placeholder"``,
    ``"unknown"``) and ``note`` is a human-readable elaboration
    the inspector can render under the Position section.
    """
    method = (distance_method or "").strip().lower()

    if method == "redshift_hubble_proxy":
        return (
            "redshift_proxy",
            "approximate distance from a redshift→Hubble-law inversion; "
            "treat as order-of-magnitude only.",
        )
    if method == "placeholder_sphere":
        return (
            "placeholder",
            "no reliable distance available; placed on a fixed "
            "celestial-sphere radius for visualization only.",
        )

    if distance_parsec is not None and distance_parsec > 0.0:
        # Parallax-derived distance is technically still "explicit"
        # in the schema, but we surface the parallax SNR if we have
        # the error — the artist needs to know when a parallax
        # inversion is unreliable.
        if parallax_mas is not None and parallax_mas > 0.0:
            if parallax_error_mas is not None and parallax_error_mas > 0:
                snr = float(parallax_mas) / float(parallax_error_mas)
                if snr < 5.0:
                    return (
                        "parallax",
                        f"distance from parallax inversion (parallax SNR ≈ {snr:.1f}); "
                        "low SNR — treat with caution.",
                    )
                return (
                    "parallax",
                    f"distance from parallax inversion (parallax SNR ≈ {snr:.1f}).",
                )
            return (
                "parallax",
                "distance from parallax inversion (parallax SNR not reported).",
            )
        return (
            "explicit",
            "distance reported directly by the source catalog.",
        )

    if parallax_mas is not None and parallax_mas > 0.0:
        return (
            "parallax",
            "distance not stored; can be inferred from the parallax field.",
        )

    return ("unknown", "no distance and no parallax reported.")


# ---------------------------------------------------------------------------
# Proper-motion summary
# ---------------------------------------------------------------------------

#: Rough cutoff (mas/yr in great-circle terms) above which a
#: star's drift is visible on a year-over-year scale in the
#: typical UNAV viewport. Barnard's Star is ~10,300 mas/yr;
#: Sirius is ~1,300; the median Gaia DR3 source is ~5.
PROPER_MOTION_THRESHOLD_MASYR: float = 50.0


def motion_summary(
    pmra_masyr: Optional[float],
    pmdec_masyr: Optional[float],
) -> Optional[str]:
    """Describe annual proper motion in plain language.

    Returns ``None`` when both rates are missing. When at least
    one is present, returns a one-line string of the form:

        "drifting at 12.4 mas/yr (slow)"

    The categories are: ``negligible`` (< 1), ``slow`` (1–10),
    ``moderate`` (10–100), ``fast`` (100–1,000), ``very fast``
    (> 1,000).
    """
    if pmra_masyr is None and pmdec_masyr is None:
        return None
    pmra = float(pmra_masyr or 0.0)
    pmdec = float(pmdec_masyr or 0.0)
    total = math.hypot(pmra, pmdec)
    if total < 1.0:
        bucket = "negligible"
    elif total < 10.0:
        bucket = "slow"
    elif total < 100.0:
        bucket = "moderate"
    elif total < 1_000.0:
        bucket = "fast"
    else:
        bucket = "very fast"
    return f"drifting at {total:.1f} mas/yr ({bucket})"
