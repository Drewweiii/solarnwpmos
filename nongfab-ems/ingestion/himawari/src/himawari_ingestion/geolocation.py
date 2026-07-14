from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import xarray as xr


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
