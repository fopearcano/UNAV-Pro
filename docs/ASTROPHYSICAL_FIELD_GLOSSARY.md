# Astrophysical Field Glossary

Every field name UNAV's metadata inspector renders, with a
short description and a longer one. The canonical source is
`unav_pro/knowledge/catalog_glossary.py`; this document
mirrors the same entries in human-readable form.

The inspector resolves names case-insensitively and accepts
common aliases (`"RA"` / `"ra"` / `"right ascension"` /
`"ra_deg"` all map to the same entry).

---

## ra — Right ascension

**Short.** The east-west celestial coordinate.

**Long.** The east-west coordinate on the celestial sphere,
measured along the celestial equator from the vernal equinox.
Wraps at 360°. Together with declination it gives a star's
direction from Earth in the ICRS frame.

**Unit.** degrees.

**Aliases.** `right ascension`, `ra_deg`.

---

## dec — Declination

**Short.** The north-south celestial coordinate.

**Long.** The north-south coordinate on the celestial sphere,
from -90° at the south celestial pole to +90° at the north.
Together with right ascension it gives a star's direction from
Earth in the ICRS frame.

**Unit.** degrees.

**Aliases.** `declination`, `dec_deg`.

---

## parallax

**Short.** Apparent angular shift due to Earth's orbital
motion.

**Long.** The angle (in milliarcseconds) by which a nearby
star appears to shift across the sky over a year because of
Earth's orbit. Distance in parsec is `1000 / parallax_mas`.
Only useful when the parallax is much larger than its reported
uncertainty.

**Unit.** mas (milliarcseconds).

**Aliases.** `parallax_mas`.

---

## parsec

**Short.** The standard astronomical distance unit.

**Long.** The distance at which one astronomical unit
(Earth-Sun distance) subtends one arcsecond. 1 pc ≈ 3.26
light-years. UNAV stores all heliocentric Cartesian positions
in parsec; the C4D scale factor lets the artist switch between
AU / pc / kpc / Mpc display units.

**Unit.** pc.

**Aliases.** `pc`.

---

## redshift

**Short.** Wavelength stretch caused by recession or
cosmological expansion.

**Long.** The fractional shift `z = (λ_observed - λ_rest) /
λ_rest` of a galaxy's spectrum. For `z << 1` it is roughly
`v/c` (recession velocity). UNAV converts redshift to a
Hubble-law distance only as a coarse proxy; see
[`REDSHIFT_DISTANCE_LIMITATIONS.md`](REDSHIFT_DISTANCE_LIMITATIONS.md)
for caveats.

**Unit.** dimensionless.

**Aliases.** `z`.

---

## proper_motion

**Short.** Annual angular drift across the sky.

**Long.** How fast a star's apparent position changes per
year. Reported as two components — `pmra` (along great-circle
right ascension, with `cos(dec)` baked in) and `pmdec` (along
declination). UNAV uses this for the v1.2 Time Navigator's
epoch propagation. See
[`GAIA_PROPER_MOTION_LIMITATIONS.md`](GAIA_PROPER_MOTION_LIMITATIONS.md).

**Unit.** mas/yr.

**Aliases.** `pm`, `pmra`, `pmdec`, `proper motion`.

---

## radial_velocity

**Short.** Line-of-sight velocity toward / away from us.

**Long.** Component of a star's velocity along the line of
sight, measured from Doppler-shifted spectral lines. Positive
means receding. UNAV does not currently propagate the implied
distance change over time; the v1.2 Time Navigator only
handles transverse (proper-motion) motion.

**Unit.** km/s.

**Aliases.** `rv`, `radial velocity`, `radial_velocity_kms`.

---

## apparent_magnitude

**Short.** How bright the object looks from Earth.

**Long.** The brightness of an object as seen from Earth on a
logarithmic, inverted scale: a magnitude of 0 is roughly Vega;
a difference of 5 magnitudes is a factor of 100 in flux. UNAV
uses apparent magnitude to scale render radii and to drive the
magnitude-based size mode.

**Unit.** mag.

**Aliases.** `apparent magnitude`, `phot_g_mean_mag`.

---

## absolute_magnitude

**Short.** How bright the object would look at 10 parsec.

**Long.** The apparent magnitude an object would have if
placed at 10 pc. Independent of distance; a measure of
intrinsic luminosity. `M = m - 5 · log10(d/10pc)`. UNAV does
not compute this for every row — it is only present when the
source catalog reports it.

**Unit.** mag.

**Aliases.** `absolute magnitude`.

---

## color_index

**Short.** Difference between two photometric bands.

**Long.** A two-band magnitude difference (e.g. B-V for stars,
g-r for SDSS galaxies, BP-RP for Gaia). Approximates an
object's surface temperature: bluer → smaller / more negative;
redder → larger / more positive.

**Unit.** mag.

**Aliases.** `bp_rp`, `color`, `g_r`.

---

## spectral_type

**Short.** Morgan-Keenan classification letter (+ subclass).

**Long.** A letter (O, B, A, F, G, K, M, plus L/T for brown
dwarfs) indicating the star's surface temperature from hottest
(O) to coolest (T), often with a number 0-9 for the subclass
and a roman numeral for the luminosity class.

**Unit.** string.

**Aliases.** `mk class`.

---

## epoch

**Short.** The instant a position is valid for.

**Long.** An astronomical position carries an epoch — the time
the (ra, dec, distance) tuple is valid for. Gaia DR3 is
reported at J2016.0; JPL Horizons returns whatever epoch you
asked for. UNAV's v1.2 Time Navigator stores every state at an
explicit epoch.

**Unit.** JD or ISO datetime.

**Aliases.** `reference epoch`.

---

## julian_date

**Short.** Days since 4713 BC noon UT.

**Long.** A continuous time scale used in astronomy: a single
real number counting days since noon on January 1, 4713 BC.
UNAV stores every epoch as a JD float so subtractions give
days directly. J2000 is JD 2451545.0; J2016.0 (the Gaia DR3
reference epoch) is JD 2457389.0. See
[`EPOCHS_AND_JULIAN_DATES.md`](EPOCHS_AND_JULIAN_DATES.md).

**Unit.** day.

**Aliases.** `jd`.

---

## ecliptic

**Short.** Plane of Earth's orbit around the Sun.

**Long.** The plane defined by Earth's orbital motion. Solar-
system bodies sit close to it; ecliptic coordinates are
convenient for solar-system work. UNAV's JPL connector
deliberately requests ICRS / equatorial (not ecliptic) so its
rows align with Gaia's frame.

**Unit.** reference frame.

**Aliases.** `ecliptic plane`.

---

## equatorial_coordinates

**Short.** The (RA, Dec) celestial coordinate system.

**Long.** Coordinates aligned with Earth's equator extended
into space — the natural system for ground-based astrometry.
UNAV uses ICRS, the inertial realisation of equatorial
coordinates fixed by extragalactic radio sources, for every
row in the catalog.

**Unit.** degrees.

**Aliases.** `equatorial`, `icrs`.

---

## How to add a new term

1. Append a `GlossaryEntry(...)` to `_ENTRIES` in
   `unav_pro/knowledge/catalog_glossary.py`.
2. Mirror the entry here so the doc and the code agree.
3. Run the tests — `test_required_terms_are_defined` will
   pass automatically; if you reference the new term from the
   inspector or summary you should also add a focused test
   asserting the inspector renders it.
