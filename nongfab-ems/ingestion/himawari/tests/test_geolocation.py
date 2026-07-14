import numpy as np
import pytest
import xarray as xr

from himawari_ingestion.geolocation import calibrate_pixel_index


def test_calibrate_pixel_index_finds_nearest_grid_point():
    lat = np.array([[13.0, 13.0, 13.0], [12.7, 12.7, 12.7], [12.4, 12.4, 12.4]], dtype=np.float32)
    lon = np.array([[100.9, 101.15, 101.4], [100.9, 101.15, 101.4], [100.9, 101.15, 101.4]], dtype=np.float32)
    ds = xr.Dataset({"Latitude": (("Rows", "Columns"), lat), "Longitude": (("Rows", "Columns"), lon)})

    pixel = calibrate_pixel_index(ds, target_lat=12.71, target_lon=101.15)

    assert pixel.row == 1
    assert pixel.col == 1
    assert pixel.latitude == pytest.approx(12.7, abs=1e-4)
    assert pixel.longitude == pytest.approx(101.15, abs=1e-4)


def test_calibrate_pixel_index_ignores_nan_fill_values():
    lat = np.array([[np.nan, 12.71], [np.nan, np.nan]], dtype=np.float32)
    lon = np.array([[np.nan, 101.15], [np.nan, np.nan]], dtype=np.float32)
    ds = xr.Dataset({"Latitude": (("Rows", "Columns"), lat), "Longitude": (("Rows", "Columns"), lon)})

    pixel = calibrate_pixel_index(ds, target_lat=12.71, target_lon=101.15)

    assert pixel.row == 0
    assert pixel.col == 1
