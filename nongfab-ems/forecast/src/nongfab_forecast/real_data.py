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

from nongfab_features import soiling

from . import pv_conversion
from .local_store import RealDataStore


def _numeric_col_or_zeros(df: pd.DataFrame, name: str) -> np.ndarray:
    """A numeric column as a float array, or zeros if the column is absent/empty.
    Guards the marine features against thin stores / older rows where the
    nullable wind/humidity/precip columns may be missing or NaN."""
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    return np.zeros(len(df), dtype=float)


def _numeric_val_or_zero(row: "pd.Series", name: str) -> float:
    """One numeric cell as a float, or 0.0 when missing/NaN (serving path)."""
    value = row.get(name) if hasattr(row, "get") else None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if np.isnan(value) else value

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
    # Marine features (2026-07-24) - coastal salt-spray/humidity drivers derived
    # from the already-stored wind/humidity/precip columns (see nongfab_features.
    # soiling). Serving builds the identical columns in current_hour_conditions_kstep.
    u = _numeric_col_or_zeros(at_lead, "wind10m_u_ms")
    v = _numeric_col_or_zeros(at_lead, "wind10m_v_ms")
    rh = _numeric_col_or_zeros(at_lead, "relative_humidity_pct")
    precip = _numeric_col_or_zeros(at_lead, "precip_mm")
    X = pd.DataFrame(
        {
            "ssrd_w_m2": at_lead["ssrd_w_m2"].to_numpy(),
            "temp2m_c": at_lead["temp2m_c"].to_numpy(),
            "power_lag1": power.shift(1).bfill().to_numpy(),
            "clear_sky_ssrd_w_m2": _clear_sky_ssrd_w_m2(at_lead["valid_time"]),
            "cloud_index": _cloud_index_nearest_to(store, at_lead["issue_time"]),
            "wind_speed_ms": soiling.wind_speed_ms(u, v),
            "relative_humidity_pct": rh,
            "precip_mm": precip,
            "salt_soiling_index": soiling.salt_soiling_index(u, v, rh),
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

    u = _numeric_val_or_zero(row, "wind10m_u_ms")
    v = _numeric_val_or_zero(row, "wind10m_v_ms")
    rh = _numeric_val_or_zero(row, "relative_humidity_pct")
    precip = _numeric_val_or_zero(row, "precip_mm")
    return pd.DataFrame(
        {
            "ssrd_w_m2": [row["ssrd_w_m2"]],
            "temp2m_c": [row["temp2m_c"]],
            "power_lag1": [lag_power],
            "clear_sky_ssrd_w_m2": _clear_sky_ssrd_w_m2([row["valid_time"]]),
            "cloud_index": _cloud_index_nearest_to(store, [row["issue_time"]]),
            "wind_speed_ms": [float(soiling.wind_speed_ms(u, v))],
            "relative_humidity_pct": [rh],
            "precip_mm": [precip],
            "salt_soiling_index": [float(soiling.salt_soiling_index(u, v, rh))],
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


# How far a `timestamps` entry may sit from its nearest real cloud_history
# reading and still use it in _historical_attenuation() below - wide enough to
# absorb Himawari backfill's own hourly cadence (see himawari_ingestion.backfill's
# docstring) not lining up exactly on this function's hour-aligned timestamps,
# narrow enough that a timestamp far outside cloud_history's actual coverage
# (e.g. before this deployment's Himawari ingestion had reached that far back)
# correctly falls back to the clear-sky default below instead of borrowing a
# stale reading from hours away.
_HISTORICAL_CLOUD_MATCH_TOLERANCE = pd.Timedelta(hours=2)


def _cloud_opacity_to_attenuation(opacity_pct: float) -> float:
    """Same directional-not-calibrated approximation both attenuation paths
    below share - see physics_baseline_series' own docstring for the caveat."""
    return max(0.05, 1 - 0.8 * (opacity_pct / 100))


def cloud_factor_for_time(
    store: RealDataStore | None, when: datetime,
    tolerance: pd.Timedelta = _HISTORICAL_CLOUD_MATCH_TOLERANCE,
) -> float | None:
    """Real plant-wide cloud GHI factor (0.05..1.0) nearest `when`, from the
    live Himawari `cloud_history`, or None when no real observation exists
    within `tolerance` of `when` (empty store, or `when` outside coverage).

    Unlike `_latest_cloud_attenuation` (which returns a neutral 1.0 both for
    "genuinely clear" and "no data"), this returns None for the no-data case so
    the caller can honestly label the result real vs. synthetic - the signal
    the irradiance-map overlay uses to decide `data_source` and whether to
    anchor to real cloud conditions (2026-07-22 roadmap item 4). Uses the same
    nearest-match tolerance and opacity->attenuation approximation as the
    forecast physics baseline, so the map and the forecast agree on "how cloudy
    is it right now".
    """
    if store is None:
        return None
    cloud = store.cloud_history_df()
    if len(cloud) == 0:
        return None
    cloud = cloud[["observed_at", "cloud_opacity_pct"]].dropna()
    if cloud.empty:
        return None
    observed = pd.to_datetime(cloud["observed_at"], utc=True).reset_index(drop=True)
    opacity = cloud["cloud_opacity_pct"].reset_index(drop=True)
    target = pd.Timestamp(when)
    target = target.tz_localize("UTC") if target.tzinfo is None else target.tz_convert("UTC")
    deltas = (observed - target).abs()
    nearest = int(deltas.idxmin())
    if deltas.iloc[nearest] > tolerance:
        return None
    return _cloud_opacity_to_attenuation(float(opacity.iloc[nearest]))


def _latest_cloud_attenuation(store: RealDataStore | None, max_cloud_age_minutes: float) -> float:
    """The original single-reading attenuation: whatever `store`'s most recent
    cloud observation says right now, applied uniformly to every requested
    timestamp - correct for live/near-future serving (there is only one "now"),
    and deliberately kept as-is for backfill_forecast_history's retrospective
    use too (a forecast issued in the past couldn't have seen a cloud reading
    from its own future - see that function's own docstring)."""
    if store is None:
        return 1.0
    latest = store.latest_cloud_observation()
    if latest is None:
        return 1.0
    observed_at, opacity_pct, _cloud_index = latest
    age_minutes = (datetime.now(timezone.utc) - observed_at).total_seconds() / 60
    if age_minutes > max_cloud_age_minutes:
        return 1.0
    return _cloud_opacity_to_attenuation(opacity_pct)


def _historical_cloud_attenuation(timestamps: pd.DatetimeIndex, store: RealDataStore) -> np.ndarray:
    """Per-timestamp attenuation from real cloud_history, nearest-match within
    `_HISTORICAL_CLOUD_MATCH_TOLERANCE` - unlike `_latest_cloud_attenuation`'s
    single reading applied everywhere, this looks up *that specific hour's own*
    real cloud opacity (2026-07-19, for backfill_generated_power_history's
    retrospective "actual power" estimate specifically - see that function's
    own docstring for why "actual" and "forecast" deliberately diverge here).
    Falls back to attenuation=1.0 (clear-sky) for any timestamp with no
    historical match within tolerance, same graceful-degradation default as
    the no-cloud-data case in `_latest_cloud_attenuation` - an incomplete or
    still-warming-up cloud_history never raises, it just makes that one hour
    an optimistic clear-sky guess like the old behavior always was.
    """
    cloud_df = store.cloud_history_df()
    if cloud_df.empty:
        return np.full(len(timestamps), 1.0)

    # Stays in pandas Timestamp/Timedelta space throughout (not raw numpy
    # datetime64) - both `observed` and `timestamps` are tz-aware (UTC), and
    # numpy has no native tz-aware datetime64 dtype, so converting either
    # side via np.datetime64() silently drops to an incomparable object
    # dtype instead of raising.
    observed = pd.DatetimeIndex(cloud_df["observed_at"])
    opacity = cloud_df["cloud_opacity_pct"].to_numpy()

    attenuation = np.full(len(timestamps), 1.0)
    for i, ts in enumerate(timestamps):
        deltas = np.abs(observed - ts)
        nearest = deltas.argmin()
        if deltas[nearest] <= _HISTORICAL_CLOUD_MATCH_TOLERANCE:
            attenuation[i] = _cloud_opacity_to_attenuation(opacity[nearest])
    return attenuation


def physics_baseline_series(
    zone: str,
    timestamps: pd.DatetimeIndex,
    store: RealDataStore | None = None,
    max_cloud_age_minutes: float = 30.0,
    use_historical_cloud: bool = False,
) -> pd.DataFrame:
    """A no-ML estimate: pvlib clear-sky GHI, attenuated by real cloud
    observations, converted through the zone's physics PV model. Used by
    serving.get_forecast_with_fallback() so the dashboard shows *something*
    real-weather-driven instead of a 404 while too little history has
    accumulated to trust an ML model yet (see root README "Known gaps").

    `use_historical_cloud=False` (default): attenuated by the single most
    recent real cloud observation if one exists and is fresh enough (else
    assumed clear-sky, an explicitly optimistic bias - see README) - correct
    for live/near-future serving, and for backfill_forecast_history's
    retrospective seed (a forecast issued at some past hour has no business
    seeing a cloud reading from its own future, so "whatever the live
    fallback would have said" is the honest retrospective number there).

    `use_historical_cloud=True`: attenuated by each timestamp's *own* nearest
    real cloud_history reading instead (2026-07-19) - used by
    backfill_generated_power_history specifically, where "actual power" for
    an already-past hour should reflect that hour's real weather when it's
    available, not today's snapshot replayed across every past hour. Without
    this, backfill_generated_power_history and backfill_forecast_history
    called physics_baseline_series() with identical inputs and produced
    bit-identical numbers for the same cold-start window - see
    backfill_generated_power_history's own docstring for the full story.

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

    if use_historical_cloud and store is not None:
        attenuation = _historical_cloud_attenuation(timestamps, store)
    else:
        attenuation = _latest_cloud_attenuation(store, max_cloud_age_minutes)

    ghi_effective = clearsky["ghi_clearsky"] * attenuation
    params = pv_params_for_zone(zone)
    power = pv_conversion.predict_power_kw(ghi_effective, NOMINAL_AMBIENT_TEMP_C, params)
    return pd.DataFrame({"pred": power.to_numpy()}, index=timestamps)


# How far a given hour-of-today slot may sit from its nearest real NWP
# valid_time and still count as "covered" by real data - matches
# api/routes_weather.py's `_nearest_real_row` default (1.5h), wide enough to
# absorb GFS's coarser (3-hourly beyond the near-term) forecast-hour spacing
# without over-counting a distant row as this slot's own reading.
_DAY_CONDITIONS_TOLERANCE = pd.Timedelta(hours=1.5)

# Fraction of today's 24 hourly slots that must have a real NWP match within
# `_DAY_CONDITIONS_TOLERANCE` for `real_day_conditions` to trust the day as
# real (else it raises InsufficientHistoryError and the caller falls back to
# the synthetic generator) - same 0.8 bar api/routes_weather.py's
# `_real_window` uses for the weather strip, and for the same reason: a day
# stitched from a handful of scattered real rows is worse than an honest,
# fully-populated synthetic fallback.
DAY_CONDITIONS_MIN_COVERAGE = 0.8


def real_day_conditions(
    store: RealDataStore, now: datetime | None = None, coverage: float = DAY_CONDITIONS_MIN_COVERAGE
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """`(idx, ssrd_w_m2, temp_c)` for the current UTC calendar day (00:00-23:00,
    hourly) built from real ingested NWP history - the real-data counterpart to
    `nongfab_simulation.dev_data.synthetic_day_irradiance_temp()`, returning the
    exact same tuple shape so the API's `/performance`, `/simulate`, and
    `/ws/live` routes can feed it straight into `simulate_zone_baseline()` in
    place of the synthetic generator (see api/baseline.py, which does the
    real-or-synthetic fallback).

    Zone-independent: weather here is site-wide - one shared NWP series drives
    every zone, only each zone's own capacity/losses differ - exactly as the
    synthetic generator and `/weather/strip` already assume.

    Each hourly slot is filled from the nearest real NWP `valid_time` within
    `_DAY_CONDITIONS_TOLERANCE`; slots with no match inside the tolerance are
    left as gaps and linearly interpolated from the surrounding real values
    (keeping the series internally consistent with the real, cloud-affected
    NWP rather than splicing in a separate clear-sky estimate for the holes).
    Raises `InsufficientHistoryError` if fewer than `coverage` of the 24
    slots have a real match - the caller then falls back to the synthetic
    generator, the same real-or-synthetic split `/weather/strip` already uses.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    day_start = pd.Timestamp(now).tz_convert("UTC").normalize()
    idx = pd.date_range(day_start, periods=24, freq="h", tz="UTC")

    nwp = _deduped_nwp_history(store)
    if len(nwp) == 0:
        raise InsufficientHistoryError("no real NWP rows accumulated yet")

    nwp = nwp.sort_values("valid_time")
    merged = pd.merge_asof(
        pd.DataFrame({"valid_time": idx}),
        nwp[["valid_time", "ssrd_w_m2", "temp2m_c"]],
        on="valid_time",
        direction="nearest",
        tolerance=_DAY_CONDITIONS_TOLERANCE,
    )
    matched = int(merged["ssrd_w_m2"].notna().sum())
    if matched < len(idx) * coverage:
        raise InsufficientHistoryError(
            f"only {matched}/{len(idx)} of today's hourly slots have a real NWP match, need >= {coverage:.0%}"
        )

    ssrd = merged["ssrd_w_m2"].interpolate(limit_direction="both").to_numpy()
    temp = merged["temp2m_c"].interpolate(limit_direction="both").to_numpy()
    return idx, ssrd, temp


__all__ = [
    "DAY_CONDITIONS_MIN_COVERAGE",
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
    "real_day_conditions",
    "real_day_frame",
    "real_future_regressors",
    "real_hour_frame",
    "real_hour_frame_kstep",
    "real_minute_frame",
    "recent_minute_window",
]
