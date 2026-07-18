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

## The 9 variables (2026-07-18)

Extended the same window to also carry the rest of jitkomut's reference
paper's 9 forecast variables, for ForecastPage's real-time 3x3 table +
grouped graphs (see web/README.md's matching dated entry for the full
audit of which were already used vs. collected-but-unsurfaced):
I/T/I_wrf were already here (`ssrd_w_m2`/`temp_c` - I is the actual/past/
now portion, I_wrf is the same field's future-forecast portion, split
client-side by timestamp vs. now exactly like the main power chart already
splits actualPast/actualNow vs. pred). Newly added below:
- **I_clr** (`ghi_clearsky_w_m2`) and **cos(zenith)** (`cos_zenith`) - both
  deterministic solar geometry (pvlib Ineichen + solar position), computable
  for the *entire* window including future hours, since neither needs a
  weather forecast at all - see `nongfab_features.clearsky`.
- **k-hat** (`cloud_index`) - the real Himawari-derived clear-sky index
  already flowing through the Sum-k LSTM training pipeline (see
  `nongfab_forecast.real_data._cloud_index_nearest_to`) - `None` wherever
  no cloud observation exists nearby in time, which naturally means never
  for future hours (Himawari has no forecast mode, only observations).
- **RH** (`relative_humidity_pct`) and **wind speed** (`wind_speed_ms`) -
  present in the same NWP row as ssrd/temp, but deliberately `None` for
  future timestamps even though the GFS row technically carries a value
  there: unlike ssrd/temp, RH/wind were never validated as trained-model
  regressors in this pipeline, so presenting them as "forecast" here would
  overstate confidence this project hasn't earned for them yet - the
  user's own explicit instruction for this dashboard: "ถ้าบางตัวแปรไม่มีการ
  forecast ก็ไม่เป็นไรไม่ต้องไปฝืนสุ่มค่าข้อมูล forecast".
- **UV index** (`uv_daily`, a separate list on the response, not part of
  `points`) - `uv_history` is daily-resolution only (NASA POWER's own
  granularity, see ingestion/nasa_power/README.md), so it can't share the
  hourly `points` list's shape without fabricating intra-day values that
  don't exist.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
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

# How many days of accumulated UV history to return alongside the hourly
# window - daily-resolution, so a handful of days is already a meaningful
# trend line without over-fetching an ever-growing accumulated table.
_UV_HISTORY_DAYS = 14

# Cloud observations (Himawari) more than this far from a target hour aren't
# treated as "at that hour" - wider than /weather/clouds' own 30-minute
# staleness guard (a *current-conditions* check) since this is backfilling a
# multi-hour window from whatever poll cadence actually landed, not gating
# freshness of a single "right now" reading.
_CLOUD_INDEX_MAX_DELTA_HOURS = 1.0


class WeatherStripPoint(BaseModel):
    timestamp: datetime
    temp_c: float
    ssrd_w_m2: float
    ghi_clearsky_w_m2: float
    cos_zenith: float
    cloud_index: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_ms: float | None = None


class UvDailyPoint(BaseModel):
    date: date
    uv_index: float


class WeatherStripResponse(BaseModel):
    data_source: str  # "real" or "synthetic" - see this module's own docstring
    points: list[WeatherStripPoint]
    uv_daily: list[UvDailyPoint] = []


def _nearest_real_row(df: pd.DataFrame, target: datetime, max_delta_hours: float = 1.5) -> pd.Series | None:
    deltas = (df["valid_time"] - target).abs()
    idx = deltas.idxmin()
    if deltas.loc[idx].total_seconds() > max_delta_hours * 3600:
        return None
    return df.loc[idx]


def _solar_geometry(targets: list[datetime]) -> tuple[np.ndarray, np.ndarray]:
    """(ghi_clearsky_w_m2, cos_zenith) arrays aligned 1:1 with `targets` - pure
    pvlib geometry (Ineichen clear-sky model + solar position), needs no
    weather data at all, so this is computable for the entire window
    (including future hours) regardless of data_source.
    """
    lat, lon = nong_fab_site_location()
    geo = compute_clearsky_and_position(pd.DatetimeIndex(targets), lat, lon)
    return geo["ghi_clearsky"].to_numpy(), np.cos(np.radians(geo["zenith_deg"].to_numpy()))


