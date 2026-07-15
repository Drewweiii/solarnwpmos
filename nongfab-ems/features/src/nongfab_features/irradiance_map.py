"""Plant-wide irradiance grid - Module 7's Feature E (MapLibre irradiance
overlay). Reuses this module's own clear-sky/solar-position calculation
(clearsky.py) rather than duplicating it: solar position and clear-sky GHI
are computed ONCE, at the plant's own nominal center, for the requested
instant - a defensible simplification, not a shortcut, since the 3 zones
span under ~2km and solar position/airmass are effectively identical across
that distance (the same assumption `/sun-path/{zone}` already documents and
relies on - see routes_solar3d.py). What actually varies point-to-point
across a grid this size is cloud cover, not solar geometry.

No live cloud-tile store exists in this dev environment yet (Module 1's own
"Known gaps" - MinIO/TimescaleDB rasters aren't accumulated/queryable here),
so `cloud_factor` below is a deterministic seeded synthetic value driven by
(grid position, timestamp) - NOT a real Himawari sample - documented the
same way as `nongfab_simulation.dev_data.synthetic_day_irradiance_temp()`.
Swapping in a real `himawari_ingestion.sampling.sample_cloud_at()` call per
grid point is a follow-up once Module 1 has a live raster store, not a
redesign of this module's shape.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nongfab_common.assets import AssetRegistry, load_assets, target_bbox

# 10x10 = 100 points - dense enough to render a smooth overlay, cheap enough
# to compute (and send over the wire) per-request with no caching.
DEFAULT_GRID_SIZE = 10

# Maps a raw [-1, 1] pseudo-cloud wave to a GHI multiplier: even the
# cloudiest simulated patch still lets some diffuse irradiance through
# (0.35), never fully opaque like night-time zero (that comes from
# clear-sky GHI itself being ~0, not from this factor).
_CLOUD_FACTOR_MIN = 0.35
_CLOUD_FACTOR_MAX = 1.0

MAX_DISPLAY_GHI_W_M2 = 1000.0  # the map overlay's own documented display range


@dataclass(frozen=True)
class GridPoint:
    lat: float
    lon: float
    ghi_w_m2: float
    cloud_factor: float  # 0 (fully overcast) .. 1 (clear sky), multiplies clear-sky GHI


def _cloud_factor(lat: float, lon: float, epoch_seconds: float) -> float:
    """Deterministic pseudo-cloud field: three slow sine waves over (lat,
    lon, time) so the overlay looks like drifting cloud cover rather than
    per-pixel noise, and is reproducible for a given (position, time) rather
    than actually random. See module docstring - a placeholder for a real
    Himawari sample, not a forecast. Wavelengths/speeds are chosen only to
    look like slowly-drifting fronts at plant scale over a day, not
    calibrated to any real meteorological motion vector.
    """
    t_hours = epoch_seconds / 3600.0
    wave1 = math.sin(lat * 40 + t_hours * 0.5)
    wave2 = math.sin(lon * 35 - t_hours * 0.3 + 1.7)
    wave3 = math.sin((lat + lon) * 22 + t_hours * 0.15)
    raw = (wave1 + wave2 + wave3) / 3  # in [-1, 1]
    midpoint = (_CLOUD_FACTOR_MIN + _CLOUD_FACTOR_MAX) / 2
    half_range = (_CLOUD_FACTOR_MAX - _CLOUD_FACTOR_MIN) / 2
    return midpoint + half_range * raw


def grid_points(registry: AssetRegistry | None = None, n: int = DEFAULT_GRID_SIZE) -> list[tuple[float, float]]:
    """n x n (lat, lon) points evenly spaced across the plant's target bbox -
    the same bbox Module 1's cloud-tile fetch targets
    (`nongfab_common.assets.target_bbox()`), reused rather than duplicated.
    """
    registry = registry or load_assets()
    lat_min, lat_max, lon_min, lon_max = target_bbox(registry)
    if n < 2:
        return [((lat_min + lat_max) / 2, (lon_min + lon_max) / 2)]
    lats = [lat_min + (lat_max - lat_min) * i / (n - 1) for i in range(n)]
    lons = [lon_min + (lon_max - lon_min) * j / (n - 1) for j in range(n)]
    return [(lat, lon) for lat in lats for lon in lons]


def irradiance_grid(
    clearsky_ghi_w_m2: float, epoch_seconds: float, registry: AssetRegistry | None = None, n: int = DEFAULT_GRID_SIZE,
) -> list[GridPoint]:
    """Applies the synthetic cloud factor to one shared clear-sky GHI value
    (the caller computes it once via `clearsky.compute_clearsky_and_position`
    at the plant's nominal center - see module docstring) across every grid
    point, clipped to `MAX_DISPLAY_GHI_W_M2`.
    """
    points = grid_points(registry, n)
    result = []
    for lat, lon in points:
        factor = _cloud_factor(lat, lon, epoch_seconds)
        ghi = max(0.0, min(MAX_DISPLAY_GHI_W_M2, clearsky_ghi_w_m2 * factor))
        result.append(GridPoint(lat=lat, lon=lon, ghi_w_m2=ghi, cloud_factor=factor))
    return result
