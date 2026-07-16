from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Enforces a minimum wall-clock interval between outbound requests. Identical
    to ingestion.nasa_power/himawari/nwp's own RateLimiter - kept as a per-module
    copy (not a shared dependency) so each ingestion module stays independently
    installable/deployable, matching this repo's existing convention.

    Not much load-bearing here in practice: this module makes one request per
    backfill run (a full year in a single seriescalc call), not a repeated poll
    loop - kept for interface symmetry with the other ingestion modules'
    datasource.py signatures, and in case a future retry/refresh cadence needs it.

    No RobotsChecker: PVGIS's seriescalc endpoint is a documented public API, not a
    scraped website - see README "Data source & ToS" for the check performed
    before this module was written, and the live confirmation (via Railway's
    console, since this dev sandbox's own egress policy blocks
    re.jrc.ec.europa.eu) that it returns real data for Nong Fab's coordinates.
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