def _nearest_cloud_index(cloud_df: pd.DataFrame, target: datetime) -> float | None:
    if cloud_df.empty:
        return None
    deltas = (cloud_df["observed_at"] - target).abs()
    idx = deltas.idxmin()
    if deltas.loc[idx].total_seconds() > _CLOUD_INDEX_MAX_DELTA_HOURS * 3600:
        return None
    return float(cloud_df.loc[idx, "cloud_index"])


def _maybe_float(value: object) -> float | None:
    return None if pd.isna(value) else float(value)  # type: ignore[arg-type]


def _wind_speed_ms(row: pd.Series) -> float | None:
    u, v = row.get("wind10m_u_ms"), row.get("wind10m_v_ms")
    if pd.isna(u) or pd.isna(v):
        return None
    return float(np.hypot(u, v))


def _real_window(store: RealDataStore, now: datetime, hours_each_side: int) -> list[WeatherStripPoint] | None:
    df = store.nwp_history_df()
    if df.empty:
        return None

    hour_start = now.replace(minute=0, second=0, microsecond=0)
    targets = [hour_start + timedelta(hours=offset) for offset in range(-hours_each_side, hours_each_side + 1)]
    ghi_clearsky_arr, cos_zenith_arr = _solar_geometry(targets)
    cloud_df = store.cloud_history_df()

    points: list[WeatherStripPoint] = []
    for i, target in enumerate(targets):
        row = _nearest_real_row(df, target)
        if row is None:
            continue
        # RH/wind are never shown for future hours even though the GFS row
        # technically carries a value there - see this module's own docstring
        # on why (never validated as trained regressors, unlike ssrd/temp).
        is_future = target > now
        points.append(
            WeatherStripPoint(
                timestamp=target,
                temp_c=float(row["temp2m_c"]),
                ssrd_w_m2=float(row["ssrd_w_m2"]),
                ghi_clearsky_w_m2=float(ghi_clearsky_arr[i]),
                cos_zenith=float(cos_zenith_arr[i]),
                cloud_index=_nearest_cloud_index(cloud_df, target),
                relative_humidity_pct=None if is_future else _maybe_float(row.get("relative_humidity_pct")),
                wind_speed_ms=None if is_future else _wind_speed_ms(row),
            )
        )

    if len(points) < len(targets) * _MIN_REAL_COVERAGE_FRACTION:
        return None
    return points


def _synthetic_window(now: datetime, hours_each_side: int) -> list[WeatherStripPoint]:
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    idx = pd.date_range(
        hour_start - timedelta(hours=hours_each_side), hour_start + timedelta(hours=hours_each_side), freq="h", tz="UTC"
    )
    ssrd, temp = synthetic_temp_at(idx)
    targets = [ts.to_pydatetime() for ts in idx]
    ghi_clearsky_arr, cos_zenith_arr = _solar_geometry(targets)
    # cloud_index/RH/wind stay None here - no real observation exists at all
    # in synthetic-fallback mode, and fabricating plausible-looking values for
    # them would misrepresent a made-up number as real weather data.
    return [
        WeatherStripPoint(
            timestamp=target,
            temp_c=float(t),
            ssrd_w_m2=float(s),
            ghi_clearsky_w_m2=float(ghi_clearsky_arr[i]),
            cos_zenith=float(cos_zenith_arr[i]),
        )
        for i, (target, s, t) in enumerate(zip(targets, ssrd, temp))
    ]


def _uv_daily(store: RealDataStore, now: datetime) -> list[UvDailyPoint]:
    df = store.uv_history_df()
    if df.empty:
        return []
    cutoff = (now - timedelta(days=_UV_HISTORY_DAYS)).date()
    recent = df[df["observation_date"] >= cutoff].sort_values("observation_date")
    return [UvDailyPoint(date=row["observation_date"], uv_index=float(row["uv_index"])) for _, row in recent.iterrows()]


@router.get("/weather/strip", response_model=WeatherStripResponse)
async def get_weather_strip(
    request: Request, hours_each_side: int = DEFAULT_HOURS_EACH_SIDE, _user=Depends(require_role("viewer"))
) -> WeatherStripResponse:
    now = datetime.now(timezone.utc)
    store: RealDataStore = request.app.state.real_data_store
    uv_daily = _uv_daily(store, now)

    real_points = _real_window(store, now, hours_each_side)
    if real_points is not None:
        return WeatherStripResponse(data_source="real", points=real_points, uv_daily=uv_daily)

    return WeatherStripResponse(data_source="synthetic", points=_synthetic_window(now, hours_each_side), uv_daily=uv_daily)


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
