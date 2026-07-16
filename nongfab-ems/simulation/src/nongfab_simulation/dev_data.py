"""Synthetic "current conditions" generator - dev/demo only, used wherever no
real accumulated irradiance/temperature history exists yet (Module 1/2's
caveat - see README "Known gaps"). Extracted so this module's own dev API
and Module 6's production API use the exact same generator rather than two
copies that could silently drift apart.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd


def synthetic_day_irradiance_temp(n_hours: int = 24, seed: int = 0) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """`idx` spans one UTC calendar day (00:00-23:00), so this function's own
    day/night sine phase has to be chosen relative to UTC, but the plant is
    in Thailand (Asia/Bangkok, UTC+7) - `(hour + 1)` peaks the curve at
    05:00 UTC (12:00 ICT, Thai local noon), with the positive (daylight)
    part of the curve spanning UTC hours 0-10 (07:00-17:00 ICT), matching
    real Thai daylight hours - not the plant's true sunrise/sunset (that's
    `nongfab_features.clearsky`'s real pvlib solar position, used by
    /geometry and /sun-path), just this module's own separate synthetic
    generator finally agreeing with it on *which* hours are "day"
    (previously peaked at 12:00 UTC = 19:00 ICT, nighttime - found live
    2026-07-16 while verifying the panel-color-by-real-output feature:
    every panel showed red and Actual: 0.0 kW at Thai local noon, because
    this function's old phase thought it was night). Every caller
    (`/performance`, `/simulate`, `/energy-report`, `/irradiance-map`,
    `/ws/live`) shares this one fix.
    """
    rng = np.random.default_rng(seed)
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    idx = pd.date_range(start, periods=n_hours, freq="h", tz="UTC")
    hour = idx.hour.to_numpy()
    ssrd = np.clip(1000 * np.sin(np.pi * (hour + 1) / 12), 0, None)
    temp = 28 + 5 * np.sin(np.pi * (hour + 1) / 12) + rng.normal(0, 0.5, size=n_hours)
    return idx, ssrd, temp


_LIVE_EFFICIENCY_MIN = 0.85
_LIVE_EFFICIENCY_MAX = 1.0
_LIVE_EFFICIENCY_BUCKET_SECONDS = 300  # 5 minutes


def live_efficiency_factor(zone: str, now: datetime | None = None) -> float:
    """Bounded [0.85, 1.0] multiplier for "how much of the clean physics
    estimate is actually coming out today" - approximates real-world losses
    (soiling, minor clipping, temperature derate variance) that no real
    inverter/SCADA telemetry exists to measure yet (see this module's own
    docstring, and routes_performance.py's - there is genuinely no plant
    telemetry anywhere in this system). Deliberately capped at 1.0 so this
    can only ever claim *less* than the physics model, never more -
    documented approximation, not a measurement.

    Unlike synthetic_day_irradiance_temp()'s fixed seed=0 (intentionally
    reproducible for simulate/energy-report/irradiance-map, which shouldn't
    drift between calls), this is keyed off real wall-clock time so a
    dashboard polling it every 60s actually sees it move: each 5-minute
    bucket gets its own deterministic anchor value, and time *within* a
    bucket is linearly interpolated toward the next one - so it drifts
    smoothly and continuously rather than holding flat then jumping at
    bucket boundaries (a quick double-refresh a few seconds apart still
    reads as "the same" to a human, just not bit-for-bit identical) -
    approved 2026-07-16 as the "bounded, real-time-varying" choice over
    both a frozen fixed-seed value and a fully random one.
    """
    now = now or datetime.now(timezone.utc)
    ts = now.timestamp()
    bucket = int(ts // _LIVE_EFFICIENCY_BUCKET_SECONDS)
    frac = (ts % _LIVE_EFFICIENCY_BUCKET_SECONDS) / _LIVE_EFFICIENCY_BUCKET_SECONDS

    def _bucket_value(b: int) -> float:
        digest = hashlib.sha256(f"{zone}:{b}".encode()).digest()
        unit = digest[0] / 255
        return _LIVE_EFFICIENCY_MIN + (_LIVE_EFFICIENCY_MAX - _LIVE_EFFICIENCY_MIN) * unit

    return _bucket_value(bucket) * (1 - frac) + _bucket_value(bucket + 1) * frac
