"""GET /weather/strip - a real-clock-centered window of hourly temperature/
irradiance readings for the dashboard's scrolling weather strip
(Module 7's ForecastPage). Weather here is site-wide, not per-zone (Module 5's
own `simulate_zone_baseline` reuses one shared irradiance/temp series across
all 3 zones - only *power* varies by zone, via each zone's own capacity/
losses), so this route takes no `{zone}` path param, unlike `/performance`.

Conditioned on real accumulated NWP data (the same `RealDataStore` Module 4's
forecast pipeline already reads - see `get_forecast_with_fallback`'s own
docstring) when there's real coverage across (most of) the requested window,
falling back to the same synthetic day/night baseline every other
unauthenticated-telemetry route in this app already uses otherwise -
`data_source` in the response says which, so the frontend can label it
honestly rather than imply it's live weather when it isn't.

## The 9 variables (2026-07-18, see get_current_conditions's own docstring
for the full per-variable audit of which were already real model features
vs. ingested-but-never-surfaced)

Extended the same window to also carry the rest of the Songsiri reference
deck's 9 forecast variables, for ForecastPage's real-time 3x3 table +
grouped graphs (see web/README.md's matching dated entry). I/T/I_wrf were
already here (`ssrd_w_m2`/`temp_c` - I is the actual/past/now portion,
I_wrf is the same field's future-forecast portion, split client-side by
timestamp vs. now exactly like the main power chart already splits
actualPast/actualNow vs. pred). `relative_humidity_pct`/`wind_speed_ms`
are `None` in synthetic-fallback mode (the synthetic baseline models
temperature/irradiance only) AND for future timestamps even in real-data
mode (2026-07-19: unlike ssrd/temp, neither was ever validated as a
trained-model regressor in this pipeline, so presenting them as "forecast"
would overstate confidence this project hasn't earned for them yet - the
user's own explicit instruction: "ถ้าบางตัวแปรไม่มีการforecast ก็ไม่เป็นไร
ไม่ต้องไปฝืนสุ่มค่าข้อมูล forecast"). `clearsky_ghi_w_m2`/`zenith_deg`/
`cos_zenith`/`clear_sky_index` are always populated - pure pvlib astronomy
plus a ratio against `ssrd_w_m2`, independent of whether the NWP data
itself is real or synthetic.
"""

from __future__ import annotations

import math
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, Depends, Request
from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location
from nongfab_forecast.local_store import RealDataStore
from nongfab_simulation.dev_data import synthetic_temp_at
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["weather"])

# Generous default: comfortably covers the dashboard's +/-4..+/-8h display
# window with room to spare on both sides, so the frontend never has to ask
# for a wider window than this endpoint already returns by default.
DEFAULT_HOURS_EACH_SIDE = 12

# A real window must cover at least this fraction of the requested hourly
# slots to be trusted as "real" - a strip with big gaps stitched from a
# handful of real points is worse than an honest, fully-populated synthetic
# fallback.
_MIN_REAL_COVERAGE_FRACTION = 0.8


class WeatherStripPoint(BaseModel):
    timestamp: datetime
    temp_c: float
    ssrd_w_m2: float
    # The remaining Songsiri reference-deck variables (2026-07-18, see
    # get_current_conditions's own docstring for the full audit) - added
    # here, not just to `/weather/conditions`'s single-instant snapshot,
    # because ForecastPage's grouped variable graphs need a real time
    # series, and this endpoint already *is* one (real accumulated NWP
    # data when available, spanning both past and a bit of future - see
    # this module's own docstring). `relative_humidity_pct`/`wind_speed_ms`
    # are None in synthetic-fallback mode (the synthetic baseline models
    # temperature/irradiance only) and for future timestamps even in real
    # mode (see this module's own docstring); `clearsky_ghi_w_m2`/
    # `zenith_deg`/`cos_zenith`/`clear_sky_index` are always populated -
    # they're pure astronomy (pvlib) plus a ratio against `ssrd_w_m2`,
    # independent of whether the NWP data itself is real or synthetic.
    relative_humidity_pct: float | None = None
    wind_speed_ms: float | None = None
    clearsky_ghi_w_m2: float
    zenith_deg: float
    cos_zenith: float
    clear_sky_index: float | None = None


