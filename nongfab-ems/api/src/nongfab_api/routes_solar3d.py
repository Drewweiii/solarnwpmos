"""GET /geometry/{zone} and GET /sun-path/{zone} - Feature B (3D panel-level
shading/solar-access) and Feature C (sun-path sweep)'s data backend. Both
routes reuse Module 3's pvlib-based solar position (`nongfab_features.
clearsky.compute_clearsky_and_position`) and the new per-zone panel-grid +
row-shading model (`nongfab_features.panel_geometry`/`shading`) rather than
duplicating any of that math here.

Solar position (`/sun-path`) is computed from the plant's shared nominal
center (`nongfab_features.clearsky.nong_fab_site_location()`), the same
location every other module uses - not truly zone-specific (all 3 zones are
within ~2km of each other, an immaterial difference for solar position) but
kept under `/{zone}` for path consistency with every other per-zone route,
and so an unknown zone still 404s like the rest of the API.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from nongfab_common.assets import load_assets
from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location
from nongfab_features.panel_geometry import generate_zone_layout
from nongfab_features.shading import average_solar_access_pct, zone_solar_access
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["solar3d"])


class SolarPositionOut(BaseModel):
    azimuth_deg: float
    elevation_deg: float


class PanelOut(BaseModel):
    block_id: str
    row: int
    col: int
    east_m: float
    north_m: float
    width_m: float
    slant_height_m: float
    solar_access_pct: float


class GeometryResponse(BaseModel):
    zone: str
    simulated_zone: bool
    at: datetime
    tilt_deg: float
    azimuth_deg: float
    row_pitch_m: float
    sun: SolarPositionOut
    average_solar_access_pct: float
    panels: list[PanelOut]


class SunPathPoint(BaseModel):
    time: datetime
    azimuth_deg: float
    elevation_deg: float


class SunPathResponse(BaseModel):
    zone: str
    date: str
    points: list[SunPathPoint]


def _validate_zone(zone: str) -> str:
    capacities = nong_fab_zone_capacities_kwp()
    if zone not in capacities:
        raise HTTPException(status_code=404, detail=f"unknown zone {zone!r}; known zones: {sorted(capacities)}")
    return zone


@router.get("/geometry/{zone}", response_model=GeometryResponse)
async def get_geometry(zone: str, at: datetime | None = None, _user=Depends(require_role("viewer"))) -> GeometryResponse:
    """Panel-by-panel layout + solar access at one instant (`at`, defaults to
    now). Solar position and per-panel shading are both computed fresh per
    request (no caching) - the panel counts (84/196/320) keep the response
    small enough that this is cheap, and it keeps every call self-consistent
    (no risk of a stale cached sun position drifting from `at`).
    """
    zone = _validate_zone(zone)
    when = at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    registry = load_assets()
    layout = generate_zone_layout(zone, registry)

    lat, lon = nong_fab_site_location()
    solpos = compute_clearsky_and_position(pd.DatetimeIndex([when]), lat, lon)
    elevation_deg = float(solpos["elevation_deg"].iloc[0])
    azimuth_deg = float(solpos["azimuth_deg"].iloc[0])

    access = zone_solar_access(layout, elevation_deg, azimuth_deg)
    panels = [
        PanelOut(
            block_id=p.block_id, row=p.row, col=p.col, east_m=p.east_m, north_m=p.north_m,
            width_m=p.width_m, slant_height_m=p.slant_height_m, solar_access_pct=a.solar_access_pct,
        )
        for p, a in zip(layout.panels, access, strict=True)
    ]

    return GeometryResponse(
        zone=zone, simulated_zone=registry.zone(zone).simulated, at=when,
        tilt_deg=layout.tilt_deg, azimuth_deg=layout.azimuth_deg, row_pitch_m=layout.row_pitch_m,
        sun=SolarPositionOut(azimuth_deg=azimuth_deg, elevation_deg=elevation_deg),
        average_solar_access_pct=average_solar_access_pct(access), panels=panels,
    )


@router.get("/sun-path/{zone}", response_model=SunPathResponse)
async def get_sun_path(zone: str, date: str | None = None, _user=Depends(require_role("viewer"))) -> SunPathResponse:
    """The day's azimuth/elevation arc (`date`, `YYYY-MM-DD`, defaults to
    today UTC) at 15-minute resolution, filtered to daylight (elevation >
    0) - the sweep Feature C's date-scrubbed sun-path arc plots.
    """
    zone = _validate_zone(zone)
    try:
        day = date_type.fromisoformat(date) if date else datetime.now(timezone.utc).date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"date must be YYYY-MM-DD, got {date!r}") from exc

    lat, lon = nong_fab_site_location()
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    index = pd.date_range(start, periods=96, freq="15min", tz="UTC")  # 24h at 15-minute resolution
    solpos = compute_clearsky_and_position(index, lat, lon)

    points = [
        SunPathPoint(time=ts.to_pydatetime(), azimuth_deg=float(row.azimuth_deg), elevation_deg=float(row.elevation_deg))
        for ts, row in solpos.iterrows()
        if row.elevation_deg > 0
    ]
    return SunPathResponse(zone=zone, date=day.isoformat(), points=points)
