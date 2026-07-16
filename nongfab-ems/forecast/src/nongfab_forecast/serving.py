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
from .hour_ahead import predict_hour_ahead_kstep
from .local_store import RealDataStore
from .minute_ahead import predict_minute_ahead
from .pv_conversion import nong_fab_zone_capacities_kwp

VALID_HORIZONS = ("minute", "hour", "day")


def _ceil_to(dt: datetime, step: timedelta) -> datetime:
    """Rounds `dt` up to the next clean multiple of `step` since the Unix
    epoch (or returns it unchanged if already exactly on a boundary) - e.g.
    with `step=timedelta(hours=1)`, 14:23:07 -> 15:00:00.

    Forecast timestamp grids are anchored to this instead of the raw
    sub-minute `datetime.now()`, so they stay fixed at clean boundaries
    across repeated polls instead of drifting by a few random seconds every
    time - found live 2026-07-16: the dashboard's x-axis kept visibly
    shifting on every 60s auto-refresh (e.g. tick labels "01:47" one poll,
    "02:29" the next), because every poll baked that exact instant's own
    seconds/minutes into the timestamp anchor, and the newly-added 60s
    refetch (see web/README.md's own dated entry) made that constant drift
    obvious instead of only showing up on a manual page reload.
    """
    epoch = datetime(1970, 1, 1, tzinfo=dt.tzinfo)
    remainder = (dt - epoch) % step
    return dt if remainder == timedelta(0) else dt + (step - remainder)

# Fallback-only prediction interval: a fixed symmetric +/-20% band around the
# physics estimate, NOT a real uncertainty quantification (the physics
# baseline is deterministic - there are no model residuals to measure a
# quantile from). Documented approximation, not a measurement - same pattern
# as this codebase's other "no real data yet" placeholders (e.g.
# nongfab_simulation.dev_data.live_efficiency_factor's bounded multiplier).
# Exists purely so the dashboard shows *some* honest-looking uncertainty band
# instead of none while too little real history has accumulated to train a
# real quantile model - approved by the user 2026-07-16 over leaving the
# fallback path bandless. No explicit "switch-over" logic needed: the
# try/except below already prefers get_latest_forecast()'s real ML quantile
# output (see hour_ahead.py/day_ahead.py) the moment a model exists, and only
# reaches this fallback while ModelNotTrainedError still applies - so once
# enough real NWP/cloud history accumulates and a model trains, this fixed
# band stops being used automatically, with no separate migration step.
FALLBACK_PI_HALF_WIDTH_PCT = 0.20

# Hour-ahead's k-step lead hours - HourAheadKStepModel holds one independently-
# trained model per lead (see hour_ahead.py's own docstring for why not one
# multi-output model), replacing the original single "+1h only" point forecast.
HOUR_LEAD_HOURS = (1, 2, 3, 4, 5, 6)

# Day-ahead's forecast window: 72h (3 days), not literally "one day" - the model
# name is inherited from the architecture doc's 3-horizon taxonomy (minute/hour/
# day), but the actual served window is capped at 3 days because that's the
# reach of the real NWP data actually available (see api/config.py's
# nwp_poll_forecast_hours, which fetches out to 72h) and because forecast skill
# beyond ~3-4 days degrades sharply for post-processed NWP-driven solar
# forecasting (Songsiri, "An Introduction to Solar Energy Forecasting", Chula/
# CUEE - see forecast/README.md's "Reference" section) - going further would be
# serving numbers with no real basis for extra confidence.
MAX_DAY_AHEAD_HOURS = 72


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
    # Motion columns match real_data.MINUTE_FEATURE_COLS's shape (not derived from
    # opacity - just independent noise in a plausible km/h range) so a model trained
    # on this synthetic fallback has the same feature schema as one trained on real
    # data - see real_data.py's own motion feature docstring for what these mean
    # when they're real.
    motion_u_kmh = rng.normal(0, 5, size=n)
    motion_v_kmh = rng.normal(0, 5, size=n)
    return pd.DataFrame(
        {"cloud_opacity_pct": opacity, "cloud_index": cloud_index, "motion_u_kmh": motion_u_kmh, "motion_v_kmh": motion_v_kmh}
    )


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
    anchor = _ceil_to(datetime.now(timezone.utc), timedelta(hours=1))
    idx = pd.date_range(anchor - timedelta(hours=n_hours), periods=n_hours, freq="h", tz="UTC")
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
        minute_anchor = _ceil_to(now, timedelta(minutes=10))
        points = [ForecastPoint(timestamp=minute_anchor + timedelta(minutes=10 * i), pred=float(v)) for i, v in enumerate(pred)]

    elif horizon == "hour":
        X_by_lead_hour: dict[int, pd.DataFrame] = {}
        any_real = False
        for lead in HOUR_LEAD_HOURS:
            try:
                X_by_lead_hour[lead] = real_data.current_hour_conditions_kstep(zone, store, lead, now)
                any_real = True
            except real_data.InsufficientHistoryError:
                X_lead, _ = _synthetic_hour_df(n=1, seed=hash((zone, f"hour-now-{lead}")) % 1000)
                X_by_lead_hour[lead] = X_lead
        data_source = "real" if any_real else "synthetic"
        result = predict_hour_ahead_kstep(model, X_by_lead_hour)
        hour_anchor = _ceil_to(now, timedelta(hours=1))
        points = [
            ForecastPoint(
                timestamp=hour_anchor + timedelta(hours=int(lead) - 1),
                pred=float(row.pred),
                lower=float(row.lower),
                upper=float(row.upper),
            )
            for lead, row in result.iterrows()
        ]

    else:  # day
        try:
            history_df = real_data.real_day_frame(zone, store)
            future_df = real_data.real_future_regressors(store, now)[:MAX_DAY_AHEAD_HOURS]
            if len(future_df) == 0:
                raise real_data.InsufficientHistoryError("no real future NWP rows accumulated yet")
            data_source = "real"
        except real_data.InsufficientHistoryError:
            history_df = _synthetic_day_df(n_hours=24 * 5, seed=hash((zone, "day-history")) % 1000)
            future_df = _synthetic_day_df(n_hours=MAX_DAY_AHEAD_HOURS, seed=hash((zone, "day-now")) % 1000)
            future_df.index = history_df.index[-1] + pd.to_timedelta(np.arange(1, MAX_DAY_AHEAD_HOURS + 1), unit="h")
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
        timestamps = pd.date_range(_ceil_to(now, timedelta(minutes=10)), periods=6, freq="10min")
    elif horizon == "hour":
        timestamps = pd.date_range(_ceil_to(now, timedelta(hours=1)), periods=len(HOUR_LEAD_HOURS), freq="h")
    else:
        timestamps = pd.date_range(_ceil_to(now, timedelta(hours=1)), periods=MAX_DAY_AHEAD_HOURS, freq="h")

    baseline = real_data.physics_baseline_series(zone, timestamps, store)
    points = [
        ForecastPoint(
            timestamp=ts.to_pydatetime(),
            pred=float(row.pred),
            lower=max(0.0, float(row.pred) * (1 - FALLBACK_PI_HALF_WIDTH_PCT)),
            upper=float(row.pred) * (1 + FALLBACK_PI_HALF_WIDTH_PCT),
        )
        for ts, row in baseline.iterrows()
    ]
    return ForecastResult(
        zone=zone, horizon=horizon, issued_at=now, model_version=0, points=points, data_source="real", model_type="physics_baseline"
    )
