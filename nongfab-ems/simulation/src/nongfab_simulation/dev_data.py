"""Synthetic "current conditions" generator - dev/demo only, used wherever no
real accumulated irradiance/temperature history exists yet (Module 1/2's
caveat - see README "Known gaps"). Extracted so this module's own dev API
and Module 6's production API use the exact same generator rather than two
copies that could silently drift apart.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd


def synthetic_day_irradiance_temp(n_hours: int = 24, seed: int = 0) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    idx = pd.date_range(start, periods=n_hours, freq="h", tz="UTC")
    hour = idx.hour.to_numpy()
    ssrd = np.clip(1000 * np.sin(np.pi * (hour - 6) / 12), 0, None)
    temp = 28 + 5 * np.sin(np.pi * (hour - 6) / 12) + rng.normal(0, 0.5, size=n_hours)
    return idx, ssrd, temp
