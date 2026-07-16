"""Real-data feature layer: assembles model-ready frames from real ingested +
backfilled NWP/cloud/UV history (local_store.RealDataStore), as an opportunistic
alternative to serving.py/training.py's synthetic sine-wave generators
(_synthetic_minute_df/_synthetic_hour_df/_synthetic_day_df) - see root README
"Known gaps": Module 3/4 previously trained and served on synthetic data only,
never anything Module 1/2 actually ingested.

No real generated-power telemetry exists anywhere in this system (Jetty is a
simulated capacity projection with no panels installed; GIS/ISB have no SCADA tap
wired in yet - and the user explicitly scoped this out: pull real *weather* inputs,
not fabricated "real" power output). So every `power_kw` value here is the physics
-based PV conversion model (pv_conversion.predict_power_kw) applied to REAL
irradiance/temperature, never a real measured target. This mirrors the actual
academic reference this project cites (Suksamosorn & Songsiri, MOS+KF): forecast
the weather-driven signal, convert through a calibrated physical model - it is not
a shortcut, it is the standard approach when no plant telemetry exists yet.

Every builder here raises InsufficientHistoryError below its own minimum-row bar
rather than degrade silently - training.py/serving.py catch it and fall back to the
existing synthetic path, so a thin/empty store behaves exactly as this repo did
before this module existed (see local_store.default_db_path's docstring).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import pv_conversion
from .local_store import RealDataStore

MIN_HOUR_ROWS = 24
MIN_DAY_ROWS = 24 * 3  # a few days of hourly-equivalent coverage - short on purpose, this is cold-start seeding, not a maturity bar
MIN_MINUTE_ROWS = 30

# Nominal ambient temperature used only by physics_baseline_series() when no real
# NWP temperature is available for the requested timestamps - same documented
# placeholder value as api/routes_irradiance_map.py's NOMINAL_AMBIENT_TEMP_C, kept
# in sync deliberately (both exist for the same "no real reading yet" reason).
NOMINAL_AMBIENT_TEMP_C = 30.0

# Sum-k LSTM's reference architecture (see forecast/README.md's dated entry) calls
# for two real signals the original hour-ahead feature set didn't carry: I_clr
# (clear-sky irradiance at the *future* valid_time - see _clear_sky_ssrd_w_m2) and
# CI (cloud index observed *now*, at issue_time - see _cloud_index_nearest_to).
# Added to real_hour_frame_kstep/current_hour_conditions_kstep so all three
# competing candidates (LightGBM/Random Forest/Sum-k LSTM) see the same features,
# not just Sum-k LSTM - LightGBM/RF simply get two more real inputs to split on.
#
# No fresh cloud reading within this many minutes of issue_time -> fall back to
# this neutral default rather than raising InsufficientHistoryError: cloud
# backfill maturing on its own schedule (a separate ingestion source, see
# api/ingestion_scheduler.py) shouldn't block hour-ahead training that's
# otherwise ready to go on NWP data alone. Same "assume mostly-clear, explicitly
# optimistic bias" spirit as physics_baseline_series's own documented default,
# not a measurement.
_UNKNOWN_CLOUD_INDEX_DEFAULT = 0.3
_CLOUD_INDEX_MAX_AGE_MINUTES = 60.0


class InsufficientHistoryError(RuntimeError):
    """Real history exists but hasn't reached this builder's minimum row count yet."""


def pv_params_for_zone(zone: str) -> pv_conversion.PVConversionParams:
    """Always the capacity-derived physics fallback (pv_conversion.
    default_params_from_capacity), for every zone including non-simulated ones -
    fit_pv_conversion_model() needs real (I, T, P) history including a real P,
    which doesn't exist anywhere in this system (see module docstring). This is a
    deliberate, permanent scope decision, not a placeholder pending real telemetry.
    """
    capacities = pv_conversion.nong_fab_zone_capacities_kwp()
    if zone not in capacities:
        raise ValueError(f"unknown zone {zone!r}; known zones: {sorted(capacities)}")
    return pv_conversion.default_params_from_capacity(capacities[zone])


def _deduped_nwp_history(store: RealDataStore) -> pd.DataFrame:
    df = store.nwp_history_df()
    if len(df) == 0:
        return df
    return df.sort_values("valid_time").drop_duplicates("valid_time", keep="last").reset_index(drop=True)


def real_hour_frame(zone: str, store: RealDataStore) -> tuple[pd.DataFrame, pd.Series]:
    """(X, y) for hour_ahead.train_hour_ahead_model: X has ssrd_w_m2/temp2m_c/
    power_lag1 columns (matching serving.py's existing synthetic shape exactly, so
    hour_ahead.py itself needed no changes), y is power_kw.
    """
    nwp = _deduped_nwp_history(store)
    if len(nwp) < MIN_HOUR_ROWS:
        raise InsufficientHistoryError(f"only {len(nwp)} real NWP rows accumulated, need >= {MIN_HOUR_ROWS}")

    params = pv_params_for_zone(zone)
    power = pv_conversion.predict_power_kw(nwp["ssrd_w_m2"], nwp["temp2m_c"], params)
    X = pd.DataFrame(
        {
            "ssrd_w_m2": nwp["ssrd_w_m2"].to_numpy(),
            "temp2m_c": nwp["temp2m_c"].to_numpy(),
            "power_lag1": power.shift(1).bfill().to_numpy(),
        }
    )
    y = pd.Series(power.to_numpy(), name="power_kw")
    return X, y


MIN_HOUR_ROWS_PER_LEAD = 8  # lower than MIN_HOUR_ROWS: k-step data is split across 6 lead-hour buckets, not pooled


def _clear_sky_ssrd_w_m2(valid_times) -> np.ndarray:
    """Clear-sky GHI (Ineichen model, via nongfab_features.clearsky) at each of
    `valid_times` - Sum-k LSTM's I_clr, a genuine *future* regressor: unlike NWP,
    it needs no forecast at all, since clear-sky irradiance is a deterministic
    function of solar geometry and time, computable exactly for any future
    instant, not just observed history.
    """
    from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location

    lat, lon = nong_fab_site_location()
    idx = pd.DatetimeIndex(valid_times)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    clearsky = compute_clearsky_and_position(idx, lat, lon)
    return clearsky["ghi_clearsky"].to_numpy()


def _cloud_index_nearest_to(store: RealDataStore, issue_times) -> np.ndarray:
    """Real cloud index (Himawari-derived, via store.cloud_history_df()) nearest
    each of `issue_times` - Sum-k LSTM's CI, a lagged/exogenous regressor known
    at forecast-*issue* time (cloud conditions right now), not the future
    valid_time being forecast. Falls back to _UNKNOWN_CLOUD_INDEX_DEFAULT (not
    InsufficientHistoryError) wherever no cloud observation exists within
    _CLOUD_INDEX_MAX_AGE_MINUTES - see that constant's own docstring.
    """
    issue_times = pd.DatetimeIndex(issue_times)
    cloud = store.cloud_history_df()
    if len(cloud) == 0:
        return np.full(len(issue_times), _UNKNOWN_CLOUD_INDEX_DEFAULT)

    cloud = cloud[["observed_at", "cloud_index"]].sort_values("observed_at")
    left = pd.DataFrame({"issue_time": issue_times, "_order": range(len(issue_times))}).sort_values("issue_time")
    merged = pd.merge_asof(
        left, cloud, left_on="issue_time", right_on="observed_at", direction="nearest",
        tolerance=pd.Timedelta(minutes=_CLOUD_INDEX_MAX_AGE_MINUTES),
    ).sort_values("_order")
    return merged["cloud_index"].fillna(_UNKNOWN_CLOUD_INDEX_DEFAULT).to_numpy()


def _nwp_history_with_lead_hours(store: RealDataStore) -> pd.DataFrame:
    """Real NWP history with an added `lead_hours` column (valid_time - issue_time,
    whole hours) - deliberately NOT deduped by valid_time alone (unlike
    _deduped_nwp_history): k-step training needs to tell apart "this row was
    originally a 2-hour-ahead forecast" from "this row was originally a 6-hour-
    ahead forecast" for the *same* valid_time, which valid_time-only dedup would
    collapse into a single row and lose (see real_hour_frame_kstep's docstring for
    why that distinction is the whole point of k-step models).
    """
    df = store.nwp_history_df()
    if len(df) == 0:
        return df
    df = df.sort_values(["valid_time", "issue_time"]).reset_index(drop=True)
    df["lead_hours"] = ((df["valid_time"] - df["issue_time"]).dt.total_seconds() / 3600).round().astype(int)
    return df


def real_hour_frame_kstep(zone: str, store: RealDataStore, lead_hour: int) -> tuple[pd.DataFrame, pd.Series]:
    """(X, y) for training one of HourAheadKStepModel's per-lead sub-models: X
    has ssrd_w_m2/temp2m_c (the real NWP forecast originally issued `lead_hour`
    hours before its own valid_time - not "whatever the latest forecast for that
    valid_time happens to be now", see _nwp_history_with_lead_hours) plus
    power_lag1 (physics power of the previous row *within this same lead_hour's
    own series* - a same-lead persistence anchor), plus clear_sky_ssrd_w_m2/
    cloud_index (Sum-k LSTM's I_clr/CI - see those helpers' own docstrings; also
    available to LightGBM/Random Forest, since all three candidates train on the
    same X), y is power_kw at that lead.
    """
    df = _nwp_history_with_lead_hours(store)
    at_lead = df[df["lead_hours"] == lead_hour].reset_index(drop=True) if len(df) else df
    if len(at_lead) < MIN_HOUR_ROWS_PER_LEAD:
        raise InsufficientHistoryError(f"only {len(at_lead)} real NWP rows at lead_hour={lead_hour}, need >= {MIN_HOUR_ROWS_PER_LEAD}")

    params = pv_params_for_zone(zone)
    power = pv_conversion.predict_power_kw(at_lead["ssrd_w_m2"], at_lead["temp2m_c"], params)
    X = pd.DataFrame(
        {
            "ssrd_w_m2": at_lead["ssrd_w_m2"].to_numpy(),
            "temp2m_c": at_lead["temp2m_c"].to_numpy(),
            "power_lag1": power.shift(1).bfill().to_numpy(),
            "clear_sky_ssrd_w_m2": _clear_sky_ssrd_w_m2(at_lead["valid_time"]),
            "cloud_index": _cloud_index_nearest_to(store, at_lead["issue_time"]),
        }
    )
    y = pd.Series(power.to_numpy(), name="power_kw")
    return X, y


def current_hour_conditions_kstep(zone: str, store: RealDataStore, lead_hour: int, now: datetime | None = None) -> pd.DataFrame:
    """Single-row serving-time input for HourAheadKStepModel's lead_hour
    sub-model: the real NWP row at that same lead_hour bucket whose valid_time
    is nearest `now + lead_hour` (i.e. "the freshest real forecast we have for
    that specific future instant"), with power_lag1 the physics power of the
    previous row in that same lead_hour's own series (mirrors
    real_hour_frame_kstep's lag definition, so training and serving agree).
    """
    now = now or datetime.now(timezone.utc)
    df = _nwp_history_with_lead_hours(store)
    at_lead = df[df["lead_hours"] == lead_hour].reset_index(drop=True) if len(df) else df
    if len(at_lead) == 0:
        raise InsufficientHistoryError(f"no real NWP rows accumulated yet at lead_hour={lead_hour}")

    target_valid_time = pd.Timestamp(now) + pd.Timedelta(hours=lead_hour)
    idx_nearest = (at_lead["valid_time"] - target_valid_time).abs().idxmin()
    row = at_lead.loc[idx_nearest]
    params = pv_params_for_zone(zone)

    pos = at_lead.index.get_loc(idx_nearest)
    lag_power = 0.0
    if pos > 0:
        prev = at_lead.iloc[pos - 1]
        lag_power = float(pv_conversion.predict_power_kw(prev["ssrd_w_m2"], prev["temp2m_c"], params))

    return pd.DataFrame(
        {
            "ssrd_w_m2": [row["ssrd_w_m2"]],
            "temp2m_c": [row["temp2m_c"]],
            "power_lag1": [lag_power],
            "clear_sky_ssrd_w_m2": _clear_sky_ssrd_w_m2([row["valid_time"]]),
            "cloud_index": _cloud_index_nearest_to(store, [row["issue_time"]]),
        }
    )


def real_day_frame(zone: str, store: RealDataStore) -> pd.DataFrame:
    """Hourly-indexed frame for day_ahead.train_day_ahead_model (target_col=
    "power_kw", regressor_cols=["ssrd_w_m2", "temp2m_c"]) - same column shape as
    serving.py's existing _synthetic_day_df.
    """
    nwp = _deduped_nwp_history(store)
    if len(nwp) < MIN_DAY_ROWS:
        raise InsufficientHistoryError(f"only {len(nwp)} real NWP rows accumulated, need >= {MIN_DAY_ROWS}")

    params = pv_params_for_zone(zone)
    power = pv_conversion.predict_power_kw(nwp["ssrd_w_m2"], nwp["temp2m_c"], params)
    df = pd.DataFrame(
        {"power_kw": power.to_numpy(), "ssrd_w_m2": nwp["ssrd_w_m2"].to_numpy(), "temp2m_c": nwp["temp2m_c"].to_numpy()},
        index=pd.DatetimeIndex(nwp["valid_time"], name="ds"),
    )
    return df[~df.index.duplicated(keep="last")].sort_index()


def current_hour_conditions(zone: str, store: RealDataStore, now: datetime | None = None) -> pd.DataFrame:
    """A single-row frame (ssrd_w_m2/temp2m_c/power_lag1) for hour_ahead.
    predict_hour_ahead's serving-time input - the real NWP row nearest `now`,
    with power_lag1 the physics-converted power of the *previous* chronological
    row (0 if there isn't one yet - the very first real row accumulated).
    """
    now = now or datetime.now(timezone.utc)
    nwp = _deduped_nwp_history(store)
    if len(nwp) == 0:
        raise InsufficientHistoryError("no real NWP rows accumulated yet")

    idx_nearest = (nwp["valid_time"] - pd.Timestamp(now)).abs().idxmin()
    row = nwp.loc[idx_nearest]
    params = pv_params_for_zone(zone)

    pos = nwp.index.get_loc(idx_nearest)
    lag_power = 0.0
    if pos > 0:
        prev = nwp.iloc[pos - 1]
        lag_power = float(pv_conversion.predict_power_kw(prev["ssrd_w_m2"], prev["temp2m_c"], params))

    return pd.DataFrame({"ssrd_w_m2": [row["ssrd_w_m2"]], "temp2m_c": [row["temp2m_c"]], "power_lag1": [lag_power]})


def real_future_regressors(store: RealDataStore, now: datetime | None = None) -> pd.DataFrame:
    """Real future NWP rows (valid_time > now) already accumulated by the live poll
    loop's own multi-forecast-hour fetches (NomadsGfsDataSource.fetch_latest_cycle
    pulls every configured forecast hour of the latest cycle, not just f001) - the
    day-ahead future-regressors input day_ahead.predict_day_ahead needs. Distinct
    from real_day_frame's *past* rows (the training target), though both read the
    same table.
    """
    now = now or datetime.now(timezone.utc)
    nwp = _deduped_nwp_history(store)
    if len(nwp) == 0:
        raise InsufficientHistoryError("no real NWP rows accumulated yet")
    future = nwp[nwp["valid_time"] > pd.Timestamp(now)]
    return pd.DataFrame(
        {"ssrd_w_m2": future["ssrd_w_m2"].to_numpy(), "temp2m_c": future["temp2m_c"].to_numpy()},
        index=pd.DatetimeIndex(future["valid_time"], name="ds"),
    )


MINUTE_FEATURE_COLS = ["cloud_opacity_pct", "cloud_index", "motion_u_kmh", "motion_v_kmh"]


def _motion_uv_columns(cloud: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Converts stored (speed_kmh, direction_deg) polar motion into cartesian
    (u=east, v=north) km/h components - avoids the circular discontinuity a raw
    direction_deg feature would create for an ML model (359deg and 1deg are
    physically almost the same direction but numerically far apart). Missing
    motion (the run's first stored frame, or a shape-mismatch skip - see
    himawari_ingestion.schemas.CloudRasterFrame's own docstring) fills to
    (0, 0) - "no motion known" is self-consistent with a zero-magnitude vector,
    not a real "moving north" claim.
    """
    speed = cloud["motion_speed_kmh"].fillna(0.0)
    direction_rad = np.deg2rad(cloud["motion_direction_deg"].fillna(0.0))
    u = speed * np.sin(direction_rad)
    v = speed * np.cos(direction_rad)
    return u, v


def real_minute_frame(store: RealDataStore) -> pd.DataFrame:
    """Frame for minute_ahead.train_minute_ahead_model (feature_cols=
    MINUTE_FEATURE_COLS, target_col="cloud_opacity_pct") - cloud opacity/index
    plus the cloud motion vector (himawari_ingestion.motion, computed by
    api/ingestion_scheduler.py between consecutive polled/backfilled frames) as
    two extra cartesian features - a leading indicator of an approaching cloud
    front the CNN-LSTM couldn't see from opacity/index alone.
    """
    cloud = store.cloud_history_df()
    if len(cloud) < MIN_MINUTE_ROWS:
        raise InsufficientHistoryError(f"only {len(cloud)} real cloud rows accumulated, need >= {MIN_MINUTE_ROWS}")

    cloud = cloud.sort_values("observed_at").drop_duplicates("observed_at", keep="last")
    motion_u, motion_v = _motion_uv_columns(cloud)
    return pd.DataFrame(
        {
            "cloud_opacity_pct": cloud["cloud_opacity_pct"].to_numpy(),
            "cloud_index": cloud["cloud_index"].to_numpy(),
            "motion_u_kmh": motion_u.to_numpy(),
            "motion_v_kmh": motion_v.to_numpy(),
        }
    )


def recent_minute_window(store: RealDataStore, lookback: int) -> pd.DataFrame:
    """The most recent `lookback` real cloud rows, oldest-first - the serving-time
    input predict_minute_ahead() needs (a fixed-length recent window, not a full
    training frame).
    """
    frame = real_minute_frame(store)  # raises InsufficientHistoryError below MIN_MINUTE_ROWS, same bar as training
    if len(frame) < lookback:
        raise InsufficientHistoryError(f"only {len(frame)} real cloud rows accumulated, need >= {lookback} for this model's lookback")
    return frame.tail(lookback).reset_index(drop=True)


def physics_baseline_series(
    zone: str, timestamps: pd.DatetimeIndex, store: RealDataStore | None = None, max_cloud_age_minutes: float = 30.0
) -> pd.DataFrame:
    """A no-ML estimate: pvlib clear-sky GHI, attenuated by the most recent real
    cloud observation if one exists and is fresh enough (else assumed clear-sky,
    an explicitly optimistic bias - see README), converted through the zone's
    physics PV model. Used by serving.get_forecast_with_fallback() so the dashboard
    shows *something* real-weather-driven instead of a 404 while too little history
    has accumulated to trust an ML model yet (see root README "Known gaps").

    The cloud attenuation factor (`1 - 0.8 * opacity_pct/100`) is a simple, documented
    approximation, not a fitted relationship - opacity is a coverage percentage, not
    a radiative transfer calculation, so this is directional (more cloud -> less GHI)
    rather than calibrated. Good enough for "don't show a flat clear-sky lie when we
    know it's overcast right now", not a substitute for the real ML models once they
    have enough history to train.
    """
    from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location

    lat, lon = nong_fab_site_location()
    clearsky = compute_clearsky_and_position(timestamps, lat, lon)

    attenuation = 1.0
    if store is not None:
        latest = store.latest_cloud_observation()
        if latest is not None:
            observed_at, opacity_pct, _cloud_index = latest
            age_minutes = (datetime.now(timezone.utc) - observed_at).total_seconds() / 60
            if age_minutes <= max_cloud_age_minutes:
                attenuation = max(0.05, 1 - 0.8 * (opacity_pct / 100))

    ghi_effective = clearsky["ghi_clearsky"] * attenuation
    params = pv_params_for_zone(zone)
    power = pv_conversion.predict_power_kw(ghi_effective, NOMINAL_AMBIENT_TEMP_C, params)
    return pd.DataFrame({"pred": power.to_numpy()}, index=timestamps)


__all__ = [
    "InsufficientHistoryError",
    "MIN_DAY_ROWS",
    "MIN_HOUR_ROWS",
    "MIN_HOUR_ROWS_PER_LEAD",
    "MIN_MINUTE_ROWS",
    "MINUTE_FEATURE_COLS",
    "current_hour_conditions",
    "current_hour_conditions_kstep",
    "physics_baseline_series",
    "pv_params_for_zone",
    "real_day_frame",
    "real_future_regressors",
    "real_hour_frame",
    "real_hour_frame_kstep",
    "real_minute_frame",
    "recent_minute_window",
]
