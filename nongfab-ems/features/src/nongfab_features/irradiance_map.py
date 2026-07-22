"""Plant-wide irradiance grid - Module 7's Feature E (MapLibre irradiance
overlay). Reuses this module's own clear-sky/solar-position calculation
(clearsky.py) rather than duplicating it: solar position and clear-sky GHI
are computed ONCE, at the plant's own nominal center, for the requested
instant - a defensible simplification, not a shortcut, since the 3 zones
span under ~2km and solar position/airmass are effectively identical across
that distance (the same assumption `/sun-path/{zone}` already documents and
relies on - see routes_solar3d.py). What actually varies point-to-point
across a grid this size is cloud cover, not solar geometry.

No per-point live cloud *raster* store exists in this dev environment (Module
1's own "Known gaps" - MinIO/TimescaleDB rasters aren't accumulated/queryable
on Railway; `himawari_ingestion.sampling.sample_cloud_at_time()` needs raw
tile storage that isn't here). What *does* exist is a real plant-wide Himawari
cloud time-series (`local_store.cloud_history`, one value at Nong Fab's own
pixel per timestamp).

So (2026-07-22, roadmap item 4) `cloud_factor_at` now takes an optional
`base_cloud_factor`: when the caller passes the real plant-wide cloud GHI
factor (from `nongfab_forecast.real_data.cloud_factor_for_time`), the overlay
is *anchored to real cloud conditions* and the sine field degrades to a small
labelled spatial texture (`_SPATIAL_TEXTURE_AMPLITUDE`) around that real level
- honest about what's real (the plant-wide cloudiness) vs. interpolated (the
sub-2km spatial variation, which no per-point data exists for). With
`base_cloud_factor=None` it falls back to the original fully-synthetic field
(deterministic seeded (position, timestamp) waves, same convention as
`nongfab_simulation.dev_data.synthetic_day_irradiance_temp()`), used only when
no real cloud observation is available.
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

# When anchored to a real plant-wide cloud level (`base_cloud_factor`), the
# sine field no longer sets the absolute cloudiness - it only adds a small
# +/- spatial ripple around the real level so the sub-2km overlay still reads
# as a field rather than a flat wash. Deliberately small: it's labelled
# interpolated texture, not real per-point data (none exists). The real base
# can itself go well below _CLOUD_FACTOR_MIN under genuine heavy overcast, so
# the anchored result is clipped to a wider [_REAL_ANCHORED_FLOOR, 1.0].
_SPATIAL_TEXTURE_AMPLITUDE = 0.12
_REAL_ANCHORED_FLOOR = 0.05

MAX_DISPLAY_GHI_W_M2 = 1000.0  # the map overlay's own documented display range


@dataclass(frozen=True)
class GridPoint:
    lat: float
    lon: float
    ghi_w_m2: float
    cloud_factor: float  # 0 (fully overcast) .. 1 (clear sky), multiplies clear-sky GHI


def cloud_factor_at(
    lat: float, lon: float, epoch_seconds: float, base_cloud_factor: float | None = None
) -> float:
    """Cloud GHI multiplier (0..1) at one point.

    `base_cloud_factor` is the real plant-wide cloud level (from
    `nongfab_forecast.real_data.cloud_factor_for_time`, itself derived from the
    live Himawari `cloud_history`). When given, the result is that real level
    plus a small deterministic spatial ripple (`_SPATIAL_TEXTURE_AMPLITUDE`),
    clipped to `[_REAL_ANCHORED_FLOOR, 1.0]` - real cloudiness, interpolated
    sub-2km texture (no per-point data exists; see module docstring).

    With `base_cloud_factor=None` (no real observation available) it returns
    the original fully-synthetic field: three slow sine waves over (lat, lon,
    time) so the overlay looks like drifting cloud cover, reproducible for a
    given (position, time). Wavelengths/speeds are chosen only to look like
    slowly-drifting fronts at plant scale, not calibrated to any real motion.

    Public (not `irradiance_grid()`-only) since Feature A's per-zone "cloud
    factor" readout and Feature E's zone-pin click panel both want this same
    value at one specific point (a zone's own centroid) rather than a whole
    grid - see `routes_performance.py`/`routes_irradiance_map.py`.
    """
    t_hours = epoch_seconds / 3600.0
    wave1 = math.sin(lat * 40 + t_hours * 0.5)
    wave2 = math.sin(lon * 35 - t_hours * 0.3 + 1.7)
    wave3 = math.sin((lat + lon) * 22 + t_hours * 0.15)
    raw = (wave1 + wave2 + wave3) / 3  # in [-1, 1]
    if base_cloud_factor is not None:
        anchored = base_cloud_factor + _SPATIAL_TEXTURE_AMPLITUDE * raw
        return max(_REAL_ANCHORED_FLOOR, min(_CLOUD_FACTOR_MAX, anchored))
    midpoint = (_CLOUD_FACTOR_MIN + _CLOUD_FACTOR_MAX) / 2
    half_range = (_CLOUD_FACTOR_MAX - _CLOUD_FACTOR_MIN) / 2
    return midpoint + half_range * raw


def irradiance_at_point(
    lat: float, lon: float, clearsky_ghi_w_m2: float, epoch_seconds: float,
    base_cloud_factor: float | None = None,
) -> GridPoint:
    """Same clear-sky x cloud-factor model as `irradiance_grid()`, evaluated
    at one arbitrary (lat, lon) instead of a whole grid - e.g. a zone's own
    centroid, not the nearest generic grid cell. `base_cloud_factor` anchors
    the overlay to real cloud conditions - see `cloud_factor_at`.
    """
    factor = cloud_factor_at(lat, lon, epoch_seconds, base_cloud_factor)
    ghi = max(0.0, min(MAX_DISPLAY_GHI_W_M2, clearsky_ghi_w_m2 * factor))
    return GridPoint(lat=lat, lon=lon, ghi_w_m2=ghi, cloud_factor=factor)


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
    clearsky_ghi_w_m2: float, epoch_seconds: float, registry: AssetRegistry | None = None,
    n: int = DEFAULT_GRID_SIZE, base_cloud_factor: float | None = None,
) -> list[GridPoint]:
    """Applies the cloud factor to one shared clear-sky GHI value (the caller
    computes it once via `clearsky.compute_clearsky_and_position` at the
    plant's nominal center - see module docstring) across every grid point,
    clipped to `MAX_DISPLAY_GHI_W_M2`. `base_cloud_factor` anchors the overlay
    to real plant-wide cloud conditions - see `cloud_factor_at`.
    """
    points = grid_points(registry, n)
    return [irradiance_at_point(lat, lon, clearsky_ghi_w_m2, epoch_seconds, base_cloud_factor) for lat, lon in points]
