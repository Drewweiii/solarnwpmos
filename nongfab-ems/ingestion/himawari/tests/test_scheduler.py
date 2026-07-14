from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from himawari_ingestion.scheduler import IngestionJob
from himawari_ingestion.schemas import CloudObservation, RawFetchResult


def _make_observation() -> CloudObservation:
    return CloudObservation(
        observed_at=datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc),
        latitude=12.71,
        longitude=101.15,
        cloud_opacity_pct=42.0,
        cloud_index=0.5,
        source="mock-fixture",
    )


@pytest.mark.asyncio
async def test_run_once_records_last_observation_on_success():
    observation = _make_observation()
    raw = RawFetchResult(url="mock://x", fetched_at=datetime.now(timezone.utc), content_type="application/json", body=b"{}")

    datasource = AsyncMock()
    datasource.fetch_latest.return_value = (raw, observation)
    raw_storage = AsyncMock()
    raw_storage.put_raw.return_value = "some/key.bin"
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")
    await job.run_once()

    assert job.last_observation == observation
    assert job.last_raw_object_key == "some/key.bin"
    assert job.last_error is None
    assert job.last_fetched_at is not None
    timescale.write_observation.assert_awaited_once_with(observation, "some/key.bin")


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
    observation = _make_observation()
    raw = RawFetchResult(url="mock://x", fetched_at=datetime.now(timezone.utc), content_type="application/json", body=b"{}")

    datasource = AsyncMock()
    datasource.fetch_latest.return_value = (raw, observation)
    raw_storage = AsyncMock()
    raw_storage.put_raw.side_effect = ConnectionError("no minio")
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")
    await job.run_once()

    assert job.last_observation is None  # only set once the whole cycle (incl. storage) succeeds
    assert "no minio" in job.last_error
