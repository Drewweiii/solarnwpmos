"""Cloud motion vector estimation from two consecutive raster frames.

This is the "ต่อยอด" extension: a coarse regional cloud-motion signal (speed +
direction) that helps the minute-ahead CNN-LSTM anticipate an approaching cloud
front, computed from the same small (7x5 pixel) tile geolocation.py calibrates.
At that resolution this cannot track individual cloud cells precisely - it's a
dominant-shift estimate for the whole tile, using classic FFT-based phase
correlation (Kuglin & Hines, 1975), not object tracking.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MotionVector:
    shift_rows: float  # pixels/interval; positive = southward (row index increases southward in this grid)
    shift_cols: float  # pixels/interval; positive = eastward (col index increases eastward in this grid)
    speed_kmh: float
    direction_deg: float  # compass bearing the cloud pattern is moving TOWARD (0=N, 90=E)


def phase_correlation_shift(prev: np.ndarray, curr: np.ndarray) -> tuple[float, float]:
    """Dominant integer-pixel shift of `curr` relative to `prev` via FFT phase correlation.
    Returns (shift_rows, shift_cols). NaNs (e.g. off-disk fill values) are replaced
    with the frame's own mean so they don't dominate the cross-power spectrum.
    """
    if prev.shape != curr.shape:
        raise ValueError(f"frames must have the same shape to compute motion, got {prev.shape} vs {curr.shape}")

    a = np.nan_to_num(prev, nan=np.nanmean(prev))
    b = np.nan_to_num(curr, nan=np.nanmean(curr))

    fa = np.fft.fft2(a)
    fb = np.fft.fft2(b)
    cross_power = fb * np.conj(fa)  # peak of the IFFT gives curr's shift relative to prev
    denom = np.abs(cross_power)
    denom[denom == 0] = 1e-12
    r = np.fft.ifft2(cross_power / denom).real

    rows, cols = r.shape
    peak_row, peak_col = np.unravel_index(np.argmax(r), r.shape)

    shift_row = peak_row - rows if peak_row > rows // 2 else peak_row
    shift_col = peak_col - cols if peak_col > cols // 2 else peak_col
    return float(shift_row), float(shift_col)


def estimate_cloud_motion(
    prev: np.ndarray, curr: np.ndarray, row_spacing_km: float, col_spacing_km: float, interval_minutes: float
) -> MotionVector:
    shift_row, shift_col = phase_correlation_shift(prev, curr)

    dy_km = shift_row * row_spacing_km  # +south
    dx_km = shift_col * col_spacing_km  # +east
    distance_km = math.hypot(dy_km, dx_km)
    speed_kmh = distance_km / (interval_minutes / 60) if interval_minutes > 0 else 0.0

    north_component = -dy_km
    east_component = dx_km
    direction_deg = (math.degrees(math.atan2(east_component, north_component)) + 360) % 360

    return MotionVector(shift_rows=shift_row, shift_cols=shift_col, speed_kmh=speed_kmh, direction_deg=direction_deg)
