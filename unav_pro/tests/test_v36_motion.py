"""v3.6 motion-helper tests."""

from __future__ import annotations

import math

import pytest

from cinematic import (
    EASING_PRESETS,
    ApproachDepartParameters,
    DriftParameters,
    Easing,
    FlybyParameters,
    OrbitParameters,
    apply_easing,
    approach_depart_position,
    approach_depart_track,
    determinism_signature,
    drift_offset,
    drift_track,
    flyby_position,
    flyby_track,
    orbit_position,
    orbit_track,
)


# ---------------------------------------------------------------------------
# Easing
# ---------------------------------------------------------------------------


def test_easing_presets_complete():
    expected = {
        Easing.LINEAR, Easing.EASE_IN, Easing.EASE_OUT,
        Easing.EASE_IN_OUT, Easing.STEP, Easing.SLOW_SETTLE,
    }
    assert expected == set(EASING_PRESETS)


def test_apply_easing_endpoints_are_zero_and_one():
    for easing in EASING_PRESETS:
        if easing is Easing.STEP:
            assert apply_easing(0.0, easing) == 0.0
            assert apply_easing(1.0, easing) == 1.0
        else:
            assert math.isclose(apply_easing(0.0, easing), 0.0, abs_tol=1e-6)
            assert math.isclose(apply_easing(1.0, easing), 1.0, abs_tol=1e-6)


def test_apply_easing_clamps_inputs():
    for easing in EASING_PRESETS:
        assert 0.0 <= apply_easing(-1.0, easing) <= 1.0
        assert 0.0 <= apply_easing(2.0, easing) <= 1.0


def test_apply_easing_linear_is_identity():
    assert apply_easing(0.5, Easing.LINEAR) == 0.5


def test_apply_easing_step_jumps_at_one():
    assert apply_easing(0.99, Easing.STEP) == 0.0
    assert apply_easing(1.0, Easing.STEP) == 1.0


def test_apply_easing_ease_in_starts_slow():
    assert apply_easing(0.25, Easing.EASE_IN) < 0.25


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------


def test_drift_offset_is_three_tuple():
    out = drift_offset(t_seconds=1.0, parameters=DriftParameters())
    assert len(out) == 3


def test_drift_offset_zero_amplitude_returns_zero():
    out = drift_offset(
        t_seconds=1.0,
        parameters=DriftParameters(amplitude=0.0),
    )
    assert out == (0.0, 0.0, 0.0)


def test_drift_offset_deterministic_for_same_seed():
    a = drift_offset(t_seconds=2.5, parameters=DriftParameters(seed=42))
    b = drift_offset(t_seconds=2.5, parameters=DriftParameters(seed=42))
    assert a == b


def test_drift_offset_differs_for_different_seeds():
    a = drift_offset(t_seconds=2.5, parameters=DriftParameters(seed=0))
    b = drift_offset(t_seconds=2.5, parameters=DriftParameters(seed=99))
    assert a != b


def test_drift_track_count():
    track = drift_track(
        duration_seconds=4.0, sample_count=10,
        parameters=DriftParameters(),
    )
    assert len(track) == 10


def test_drift_track_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        drift_track(duration_seconds=0, sample_count=10)
    with pytest.raises(ValueError):
        drift_track(duration_seconds=1.0, sample_count=0)


def test_drift_track_single_sample():
    track = drift_track(
        duration_seconds=1.0, sample_count=1,
        parameters=DriftParameters(),
    )
    assert len(track) == 1


# ---------------------------------------------------------------------------
# Orbit
# ---------------------------------------------------------------------------


def test_orbit_position_at_zero_t():
    pos = orbit_position(
        target=(0, 0, 0), t=0.0,
        parameters=OrbitParameters(radius=10.0),
    )
    # Distance from target equals radius.
    d = math.sqrt(sum(c * c for c in pos))
    assert math.isclose(d, 10.0, rel_tol=1e-6)


def test_orbit_position_full_revolution_returns_to_start():
    params = OrbitParameters(radius=10.0, revolutions=1.0)
    a = orbit_position(target=(0, 0, 0), t=0.0, parameters=params)
    b = orbit_position(target=(0, 0, 0), t=1.0, parameters=params)
    for ai, bi in zip(a, b):
        assert math.isclose(ai, bi, abs_tol=1e-6)


def test_orbit_position_clamps_t():
    params = OrbitParameters()
    a = orbit_position(target=(0, 0, 0), t=-1.0, parameters=params)
    b = orbit_position(target=(0, 0, 0), t=0.0, parameters=params)
    assert a == b


def test_orbit_track_returns_n_samples():
    track = orbit_track(
        target=(0, 0, 0), sample_count=8,
        parameters=OrbitParameters(),
    )
    assert len(track) == 8


