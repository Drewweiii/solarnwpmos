import numpy as np
import pytest

from himawari_ingestion.motion import estimate_cloud_motion, phase_correlation_shift


def test_phase_correlation_recovers_known_positive_shift():
    rng = np.random.default_rng(0)
    base = rng.normal(size=(7, 5))
    shifted = np.roll(base, shift=(2, 1), axis=(0, 1))

    shift_row, shift_col = phase_correlation_shift(base, shifted)

    assert shift_row == pytest.approx(2.0)
    assert shift_col == pytest.approx(1.0)


def test_phase_correlation_recovers_known_negative_shift():
    rng = np.random.default_rng(1)
    base = rng.normal(size=(7, 5))
    shifted = np.roll(base, shift=(-2, -1), axis=(0, 1))

    shift_row, shift_col = phase_correlation_shift(base, shifted)

    assert shift_row == pytest.approx(-2.0)
    assert shift_col == pytest.approx(-1.0)


def test_phase_correlation_zero_shift_for_identical_frames():
    rng = np.random.default_rng(2)
    base = rng.normal(size=(7, 5))

    shift_row, shift_col = phase_correlation_shift(base, base.copy())

    assert shift_row == pytest.approx(0.0)
    assert shift_col == pytest.approx(0.0)


def test_phase_correlation_rejects_mismatched_shapes():
    with pytest.raises(ValueError):
        phase_correlation_shift(np.zeros((7, 5)), np.zeros((3, 3)))


def test_estimate_cloud_motion_direction_for_south_east_shift():
    rng = np.random.default_rng(0)
    base = rng.normal(size=(7, 5))
    shifted = np.roll(base, shift=(2, 1), axis=(0, 1))  # +row=south, +col=east

    mv = estimate_cloud_motion(base, shifted, row_spacing_km=2.2, col_spacing_km=2.8, interval_minutes=10)

    assert mv.speed_kmh > 0
    assert 90 < mv.direction_deg < 180  # between due-east and due-south


def test_estimate_cloud_motion_handles_nan_fill_values():
    rng = np.random.default_rng(3)
    base = rng.normal(size=(7, 5))
    base_with_nan = base.copy()
    base_with_nan[0, 0] = np.nan
    shifted = np.roll(base, shift=(1, 0), axis=(0, 1))

    mv = estimate_cloud_motion(base_with_nan, shifted, row_spacing_km=2.2, col_spacing_km=2.8, interval_minutes=10)
    assert mv.speed_kmh >= 0  # must not raise/NaN out