class WeatherStripResponse(BaseModel):
    data_source: str  # "real" or "synthetic" - see this module's own docstring
    points: list[WeatherStripPoint]


def _nearest_real_row(df: pd.DataFrame, target: datetime, max_delta_hours: float = 1.5) -> pd.Series | None:
    deltas = (df["valid_time"] - target).abs()
    idx = deltas.idxmin()
    if deltas.loc[idx].total_seconds() > max_delta_hours * 3600:
        return None
    return df.loc[idx]


def _clearsky_fields(target: datetime) -> tuple[float, float, float]:
    """(clearsky_ghi_w_m2, zenith_deg, cos_zenith) at `target` - pure pvlib
    astronomy, independent of whether any real NWP data exists, so every
    strip point (real or synthetic) gets these three populated. Shared by
    `_real_window`/`_synthetic_window` rather than duplicated inline.
    """
    lat, lon = nong_fab_site_location()
    solpos = compute_clearsky_and_position(pd.DatetimeIndex([target]), lat, lon)
    clearsky_ghi = float(solpos["ghi_clearsky"].iloc[0])
    zenith_deg = float(solpos["zenith_deg"].iloc[0])
    return clearsky_ghi, zenith_deg, math.cos(math.radians(zenith_deg))


def _clear_sky_index(measured_w_m2: float, clearsky_w_m2: float) -> float | None:
    if clearsky_w_m2 <= 1.0:  # night, or numerically unstable near sunrise/sunset
        return None
    return min(2.0, max(0.0, measured_w_m2 / clearsky_w_m2))


def _real_window(store: RealDataStore, now: datetime, hours_each_side: int) -> list[WeatherStripPoint] | None:
    df = store.nwp_history_df()
    if df.empty:
        return None

    hour_start = now.replace(minute=0, second=0, microsecond=0)
    targets = [hour_start + timedelta(hours=offset) for offset in range(-hours_each_side, hours_each_side + 1)]

    points: list[WeatherStripPoint] = []
    for target in targets:
        row = _nearest_real_row(df, target)
        if row is None:
            continue
        ssrd = float(row["ssrd_w_m2"])
        clearsky_ghi, zenith_deg, cos_zenith = _clearsky_fields(target)
        # RH/wind are never shown for future hours even though the GFS row
        # technically carries a value there - see this module's own docstring
        # on why (never validated as trained regressors, unlike ssrd/temp).
        is_future = target > now
        rh = row.get("relative_humidity_pct")
        points.append(
            WeatherStripPoint(
                timestamp=target,
                temp_c=float(row["temp2m_c"]),
                ssrd_w_m2=ssrd,
                relative_humidity_pct=None if is_future else (float(rh) if pd.notna(rh) else None),
                wind_speed_ms=None if is_future else _wind_speed_ms(row.get("wind10m_u_ms"), row.get("wind10m_v_ms")),
                clearsky_ghi_w_m2=clearsky_ghi,
                zenith_deg=zenith_deg,
                cos_zenith=cos_zenith,
                clear_sky_index=_clear_sky_index(ssrd, clearsky_ghi),
            )
        )

    if len(points) < len(targets) * _MIN_REAL_COVERAGE_FRACTION:
        return None
    return points


def _synthetic_point(ts: pd.Timestamp, ssrd: float, temp: float) -> WeatherStripPoint:
    when = ts.to_pydatetime()
    clearsky_ghi, zenith_deg, cos_zenith = _clearsky_fields(when)
    return WeatherStripPoint(
        timestamp=when,
        temp_c=float(temp),
        ssrd_w_m2=float(ssrd),
        # relative_humidity_pct/wind_speed_ms stay None - the synthetic
        # baseline (nongfab_simulation.dev_data) only ever models
        # temperature/irradiance, not humidity/wind - see this file's
        # WeatherStripPoint docstring.
        clearsky_ghi_w_m2=clearsky_ghi,
        zenith_deg=zenith_deg,
        cos_zenith=cos_zenith,
        clear_sky_index=_clear_sky_index(float(ssrd), clearsky_ghi),
    )


