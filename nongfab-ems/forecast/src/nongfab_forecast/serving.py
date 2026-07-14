"""Forecast serving: load the latest registered model for a (zone, horizon)
and produce a forecast against synthetic "current conditions" (no real
accumulated history exists yet - see README "Known gaps"). Extracted from
this module's own dev API (api.py) so Module 6's production API can reuse
the exact same per-horizon serving logic (which synthetic generator to use,
how to map each horizon's predict_*() output into a common point format)
instead of duplicating it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import registry
from .day_ahead import predict_day_ahead
from .hour_ahead import predict_hour_ahead
from .minute_ahead import predict_minute_ahead
from .pv_conversion import nong_fab_zone_capacities_kwp

VALID_HORIZONS = ("minute", "hour", "day")


class UnknownZoneError(ValueError):
    pass


class UnknownHorizonError(ValueError):
    pass


class ModelNotTrainedError(ValueError):
    pass


def validate_zone(zone: str) -> str:
    capacities = nong_fab_zone_capacities_kwp()
    if zone not in capacities:
        raise UnknownZoneError(f"unknown zone {zone!r}; known zones: {sorted(capacities)}")
    return zone


def validate_horizon(horizon: str) -> str:
    if horizon not in VALID_HORIZONS:
        raise UnknownHorizonError(f"unknown horizon {horizon!r}; expected one of {VALID_HORIZONS}")
    return horizon


def _synthetic_minute_df(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    opacity = np.clip(50 + 30 * np.sin(2 * np.pi * t / 40) + 0.01 * t + rng.normal(0, 1.5, size=n), 0, 100)
    cloud_index = opacity / 100.0 + rng.normal(0, 0.02, size=n)
    return pd.DataFrame({"cloud_opacity_pct": opacity, "cloud_index": cloud_index})


def _synthetic_hour_df(n: int, seed: int) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    irradiance = rng.uniform(0, 1000, size=n)
    temp = rng.uniform(20, 40, size=n)
    lag_power = rng.uniform(0, 200, size=n)
    power = 0.2 * irradiance - 0.5 * temp + 0.1 * lag_power + 10 + rng.normal(0, 5, size=n)
    X = pd.DataFrame({"ssrd_w_m2": irradiance, "temp2m_c": temp, "power_lag1": lag_power})
    return X, pd.Series(power, name="power_kw")


def _synthetic_day_df(n_hours: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(datetime.now(timezone.utc) - timedelta(hours=n_hours), periods=n_hours, freq="h", tz="UTC")
    hour = idx.hour.to_numpy()
    ssrd = np.clip(800 * np.sin(np.pi * (hour - 6) / 12), 0, None)
    temp = 28 + 5 * np.sin(np.pi * (hour - 6) / 12) + rng.normal(0, 0.5, size=n_hours)
    power = 0.15 * ssrd - 0.3 * temp + rng.normal(0, 5, size=n_hours) + 15
    return pd.DataFrame({"power_kw": power, "ssrd_w_m2": ssrd, "temp2m_c": temp}, index=idx)


@dataclass(frozen=True)
class ForecastPoint:
    timestamp: datetime
    pred: float
    lower: float | None = None
    upper: float | None = None


@dataclass(frozen=True)
class ForecastResult:
    zone: str
    horizon: str
    issued_at: datetime
    model_version: int
    points: list[ForecastPoint]


def get_latest_forecast(zone: str, horizon: str) -> ForecastResult:
    """Raises UnknownZoneError/UnknownHorizonError for bad input, or
    ModelNotTrainedError if no model has been registered yet for this
    (zone, horizon) - callers (dev API, Module 6) translate these into
    whatever HTTP status they use for "not found" vs "not trained yet".
    """
    zone = validate_zone(zone)
    horizon = validate_horizon(horizon)

    try:
        model = registry.load_model(horizon, zone, version="latest")
    except ValueError as exc:
        raise ModelNotTrainedError(str(exc)) from exc

    client = registry.MlflowClient()
    versions = client.search_model_versions(f"name='{registry.registered_model_name_for(horizon, zone)}'")
    latest_version = max(int(v.version) for v in versions)

    now = datetime.now(timezone.utc)

    if horizon == "minute":
        window = _synthetic_minute_df(n=model.lookback, seed=hash((zone, "minute-now")) % 1000)
        pred = predict_minute_ahead(model, window)
        points = [ForecastPoint(timestamp=now + timedelta(minutes=10 * (i + 1)), pred=float(v)) for i, v in enumerate(pred)]

    elif horizon == "hour":
        X_now, _ = _synthetic_hour_df(n=1, seed=hash((zone, "hour-now")) % 1000)
        result = predict_hour_ahead(model, X_now)
        points = [
            ForecastPoint(timestamp=now + timedelta(hours=1), pred=float(row.pred), lower=float(row.lower), upper=float(row.upper))
            for row in result.itertuples()
        ]

    else:  # day
        history_df = _synthetic_day_df(n_hours=24 * 5, seed=hash((zone, "day-history")) % 1000)
        future_df = _synthetic_day_df(n_hours=24, seed=hash((zone, "day-now")) % 1000)
        future_df.index = history_df.index[-1] + pd.to_timedelta(np.arange(1, 25), unit="h")
        result = predict_day_ahead(model, history_df, future_df[["ssrd_w_m2", "temp2m_c"]], periods=24)
        points = [
            ForecastPoint(timestamp=ts.to_pydatetime(), pred=float(row.pred), lower=float(row.lower), upper=float(row.upper))
            for ts, row in result.iterrows()
        ]

    return ForecastResult(zone=zone, horizon=horizon, issued_at=now, model_version=latest_version, points=points)
