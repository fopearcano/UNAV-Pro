# Epochs and Julian Dates

The v1.2 time model. How UNAV represents an instant in time,
which epochs are first-class, and the helpers in
``core/time_model.py`` you can lean on.

---

## 1. Why Julian Date?

UNAV stores every temporal field as a **Julian Date** (JD), a
single ``float64`` counting **days since 4713 BC noon UT**. The
choice has three motivations:

* **No timezone surface.** A JD is a scalar. There's no
  "is this UTC or local?" question to answer. UNAV's UI surface
  only renders ISO strings — the storage / wire / DB layer
  speaks JD.
* **Stable arithmetic.** ``epoch_b - epoch_a`` is days. The
  resolver's "how far has this star drifted in years" calculation
  is just ``(target_jd - reference_jd) / 365.25``.
* **Astronomy convention.** Gaia DR3 reports its astrometry at
  ``epoch=2016.0`` (JD 2457389.0). JPL Horizons accepts JD or
  calendar dates interchangeably. SPICE kernels are JD-native.
  Picking JD means UNAV's data layer matches the upstream
  conventions exactly.

A double has ~16 decimal digits of precision; with JDs near
2.46 × 10⁶ (today), that leaves ~10⁻¹⁰ days ≈ 10 µs of
representable precision — far beyond what any UNAV consumer
needs.

---

## 2. The named anchors UNAV recognises

| Name        | JD             | Calendar date (ISO UTC)     | Source                          |
|-------------|----------------|------------------------------|---------------------------------|
| ``J2000.0`` | 2451545.0      | 2000-01-01T12:00:00         | IAU standard reference epoch.   |
| ``J2016.0`` | 2457389.0      | 2016-01-01T12:00:00         | Gaia DR3 reference epoch.       |

These two are exposed as the constants ``J2000_JD`` and
``J2016_JD`` from ``core/time_model.py``, and as the
``NAMED_EPOCHS`` mapping for string-based lookup.

The default reference epoch for new-`TimeNavigatorState`
instances is **J2016.0** because Gaia DR3 — UNAV's primary
star catalog — is the most common dataset the artist will be
exploring.

---

## 3. The conversions UNAV provides

All in ``core/time_model.py``. Stdlib-only; no astropy / no
SPICE dependency.

### 3.1 ISO ↔ JD

```python
from core.time_model import iso_to_julian_date, julian_date_to_iso

iso_to_julian_date("2026-01-01T00:00:00")   # → 2461041.5
julian_date_to_iso(2461041.5)                # → "2026-01-01T00:00:00"
```

Implemented via the Meeus formulation (Astronomical Algorithms,
ch. 7). Round-trips through the Gregorian boundary correctly.
``datetime.datetime`` objects are also accepted by
``iso_to_julian_date``.

### 3.2 Julian Year ↔ JD

```python
from core.time_model import julian_date_to_jyear, jyear_to_julian_date

julian_date_to_jyear(2457389.0)   # → 2016.0
jyear_to_julian_date(2016.0)      # → 2457389.0
```

A "Julian year" is exactly 365.25 days. ``2016.0`` means "2016
January 1.5 TT". Gaia DR3's ``ref_epoch`` field is reported in
this convention.

### 3.3 ``years_between``

```python
from core.time_model import years_between
years_between(J2016_JD, J2016_JD + 365.25)   # → 1.0
```

A thin convenience for the proper-motion resolver.

### 3.4 ``coerce_epoch``

The Time Navigator dialog and several CLI tools accept any of:
``None``, an ``Epoch``, a float (JD or Jyear, auto-detected),
an ISO datetime string, a named-epoch string. ``coerce_epoch``
unifies them:

```python
from core.time_model import coerce_epoch

coerce_epoch("J2016.0").jd        # → 2457389.0
coerce_epoch("2026-01-01").jd     # → 2461041.5
coerce_epoch(2461041.5).jd        # → 2461041.5
coerce_epoch(2016.0).jd           # → 2457389.0  (interpreted as Jyear)
coerce_epoch(None)                # → None
```

The float / Jyear disambiguation: values outside
``[1900, 2200]`` are treated as JDs, values inside are treated as
Jyears. The reasoning is documented in the implementation — it's
a heuristic and the typed ``Epoch.from_*`` constructors are
preferred for code that knows what it has.

### 3.5 The ``Epoch`` dataclass

```python
@dataclass
class Epoch:
    jd: float
    label: str = ""
```

A typed wrapper used by every UNAV API that takes an epoch.
Construction goes through ``Epoch.from_jd``, ``Epoch.from_iso``,
``Epoch.from_jyear``, or ``Epoch.from_name``. The ``label`` is
free-form (used by the dialog to display the user-typed string
verbatim).

---

## 4. Timescale: TT vs UTC

UNAV does **not** distinguish between Terrestrial Time (TT) and
UTC at the v1.2 level. The Gaia and JPL reference epochs are
TT-flavoured under the hood (TT = TAI + 32.184 s ≈ UTC + 69 s
today), but for the visual-fidelity needs UNAV serves
(scene-position drift over months / years / centuries) the ~70-
second offset is **invisible** — a star with the largest known
proper motion (Barnard's, ~10 arcsec / yr) drifts ~2 micro-arcsec
in 70 s, which is roughly six orders of magnitude below the
plugin's screen resolution.

If a future feature needs sub-second precision (e.g. spacecraft
flyby cinematics), the abstraction will need to carry an explicit
timescale tag. v1.2 does not.

---

## 5. Where the constants surface

| Constant                       | Value      | Where defined                         |
|--------------------------------|------------|----------------------------------------|
| ``J2000_JD``                   | 2451545.0  | ``core/time_model.py``                 |
| ``J2016_JD``                   | 2457389.0  | ``core/time_model.py``                 |
| ``DAYS_PER_JULIAN_YEAR``       | 365.25     | ``core/time_model.py``                 |
| ``DEFAULT_REFERENCE_EPOCH_JD`` | J2016_JD   | ``core/time_model.py``                 |
| ``DEFAULT_STEP_DAYS``          | 1.0        | ``core/time_navigator.py``             |
| ``MAX_STEP_DAYS``              | 365_250    | ``core/time_navigator.py`` (1 millennium / click) |

---

## 6. Test coverage

``unav_pro/tests/test_time_model.py`` covers:

* Round-trip ``iso_to_julian_date`` ↔ ``julian_date_to_iso``
  across J2000, J2016, modern and historical dates.
* ``julian_date_to_jyear`` / ``jyear_to_julian_date`` round-trip.
* ``coerce_epoch`` for every accepted input type.
* Named-epoch lookups and ``Epoch.from_name`` validation.
* ``Epoch`` dataclass field handling (label, equality, repr).