def _synthetic_window(now: datetime, hours_each_side: int) -> list[WeatherStripPoint]:
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    idx = pd.date_range(
        hour_start - timedelta(hours=hours_each_side), hour_start + timedelta(hours=hours_each_side), freq="h", tz="UTC"
    )
    ssrd, temp = synthetic_temp_at(idx)
    return [_synthetic_point(ts, s, t) for ts, s, t in zip(idx, ssrd, temp)]


@router.get("/weather/strip", response_model=WeatherStripResponse)
async def get_weather_strip(
    request: Request, hours_each_side: int = DEFAULT_HOURS_EACH_SIDE, _user=Depends(require_role("viewer"))
) -> WeatherStripResponse:
    now = datetime.now(timezone.utc)
    store: RealDataStore = request.app.state.real_data_store

    real_points = _real_window(store, now, hours_each_side)
    if real_points is not None:
        return WeatherStripResponse(data_source="real", points=real_points)

    return WeatherStripResponse(data_source="synthetic", points=_synthetic_window(now, hours_each_side))


# A cloud observation older than this is stale enough that showing it as
# "current" would be misleading (the Himawari poller runs every ~10min - see
# ingestion_scheduler.py's himawari_poll_interval_seconds - so a healthy
# process should never actually hit this in practice; it's a guard against a
# stalled poller silently freezing the 3D view's cloud layer in place).
_CLOUD_MAX_AGE_MINUTES = 30


class CloudConditionsResponse(BaseModel):
    available: bool
    observed_at: datetime | None = None
    cloud_opacity_pct: float | None = None
    # None whenever the underlying CloudRasterFrame had no previous frame to
    # diff motion against yet (see himawari_ingestion.schemas.CloudRasterFrame's
    # own docstring) - the frontend keeps the cloud layer static (opacity only,
    # no drift) rather than guessing a fabricated direction/speed.
    motion_speed_kmh: float | None = None
    motion_direction_deg: float | None = None


@router.get("/weather/clouds", response_model=CloudConditionsResponse)
async def get_cloud_conditions(request: Request, _user=Depends(require_role("viewer"))) -> CloudConditionsResponse:
    """Site-wide (not per-zone - one shared Himawari tile sample, same
    "weather is site-wide" reasoning as `/weather/strip` above) latest real
    cloud reading - opacity + motion vector, straight off `cloud_history`
    (Module 2's Himawari ingestion, already the same source `real_data.py`'s
    Sum-k LSTM cloud-index feature and the minute-ahead model's motion
    features read). Built for Solar3DPage's drifting cloud-layer visual
    (2026-07-18 user request) - `available=False` (not a 404) when no cloud
    row has ever been recorded yet or the latest one is too stale, so the
    frontend can render "no live cloud data" instead of a crash.
    """
    store: RealDataStore = request.app.state.real_data_store
    df = store.cloud_history_df()
    if df.empty:
        return CloudConditionsResponse(available=False)

    latest = df.iloc[-1]
    observed_at = latest["observed_at"].to_pydatetime()
    if datetime.now(timezone.utc) - observed_at > timedelta(minutes=_CLOUD_MAX_AGE_MINUTES):
        return CloudConditionsResponse(available=False)

    motion_speed = latest.get("motion_speed_kmh")
    motion_direction = latest.get("motion_direction_deg")
    return CloudConditionsResponse(
        available=True,
        observed_at=observed_at,
        cloud_opacity_pct=float(latest["cloud_opacity_pct"]),
        motion_speed_kmh=float(motion_speed) if pd.notna(motion_speed) else None,
        motion_direction_deg=float(motion_direction) if pd.notna(motion_direction) else None,
    )


# A near-term GFS reading only - same "current conditions, not a 3-day forecast
# preview" intent as _nearest_real_row's own default max_delta_hours used by
# /weather/strip above. Unlike cloud_history (only ever populated with
# already-observed frames), nwp_history also holds forecast_hours out to 72h
# (see ingestion/nwp/config.py) - without this cap, "latest row" would mean
# "furthest-future forecast row", not "now".
_PRECIP_MAX_LEAD_HOURS = 1.5

