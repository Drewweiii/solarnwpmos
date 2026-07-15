import os
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from nasa_power_ingestion.compliance import RateLimiter
from nasa_power_ingestion.config import Settings
from nasa_power_ingestion.datasource import (
    DataUnavailableError,
    MockUVDataSource,
    NASAPowerDataSource,
    _parse_power_response,
    build_datasource,
)

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "sample_power_response.json"


def test_parse_power_response_extracts_daily_values_skipping_missing_sentinel():
    body = FIXTURE_PATH.read_bytes()
    observations = _parse_power_response(body, "ALLSKY_SFC_UV_INDEX", 12.71, 101.15, "test")

    assert len(observations) == 10
    assert observations[0].observation_date == date(2026, 7, 1)
    assert observations[0].uv_index == pytest.approx(8.9)
    assert observations == sorted(observations, key=lambda o: o.observation_date)


@pytest.mark.asyncio
async def test_mock_datasource_returns_fixture_backed_observations(settings):
    source = MockUVDataSource(settings, fixture_path=FIXTURE_PATH)
    raw, observations = await source.fetch_range(date(2026, 8, 1), date(2026, 8, 5))

    assert raw.content_type == "application/json"
    assert len(observations) == 5
    assert observations[0].observation_date == date(2026, 8, 1)
    assert observations[-1].observation_date == date(2026, 8, 5)
    assert all(o.source == "mock-fixture" for o in observations)


@pytest.mark.asyncio
async def test_build_datasource_mock_mode(settings):
    source = build_datasource(settings)
    assert isinstance(source, MockUVDataSource)


def test_build_datasource_http_mode_requires_client_and_rate_limiter(settings):
    settings.source_mode = "http"
    with pytest.raises(ValueError):
        build_datasource(settings)


@pytest.mark.asyncio
@respx.mock
async def test_nasa_power_source_fetches_and_parses_real_shaped_response(settings):
    settings.source_mode = "http"
    respx.get(url__startswith=settings.base_url).mock(return_value=httpx.Response(200, content=FIXTURE_PATH.read_bytes()))

    async with httpx.AsyncClient() as client:
        source = NASAPowerDataSource(settings, client, RateLimiter(0.0), target_latitude=12.68337, target_longitude=101.11987)
        raw, observations = await source.fetch_range(date(2026, 7, 1), date(2026, 7, 10))

    assert len(observations) == 10
    assert all(o.source == NASAPowerDataSource.SOURCE_NAME for o in observations)
    assert all(o.latitude == 12.68337 and o.longitude == 101.11987 for o in observations)


@pytest.mark.asyncio
@respx.mock
async def test_nasa_power_source_raises_when_range_is_entirely_missing(settings):
    settings.source_mode = "http"
    empty_body = b'{"properties": {"parameter": {"ALLSKY_SFC_UV_INDEX": {"20260701": -999.0}}}}'
    respx.get(url__startswith=settings.base_url).mock(return_value=httpx.Response(200, content=empty_body))

    async with httpx.AsyncClient() as client:
        source = NASAPowerDataSource(settings, client, RateLimiter(0.0))
        with pytest.raises(DataUnavailableError):
            await source.fetch_range(date(2026, 7, 1), date(2026, 7, 1))


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("NASA_POWER_LIVE_TEST") != "1",
    reason="set NASA_POWER_LIVE_TEST=1 to hit the real NASA POWER API - NOT reachable from this dev sandbox (see README)",
)
@pytest.mark.asyncio
async def test_nasa_power_datasource_against_real_api():
    from datetime import timedelta

    settings = Settings(source_mode="http")
    end = datetime.now(timezone.utc).date() - timedelta(days=settings.publish_latency_days)
    start = end - timedelta(days=5)
    async with httpx.AsyncClient() as client:
        source = NASAPowerDataSource(settings, client, RateLimiter(0.5))
        raw, observations = await source.fetch_range(start, end)

    assert len(observations) > 0
    assert all(0 <= o.uv_index <= 25 for o in observations)
