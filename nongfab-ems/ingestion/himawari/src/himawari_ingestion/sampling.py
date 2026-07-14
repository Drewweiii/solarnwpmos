"""sample_cloud_at(lat, lon, t): sample cloud data at any coordinate within an
already-fetched tile, at any past time. Needed for Feature B (differential
shading along the Jetty, sampled per sub-array) and generally for anything
that wants a value at a specific point rather than just Nong Fab's own pixel.

Two layers:
- sample_cloud_at(): pure nearest-neighbor lookup within one already-loaded
  raster (no I/O) - the primitive.
- sample_cloud_at_time(): the full "t" chain - looks up which stored frame is
  closest to a timestamp (TimescaleReader), fetches it from raw storage
  (RawObjectStorage), and samples it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from .datasource import deserialize_raster
from .storage import RawObjectStorage, TimescaleReader

# Same fixed grid this product uses everywhere in Module 1 - see geolocation.py.
_KM_PER_DEG_LAT = 111.32


@dataclass(frozen=True)
class CloudSample:
    cloud_opacity_pct: float
    cloud_index: float
    matched_latitude: float
    matched_longitude: float
    distance_km: float  # how far the matched grid pixel is from the requested (lat, lon)


def sample_cloud_at(arrays: dict[str, np.ndarray], lat: float, lon: float) -> CloudSample:
    """Nearest-neighbor sample within one already-loaded tile's own lat/lon grid
    (no network/storage I/O). `arrays` is what datasource.deserialize_raster()
    returns: cloud_mask, cloud_probability, latitude, longitude (all same shape).
    """
    grid_lat = arrays["latitude"]
    grid_lon = arrays["longitude"]

    # Same flat-Earth approximation used throughout this module (fine at plant-scale
    # distances): degrees -> km, longitude scaled by cos(latitude).
    km_per_deg_lon = _KM_PER_DEG_LAT * math.cos(math.radians(lat))
    dy_km = (grid_lat - lat) * _KM_PER_DEG_LAT
    dx_km = (grid_lon - lon) * km_per_deg_lon
    dist2 = dy_km**2 + dx_km**2

    idx = np.unravel_index(np.argmin(dist2), dist2.shape)
    return CloudSample(
        cloud_opacity_pct=float(np.clip(arrays["cloud_probability"][idx] * 100.0, 0.0, 100.0)),
        cloud_index=float(np.clip(arrays["cloud_mask"][idx] / 3.0, -0.2, 1.5)),
        matched_latitude=float(grid_lat[idx]),
        matched_longitude=float(grid_lon[idx]),
        distance_km=float(math.sqrt(dist2[idx])),
    )


async def sample_cloud_at_time(
    reader: TimescaleReader, raw_storage: RawObjectStorage, source: str, lat: float, lon: float, t: datetime,
    max_delta_minutes: float = 30.0,
) -> CloudSample | None:
    """Full chain: finds the stored frame closest to `t` (within
    `max_delta_minutes`), fetches its raster from raw storage, and samples it
    at (lat, lon). Returns None if no frame is close enough to `t`.
    """
    found = await reader.find_nearest_raster_frame(source, t, max_delta_minutes=max_delta_minutes)
    if found is None:
        return None
    _actual_time, object_key = found

    body = await raw_storage.get_raw(object_key)
    arrays = deserialize_raster(body)
    return sample_cloud_at(arrays, lat, lon)
