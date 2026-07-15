from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from nasa_power_ingestion.backfill import backfill_range
from nasa_power_ingestion.compliance import RateLimiter
from nasa_power_ingestion.datasource import DataUnavailableError, NASAPowerDataSource


@pytest.mark.asyncio
async def test_backfill_range_requests_lookback_window_ending_at_publish_latency(settings):
    settings.source_mode = "http"
    settings.publish_latency_days = 3
    captured = {}

    async def fake_fetch_range(self, start, end):
        captured["start"], captured["end"] = start, end
        return object(), ["ok"]

    async with httpx.AsyncClient() as client:
        with patch.object(NASAPowerDataSource, "fetch_range", new=fake_fetch_range):
            result = await backfill_range(settings, client, RateLimiter(0.0), lookback_days=30)

    assert result is not None
    expected_end = (datetime.now(timezone.utc) - timedelta(days=3)).date()
    assert captured["end"] == expected_end
    assert captured["start"] == expected_end - timedelta(days=30)


@pytest.mark.asyncio
async def test_backfill_range_returns_none_when_entirely_unavailable(settings):
    settings.source_mode = "http"

    async with httpx.AsyncClient() as client:
        with patch.object(NASAPowerDataSource, "fetch_range", new=AsyncMock(side_effect=DataUnavailableError("no data"))):
            result = await backfill_range(settings, client, RateLimiter(0.0), lookback_days=30)

    assert result is None
