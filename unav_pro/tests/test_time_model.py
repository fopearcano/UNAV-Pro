"""Tests for unav_pro.core.time_model (v1.2)."""

from __future__ import annotations

import datetime

import pytest

from core.time_model import (
    DAYS_PER_JULIAN_YEAR,
    DEFAULT_REFERENCE_EPOCH_JD,
    Epoch,
    J2000_JD,
    J2016_JD,
    NAMED_EPOCHS,
    coerce_epoch,
    datetime_to_julian_date,
    epoch_summary,
    iso_to_julian_date,
    julian_date_to_datetime,
    julian_date_to_iso,
    julian_date_to_jyear,
    jyear_to_julian_date,
    years_between,
)


# ---------------------------------------------------------------------------
# Reference epochs
# ---------------------------------------------------------------------------


def test_j2000_constant_matches_iso_round_trip():
    assert iso_to_julian_date("2000-01-01T12:00:00") == pytest.approx(J2000_JD)


def test_j2016_constant_matches_iso_round_trip():
    assert iso_to_julian_date("2016-01-01T12:00:00") == pytest.approx(J2016_JD)


def test_default_reference_epoch_is_j2016():
    assert DEFAULT_REFERENCE_EPOCH_JD == J2016_JD


# ---------------------------------------------------------------------------
# ISO ↔ JD
# ---------------------------------------------------------------------------


def test_iso_to_jd_for_known_dates():
    assert iso_to_julian_date("2026-01-01T00:00:00") == pytest.approx(2461041.5)


def test_iso_to_jd_handles_date_only():
    # 2026-01-01 (00:00 UT) == JD 2461041.5
    assert iso_to_julian_date("2026-01-01") == pytest.approx(2461041.5)


def test_iso_with_microseconds_round_trips_to_seconds():
    jd = iso_to_julian_date("2026-04-30T12:00:00.500000")
    iso = julian_date_to_iso(jd)
    # round-trip is seconds-precise.
    assert iso.startswith("2026-04-30T12:00:")


def test_iso_to_jd_rejects_garbage():
    with pytest.raises(ValueError):
        iso_to_julian_date("not a date")


def test_jd_to_iso_round_trips_for_j2000():
    iso = julian_date_to_iso(J2000_JD)
    assert iso == "2000-01-01T12:00:00"


# ---------------------------------------------------------------------------
# JD ↔ Jyear
# ---------------------------------------------------------------------------


def test_jyear_at_j2000_is_2000():
    assert julian_date_to_jyear(J2000_JD) == pytest.approx(2000.0)


def test_jyear_at_j2016_is_2016():
    assert julian_date_to_jyear(J2016_JD) == pytest.approx(2016.0)


def test_jyear_round_trip():
    jd = jyear_to_julian_date(2026.5)
    jyear = julian_date_to_jyear(jd)
    assert jyear == pytest.approx(2026.5)


def test_years_between_signs_correctly():
    assert years_between(J2000_JD, J2016_JD) == pytest.approx(16.0)
    assert years_between(J2016_JD, J2000_JD) == pytest.approx(-16.0)


# ---------------------------------------------------------------------------
# Epoch dataclass
# ---------------------------------------------------------------------------


def test_epoch_from_iso_sets_label_to_iso_string():
    e = Epoch.from_iso("2026-01-01T00:00:00")
    assert e.iso == "2026-01-01T00:00:00"
    assert e.label  # non-empty


def test_epoch_from_jyear_propagates():
    e = Epoch.from_jyear(2016.0)
    assert e.jd == pytest.approx(J2016_JD)


def test_epoch_from_string_recognises_named_epochs():
    e = Epoch.from_string("J2000.0")
    assert e.jd == pytest.approx(J2000_JD)


def test_epoch_from_string_recognises_jyear_strings():
    e = Epoch.from_string("J2026.5")
    assert e.jyear == pytest.approx(2026.5)


def test_epoch_from_string_recognises_julian_dates():
    e = Epoch.from_string("2451545.0")
    assert e.jd == pytest.approx(2451545.0)


def test_epoch_from_string_falls_back_to_iso():
    e = Epoch.from_string("2026-04-30")
    assert e.iso.startswith("2026-04-30")


def test_epoch_rejects_empty_string():
    with pytest.raises(ValueError):
        Epoch.from_string("")


def test_epoch_rejects_non_finite_jd():
    with pytest.raises(ValueError):
        Epoch.from_jd(float("nan"))


def test_epoch_shift_days_returns_new_instance():
    e = Epoch.from_iso("2026-01-01T00:00:00")
    shifted = e.shift_days(7.0)
    assert shifted.jd == pytest.approx(e.jd + 7.0)
    assert e.jd != shifted.jd  # original untouched


def test_epoch_shift_years_round_trips_via_days():
    e = Epoch.from_jd(J2000_JD)
    shifted = e.shift_years(1.0)
    assert shifted.jd == pytest.approx(J2000_JD + DAYS_PER_JULIAN_YEAR)


def test_epoch_years_to_self_is_zero():
    e = Epoch.from_jd(J2000_JD)
    assert e.years_to(e) == 0.0


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------


def test_coerce_none_returns_none():
    assert coerce_epoch(None) is None


def test_coerce_epoch_returns_input():
    e = Epoch.from_jd(J2000_JD)
    assert coerce_epoch(e) is e


def test_coerce_float_treated_as_jd():
    assert coerce_epoch(2451545.0).jd == pytest.approx(J2000_JD)


def test_coerce_string_routes_to_from_string():
    assert coerce_epoch("J2000.0").jd == pytest.approx(J2000_JD)


def test_coerce_rejects_bad_type():
    with pytest.raises(TypeError):
        coerce_epoch(["not", "an", "epoch"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Pretty rendering
# ---------------------------------------------------------------------------


def test_epoch_summary_handles_none():
    assert "no epoch" in epoch_summary(None).lower()


def test_epoch_summary_includes_jd_and_jyear():
    s = epoch_summary(Epoch.from_jd(J2016_JD))
    assert "2457389" in s  # JD digits
    assert "2016" in s     # Jyear


# ---------------------------------------------------------------------------
# datetime conversions
# ---------------------------------------------------------------------------


def test_datetime_aware_round_trip():
    dt = datetime.datetime(
        2026, 4, 30, 12, 0, 0, tzinfo=datetime.timezone.utc,
    )
    jd = datetime_to_julian_date(dt)
    back = julian_date_to_datetime(jd)
    assert back.year == 2026 and back.month == 4 and back.day == 30


def test_datetime_naive_treated_as_utc():
    naive = datetime.datetime(2026, 1, 1, 0, 0, 0)
    aware = naive.replace(tzinfo=datetime.timezone.utc)
    assert datetime_to_julian_date(naive) == datetime_to_julian_date(aware)


# ---------------------------------------------------------------------------
# Named epochs registry
# ---------------------------------------------------------------------------


def test_named_epochs_contains_known_anchors():
    assert "J2000.0" in NAMED_EPOCHS
    assert "J2016.0" in NAMED_EPOCHS