# WMO surface-observation intensity bands (mm accumulated in roughly an hour -
# light <2.5, moderate 2.5-7.6, heavy >7.6). Applied directly to precip_mm as a
# deliberate simplification for this decorative visual, not a rigorous rain-rate
# computation - see NWPForecastPoint.precip_mm's own docstring: it's GFS's raw
# accumulated-since-init APCP value for whichever forecast hour happened to be
# nearest to now, not a de-accumulated mm/h rate. At the short lead times this
# endpoint restricts itself to (a fresh poll's fhour=1/2 rows, not a stale
# far-future one), GFS's own accumulation window is close enough to 1h that
# this stays an honest approximation - see forecast/README.md's rain-feature
# entry for the fuller reasoning.
_PRECIP_LIGHT_MM = 2.5
_PRECIP_MODERATE_MM = 7.6


class PrecipitationConditionsResponse(BaseModel):
    available: bool
    observed_at: datetime | None = None
    precip_mm: float | None = None
    # "none" | "light" | "moderate" | "heavy" - None only when available=False.
    intensity: str | None = None


def _precip_intensity(precip_mm: float) -> str:
    if precip_mm <= 0.1:
        return "none"
    if precip_mm < _PRECIP_LIGHT_MM:
        return "light"
    if precip_mm < _PRECIP_MODERATE_MM:
        return "moderate"
    return "heavy"


@router.get("/weather/precipitation", response_model=PrecipitationConditionsResponse)
async def get_precipitation_conditions(request: Request, _user=Depends(require_role("viewer"))) -> PrecipitationConditionsResponse:
    """Site-wide latest real precipitation reading (same "weather is site-wide"
    reasoning as /weather/strip and /weather/clouds above), straight off the same
    `nwp_history` table Day-ahead/Intra-day training already reads - GFS's own
    APCP field (see ingestion/nwp's datasource.py and README for the full
    ingestion path added 2026-07-18). Built for Solar3DPage's rain-animation
    visual (2026-07-18 user request, explicitly Thailand-seasonal rain only, no
    snow). `available=False` when no row has a non-null precip_mm within
    `_PRECIP_MAX_LEAD_HOURS` of now - either because the GFS subset genuinely
    carried no APCP message for that hour (see NWPForecastPoint.precip_mm's own
    docstring) or because no fresh poll has landed recently - the frontend
    renders "no rain" rather than guessing.
    """
    store: RealDataStore = request.app.state.real_data_store
    df = store.nwp_history_df()
    if df.empty:
        return PrecipitationConditionsResponse(available=False)

    df = df[df["precip_mm"].notna()]
    if df.empty:
        return PrecipitationConditionsResponse(available=False)

    now = datetime.now(timezone.utc)
    row = _nearest_real_row(df, now, max_delta_hours=_PRECIP_MAX_LEAD_HOURS)
    if row is None:
        return PrecipitationConditionsResponse(available=False)

    precip_mm = float(row["precip_mm"])
    return PrecipitationConditionsResponse(
        available=True,
        observed_at=row["valid_time"].to_pydatetime(),
        precip_mm=precip_mm,
        intensity=_precip_intensity(precip_mm),
    )


# A UV observation is daily-resolution (NASA POWER's ALLSKY_SFC_UV_INDEX -
# see ingestion/nasa_power/README.md), not hourly - a reading up to this many
# days old is still "today's" UV in practice (the daily backfill/poll may not
# have landed for "today" yet at an early UTC hour), older than this is
# stale enough to mark unavailable rather than show yesterday's number as if
# it were current.
_UV_MAX_AGE_DAYS = 2

# GFS forecast-hour tolerance for the "near-future" I_wrf reading - loose
# enough to always find *some* upcoming row from a live poller (which fetches
# discrete forecast hours, not a continuous stream), tight enough that this
# stays "the next model output", not an arbitrary multi-day-out forecast.
_FORECAST_MAX_LEAD_HOURS = 3.0


