from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Enforces a minimum wall-clock interval between outbound requests, independent
    of the scheduler. Mirrors himawari_ingestion.compliance.RateLimiter.

    No RobotsChecker here (unlike Module 1's original scraping target): NOMADS's
    GFS filter service is a documented open-data API, not a scraped website - verified
    2026-07-14 that nomads.ncep.noaa.gov/robots.txt is a plain 404 (no rules to
    respect either way) and that nomads.ncep.noaa.gov/info.php officially documents
    and endorses this exact filter/subset endpoint. See README "Data source & ToS".
    """

    def __init__(self, min_interval_seconds: float):
        self._min_interval = min_interval_seconds
        self._last_call: float | None = None
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._last_call is not None:
                elapsed = now - self._last_call
                remaining = self._min_interval - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_call = time.monotonic()
