# Gaia Proper Motion — Approximation and Limitations

UNAV Pro v1.2 propagates Gaia stars to a user-chosen epoch
using a linear ICRS great-circle approximation. This document
records **exactly what the math does**, what error it incurs,
and what it does *not* model. Read it before assuming a
propagated screen position is "correct" for a high-precision
science workflow — UNAV is a visualisation plugin, not an
astrometric pipeline.

---

## 1. The math UNAV implements

For a star with reference position ``(ra₀, dec₀)`` at reference
epoch ``T₀`` and proper-motion rates
``(pmra*, pmdec)`` (mas / yr, where ``pmra* = pmra · cos(dec)``
in the ICRS great-circle convention), the propagated position
at target epoch ``T`` is:

```
Δt        = (T - T₀) / 365.25                  [Julian years]
Δdec      = pmdec · Δt / 3_600_000             [degrees]
Δra·cosδ  = pmra* · Δt / 3_600_000             [degrees]
dec       = dec₀ + Δdec                        [degrees]
ra        = ra₀ + Δra·cosδ / cos(dec₀)         [degrees, with cos(dec) clamp]
```

Implemented in
``unav_pro/core/proper_motion.py::propagate_position``.

* **Cos(dec) factor.** Gaia reports ``pmra`` in great-circle
  units (mas/yr along the small circle of declination). UNAV
  divides by ``cos(dec₀)`` to convert back into "ICRS RA
  degrees". At dec = 60° this doubles the displacement; at the
  pole it diverges.
* **Pole-singularity clamp.** When ``|dec| > 89.9999°``, the
  ``cos(dec)`` correction is skipped and ``Δra`` is set to 0.
  A star within milli-arcsec of the celestial pole isn't a
  realistic input — but *something* has to happen there, and
  "freeze RA at the pole" is the least-wrong behaviour.
* **Dec clamp.** After applying ``Δdec``, the result is clamped
  to ``[-90°, +90°]`` to keep the value in the canonical range.
* **RA wrap.** RA is wrapped into ``[0°, 360°)`` after the
  update.

---

## 2. Error budget

UNAV's linear propagation is correct to **first order** in
``Δt``. Real stellar motion is not first-order; the deviations
are:

### 2.1 Tangent-plane vs spherical

The linear formula is the first term of the Taylor expansion of
the rigorous spherical great-circle propagation. For a typical
Gaia star:

| Δt        | Typical pm (5 mas/yr)  | Linear-vs-spherical error |
|-----------|------------------------|----------------------------|
| 1 year    | 0.0014″                | < 1 µas                    |
| 100 years | 0.14′                  | ~10 µas                    |
| 1000 years | 1.4°                  | ~few mas                   |
| 10 000 yr | 14°                   | ~arc-seconds               |

For the v1.2 visualisation use case (a few decades to a few
centuries) the linear approximation is **well below the
on-screen resolution** of the C4D viewport. Beyond ~1000 years
the spherical-vs-linear error becomes visible.

### 2.2 Radial velocity

UNAV does **not** propagate distance. A star's radial velocity
shifts its parsec coordinate over time; for a 100 km/s motion
that's ~0.0001 pc/yr, which is below the visualisation
threshold for almost all Gaia stars but accumulates over
millennia.

### 2.3 Parallax / annual aberration

The geometric apparent position of a nearby star wobbles by
~2 × parallax (mas) over a year due to Earth's orbital motion.
UNAV uses the **barycentric** mean position only — it does not
model the annual parallactic ellipse. For an artist exploring
the local neighbourhood, this means a 10 pc star will
"officially" sit at one position regardless of the time of
year.

### 2.4 Aberration / nutation / precession of the ICRS frame

The ICRS is fixed by definition. UNAV does **not** model:

* Stellar aberration (the ~20″ apparent displacement from the
  observer's velocity).
* Nutation (the 18.6-year wobble of the equatorial plane).
* Precession (the 26 ka procession of the equinoxes).

A user who wants "what does the sky look like in 10 000 BC"
will see the propagated mean star positions, not the
contemporary observer's view from Earth.

### 2.5 Covariance

Gaia DR3 reports *correlated* errors on the
(ra, dec, parallax, pmra, pmdec) 5-tuple. UNAV propagates the
**mean** only; the per-uid uncertainty does not flow through.
Showing error ellipses on the propagated position is out of
scope for v1.2 — the visualisation is a single point per star.

### 2.6 Non-linear motion

A small fraction of Gaia stars are in unresolved binaries; their
photocentre wobbles on the binary period (1–100 years for the
unresolved population). UNAV's linear model does not capture
this — these stars will appear to drift in a straight line when
they really cycle on a small ellipse.

---

## 3. What this means in practice

| Use case                                         | Linear-propagation OK? |
|--------------------------------------------------|-------------------------|
| "Where is Sirius in 2050?"                       | ✓ (sub-pixel error)     |
| "Show me the constellations in 1000 AD."         | ✓ (visible drift; error << display res) |
| "Show me the constellations in 10 000 BC."       | ⚠ (linear error becomes visible at the pole; precession of the equatorial frame *not* modelled) |
| "What does Tau Ceti's binary look like?"         | ✗ (no binary motion)    |
| "Compute astrometric residuals for science."     | ✗ (use astropy / SOFA / SPICE) |

UNAV is a Cinema 4D plugin for **visualising** astronomical
catalogs. The propagation in ``core/proper_motion.py`` is the
right tool for visual fidelity over decades, the wrong tool
for sub-mas astrometric work.

---

## 4. The propagation API

```python
from core.proper_motion import (
    ProperMotionState, propagate_position, propagate_object,
    is_propagatable, reference_epoch_for,
)
from core.time_model import J2016_JD

# Low-level: pure (ra, dec) propagation.
state = ProperMotionState(
    ra_deg=10.0, dec_deg=45.0,
    pmra_masyr=20.0, pmdec_masyr=-5.0,
    reference_epoch_jd=J2016_JD,
)
ra, dec = propagate_position(state, target_jd=J2016_JD + 365.25 * 100)

# High-level: clones a CatalogObject and invalidates its cache.
obj2 = propagate_object(obj, target_jd=...)
```

The ``propagate_object`` path is what the temporal resolver
uses internally. It does the (ra, dec) update then re-runs
``compute_derived_fields`` so the cartesian xyz and the C4D-
units cache are coherent at the new epoch.

---

## 5. Test coverage

``unav_pro/tests/test_proper_motion.py`` covers:

* Zero-Δt is identity.
* 1°/yr in dec → 100° after 100 yr.
* cos(dec) correction at dec=60° doubles the RA displacement.
* Pole-singularity clamp at dec=89.99999°.
* Dec output clamps at ±90°.
* Negative pmra moves RA west.
* RA wraps through 360°.
* ``propagate_object`` clones (does not mutate) and invalidates
  the cartesian / c4d cache on the result.
* ``is_propagatable`` is False for a row with no pmra/pmdec.
* ``reference_epoch_for`` returns J2016 for Gaia, the row's
  explicit ``reference_epoch_jd`` otherwise.

---

## 6. References

* Lindegren, L. et al. (2021). *Gaia Early Data Release 3 —
  The astrometric solution*. A&A, 649, A2.
* Meeus, J. (1998). *Astronomical Algorithms*, 2nd edition,
  ch. 21 ("Precession").
* IAU Resolution B1.3 (2000) — definition of the ICRS.
