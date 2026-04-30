"""Epoch / time helpers for the v1.2 temporal layer.

Pure CPython, stdlib-only. Provides:

* canonical reference epochs (J2000, J2016 — Gaia DR3's reference,
  the current calendar year),
* ISO-8601 ↔ Julian Date conversions,
* Julian-year (``J2026.5``) ↔ Julian-Date conversions,
* the ``Epoch`` dataclass that the rest of the codebase passes
  around when it needs a "what time is it?" handle.

The astronomical conventions:

* **Julian Date (JD)** — continuous count of days since
  noon UT on Jan 1, 4713 BC (Julian calendar). The reference
  used by JPL Horizons, Gaia, SDSS, DESI; the natural
  exchange format for UNAV's temporal layer.
* **J2000.0** — JD 2451545.0 (2000 Jan 1, 12:00 TT).
* **J2016.0** — Gaia DR3's reference epoch
  (JD 2457389.0 = 2016 Jan 1, 12:00 TT).
* **Julian Year ("Jyear")** — fractional year along the
  365.25-day Julian century: ``Jyear = 2000 + (JD - 2451545.0) / 365.25``.

UNAV does **not** distinguish UT / UTC / TT / TDB at this
layer — astronomical-grade precision is out of v1.2 scope.
The conversions are good to a few seconds; for a stellar
proper-motion propagation that's well below the noise floor
of a Gaia-DR3-style ``pmra``/``pmdec`` measurement.

See ``docs/EPOCHS_AND_JULIAN_DATES.md`` for the contract this
module exports.
"""

from __future__ import annotations

import datetime
import math
import re
from dataclasses import dataclass, field
from typing import Optional, Union


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: J2000.0 in Julian Date.
J2000_JD: float = 2_451_545.0

#: Gaia DR3 reference epoch (J2016.0) in Julian Date.
J2016_JD: float = 2_457_389.0

#: Days per Julian year.
DAYS_PER_JULIAN_YEAR: float = 365.25

#: Days per Julian century (used when converting astrometric
#: proper motions later).
DAYS_PER_JULIAN_CENTURY: float = 36525.0

#: Default reference epoch for unmarked sources. Falls in the
#: middle of the modern Gaia / SDSS / DESI release window so
#: a row that doesn't carry an explicit reference reads as
#: "modern catalog data."
DEFAULT_REFERENCE_EPOCH_JD: float = J2016_JD

#: Compact set of well-known epochs by name; the dialog can
#: surface them in a dropdown so the artist doesn't have to
#: remember 2451545.0.
NAMED_EPOCHS = {
    "J2000.0": J2000_JD,
    "J2016.0": J2016_JD,
}


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


_ISO_RE = re.compile(
    r"^(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})"
    r"(?:[T ](?P<H>\d{1,2}):(?P<M>\d{1,2})(?::(?P<S>\d{1,2}(?:\.\d+)?))?)?$"
)


def _parse_iso(value: str) -> datetime.datetime:
    """Parse a flexible ISO-ish datetime string. Accepts
    ``"2026-01-01"``, ``"2026-01-01T00:00:00"``,
    ``"2026-01-01 12:34:56.789"``."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"empty / non-string ISO value: {value!r}")
    m = _ISO_RE.match(value.strip())
    if m is None:
        raise ValueError(f"unrecognised ISO datetime: {value!r}")
    parts = m.groupdict()
    year = int(parts["y"])
    month = int(parts["m"])
    day = int(parts["d"])
    hour = int(parts["H"]) if parts["H"] else 0
    minute = int(parts["M"]) if parts["M"] else 0
    if parts["S"]:
        sec_float = float(parts["S"])
        sec = int(sec_float)
        micro = int(round((sec_float - sec) * 1e6))
        if micro >= 1_000_000:
            sec += 1
            micro -= 1_000_000
    else:
        sec = 0
        micro = 0
    return datetime.datetime(
        year, month, day, hour, minute, sec, micro,
        tzinfo=datetime.timezone.utc,
    )


def datetime_to_julian_date(dt: datetime.datetime) -> float:
    """Convert a UTC ``datetime`` to Julian Date.

    The Meeus formula in chapter 7 of *Astronomical Algorithms*.
    Naive datetimes are treated as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    dt = dt.astimezone(datetime.timezone.utc)
    Y, M, D = dt.year, dt.month, dt.day
    if M <= 2:
        Y -= 1
        M += 12
    A = Y // 100
    B = 2 - A + A // 4
    jdn = (
        int(365.25 * (Y + 4716))
        + int(30.6001 * (M + 1))
        + D + B - 1524.5
    )
    fraction = (
        dt.hour
        + dt.minute / 60.0
        + (dt.second + dt.microsecond / 1e6) / 3600.0
    ) / 24.0
    return float(jdn) + float(fraction)


def iso_to_julian_date(value: str) -> float:
    """Convert an ISO-ish datetime string to Julian Date."""
    return datetime_to_julian_date(_parse_iso(value))


