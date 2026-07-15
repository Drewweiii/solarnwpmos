import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from himawari_ingestion.backfill import backfill_range, historical_slots
from himawari_ingestion.compliance import RateLimiter
from himawari_ingestion.datasource import HimawariAHICloudSource


def test_historical_slots_spans_the_window_at_the_given_cadence():
    end = datetime(2026, 7, 15, 3, 0, tzinfo=timezone.utc)
    slots = historical_slots(end, lookback_days=1, cadence_minutes=180)

    assert slots[0] == datetime(2026, 7, 14, 3, 0, tzinfo=timezone.utc)
    assert slots[-1] == end
    assert slots == sorted(slots)
    assert all((s - slots[0]).total_seconds() % (180 * 60) == 0 for s in slots)
    assert len(slots) == 9  # 24h / 3h + 1 (inclusive of both ends)


def test_historical_slots_zero_lookback_returns_just_the_end_timestamp():
    end = datetime(2026, 7, 15, 3, 0, tzinfo=timezone.utc)
    assert historical_slots(end, lookback_days=0, cadence_minutes=30) == [end]


@pytest.mark.asyncio
async def test_backfill_range_yields_one_pair_per_slot_in_chronological_order(settings):
    settings.source_mode = "http"
    fake_frame = object()

    async def fake_fetch_at(anchor):
        return object(), fake_frame

    async with httpx.AsyncClient() as client:
        with patch.object(HimawariAHICloudSource, "fetch_at", new=AsyncMock(side_effect=fake_fetch_at)):
            results = [
                r
                async for r in backfill_range(
                    settings, client, RateLimiter(0.0),
                    lookback_days=0, cadence_minutes=60,
                )
            ]

    assert len(results) == 1
    assert results[0] is not None
    assert results[0][1] is fake_frame


@pytest.mark.asyncio
async def test_backfill_range_continues_past_a_failed_slot(settings):
    settings.source_mode = "http"
    calls = []

    async def flaky_fetch_at(anchor):
        calls.append(anchor)
        if len(calls) == 1:
            raise RuntimeError("simulated NOAA fetch failure")
        return object(), "ok"

    async with httpx.AsyncClient() as client:
        with patch.object(HimawariAHICloudSource, "fetch_at", new=AsyncMock(side_effect=flaky_fetch_at)):
            results = [
                r
                async for r in backfill_range(
                    settings, client, RateLimiter(0.0),
                    lookback_days=1, cadence_minutes=1440,  # 2 slots: start and end of a 1-day window
                )
            ]

    assert len(results) == 2
    assert results[0] is None
    assert results[1] == (results[1][0], "ok") or results[1][1] == "ok"


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_LIVE_NOAA_TESTS") != "1", reason="set RUN_LIVE_NOAA_TESTS=1 to hit the real NOAA S3 bucket")
@pytest.mark.asyncio
async def test_backfill_range_against_real_noaa_bucket_small_window():
    """1-day/3-hourly (9 slots) real backfill against the live NOAA bucket - a small,
    fast proxy for the full 30-day/hourly production backfill, run here to prove the
    whole loop (not just one fetch_at call) actually works end to end.
    """
    from himawari_ingestion.config import Settings

    settings = Settings(source_mode="http", min_seconds_between_requests=0.5)
    async with httpx.AsyncClient() as client:
        results = [
            r
            async for r in backfill_range(settings, client, RateLimiter(0.5), lookback_days=1, cadence_minutes=180)
        ]

    assert len(results) == 9
    succeeded = [r for r in results if r is not None]
    assert len(succeeded) >= 7  # allow a couple of gaps
    for _, frame in succeeded:
        assert 0 <= frame.nong_fab_cloud_opacity_pct <= 100
        assert -0.2 <= frame.nong_fab_cloud_index <= 1.5
