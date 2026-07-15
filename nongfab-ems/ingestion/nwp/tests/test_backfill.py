import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from nwp_ingestion.backfill import backfill_range, historical_cycles
from nwp_ingestion.compliance import RateLimiter
from nwp_ingestion.config import Settings
from nwp_ingestion.datasource import S3GfsBackfillDataSource


def test_historical_cycles_covers_every_configured_cycle_hour_across_the_window():
    end = datetime(2026, 7, 15, 3, 0, tzinfo=timezone.utc)
    cycles = historical_cycles(end, lookback_days=2, cycles=[0, 6, 12, 18])

    assert cycles[0] == datetime(2026, 7, 13, 0, 0, tzinfo=timezone.utc)
    assert cycles[-1] == datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)
    assert all(c.hour in (0, 6, 12, 18) for c in cycles)
    assert cycles == sorted(cycles)  # chronological order
    # 2 full days (13th, 14th) x 4 cycles + the 15th's 00Z only (anchor is 03:00, so
    # 06/12/18 on the 15th are in the future relative to `end` and correctly excluded)
    assert len(cycles) == 9


def test_historical_cycles_zero_lookback_returns_cycles_up_to_end_only():
    end = datetime(2026, 7, 15, 3, 0, tzinfo=timezone.utc)
    cycles = historical_cycles(end, lookback_days=0, cycles=[0, 6, 12, 18])
    assert cycles == [datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)]


@pytest.mark.asyncio
async def test_backfill_range_yields_one_pair_per_cycle_in_order():
    settings = Settings(source_mode="http", gfs_cycles=[0, 12], publish_latency_minutes=0)
    fake_points = [object(), object()]

    async def fake_fetch_cycle(issue_time, forecast_hour):
        return object(), fake_points[issue_time.hour // 12]

    async with httpx.AsyncClient() as client:
        with patch.object(S3GfsBackfillDataSource, "fetch_cycle", new=AsyncMock(side_effect=fake_fetch_cycle)):
            results = [
                r
                async for r in backfill_range(settings, client, RateLimiter(0.0), lookback_days=0)
            ]

    assert len(results) == 2  # cycles [0, 12] on the anchor day
    assert all(r is not None for r in results)
    assert [r[1] for r in results] == fake_points


@pytest.mark.asyncio
async def test_backfill_range_yields_none_for_a_failed_cycle_and_continues():
    settings = Settings(source_mode="http", gfs_cycles=[0, 12], publish_latency_minutes=0)

    async def flaky_fetch_cycle(issue_time, forecast_hour):
        if issue_time.hour == 0:
            raise RuntimeError("simulated NOAA fetch failure")
        return object(), "ok"

    async with httpx.AsyncClient() as client:
        with patch.object(S3GfsBackfillDataSource, "fetch_cycle", new=AsyncMock(side_effect=flaky_fetch_cycle)):
            results = [
                r
                async for r in backfill_range(settings, client, RateLimiter(0.0), lookback_days=0)
            ]

    assert results[0] is None
    assert results[1][1] == "ok"


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("NWP_LIVE_TEST") != "1", reason="set NWP_LIVE_TEST=1 to hit the real AWS GFS bucket")
@pytest.mark.asyncio
async def test_backfill_range_against_real_aws_bucket_small_window():
    """2-day real backfill (8 cycles) against the live NOAA AWS bucket - a small,
    fast proxy for the full 30-day production backfill, run here to prove the whole
    loop (not just one fetch_cycle call) actually works end to end.
    """
    settings = Settings(source_mode="http")
    async with httpx.AsyncClient() as client:
        results = [
            r
            async for r in backfill_range(
                settings, client, RateLimiter(0.5), lookback_days=2, target_latitude=12.68337, target_longitude=101.11987
            )
        ]

    assert len(results) >= 6  # allow a couple of gaps, but most of 8 candidate cycles should succeed
    succeeded = [r for r in results if r is not None]
    assert len(succeeded) >= 6
    for _, point in succeeded:
        assert 0 <= point.ssrd_w_m2 <= 1500
        assert -30 <= point.temp2m_c <= 60
