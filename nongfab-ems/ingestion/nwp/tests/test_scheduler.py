from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from nwp_ingestion.schemas import NWPForecastPoint, RawFetchResult
from nwp_ingestion.scheduler import IngestionJob, build_scheduler


def _make_point(valid_time: datetime, ssrd: float = 500.0, temp_c: float = 28.0) -> NWPForecastPoint:
    return NWPForecastPoint(
        issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc),
        valid_time=valid_time,
        latitude=12.71, longitude=101.15,
        ssrd_w_m2=ssrd, temp2m_c=temp_c, wind10m_u_ms=1.0, wind10m_v_ms=0.5,
        relative_humidity_pct=70.0, source="mock-fixture",
    )


def _make_raw(fhour: int) -> RawFetchResult:
    return RawFetchResult(
        url="mock://x", fetched_at=datetime.now(timezone.utc), content_type="application/x-grib2", body=b"x",
        issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc), forecast_hour=fhour,
    )


@pytest.mark.asyncio
async def test_run_once_records_all_points_and_writes_each():
    pairs = [
        (_make_raw(1), _make_point(datetime(2026, 7, 14, 1, tzinfo=timezone.utc), ssrd=100.0)),
        (_make_raw(2), _make_point(datetime(2026, 7, 14, 2, tzinfo=timezone.utc), ssrd=200.0)),
    ]
    datasource = AsyncMock()
    datasource.fetch_latest_cycle.return_value = pairs
    raw_storage = AsyncMock()
    raw_storage.put_raw.return_value = "some/key.grib2"
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")
    await job.run_once()

    assert len(job.last_points) == 2
    assert job.last_cycle_issue_time == datetime(2026, 7, 14, 0, tzinfo=timezone.utc)
    assert job.last_error is None
    assert timescale.write_forecast_point.await_count == 2
    assert raw_storage.put_raw.await_count == 2


@pytest.mark.asyncio
async def test_run_once_records_error_and_never_raises():
    datasource = AsyncMock()
    datasource.fetch_latest_cycle.side_effect = RuntimeError("boom")
    raw_storage = AsyncMock()
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")
    await job.run_once()  # must not raise

    assert job.last_points == []
    assert job.last_error == "RuntimeError: boom"
    assert job.last_fetched_at is not None


@pytest.mark.asyncio
async def test_run_once_records_storage_failure_separately_from_fetch():
    pairs = [(_make_raw(1), _make_point(datetime(2026, 7, 14, 1, tzinfo=timezone.utc)))]
    datasource = AsyncMock()
    datasource.fetch_latest_cycle.return_value = pairs
    raw_storage = AsyncMock()
    raw_storage.put_raw.side_effect = ConnectionError("no minio")
    timescale = AsyncMock()

    job = IngestionJob(datasource, raw_storage, timescale, "mock")
    await job.run_once()

    assert job.last_points == []
    assert "no minio" in job.last_error


def test_build_scheduler_triggers_at_publish_latency_offset_from_each_cycle():
    job = IngestionJob(AsyncMock(), AsyncMock(), AsyncMock(), "mock")
    scheduler = build_scheduler(job, gfs_cycles=[0, 6, 12, 18], publish_latency_minutes=240)

    trigger = scheduler.get_job("nwp_ingestion").trigger
    field_strs = {f.name: str(f) for f in trigger.fields}
    # 240min = 4h offset -> 00+4=04, 06+4=10, 12+4=16, 18+4=22
    assert field_strs["hour"] == "4,10,16,22"
    assert field_strs["minute"] == "0"
