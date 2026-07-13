import json

import httpx
import pytest
import respx

from himawari_ingestion.compliance import RateLimiter, RobotsChecker
from himawari_ingestion.datasource import ComplianceError, HimawariOptemisSource, MockCloudDataSource, build_datasource

BASE_URL = "https://himawari.optemis.space"


@pytest.mark.asyncio
async def test_mock_datasource_returns_observation_at_configured_site(settings):
    source = MockCloudDataSource(settings, jitter=False)
    raw, observation = await source.fetch_latest()

    assert observation.latitude == settings.site_latitude
    assert observation.longitude == settings.site_longitude
    assert observation.source == "mock-fixture"
    assert raw.content_type == "application/json"
    assert json.loads(raw.body)["cloud_opacity"] == observation.cloud_opacity_pct


@pytest.mark.asyncio
async def test_build_datasource_mock_mode(settings):
    source = build_datasource(settings)
    assert isinstance(source, MockCloudDataSource)


@pytest.mark.asyncio
@respx.mock
async def test_http_source_fetches_and_parses(settings):
    settings.source_mode = "http"
    respx.get(f"{BASE_URL}/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n"))
    respx.get(f"{BASE_URL}{settings.api_path}").mock(
        return_value=httpx.Response(
            200,
            json={"timestamp": "2024-06-01T03:00:00Z", "latitude": 12.71, "longitude": 101.15, "cloud_opacity": 30.0, "cloud_index": 0.4},
        )
    )

    async with httpx.AsyncClient() as client:
        robots = RobotsChecker(settings.base_url, settings.user_agent, timeout=2.0, cache_ttl=60.0)
        rate_limiter = RateLimiter(0.0)
        source = HimawariOptemisSource(settings, client, robots, rate_limiter)
        raw, observation = await source.fetch_latest()

    assert observation.cloud_opacity_pct == 30.0
    assert observation.cloud_index == 0.4
    assert observation.source == "himawari.optemis.space"


@pytest.mark.asyncio
@respx.mock
async def test_http_source_blocked_by_robots_disallow(settings):
    settings.source_mode = "http"
    respx.get(f"{BASE_URL}/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\nDisallow: /\n"))

    async with httpx.AsyncClient() as client:
        robots = RobotsChecker(settings.base_url, settings.user_agent, timeout=2.0, cache_ttl=60.0)
        rate_limiter = RateLimiter(0.0)
        source = HimawariOptemisSource(settings, client, robots, rate_limiter)
        with pytest.raises(ComplianceError):
            await source.fetch_latest()


@pytest.mark.asyncio
@respx.mock
async def test_http_source_retries_then_succeeds(settings):
    settings.source_mode = "http"
    settings.max_retry_attempts = 3
    respx.get(f"{BASE_URL}/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n"))

    route = respx.get(f"{BASE_URL}{settings.api_path}")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(
            200,
            json={"timestamp": "2024-06-01T03:00:00Z", "latitude": 12.71, "longitude": 101.15, "cloud_opacity": 55.0, "cloud_index": 0.6},
        ),
    ]

    async with httpx.AsyncClient() as client:
        robots = RobotsChecker(settings.base_url, settings.user_agent, timeout=2.0, cache_ttl=60.0)
        rate_limiter = RateLimiter(0.0)
        source = HimawariOptemisSource(settings, client, robots, rate_limiter)
        raw, observation = await source.fetch_latest()

    assert observation.cloud_opacity_pct == 55.0
    assert route.call_count == 2