def test_orbit_track_deterministic():
    params = OrbitParameters(radius=5.0, revolutions=2.0)
    a = orbit_track(target=(0, 0, 0), sample_count=16, parameters=params)
    b = orbit_track(target=(0, 0, 0), sample_count=16, parameters=params)
    assert a == b


def test_orbit_track_handles_zero_axis():
    """A zero-vector axis should default to up."""
    params = OrbitParameters(radius=5.0, axis=(0, 0, 0))
    track = orbit_track(target=(0, 0, 0), sample_count=4, parameters=params)
    assert len(track) == 4


def test_orbit_track_rejects_zero_samples():
    with pytest.raises(ValueError):
        orbit_track(target=(0, 0, 0), sample_count=0,
                    parameters=OrbitParameters())


# ---------------------------------------------------------------------------
# Flyby
# ---------------------------------------------------------------------------


def test_flyby_endpoints_are_far_from_target():
    params = FlybyParameters(
        approach_distance=100.0, depart_distance=100.0,
    )
    start = flyby_position(target=(0, 0, 0), t=0.0, parameters=params)
    end = flyby_position(target=(0, 0, 0), t=1.0, parameters=params)
    assert math.sqrt(sum(c * c for c in start)) > 50.0
    assert math.sqrt(sum(c * c for c in end)) > 50.0


def test_flyby_passes_through_offset_at_midpoint():
    params = FlybyParameters(
        approach_distance=100.0, depart_distance=100.0,
        miss_offset=(5.0, 0.0, 0.0),
        easing=Easing.LINEAR,
    )
    mid = flyby_position(target=(0, 0, 0), t=0.5, parameters=params)
    assert math.isclose(mid[0], 5.0, abs_tol=1e-6)


def test_flyby_track_length():
    track = flyby_track(
        target=(0, 0, 0), sample_count=20,
        parameters=FlybyParameters(),
    )
    assert len(track) == 20


def test_flyby_track_deterministic():
    params = FlybyParameters()
    a = flyby_track(target=(0, 0, 0), sample_count=8, parameters=params)
    b = flyby_track(target=(0, 0, 0), sample_count=8, parameters=params)
    assert a == b


# ---------------------------------------------------------------------------
# Approach / depart
# ---------------------------------------------------------------------------


def test_approach_endpoints():
    params = ApproachDepartParameters(
        mode="approach", axis=(0, 0, 1),
        distance=100.0, settle_distance=10.0,
        easing=Easing.LINEAR,
    )
    start = approach_depart_position(target=(0, 0, 0), t=0.0, parameters=params)
    end = approach_depart_position(target=(0, 0, 0), t=1.0, parameters=params)
    assert start == (0.0, 0.0, 100.0)
    assert end == (0.0, 0.0, 10.0)


def test_depart_reverses_endpoints():
    params = ApproachDepartParameters(
        mode="depart", axis=(0, 0, 1),
        distance=100.0, settle_distance=10.0,
        easing=Easing.LINEAR,
    )
    start = approach_depart_position(target=(0, 0, 0), t=0.0, parameters=params)
    end = approach_depart_position(target=(0, 0, 0), t=1.0, parameters=params)
    assert start == (0.0, 0.0, 10.0)
    assert end == (0.0, 0.0, 100.0)


def test_approach_depart_invalid_mode_raises():
    with pytest.raises(ValueError):
        approach_depart_position(
            target=(0, 0, 0), t=0.5,
            parameters=ApproachDepartParameters(mode="zoom"),
        )


def test_approach_depart_track_length():
    track = approach_depart_track(
        target=(0, 0, 0), sample_count=12,
        parameters=ApproachDepartParameters(),
    )
    assert len(track) == 12


# ---------------------------------------------------------------------------
# Determinism signatures
# ---------------------------------------------------------------------------


def test_determinism_signature_orbit():
    sig_a = determinism_signature(
        target=(0, 0, 0),
        parameters=OrbitParameters(radius=5.0),
    )
    sig_b = determinism_signature(
        target=(0, 0, 0),
        parameters=OrbitParameters(radius=5.0),
    )
    assert sig_a == sig_b


def test_determinism_signature_flyby():
    a = determinism_signature(
        target=(0, 0, 0), parameters=FlybyParameters(),
    )
    b = determinism_signature(
        target=(0, 0, 0), parameters=FlybyParameters(),
    )
    assert a == b


def test_determinism_signature_drift_seeded():
    a = determinism_signature(
        target=(0, 0, 0),
        parameters=DriftParameters(seed=7),
    )
    b = determinism_signature(
        target=(0, 0, 0),
        parameters=DriftParameters(seed=7),
    )
    assert a == b


def test_determinism_signature_unknown_param_type_raises():
    with pytest.raises(TypeError):
        determinism_signature(target=(0, 0, 0), parameters=object())