class CurrentConditionsResponse(BaseModel):
    available: bool
    observed_at: datetime | None = None
    # I - real (GFS SSRD) irradiance nearest "now" - the same signal this
    # app treats as ground truth throughout (no independent telemetry
    # sensor exists - see root README's standing honesty caveat).
    irradiance_w_m2: float | None = None
    # T - real (GFS 2m temperature) nearest "now".
    temp_c: float | None = None
    # RH - real (GFS 2m relative humidity) nearest "now" - ingested since
    # the NWP pipeline's first version but never previously surfaced via any
    # API route or used as a model feature (found while auditing this
    # endpoint's own 9-variable checklist, 2026-07-18).
    relative_humidity_pct: float | None = None
    # WS - real wind speed magnitude, sqrt(u^2 + v^2) from GFS's
    # wind10m_u_ms/wind10m_v_ms components (stored as components, not a
    # scalar speed, because the minute-ahead model's own motion features
    # need direction too - see real_data.py's `_motion_uv_columns`). Same
    # "ingested but never surfaced" gap as RH above.
    wind_speed_ms: float | None = None
    # I_clr - clear-sky GHI (pvlib Ineichen model) at the same instant as
    # the readings above - always computable (pure astronomy + a clear-sky
    # radiative model), never gated on real data availability the way the
    # NWP-sourced fields are.
    clearsky_ghi_w_m2: float | None = None
    # cosθ / zenith angle - same pvlib solar-position computation every
    # other module already uses (clearsky.py's own `compute_clearsky_and_
    # position`) - computed here for the first time as its own explicit
    # weather-conditions field (elsewhere in the app it's only ever
    # returned bundled with panel geometry/sun-path data, not alongside the
    # other 8 variables in one place).
    zenith_deg: float | None = None
    cos_zenith: float | None = None
    # k-hat - clear-sky index (measured / clear-sky GHI), same formula as
    # `clearsky.clear_sky_index()` (that function operates on a pandas
    # Series for batch feature-engineering use; this is the same math
    # applied to one scalar reading instead of importing it for a
    # single-value call). None whenever clear-sky GHI is too close to zero
    # (night) for the ratio to be meaningful - same "safe near zero" guard
    # `clear_sky_index()` itself applies.
    clear_sky_index: float | None = None
    # I_wrf - the real NWP model's own *forecast* irradiance for a near-
    # future hour (not "now") - the closest honest analog this app has to
    # "predicted GHI from WRF" (this project's NWP source is GFS, not WRF -
    # see ingestion/nwp/README.md - but it plays the identical role: a
    # numerical weather model's own forward-looking GHI prediction, as
    # opposed to `irradiance_w_m2` above, which is the same underlying GFS
    # signal at the nearest-to-now hour, treated as this app's ground
    # truth throughout since no independent telemetry exists).
    forecast_irradiance_w_m2: float | None = None
    forecast_valid_at: datetime | None = None
    # UV - daily-resolution only (NASA POWER), unlike every other field on
    # this response which is effectively real-time (updates on the next
    # NWP poll, ~hourly). `uv_observation_date` makes that daily cadence
    # explicit so the frontend can caption it honestly rather than implying
    # hourly freshness it doesn't have.
    uv_index: float | None = None
    uv_observation_date: date_type | None = None


class UvHistoryPoint(BaseModel):
    observation_date: date_type
    uv_index: float


class UvHistoryResponse(BaseModel):
    points: list[UvHistoryPoint]  # oldest first


@router.get("/weather/uv-history", response_model=UvHistoryResponse)
async def get_uv_history(request: Request, _user=Depends(require_role("viewer"))) -> UvHistoryResponse:
    """Every real daily UV reading this deployment has accumulated (NASA
    POWER's ALLSKY_SFC_UV_INDEX - see ingestion/nasa_power/README.md),
    oldest first - added 2026-07-19 so the frontend can chart UV as one bar
    per real day it actually has, instead of faking an intraday curve from
    a single daily value (UV genuinely has no hourly resolution to plot -
    see ForecastPage.tsx's SolarVariablesGraphs docstring for the full
    per-variable charting rationale). No date-range filtering: `uv_history` only ever
    holds a few dozen rows at most (one per day since this container booted,
    plus whatever `_backfill_uv` seeded), so there's no pagination concern
    worth adding yet.

    Same ephemeral-per-container caveat as every other real_data_store-
    backed history in this app (see local_store.py's own docstring) - a
    fresh deploy starts this back at whatever the startup UV backfill
    managed to seed (often nothing - NASA POWER has never been reachable
    from every environment this repo runs in, see that backfill's own
    non-fatal failure handling), then grows one point per real day the
    process stays up. An empty `points` list is a legitimate response, not
    an error - the frontend should render its own "not enough days yet"
    state for it, same spirit as every other honest-empty chart state this
    app already has (Model Competition, before-today actual power, etc.).
    """
    store: RealDataStore = request.app.state.real_data_store
    uv_df = store.uv_history_df()
    if uv_df.empty:
        return UvHistoryResponse(points=[])
    return UvHistoryResponse(
        points=[
            UvHistoryPoint(observation_date=row["observation_date"], uv_index=float(row["uv_index"]))
            for _, row in uv_df.iterrows()
        ]
    )