def julian_date_to_datetime(jd: float) -> datetime.datetime:
    """Convert Julian Date back to a UTC ``datetime``. Inverse
    of ``datetime_to_julian_date`` to ~ second precision."""
    jd = float(jd)
    jd_plus = jd + 0.5
    Z = math.floor(jd_plus)
    F = jd_plus - Z
    if Z < 2299161:
        A = Z
    else:
        alpha = math.floor((Z - 1867216.25) / 36524.25)
        A = Z + 1 + alpha - alpha // 4
    B = A + 1524
    C = math.floor((B - 122.1) / 365.25)
    D = math.floor(365.25 * C)
    E = math.floor((B - D) / 30.6001)
    day = B - D - math.floor(30.6001 * E) + F
    month = int(E - 1) if E < 14 else int(E - 13)
    year = int(C - 4716) if month > 2 else int(C - 4715)
    day_int = int(day)
    frac = day - day_int
    seconds_total = frac * 86400.0
    hours = int(seconds_total // 3600)
    seconds_total -= hours * 3600
    minutes = int(seconds_total // 60)
    seconds_total -= minutes * 60
    seconds_int = int(seconds_total)
    micro = int(round((seconds_total - seconds_int) * 1e6))
    if micro >= 1_000_000:
        seconds_int += 1
        micro -= 1_000_000
    # Bound carry: handle 60-second rollover.
    base = datetime.datetime(
        year, month, day_int, hours, minutes, 0,
        tzinfo=datetime.timezone.utc,
    )
    return base + datetime.timedelta(seconds=seconds_int, microseconds=micro)


def julian_date_to_iso(jd: float) -> str:
    """Render a Julian Date as a UTC ISO-8601 string (no timezone
    suffix; UNAV's convention is always UTC)."""
    dt = julian_date_to_datetime(jd)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def julian_date_to_jyear(jd: float) -> float:
    """Convert Julian Date to fractional Julian year (J2000-based).
    ``J2000.0`` → 2000.0; ``J2026.5`` → 2026.5."""
    return 2000.0 + (float(jd) - J2000_JD) / DAYS_PER_JULIAN_YEAR


def jyear_to_julian_date(jyear: float) -> float:
    """Inverse of ``julian_date_to_jyear``."""
    return J2000_JD + (float(jyear) - 2000.0) * DAYS_PER_JULIAN_YEAR


def years_between(jd_a: float, jd_b: float) -> float:
    """Signed number of Julian years from ``jd_a`` to ``jd_b``.
    Used by the proper-motion propagator."""
    return (float(jd_b) - float(jd_a)) / DAYS_PER_JULIAN_YEAR


# ---------------------------------------------------------------------------
# Epoch dataclass
# ---------------------------------------------------------------------------


@dataclass
class Epoch:
    """A single point in time the rest of the codebase passes
    around when it needs a "what time is it?" handle.

    ``jd`` is the canonical value; ``label`` is the artist-friendly
    string the dialog renders. The class accepts construction from
    any of the three forms (JD, ISO, Jyear) via ``from_*`` factories.
    """

    jd: float
    label: str = ""

    def __post_init__(self) -> None:
        if not math.isfinite(self.jd):
            raise ValueError(f"non-finite julian date: {self.jd}")
        if not self.label:
            self.label = self.iso

    # ------------------------------------------------ factories
    @classmethod
    def from_jd(cls, jd: float, label: str = "") -> "Epoch":
        return cls(jd=float(jd), label=label)

    @classmethod
    def from_iso(cls, iso: str, label: str = "") -> "Epoch":
        return cls(jd=iso_to_julian_date(iso), label=label or iso)

    @classmethod
    def from_jyear(cls, jyear: float, label: str = "") -> "Epoch":
        return cls(
            jd=jyear_to_julian_date(jyear),
            label=label or f"J{float(jyear):.3f}",
        )

    @classmethod
    def from_string(cls, value: str) -> "Epoch":
        """Permissive parser. Accepts:
          * ISO datetimes (``"2026-01-01"``);
          * named epochs (``"J2000.0"``, ``"J2016.0"``);
          * Julian-year strings (``"J2026.5"``);
          * Julian Dates (``"2461042.5"``)."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("empty epoch string")
        s = value.strip()
        # Named.
        if s in NAMED_EPOCHS:
            return cls.from_jd(NAMED_EPOCHS[s], label=s)
        # Julian year (e.g. "J2026.5").
        if s.startswith(("J", "j")) and len(s) > 1:
            try:
                return cls.from_jyear(float(s[1:]), label=s)
            except ValueError:
                pass
        # Plain Julian Date (numeric).
        try:
            return cls.from_jd(float(s), label=s)
        except ValueError:
            pass
        # Fall through: ISO.
        return cls.from_iso(s)

    # ------------------------------------------------ accessors
    @property
    def iso(self) -> str:
        return julian_date_to_iso(self.jd)

    @property
    def jyear(self) -> float:
        return julian_date_to_jyear(self.jd)

    # ------------------------------------------------ math
    def shift_days(self, days: float) -> "Epoch":
        """Return a new ``Epoch`` shifted by ``days``."""
        return Epoch(jd=self.jd + float(days))

    def shift_years(self, years: float) -> "Epoch":
        return self.shift_days(years * DAYS_PER_JULIAN_YEAR)

    def years_to(self, other: "Epoch") -> float:
        return years_between(self.jd, other.jd)


# ---------------------------------------------------------------------------
# Pretty-printing helpers
# ---------------------------------------------------------------------------


def epoch_summary(epoch: Optional[Epoch]) -> str:
    """One-line summary for a status panel. ``None`` →
    "(no epoch set)" so the dialog never goes blank."""
    if epoch is None:
        return "(no epoch set)"
    return f"{epoch.label} (JD {epoch.jd:.3f}, {epoch.jyear:.3f}J)"


def coerce_epoch(value: Union[None, "Epoch", str, float]) -> Optional[Epoch]:
    """Best-effort coercion. Used by the bridge / dialog when the
    input may be a string from a UI field, a float JD from a
    config blob, or already an ``Epoch``."""
    if value is None:
        return None
    if isinstance(value, Epoch):
        return value
    if isinstance(value, (int, float)):
        return Epoch.from_jd(float(value))
    if isinstance(value, str):
        return Epoch.from_string(value)
    raise TypeError(
        f"cannot coerce {type(value).__name__} to Epoch"
    )
