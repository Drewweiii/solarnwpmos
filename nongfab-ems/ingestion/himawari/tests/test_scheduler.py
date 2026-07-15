from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import numpy as np
import pytest

from himawari_ingestion.datasource import serialize_raster
from himawari_ingestion.scheduler import IngestionJob
from himawari_ingestion.schemas import CloudRasterFrame, RawFetchResult

BBOX_KWARGS = dict(lat_min=12.61, lat_max=12.74, lon_min=101.06, lon_max=101.18, rows=7, cols=5)


def _make_frame(observed_at: datetime, opacity: float = 42.0) -> CloudRasterFrame:
    return CloudRasterFrame(
        observed_at=observed_at, source="mock-fixture", nong_fab_cloud_opacity_pct=opacity, nong_fab_cloud_index=0.5, **BBOX_KWARGS,
    )


def _make_raw(cloud_probability: np.ndarray) -> RawFetchResult:
    body = serialize_raster(np.zeros((7, 5)), cloud_probability, np.zeros((7, 5)), np.zeros((7, 5)))
    return RawFetchResult(url="mock://x", fetched_at=datetime.now(timezone.utc), content_type="application/octet-stream", body=body)


@pytest.mark.asyncio
async def test_run_once_records_last_observation_and_frame_on_success():
    observed_at = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
    frame = _make_frame(observed_at)
    raw = _make_raw(np.full((7, 5), 0.4))

    datasource = AsyncMock()
    datasource.fetch_latest.return_value = (raw, frame)
    raw_storage = AsyncMock()
    raw_storage.put_raw.return_value = "some/tile.npz"
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")
    await job.run_once()

    assert job.last_observation.cloud_opacity_pct == 42.0
    assert job.last_raster_frame == frame
    assert job.last_raw_object_key == "some/tile.npz"
    assert job.last_error is None
    timescale.write_raster_frame.assert_awaited_once_with(frame, "some/tile.npz")
    timescale.write_observation.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_once_records_error_and_never_raises():
    datasource = AsyncMock()
    datasource.fetch_latest.side_effect = RuntimeError("boom")
    raw_storage = AsyncMock()
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")
    await job.run_once()  # must not raise

    assert job.last_observation is None
    assert job.last_error == "RuntimeError: boom"
    assert job.last_fetched_at is not None


@pytest.mark.asyncio
async def test_run_once_records_storage_failure_separately_from_fetch():
    frame = _make_frame(datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc))
    raw = _make_raw(np.full((7, 5), 0.4))

    datasource = AsyncMock()
    datasource.fetch_latest.return_value = (raw, frame)
    raw_storage = AsyncMock()
    raw_storage.put_raw.side_effect = ConnectionError("no minio")
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")
    await job.run_once()

    assert job.last_observation is None
    assert "no minio" in job.last_error


@pytest.mark.asyncio
async def test_first_frame_has_no_motion():
    frame = _make_frame(datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc))
    raw = _make_raw(np.full((7, 5), 0.4))

    datasource = AsyncMock()
    datasource.fetch_latest.return_value = (raw, frame)
    raw_storage = AsyncMock()
    raw_storage.put_raw.return_value = "some/tile.npz"
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")
    await job.run_once()

    assert job.last_raster_frame.motion_speed_kmh is None
    assert job.last_raster_frame.motion_direction_deg is None


@pytest.mark.asyncio
async def test_second_frame_gets_a_motion_estimate():
    base = np.random.default_rng(0).normal(size=(7, 5))
    shifted = np.roll(base, shift=(1, 0), axis=(0, 1))

    t0 = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=10)

    datasource = AsyncMock()
    raw_storage = AsyncMock()
    raw_storage.put_raw.return_value = "some/tile.npz"
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")

    datasource.fetch_latest.return_value = (_make_raw(base), _make_frame(t0))
    await job.run_once()
    assert job.last_raster_frame.motion_speed_kmh is None

    datasource.fetch_latest.return_value = (_make_raw(shifted), _make_frame(t1))
    await job.run_once()

    assert job.last_raster_frame.motion_speed_kmh is not None
    assert job.last_raster_frame.motion_speed_kmh > 0
    assert job.last_raster_frame.motion_direction_deg is not None


@pytest.mark.asyncio
async def test_motion_skipped_and_ingestion_still_succeeds_on_shape_mismatch():
    t0 = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=10)

    datasource = AsyncMock()
    raw_storage = AsyncMock()
    raw_storage.put_raw.return_value = "some/tile.npz"
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")

    datasource.fetch_latest.return_value = (_make_raw(np.zeros((7, 5))), _make_frame(t0))
    await job.run_once()

    # simulate a reconfigured bbox producing a different tile shape
    body = serialize_raster(np.zeros((3, 3)), np.zeros((3, 3)), np.zeros((3, 3)), np.zeros((3, 3)))
    mismatched_raw = RawFetchResult(url="mock://x", fetched_at=datetime.now(timezone.utc), content_type="application/octet-stream", body=body)
    datasource.fetch_latest.return_value = (mismatched_raw, _make_frame(t1))
    await job.run_once()

    assert job.last_error is None  # must not fail the cycle
    assert job.last_raster_frame.motion_speed_kmh is None
