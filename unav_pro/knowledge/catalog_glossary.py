"""Catalog field glossary for the v1.3 knowledge layer.

A short, deterministic dictionary of the astrophysical terms
the metadata inspector renders. The inspector's "Catalog Notes"
section can pull a definition for any term name; tests assert
that every field UNAV stores has an entry.

Intentionally not exhaustive: only terms UNAV actually surfaces
in the UI / DB / binary export are defined. Adding a term means
adding it here *and* using it somewhere. No dead entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class GlossaryEntry:
    """One field's plain-language definition.

    ``term`` is the canonical name (lowercase, underscore-free
    where reasonable); ``aliases`` lets the inspector look up
    the same entry under multiple keys (e.g. ``"ra"`` and
    ``"right ascension"`` resolve to the same row).
    """

    term: str
    short: str
    long: str
    unit: Optional[str] = None
    aliases: Tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Canonical entries
# ---------------------------------------------------------------------------

_ENTRIES: Tuple[GlossaryEntry, ...] = (
    GlossaryEntry(
        term="ra",
        short="Right ascension — celestial longitude.",
        long=(
            "The east-west coordinate on the celestial sphere, "
            "measured along the celestial equator from the vernal "
            "equinox. Wraps at 360°. Together with declination it "
            "gives a star's direction from Earth in the ICRS frame."
        ),
        unit="degrees",
        aliases=("right ascension", "ra_deg"),
    ),
    GlossaryEntry(
        term="dec",
        short="Declination — celestial latitude.",
        long=(
            "The north-south coordinate on the celestial sphere, "
            "from -90° at the south celestial pole to +90° at the "
            "north. Together with right ascension it gives a star's "
            "direction from Earth in the ICRS frame."
        ),
        unit="degrees",
        aliases=("declination", "dec_deg"),
    ),
    GlossaryEntry(
        term="parallax",
        short="Apparent angular shift due to Earth's orbital motion.",
        long=(
            "The angle (in milliarcseconds) by which a nearby star "
            "appears to shift across the sky over a year because of "
            "Earth's orbit. Distance in parsec is 1000 / parallax_mas. "
            "Only useful when the parallax is much larger than its "
            "reported uncertainty."
        ),
        unit="mas",
        aliases=("parallax_mas",),
    ),
    GlossaryEntry(
        term="parsec",
        short="The standard astronomical distance unit.",
        long=(
            "The distance at which one astronomical unit (Earth-Sun "
            "distance) subtends one arcsecond. 1 pc ≈ 3.26 light-years. "
            "UNAV stores all heliocentric Cartesian positions in "
            "parsec; the C4D scale factor lets the artist switch "
            "between AU / pc / kpc / Mpc display units."
        ),
        unit="pc",
        aliases=("pc",),
    ),
    GlossaryEntry(
        term="redshift",
        short="Wavelength stretch caused by recession or cosmological expansion.",
        long=(
            "The fractional shift z = (λ_observed - λ_rest) / λ_rest "
            "of a galaxy's spectrum. For z << 1 it is roughly "
            "v/c (recession velocity). UNAV converts redshift to a "
            "Hubble-law distance only as a coarse proxy; see "
            "REDSHIFT_DISTANCE_LIMITATIONS.md for caveats."
        ),
        unit="(dimensionless)",
        aliases=("z",),
    ),
    GlossaryEntry(
        term="proper_motion",
        short="Annual angular drift across the sky.",
        long=(
            "How fast a star's apparent position changes per year. "
            "Reported as two components — pmra (along great-circle "
            "right ascension, with cos(dec) baked in) and pmdec "
            "(along declination). UNAV uses this for the v1.2 "
            "Time Navigator's epoch propagation."
        ),
        unit="mas/yr",
        aliases=("pm", "pmra", "pmdec", "proper motion"),
    ),
    GlossaryEntry(
        term="radial_velocity",
        short="Line-of-sight velocity toward / away from us.",
        long=(
            "Component of a star's velocity along the line of sight, "
            "measured from Doppler-shifted spectral lines. Positive "
            "means receding. UNAV does not currently propagate the "
            "implied distance change over time; the v1.2 Time "
            "Navigator only handles transverse (proper-motion) "
            "motion. See GAIA_PROPER_MOTION_LIMITATIONS.md §2.2."
        ),
        unit="km/s",
        aliases=("rv", "radial velocity", "radial_velocity_kms"),
    ),
    GlossaryEntry(
        term="apparent_magnitude",
        short="How bright the object looks from Earth.",
        long=(
            "The brightness of an object as seen from Earth on a "
            "logarithmic, inverted scale: a magnitude of 0 is roughly "
            "Vega; a difference of 5 magnitudes is a factor of 100 "
            "in flux. UNAV uses apparent magnitude to scale render "
            "radii and to drive the magnitude-based size mode."
        ),
        unit="mag",
        aliases=("apparent magnitude", "phot_g_mean_mag"),
    ),
    GlossaryEntry(
        term="absolute_magnitude",
        short="How bright the object would look at 10 parsec.",
        long=(
            "The apparent magnitude an object would have if placed at "
            "10 pc. Independent of distance; a measure of intrinsic "
            "luminosity. M = m - 5 · log10(d/10pc). UNAV does not "
            "compute this for every row — it is only present when "
            "the source catalog reports it."
        ),
        unit="mag",
        aliases=("absolute magnitude",),
    ),
    GlossaryEntry(
        term="color_index",
        short="Difference between two photometric bands.",
        long=(
            "A two-band magnitude difference (e.g. B-V for stars, "
            "g-r for SDSS galaxies, BP-RP for Gaia). Approximates "
            "an object's surface temperature: bluer → smaller / more "
            "negative; redder → larger / more positive."
        ),
        unit="mag",
        aliases=("bp_rp", "color", "g_r"),
    ),
    GlossaryEntry(
        term="spectral_type",
        short="Morgan-Keenan classification letter (+ subclass).",
        long=(
            "A letter (O, B, A, F, G, K, M, plus L/T for brown "
            "dwarfs) indicating the star's surface temperature "
            "from hottest (O) to coolest (T), often with a number "
            "0-9 for the subclass and a roman numeral for the "
            "luminosity class."
        ),
        unit="(string)",
        aliases=("mk class",),
    ),
    GlossaryEntry(
        term="epoch",
        short="The instant a position is valid for.",
        long=(
            "An astronomical position carries an epoch — the time "
            "the (ra, dec, distance) tuple is valid for. Gaia DR3 "
            "is reported at J2016.0; JPL Horizons returns whatever "
            "epoch you asked for. UNAV's v1.2 Time Navigator stores "
            "every state at an explicit epoch."
        ),
        unit="JD or ISO datetime",
        aliases=("reference epoch",),
    ),
    GlossaryEntry(
        term="julian_date",
        short="Days since 4713 BC noon UT.",
        long=(
            "A continuous time scale used in astronomy: a single "
            "real number counting days since noon on January 1, "
            "4713 BC. UNAV stores every epoch as a JD float so "
            "subtractions give days directly. J2000 is JD 2451545.0; "
            "J2016.0 (the Gaia DR3 reference epoch) is JD 2457389.0."
        ),
        unit="day",
        aliases=("jd",),
    ),
    GlossaryEntry(
        term="ecliptic",
        short="Plane of Earth's orbit around the Sun.",
        long=(
            "The plane defined by Earth's orbital motion. Solar-"
            "system bodies sit close to it; ecliptic coordinates "
            "are convenient for solar-system work. UNAV's JPL "
            "connector deliberately requests ICRS / equatorial "
            "(not ecliptic) so its rows align with Gaia's frame."
        ),
        unit="(reference frame)",
        aliases=("ecliptic plane",),
    ),
    GlossaryEntry(
        term="equatorial_coordinates",
        short="The (RA, Dec) celestial coordinate system.",
        long=(
            "Coordinates aligned with Earth's equator extended into "
            "space — the natural system for ground-based astrometry. "
            "UNAV uses ICRS, the inertial realisation of equatorial "
            "coordinates fixed by extragalactic radio sources, for "
            "every row in the catalog."
        ),
        unit="degrees",
        aliases=("equatorial", "icrs"),
    ),
)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

#: Mapping the inspector uses for lookup. Keys are lowercased
#: terms + aliases; values point at the same ``GlossaryEntry``
#: instances declared above.
GLOSSARY: Dict[str, GlossaryEntry] = {}
for _entry in _ENTRIES:
    GLOSSARY[_entry.term] = _entry
    for _alias in _entry.aliases:
        GLOSSARY[_alias.lower()] = _entry


def glossary_lookup(term: str) -> Optional[GlossaryEntry]:
    """Resolve ``term`` to a ``GlossaryEntry`` (or ``None`` if
    unknown). The lookup is case-insensitive and tries the term
    verbatim, with underscores converted to spaces, and vice-versa."""
    if not term:
        return None
    raw = term.strip().lower()
    if raw in GLOSSARY:
        return GLOSSARY[raw]
    # Try underscore <-> space variants.
    if "_" in raw:
        alt = raw.replace("_", " ")
        if alt in GLOSSARY:
            return GLOSSARY[alt]
    if " " in raw:
        alt = raw.replace(" ", "_")
        if alt in GLOSSARY:
            return GLOSSARY[alt]
    return None


def glossary_terms() -> List[str]:
    """Sorted list of canonical term names (excluding aliases),
    suitable for rendering a glossary index."""
    return sorted({e.term for e in _ENTRIES})
