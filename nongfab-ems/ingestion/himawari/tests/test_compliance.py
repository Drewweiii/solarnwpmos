import time

import httpx
import pytest
import respx

from himawari_ingestion.compliance import RateLimiter, RobotsChecker

BASE_URL = "https://himawari.optemis.space"


@pytest.mark.asyncio
@respx.mock
async def test_allows_path_permitted_by_robots():
    respx.get(f"{BASE_URL}/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /api/\n")
    )
    checker = RobotsChecker(BASE_URL, user_agent="test-agent", timeout=2.0, cache_ttl=60.0)
    async with httpx.AsyncClient() as client:
        decision = await checker.is_allowed("/api/v1/latest", client)
    assert decision.allowed


@pytest.mark.asyncio
@respx.mock
async def test_blocks_path_disallowed_by_robots():
    respx.get(f"{BASE_URL}/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /api/\n")
    )
    checker = RobotsChecker(BASE_URL, user_agent="test-agent", timeout=2.0, cache_ttl=60.0)
    async with httpx.AsyncClient() as client:
        decision = await checker.is_allowed("/api/v1/latest", client)
    assert not decision.allowed


@pytest.mark.asyncio
@respx.mock
async def test_fails_closed_when_robots_unreachable_by_default():
    respx.get(f"{BASE_URL}/robots.txt").mock(return_value=httpx.Response(503))
    checker = RobotsChecker(BASE_URL, user_agent="test-agent", timeout=2.0, cache_ttl=60.0, fail_open=False)
    async with httpx.AsyncClient() as client:
        decision = await checker.is_allowed("/api/v1/latest", client)
    assert not decision.allowed
    assert "unreachable" in decision.reason


@pytest.mark.asyncio
@respx.mock
async def test_fail_open_override_allows_when_robots_unreachable():
    respx.get(f"{BASE_URL}/robots.txt").mock(return_value=httpx.Response(503))
    checker = RobotsChecker(BASE_URL, user_agent="test-agent", timeout=2.0, cache_ttl=60.0, fail_open=True)
    async with httpx.AsyncClient() as client:
        decision = await checker.is_allowed("/api/v1/latest", client)
    assert decision.allowed


@pytest.mark.asyncio
async def test_rate_limiter_enforces_minimum_interval():
    limiter = RateLimiter(min_interval_seconds=0.2)
    start = time.monotonic()
    await limiter.wait()
    await limiter.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.2
