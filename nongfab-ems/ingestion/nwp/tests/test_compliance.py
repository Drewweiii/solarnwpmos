import time

import pytest

from nwp_ingestion.compliance import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_enforces_minimum_interval():
    limiter = RateLimiter(min_interval_seconds=0.2)
    start = time.monotonic()
    await limiter.wait()
    await limiter.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.2


@pytest.mark.asyncio
async def test_rate_limiter_does_not_wait_when_interval_already_elapsed():
    limiter = RateLimiter(min_interval_seconds=0.05)
    await limiter.wait()
    time.sleep(0.1)

    start = time.monotonic()
    await limiter.wait()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05
