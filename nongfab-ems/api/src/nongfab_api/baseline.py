"""Shared "today's baseline weather conditions" source for the three routes
that build a per-zone power baseline from an hourly irradiance/temperature
series: `/performance`, `/simulate`, and `/ws/live`.

All three previously called `nongfab_simulation.dev_data.
synthetic_day_irradiance_temp()` directly - a purely synthetic day. This
module is the single place that now prefers *real* ingested NWP data
(`nongfab_forecast.real_data.real_day_conditions`, driven by the same
`RealDataStore` `/forecast` and `/weather/strip` already read) and falls
back to that synthetic generator only when too little real history has
accumulated for the current day - the same real-or-synthetic split
`/weather/strip` already uses, factored out here so all three routes get
identical behavior and the honest `data_source` label rather than three
copies that could drift.

Weather is site-wide (one shared series drives every zone; only each zone's
own capacity/losses differ), so this takes no zone argument - the same
assumption `real_day_conditions`, the synthetic generator, and
`/weather/strip` all already make.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from nongfab_forecast import real_data
from nongfab_forecast.local_store import RealDataStore
from nongfab_simulation.dev_data import synthetic_day_irradiance_temp

# "real" -> today's hourly series came from real ingested NWP; "synthetic" ->
# the physics-free synthetic generator (not enough real NWP for today yet).
DataSource = str


def day_baseline_conditions(
    store: RealDataStore, now: datetime | None = None
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, DataSource]:
    """`(idx, ssrd_w_m2, temp_c, data_source)` for today - real ingested NWP
    when enough has accumulated for the current day, else the synthetic
    fallback. `idx`/`ssrd`/`temp` match `synthetic_day_irradiance_temp()`'s
    shape exactly (one UTC calendar day, 00:00-23:00 hourly), so a caller can
    swap this in for that function with no other change and feed the result
    straight into `simulate_zone_baseline()`. `data_source` is `"real"` or
    `"synthetic"` so the route can label the response honestly, the same way
    `/weather/strip` and `/forecast` already do.
    """
    try:
        idx, ssrd, temp = real_data.real_day_conditions(store, now)
        return idx, ssrd, temp, "real"
    except real_data.InsufficientHistoryError:
        idx, ssrd, temp = synthetic_day_irradiance_temp()
        return idx, ssrd, temp, "synthetic"
