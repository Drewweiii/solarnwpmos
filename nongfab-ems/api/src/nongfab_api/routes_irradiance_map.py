"""GET /irradiance-map - Module 7's Feature E: a plant-wide irradiance grid
(0-1000 W/m^2) plus the 3 zones' own pins (each with its own irradiance,
cloud factor, estimated output and plant factor, and corner boundary),
for a MapLibre overlay with a time scrubber and layer toggles. Reuses
Module 3's clear-sky/solar-position calculation (`nongfab_features.
clearsky`), the `nongfab_features.irradiance_map` grid/cloud-factor model,
and Module 5's `simulate_zone_baseline()` pipeline rather than duplicating
any of them - see `irradiance_map.py`'s own docstring for why cloud_factor
is a documented synthetic placeholder (no live Himawari raster store exists
in this dev environment yet) and why solar position is computed once at the
plant's nominal center rather than per grid point.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends
from nongfab_common.assets import load_assets
from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location
from nongfab_features.irradiance_map import DEFAULT_GRID_SIZE, irradiance_at_point, irradiance_grid
from nongfab_simulation.pipeline import simulate_zone_baseline
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["irradiance-map"])

# No real-time ambient temperature exists for an arbitrary instant/location
# (Module 1/2 don't have accumulated history yet - same caveat as every
# other module) - a fixed nominal ambient temp, roughly matching
# `nongfab_simulation.dev_data.synthetic_day_irradiance_temp()`'s own midday
# values, so the zone-pin's `estimated_ac_kw`/`plant_factor` is a real
# physics-model output (PV conversion + loss model + clipping, not a
# fabricated formula), just without a real temperature input to feed it.
NOMINAL_AMBIENT_TEMP_C = 30.0


class GridPointOut(BaseModel):
    lat: float
    lon: float
    ghi_w_m2: float
    cloud_factor: float


class LatLonOut(BaseModel):
    lat: float
    lon: float


class ZonePinOut(BaseModel):
    id: str
    name_full: str
    lat: float
    lon: float
    ac_capacity_kw: float
    simulated: bool
    ghi_w_m2: float
    cloud_factor: float
    estimated_ac_kw: float
    # actual_ac_kw / ac_capacity_kw - "plant factor" per Feature A's own
    # naming (see routes_forecast.py/ForecastPage.tsx), reusing the same
    # PV-conversion + loss-model + clipping chain `/performance/{zone}` does,
    # not a separate ad hoc formula.
    plant_factor: float
    # UL -> UR -> LR -> LL -> UL (closed ring) - a proper traversal order for
    # a GeoJSON-style polygon outline, not the raw UL/UR/LL/LR field order in
    # config/assets.yaml (which would self-intersect if used directly).
    boundary: list[LatLonOut]


class SolarPositionOut(BaseModel):
    azimuth_deg: float
    elevation_deg: float


class IrradianceMapResponse(BaseModel):
    at: datetime
    sun: SolarPositionOut
    clearsky_ghi_w_m2: float
    grid: list[GridPointOut]
    zones: list[ZonePinOut]


def _zone_boundary(zone) -> list[LatLonOut]:
    c = zone.corners
    ring = [c.UL, c.UR, c.LR, c.LL, c.UL]
    return [LatLonOut(lat=p.lat, lon=p.lon) for p in ring]


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
    epoch_seconds = when.timestamp()

    grid = irradiance_grid(clearsky_ghi, epoch_seconds, registry, DEFAULT_GRID_SIZE)

    zone_pins = []
    for z in registry.zones:
        point = irradiance_at_point(z.centroid.lat, z.centroid.lon, clearsky_ghi, epoch_seconds)
        baseline = simulate_zone_baseline(
            z.id, np.array([point.ghi_w_m2]), np.array([NOMINAL_AMBIENT_TEMP_C]), pd.DatetimeIndex([when]),
        )
        estimated_ac_kw = float(baseline.ac_power_kw.iloc[0])
        zone_pins.append(
            ZonePinOut(
                id=z.id, name_full=z.name_full, lat=z.centroid.lat, lon=z.centroid.lon,
                ac_capacity_kw=z.ac_capacity_kw, simulated=z.simulated,
                ghi_w_m2=point.ghi_w_m2, cloud_factor=point.cloud_factor,
                estimated_ac_kw=estimated_ac_kw, plant_factor=estimated_ac_kw / z.ac_capacity_kw,
                boundary=_zone_boundary(z),
            )
        )

    return IrradianceMapResponse(
        at=when,
        sun=SolarPositionOut(azimuth_deg=azimuth_deg, elevation_deg=elevation_deg),
        clearsky_ghi_w_m2=clearsky_ghi,
        grid=[GridPointOut(lat=p.lat, lon=p.lon, ghi_w_m2=p.ghi_w_m2, cloud_factor=p.cloud_factor) for p in grid],
        zones=zone_pins,
    )
