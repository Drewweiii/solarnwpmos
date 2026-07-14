from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import xarray as xr
from nongfab_common.assets import load_assets
from nongfab_common.assets import target_bbox as _config_target_bbox


@dataclass(frozen=True)
class CalibratedPixel:
    row: int
    col: int
    latitude: float
    longitude: float


# Verified live 2026-07-14 against
# AHI-CMSK_v1r1_h09_s202607130200209_e202607130209403_c202607130241190.nc:
# nearest full-disk grid pixel to Nong Fab (12.71N, 101.15E) is Rows=2086, Columns=859,
# whose actual Latitude/Longitude is (12.708836, 101.14675) - about 350m off target,
# which is expected for a ~2km/pixel fixed grid. Re-derive with calibrate_pixel_index()
# below (against a freshly opened dataset) if NOAA ever changes this product's grid.
NONG_FAB_PIXEL = CalibratedPixel(row=2086, col=859, latitude=12.708836, longitude=101.14675)


def calibrate_pixel_index(dataset: xr.Dataset, target_lat: float, target_lon: float) -> CalibratedPixel:
    """Nearest-neighbor search over the product's full Latitude/Longitude grids.

    This pulls the complete 2D lat/lon arrays (~250MB combined for the 5500x5500
    full-disk grid used by AHI-L2-FLDK-Clouds) - a one-time operator action to run
    when calibrating a new site or a new product/grid, not something to run on
    every ingestion cycle (that's what NONG_FAB_PIXEL exists to avoid).
    """
    lat = dataset["Latitude"].values
    lon = dataset["Longitude"].values
    valid = np.isfinite(lat) & np.isfinite(lon)
    dist2 = np.where(valid, (lat - target_lat) ** 2 + (lon - target_lon) ** 2, np.inf)
    row, col = (int(i) for i in np.unravel_index(np.argmin(dist2), dist2.shape))
    return CalibratedPixel(row=row, col=col, latitude=float(lat[row, col]), longitude=float(lon[row, col]))


@dataclass(frozen=True)
class CalibratedBBox:
    """A rectangular pixel-index window (in the product's native Rows/Columns grid)
    that fully covers a target lat/lon bounding box. Indices are inclusive.
    """

    row_start: int
    row_end: int
    col_start: int
    col_end: int
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    @property
    def shape(self) -> tuple[int, int]:
        return (self.row_end - self.row_start + 1, self.col_end - self.col_start + 1)


# Target lat/lon extent now comes from config/assets.yaml (union of all 3 zones'
# corners + cloud_tile.buffer_deg), not a hardcoded duplicate - see nongfab_common.
# assets.target_bbox(). Loaded once at import time; if assets.yaml's zone geometry
# ever changes, re-run calibrate_bbox_index() against a live file (below) - the
# row/col pixel window is a cached, live-verified constant, not recomputed here.
_ASSETS = load_assets()
_LAT_MIN, _LAT_MAX, _LON_MIN, _LON_MAX = _config_target_bbox(_ASSETS)

# Verified live 2026-07-14 (AHI-CMSK_v1r1_h09_s202607140740209_...) against the bbox
# above (lat [12.6071, 12.7435], lon [101.0547, 101.1799]):
# Rows=2085..2091, Columns=855..860 -> a 7x6 = 42 pixel window. (An earlier revision
# of this constant, calibrated against a slightly narrower hardcoded bbox before
# config/assets.yaml existed, was 7x5 with col_start=856 - re-verifying against the
# wider config-derived bbox picked up one more column, confirming this must be
# re-checked against real data rather than assumed unchanged.)
#
# IMPORTANT: local grid spacing here is ~0.0197 deg/row (~2.2km) and ~0.0278 deg/col
# (~2.8km at this latitude) - COARSER than the ~1.25-1.5km jetty/trestle structure this
# is meant to resolve. This window is genuinely useful for plant-level cloud opacity and
# *regional* cloud-motion direction (see motion.py), but cannot resolve differential
# shading along the jetty (head vs. tail) from this satellite product alone - that needs
# a complementary technique (e.g. cloud-height + sun-geometry shadow projection, or a
# ground-based sky camera), out of scope for this ingestion module.
NONG_FAB_BBOX = CalibratedBBox(
    row_start=2085, row_end=2091, col_start=855, col_end=860,
    lat_min=_LAT_MIN, lat_max=_LAT_MAX, lon_min=_LON_MIN, lon_max=_LON_MAX,
)

# Physical pixel spacing at this grid location, derived from the verified degree
# spacings above (-0.019720078 deg/row, 0.027801514 deg/col) via standard geodesy
# (111.32 km/deg latitude; longitude scaled by cos(latitude)). Used to convert
# motion.py's pixel-shift output into km/h for CloudRasterFrame.motion_speed_kmh.
NONG_FAB_ROW_SPACING_KM = 0.019720078 * 111.32
NONG_FAB_COL_SPACING_KM = 0.027801514 * 111.32 * math.cos(math.radians(12.71))


def local_index_within_bbox(bbox: CalibratedBBox, pixel: CalibratedPixel) -> tuple[int, int]:
    """Row/col of `pixel` within an array windowed to `bbox` (i.e. array[local_row, local_col]
    is that pixel). Used to sample Nong Fab's own value out of an already-fetched tile
    instead of a separate fetch.
    """
    local_row = pixel.row - bbox.row_start
    local_col = pixel.col - bbox.col_start
    rows, cols = bbox.shape
    if not (0 <= local_row < rows and 0 <= local_col < cols):
        raise ValueError(f"pixel ({pixel.row},{pixel.col}) falls outside bbox window {bbox}")
    return local_row, local_col


def calibrate_bbox_index(dataset: xr.Dataset, lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> CalibratedBBox:
    """Finds the smallest rectangular pixel window covering every grid point whose
    lat/lon falls inside the target bounding box. Same one-time-calibration caveat
    as calibrate_pixel_index() - pulls the full lat/lon grids once.
    """
    lat = dataset["Latitude"].values
    lon = dataset["Longitude"].values
    valid = np.isfinite(lat) & np.isfinite(lon)
    mask = valid & (lat >= lat_min) & (lat <= lat_max) & (lon >= lon_min) & (lon <= lon_max)
    rows, cols = np.where(mask)
    if len(rows) == 0:
        raise ValueError(f"no grid pixels found within bbox lat=[{lat_min},{lat_max}] lon=[{lon_min},{lon_max}]")
    return CalibratedBBox(
        row_start=int(rows.min()), row_end=int(rows.max()),
        col_start=int(cols.min()), col_end=int(cols.max()),
        lat_min=lat_min, lat_max=lat_max, lon_min=lon_min, lon_max=lon_max,
    )
