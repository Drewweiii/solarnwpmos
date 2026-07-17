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
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, Depends, Request
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


class WeatherStripResponse(BaseModel):
    data_source: str  # "real" or "synthetic" - see this module's own docstring
    points: list[WeatherStripPoint]


def _nearest_real_row(df: pd.DataFrame, target: datetime, max_delta_hours: float = 1.5) -> pd.Series | None:
    deltas = (df["valid_time"] - target).abs()
    idx = deltas.idxmin()
    if deltas.loc[idx].total_seconds() > max_delta_hours * 3600:
        return None
    return df.loc[idx]


def _real_window(store: RealDataStore, now: datetime, hours_each_side: int) -> list[WeatherStripPoint] | None:
    df = store.nwp_history_df()
    if df.empty:
        return None

    hour_start = now.replace(minute=0, second=0, microsecond=0)
    targets = [hour_start + timedelta(hours=offset) for offset in range(-hours_each_side, hours_each_side + 1)]

    points: list[WeatherStripPoint] = []
    for target in targets:
        row = _nearest_real_row(df, target)
        if row is not None:
            points.append(WeatherStripPoint(timestamp=target, temp_c=float(row["temp2m_c"]), ssrd_w_m2=float(row["ssrd_w_m2"])))

    if len(points) < len(targets) * _MIN_REAL_COVERAGE_FRACTION:
        return None
    return points


def _synthetic_window(now: datetime, hours_each_side: int) -> list[WeatherStripPoint]:
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    idx = pd.date_range(
        hour_start - timedelta(hours=hours_each_side), hour_start + timedelta(hours=hours_each_side), freq="h", tz="UTC"
    )
    ssrd, temp = synthetic_temp_at(idx)
    return [
        WeatherStripPoint(timestamp=ts.to_pydatetime(), temp_c=float(t), ssrd_w_m2=float(s)) for ts, s, t in zip(idx, ssrd, temp)
    ]


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
