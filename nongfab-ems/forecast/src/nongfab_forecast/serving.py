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

from . import real_data, registry
from .day_ahead import predict_day_ahead
from .hour_ahead import predict_hour_ahead
from .local_store import RealDataStore
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
    data_source: str = "synthetic"  # "real" when serving-time conditions came from real_data.py, not a synthetic generator
    model_type: str = "ml"  # "physics_baseline" only via get_forecast_with_fallback() below


def get_latest_forecast(zone: str, horizon: str, store: RealDataStore | None = None) -> ForecastResult:
    """Raises UnknownZoneError/UnknownHorizonError for bad input, or
    ModelNotTrainedError if no model has been registered yet for this
    (zone, horizon) - callers (dev API, Module 6) translate these into
    whatever HTTP status they use for "not found" vs "not trained yet".

    `store` (defaults to an empty in-memory RealDataStore, so every existing
    caller/test is unaffected) supplies serving-time "current conditions":
    preferred from real ingested/backfilled data (real_data.py) when enough
    has accumulated, falling back to the original synthetic generators below
    that bar - see real_data.py's own docstring for the "no real telemetry
    exists, power is always a physics conversion of real weather" caveat.
    """
    zone = validate_zone(zone)
    horizon = validate_horizon(horizon)
    store = store if store is not None else RealDataStore()

    try:
        model = registry.load_model(horizon, zone, version="latest")
    except ValueError as exc:
        raise ModelNotTrainedError(str(exc)) from exc

    client = registry.MlflowClient()
    versions = client.search_model_versions(f"name='{registry.registered_model_name_for(horizon, zone)}'")
    latest_version = max(int(v.version) for v in versions)

    now = datetime.now(timezone.utc)
    data_source = "synthetic"

    if horizon == "minute":
        try:
            window = real_data.recent_minute_window(store, model.lookback)
            data_source = "real"
        except real_data.InsufficientHistoryError:
            window = _synthetic_minute_df(n=model.lookback, seed=hash((zone, "minute-now")) % 1000)
        pred = predict_minute_ahead(model, window)
        points = [ForecastPoint(timestamp=now + timedelta(minutes=10 * (i + 1)), pred=float(v)) for i, v in enumerate(pred)]

    elif horizon == "hour":
        try:
            X_now = real_data.current_hour_conditions(zone, store, now)
            data_source = "real"
        except real_data.InsufficientHistoryError:
            X_now, _ = _synthetic_hour_df(n=1, seed=hash((zone, "hour-now")) % 1000)
        result = predict_hour_ahead(model, X_now)
        points = [
            ForecastPoint(timestamp=now + timedelta(hours=1), pred=float(row.pred), lower=float(row.lower), upper=float(row.upper))
            for row in result.itertuples()
        ]

    else:  # day
        try:
            history_df = real_data.real_day_frame(zone, store)
            future_df = real_data.real_future_regressors(store, now)[:24]
            if len(future_df) == 0:
                raise real_data.InsufficientHistoryError("no real future NWP rows accumulated yet")
            data_source = "real"
        except real_data.InsufficientHistoryError:
            history_df = _synthetic_day_df(n_hours=24 * 5, seed=hash((zone, "day-history")) % 1000)
            future_df = _synthetic_day_df(n_hours=24, seed=hash((zone, "day-now")) % 1000)
            future_df.index = history_df.index[-1] + pd.to_timedelta(np.arange(1, 25), unit="h")
        result = predict_day_ahead(model, history_df, future_df[["ssrd_w_m2", "temp2m_c"]], periods=len(future_df))
        points = [
            ForecastPoint(timestamp=ts.to_pydatetime(), pred=float(row.pred), lower=float(row.lower), upper=float(row.upper))
            for ts, row in result.iterrows()
        ]

    return ForecastResult(
        zone=zone, horizon=horizon, issued_at=now, model_version=latest_version, points=points, data_source=data_source
    )


def get_forecast_with_fallback(zone: str, horizon: str, store: RealDataStore | None = None) -> ForecastResult:
    """Same contract as get_latest_forecast() for bad input (still raises
    UnknownZoneError/UnknownHorizonError), but never raises
    ModelNotTrainedError: falls back to a physics-only estimate
    (real_data.physics_baseline_series - clear-sky x live cloud attenuation x
    the zone's PV model, no ML) instead, tagged model_type="physics_baseline"
    so callers/the dashboard can label it honestly rather than presenting it
    as an ML forecast. This is what actually fixes "the site won't produce a
    forecast" for a zone/horizon that hasn't accumulated enough real history
    to train yet - get_latest_forecast()'s raise-on-untrained contract is
    unchanged (still used directly by anything that wants the old behavior,
    e.g. existing tests).
    """
    zone = validate_zone(zone)
    horizon = validate_horizon(horizon)
    store = store if store is not None else RealDataStore()

    try:
        return get_latest_forecast(zone, horizon, store)
    except ModelNotTrainedError:
        pass

    now = datetime.now(timezone.utc)
    if horizon == "minute":
        timestamps = pd.date_range(now + timedelta(minutes=10), periods=6, freq="10min")
    elif horizon == "hour":
        timestamps = pd.date_range(now + timedelta(hours=1), periods=1, freq="h")
    else:
        timestamps = pd.date_range(now, periods=24, freq="h")

    baseline = real_data.physics_baseline_series(zone, timestamps, store)
    points = [ForecastPoint(timestamp=ts.to_pydatetime(), pred=float(row.pred)) for ts, row in baseline.iterrows()]
    return ForecastResult(
        zone=zone, horizon=horizon, issued_at=now, model_version=0, points=points, data_source="real", model_type="physics_baseline"
    )
