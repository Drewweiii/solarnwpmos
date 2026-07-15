"""Real-data training frame builders - mirror the column shape of serving.py's
_synthetic_*_df() generators exactly, so the existing per-horizon
train_*_model() calls work against them unmodified, but source every input
from real ingested weather data (Module 1's Himawari cloud observations,
Module 2's GFS NWP forecasts) instead of a sine wave.

`power_kw` columns below are still a physics-model projection
(pv_conversion.predict_power_kw), not a sensor reading - the plant has no
real power telemetry yet (see root README "Known gaps"). Every INPUT
variable (cloud opacity/index, NWP irradiance/temperature) is real, sourced
from Module 1/2's real data feeds (NOAA Himawari-9 AHI cloud product, NOAA
NOMADS GFS 0.25deg) - not synthesized.

These are pure DataFrame-in/DataFrame-out functions (no I/O), matching
pv_conversion.fit_pv_conversion_model()'s own convention, so they're testable
without a live database. Reading real accumulated history out of
TimescaleDB into the shapes these functions expect is a separate concern
(Module 1/2's own storage/sampling layers already write it in; a loader
belongs in orchestration/ once continuous ingestion has been running long
enough to accumulate a real dataset worth reading back).
"""

from __future__ import annotations

import pandas as pd

from .pv_conversion import PVConversionParams, default_params_from_capacity, predict_power_kw


def real_minute_df(himawari_observations: pd.DataFrame) -> pd.DataFrame:
    """`himawari_observations`: real Module 1 cloud observations, sorted
    chronologically, with `cloud_opacity_pct`/`cloud_index` columns (see
    ingestion/himawari's `CloudObservation` schema). Matches
    `serving._synthetic_minute_df()`'s column shape - `train_minute_ahead_model`
    predicts `cloud_opacity_pct` itself (a leading indicator), not power.
    """
    return himawari_observations[["cloud_opacity_pct", "cloud_index"]].reset_index(drop=True)


def real_hour_df(
    gfs_forecast: pd.DataFrame, zone_capacity_kwp: float, params: PVConversionParams | None = None
) -> tuple[pd.DataFrame, pd.Series]:
    """`gfs_forecast`: real Module 2 NWP forecast points (`valid_time`,
    `ssrd_w_m2`, `temp2m_c` columns) from one GFS cycle. Matches
    `serving._synthetic_hour_df()`'s (X, y) shape: `ssrd_w_m2`/`temp2m_c`/
    `power_lag1` -> `power_kw`. The first row is dropped (no prior row to
    lag from).
    """
    params = params or default_params_from_capacity(zone_capacity_kwp)
    df = gfs_forecast.sort_values("valid_time").reset_index(drop=True)
    power = predict_power_kw(df["ssrd_w_m2"], df["temp2m_c"], params)

    X = pd.DataFrame({"ssrd_w_m2": df["ssrd_w_m2"], "temp2m_c": df["temp2m_c"], "power_lag1": power.shift(1)}).iloc[1:]
    y = power.iloc[1:]
    y.name = "power_kw"
    return X.reset_index(drop=True), y.reset_index(drop=True)


def real_day_df(gfs_forecast: pd.DataFrame, zone_capacity_kwp: float, params: PVConversionParams | None = None) -> pd.DataFrame:
    """`gfs_forecast`: same real Module 2 rows as `real_hour_df()`, indexed by
    `valid_time` for NeuralProphet. Matches `serving._synthetic_day_df()`'s
    shape: `power_kw`/`ssrd_w_m2`/`temp2m_c`, indexed by a tz-aware
    DatetimeIndex.
    """
    params = params or default_params_from_capacity(zone_capacity_kwp)
    df = gfs_forecast.sort_values("valid_time").set_index("valid_time")
    power = predict_power_kw(df["ssrd_w_m2"], df["temp2m_c"], params)
    return pd.DataFrame({"power_kw": power, "ssrd_w_m2": df["ssrd_w_m2"], "temp2m_c": df["temp2m_c"]})