def _wind_speed_ms(u: float | None, v: float | None) -> float | None:
    if u is None or v is None or pd.isna(u) or pd.isna(v):
        return None
    return math.hypot(float(u), float(v))


@router.get("/weather/conditions", response_model=CurrentConditionsResponse)
async def get_current_conditions(request: Request, _user=Depends(require_role("viewer"))) -> CurrentConditionsResponse:
    """Site-wide real-time snapshot of the 9 solar-forecasting input
    variables from Songsiri's reference deck (see forecast/README.md's own
    "Reference: Songsiri" section) - I, RH, T, UV, WS, I_clr, cosθ, k-hat,
    I_wrf - added 2026-07-18 after auditing which of the 9 this app already
    computes/ingests vs. actually surfaces anywhere: I/T/I_clr/k-hat/I_wrf
    were already real model features (see real_data.py), but RH/wind speed/
    zenith angle were computed or ingested and never exposed via any route,
    and UV was ingested (NASA POWER) but never wired to anything on this
    dashboard. This route doesn't change what any model trains on - it's a
    read-only snapshot for Feature A's new 3x3 variable table.

    `available=False` only when there's no NWP data at all (or nothing
    within `/weather/strip`'s own near-term tolerance) - UV specifically can
    still be `None` even when `available=True`, since it's a separate daily-
    cadence source that can genuinely lag behind the hourly NWP feed.
    """
    store: RealDataStore = request.app.state.real_data_store
    df = store.nwp_history_df()
    if df.empty:
        return CurrentConditionsResponse(available=False)

    now = datetime.now(timezone.utc)
    row = _nearest_real_row(df, now)
    if row is None:
        return CurrentConditionsResponse(available=False)

    valid_time = row["valid_time"].to_pydatetime()
    irradiance = float(row["ssrd_w_m2"])

    lat, lon = nong_fab_site_location()
    solpos = compute_clearsky_and_position(pd.DatetimeIndex([valid_time]), lat, lon)
    clearsky_ghi = float(solpos["ghi_clearsky"].iloc[0])
    zenith_deg = float(solpos["zenith_deg"].iloc[0])
    clear_sky_index = min(2.0, max(0.0, irradiance / clearsky_ghi)) if clearsky_ghi > 1.0 else None

    future_df = df[df["valid_time"] > now]
    forecast_row = _nearest_real_row(future_df, now + timedelta(hours=1), max_delta_hours=_FORECAST_MAX_LEAD_HOURS) if len(future_df) else None

    uv_df = store.uv_history_df()
    uv_index: float | None = None
    uv_observation_date: date_type | None = None
    if len(uv_df):
        latest_uv = uv_df.iloc[-1]
        if (datetime.now(timezone.utc).date() - latest_uv["observation_date"]).days <= _UV_MAX_AGE_DAYS:
            uv_index = float(latest_uv["uv_index"])
            uv_observation_date = latest_uv["observation_date"]

    return CurrentConditionsResponse(
        available=True,
        observed_at=valid_time,
        irradiance_w_m2=irradiance,
        temp_c=float(row["temp2m_c"]),
        relative_humidity_pct=float(row["relative_humidity_pct"]) if pd.notna(row.get("relative_humidity_pct")) else None,
        wind_speed_ms=_wind_speed_ms(row.get("wind10m_u_ms"), row.get("wind10m_v_ms")),
        clearsky_ghi_w_m2=clearsky_ghi,
        zenith_deg=zenith_deg,
        cos_zenith=math.cos(math.radians(zenith_deg)),
        clear_sky_index=clear_sky_index,
        forecast_irradiance_w_m2=float(forecast_row["ssrd_w_m2"]) if forecast_row is not None else None,
        forecast_valid_at=forecast_row["valid_time"].to_pydatetime() if forecast_row is not None else None,
        uv_index=uv_index,
        uv_observation_date=uv_observation_date,
    )
