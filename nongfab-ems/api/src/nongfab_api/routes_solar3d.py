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
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from nongfab_common.assets import load_assets
from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location
from nongfab_features.moon import moon_illumination, moon_position
from nongfab_features.panel_geometry import generate_zone_layout
from nongfab_features.shading import average_solar_access_pct, string_power_balance, zone_solar_access
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


class StringEstimateOut(BaseModel):
    block_id: str
    string_index: int
    module_count: int
    avg_solar_access_pct: float
    estimated_power_kw: float


class StringBalanceOut(BaseModel):
    block_id: str
    strings: list[StringEstimateOut]
    imbalance_kw: float
    max_allowed_kw: float | None
    exceeds_limit: bool


class GeometryResponse(BaseModel):
    zone: str
    simulated_zone: bool
    at: datetime
    tilt_deg: float
    azimuth_deg: float
    row_pitch_m: float
    sun: SolarPositionOut
    # Decorative only (2026-07-18 user request) - see `nongfab_features.moon`'s
    # own module docstring for the low/medium-precision caveat. Always
    # populated (not gated on sun being below the horizon here) so the
    # frontend can decide visibility itself, same as `/moon-path` below.
    moon: SolarPositionOut
    average_solar_access_pct: float
    panels: list[PanelOut]
    # Only non-empty for zones with a real per-string layout AND a
    # `design_constraints.string_power_balance_max_kw` in config/assets.yaml
    # (Jetty today) - see `nongfab_features.shading.string_power_balance()`'s
    # own docstring for why GIS/ISB's block layout can't support this.
    string_balance: list[StringBalanceOut]


class SunPathPoint(BaseModel):
    time: datetime
    azimuth_deg: float
    elevation_deg: float


class SunPathResponse(BaseModel):
    zone: str
    date: str
    points: list[SunPathPoint]


class MoonPathPoint(BaseModel):
    time: datetime
    azimuth_deg: float
    elevation_deg: float


class MoonPathResponse(BaseModel):
    zone: str
    date: str
    points: list[MoonPathPoint]
    # Phase for that date (see moon.moon_illumination) - one value per day
    # since it barely moves over 24h. Lets the 3D view draw a phase-correct
    # crescent/gibbous marker + a "% lit" label instead of a plain full disc.
    illumination: float = 0.0  # 0.0 new .. 1.0 full
    waxing: bool = True  # True = growing (new->full), False = shrinking


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
    moon_azimuth_deg, moon_elevation_deg = moon_position(when, lat, lon)

    access = zone_solar_access(layout, elevation_deg, azimuth_deg)
    panels = [
        PanelOut(
            block_id=p.block_id, row=p.row, col=p.col, east_m=p.east_m, north_m=p.north_m,
            width_m=p.width_m, slant_height_m=p.slant_height_m, solar_access_pct=a.solar_access_pct,
        )
        for p, a in zip(layout.panels, access, strict=True)
    ]

    zone_obj = registry.zone(zone)
    string_balance: list[StringBalanceOut] = []
    if zone_obj.id == "Jetty":  # only Jetty's layout assigns `row` to a real electrical string - see string_power_balance()'s docstring
        max_allowed_kw = zone_obj.design_constraints.string_power_balance_max_kw if zone_obj.design_constraints else None
        string_balance = [
            StringBalanceOut(
                block_id=b.block_id,
                strings=[
                    StringEstimateOut(
                        block_id=s.block_id, string_index=s.string_index, module_count=s.module_count,
                        avg_solar_access_pct=s.avg_solar_access_pct, estimated_power_kw=s.estimated_power_kw,
                    )
                    for s in b.strings
                ],
                imbalance_kw=b.imbalance_kw, max_allowed_kw=b.max_allowed_kw, exceeds_limit=b.exceeds_limit,
            )
            for b in string_power_balance(access, zone_obj.module_power_w, max_allowed_kw)
        ]

    return GeometryResponse(
        zone=zone, simulated_zone=zone_obj.simulated, at=when,
        tilt_deg=layout.tilt_deg, azimuth_deg=layout.azimuth_deg, row_pitch_m=layout.row_pitch_m,
        sun=SolarPositionOut(azimuth_deg=azimuth_deg, elevation_deg=elevation_deg),
        moon=SolarPositionOut(azimuth_deg=moon_azimuth_deg, elevation_deg=moon_elevation_deg),
        average_solar_access_pct=average_solar_access_pct(access), panels=panels,
        string_balance=string_balance,
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


@router.get("/moon-path/{zone}", response_model=MoonPathResponse)
async def get_moon_path(zone: str, date: str | None = None, _user=Depends(require_role("viewer"))) -> MoonPathResponse:
    """The day's lunar azimuth/elevation arc (`date`, `YYYY-MM-DD`, defaults
    to today UTC) at 15-minute resolution - unlike `/sun-path`, this is NOT
    filtered to elevation > 0. The whole point of Feature D (2026-07-18,
    "moon rises to replace the sun after sunset") is showing the moon
    specifically while the sun is down, which is unrelated to whether the
    moon itself happens to be above its own horizon at that exact moment -
    filtering here would remove exactly the points the frontend needs.
    Visibility (only show the moon marker once the sun has set) is a
    frontend concern, decided against the sun's own position, not this
    endpoint's job.
    """
    zone = _validate_zone(zone)
    try:
        day = date_type.fromisoformat(date) if date else datetime.now(timezone.utc).date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"date must be YYYY-MM-DD, got {date!r}") from exc

    lat, lon = nong_fab_site_location()
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    index = pd.date_range(start, periods=96, freq="15min", tz="UTC")  # 24h at 15-minute resolution

    points = [
        MoonPathPoint(time=ts.to_pydatetime(), azimuth_deg=az, elevation_deg=el)
        for ts in index
        for az, el in [moon_position(ts.to_pydatetime(), lat, lon)]
    ]
    # Phase at local midday (a single representative instant - it drifts only
    # ~1%/day, so one value comfortably describes the whole date's marker).
    illumination, waxing = moon_illumination(start + timedelta(hours=12))
    return MoonPathResponse(zone=zone, date=day.isoformat(), points=points, illumination=illumination, waxing=waxing)
