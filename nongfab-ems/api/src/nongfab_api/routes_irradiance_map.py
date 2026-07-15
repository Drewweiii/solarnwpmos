"""GET /irradiance-map - Module 7's Feature E: a plant-wide irradiance grid
(0-1000 W/m^2) plus the 3 zones' own pins, for a MapLibre overlay with a time
scrubber. Reuses Module 3's clear-sky/solar-position calculation
(`nongfab_features.clearsky`) and the new `nongfab_features.irradiance_map`
grid/cloud-factor model rather than duplicating either - see that module's
own docstring for why cloud_factor is a documented synthetic placeholder
(no live Himawari raster store exists in this dev environment yet) and why
solar position is computed once at the plant's nominal center rather than
per grid point.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends
from nongfab_common.assets import load_assets
from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location
from nongfab_features.irradiance_map import DEFAULT_GRID_SIZE, irradiance_grid
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["irradiance-map"])


class GridPointOut(BaseModel):
    lat: float
    lon: float
    ghi_w_m2: float
    cloud_factor: float


class ZonePinOut(BaseModel):
    id: str
    name_full: str
    lat: float
    lon: float
    ac_capacity_kw: float
    simulated: bool


class SolarPositionOut(BaseModel):
    azimuth_deg: float
    elevation_deg: float


class IrradianceMapResponse(BaseModel):
    at: datetime
    sun: SolarPositionOut
    clearsky_ghi_w_m2: float
    grid: list[GridPointOut]
    zones: list[ZonePinOut]


@router.get("/irradiance-map", response_model=IrradianceMapResponse)
async def get_irradiance_map(at: datetime | None = None, _user=Depends(require_role("viewer"))) -> IrradianceMapResponse:
    when = at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    registry = load_assets()
    lat, lon = nong_fab_site_location()
    solpos = compute_clearsky_and_position(pd.DatetimeIndex([when]), lat, lon)
    elevation_deg = float(solpos["elevation_deg"].iloc[0])
    azimuth_deg = float(solpos["azimuth_deg"].iloc[0])
    clearsky_ghi = float(solpos["ghi_clearsky"].iloc[0])

    grid = irradiance_grid(clearsky_ghi, when.timestamp(), registry, DEFAULT_GRID_SIZE)

    return IrradianceMapResponse(
        at=when,
        sun=SolarPositionOut(azimuth_deg=azimuth_deg, elevation_deg=elevation_deg),
        clearsky_ghi_w_m2=clearsky_ghi,
        grid=[GridPointOut(lat=p.lat, lon=p.lon, ghi_w_m2=p.ghi_w_m2, cloud_factor=p.cloud_factor) for p in grid],
        zones=[
            ZonePinOut(
                id=z.id, name_full=z.name_full, lat=z.centroid.lat, lon=z.centroid.lon,
                ac_capacity_kw=z.ac_capacity_kw, simulated=z.simulated,
            )
            for z in registry.zones
        ],
    )
