from datetime import datetime, timezone
from unittest.mock import AsyncMock

import numpy as np
import pytest

from himawari_ingestion.datasource import serialize_raster
from himawari_ingestion.sampling import sample_cloud_at, sample_cloud_at_time


def _make_arrays():
    # 3x3 grid, lat decreasing by row (like the real product), lon increasing by col
    lat = np.array([[12.73, 12.73, 12.73], [12.71, 12.71, 12.71], [12.69, 12.69, 12.69]])
    lon = np.array([[101.10, 101.13, 101.16]] * 3)
    cloud_mask = np.array([[0.0, 1.0, 2.0], [1.0, 3.0, 2.0], [0.0, 1.0, 3.0]])
    cloud_probability = np.array([[0.05, 0.3, 0.6], [0.3, 0.99, 0.6], [0.05, 0.3, 0.99]])
    return {"latitude": lat, "longitude": lon, "cloud_mask": cloud_mask, "cloud_probability": cloud_probability}


def test_sample_cloud_at_matches_exact_grid_point():
    arrays = _make_arrays()
    sample = sample_cloud_at(arrays, lat=12.71, lon=101.13)  # exactly the center pixel

    assert sample.matched_latitude == pytest.approx(12.71)
    assert sample.matched_longitude == pytest.approx(101.13)
    assert sample.cloud_opacity_pct == pytest.approx(99.0)
    assert sample.cloud_index == pytest.approx(1.0)
    assert sample.distance_km == pytest.approx(0.0, abs=1e-6)


def test_sample_cloud_at_finds_nearest_when_not_exact():
    arrays = _make_arrays()
    # closer to the top-left pixel (12.73, 101.10) than any other
    sample = sample_cloud_at(arrays, lat=12.729, lon=101.101)

    assert sample.matched_latitude == pytest.approx(12.73)
    assert sample.matched_longitude == pytest.approx(101.10)
    assert sample.distance_km > 0
    assert sample.distance_km < 1.0  # much closer than the ~2km grid spacing


def test_sample_cloud_at_clips_to_valid_range():
    arrays = {
        "latitude": np.array([[12.71]]),
        "longitude": np.array([[101.15]]),
        "cloud_mask": np.array([[10.0]]),  # out-of-range raw value
        "cloud_probability": np.array([[5.0]]),  # out-of-range raw value
    }
    sample = sample_cloud_at(arrays, lat=12.71, lon=101.15)
    assert sample.cloud_opacity_pct == 100.0
    assert sample.cloud_index == 1.5


@pytest.mark.asyncio
async def test_sample_cloud_at_time_full_chain():
    arrays = _make_arrays()
    body = serialize_raster(arrays["cloud_mask"], arrays["cloud_probability"], arrays["latitude"], arrays["longitude"])

    reader = AsyncMock()
    frame_time = datetime(2026, 7, 14, 3, 0, tzinfo=timezone.utc)
    reader.find_nearest_raster_frame.return_value = (frame_time, "himawari/some/tile.npz")

    raw_storage = AsyncMock()
    raw_storage.get_raw.return_value = body

    sample = await sample_cloud_at_time(
        reader, raw_storage, source="noaa-himawari9-ahi-cmsk", lat=12.71, lon=101.13,
        t=datetime(2026, 7, 14, 3, 4, tzinfo=timezone.utc),
    )

    assert sample is not None
    assert sample.cloud_opacity_pct == pytest.approx(99.0)
    reader.find_nearest_raster_frame.assert_awaited_once()
    raw_storage.get_raw.assert_awaited_once_with("himawari/some/tile.npz")


@pytest.mark.asyncio
async def test_sample_cloud_at_time_returns_none_when_no_frame_close_enough():
    reader = AsyncMock()
    reader.find_nearest_raster_frame.return_value = None
    raw_storage = AsyncMock()

    sample = await sample_cloud_at_time(
        reader, raw_storage, source="noaa-himawari9-ahi-cmsk", lat=12.71, lon=101.13,
        t=datetime(2026, 7, 14, 3, 4, tzinfo=timezone.utc),
    )

    assert sample is None
    raw_storage.get_raw.assert_not_awaited()
