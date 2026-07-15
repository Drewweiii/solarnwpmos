from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Enforces a minimum wall-clock interval between outbound requests. Identical to
    ingestion.himawari/nwp's own RateLimiter - kept as a per-module copy (not a shared
    dependency) so each ingestion module stays independently installable/deployable,
    matching this repo's existing convention (see nwp_ingestion.compliance).

    No RobotsChecker: NASA POWER's daily point API is a documented public API, not a
    scraped website - see README "Data source & ToS" for the check performed before
    this module was written (note: not live-verified from this dev sandbox, whose
    egress policy blocks power.larc.nasa.gov outright - see that section).
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
