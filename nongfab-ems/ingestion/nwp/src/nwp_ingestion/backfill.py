"""Historical backfill orchestration: loops S3GfsBackfillDataSource.fetch_cycle()
over the last `backfill_lookback_days` to seed cold-start training history (see
README "Backfill"). Kept separate from scheduler.py (which drives the *live*
polling loop) since backfill is a one-shot bounded job, not a recurring one.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx

from .compliance import RateLimiter
from .config import Settings
from .datasource import S3GfsBackfillDataSource
from .schemas import NWPForecastPoint, RawFetchResult

logger = logging.getLogger(__name__)


def historical_cycles(end: datetime, lookback_days: int, cycles: list[int]) -> list[datetime]:
    """Every (date, cycle) issue_time in [end - lookback_days, end], oldest first -
    the set of GFS cycles backfill_range() will attempt to fetch.
    """
    start = (end - timedelta(days=lookback_days)).replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    cursor = start
    while cursor <= end:
        for hour in sorted(cycles):
            candidate = cursor.replace(hour=hour, minute=0, second=0, microsecond=0)
            if start <= candidate <= end:
                out.append(candidate)
        cursor += timedelta(days=1)
    return out


async def backfill_range(
    settings: Settings,
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    lookback_days: int | None = None,
    target_latitude: float | None = None,
    target_longitude: float | None = None,
    end: datetime | None = None,
) -> AsyncIterator[tuple[RawFetchResult, NWPForecastPoint] | None]:
    """Yields one (raw, point) pair per successfully-fetched historical cycle, in
    chronological order, or None for a cycle that failed after retries (logged, not
    raised - a gap in a 30-day backfill shouldn't abort the whole job; the caller
    decides whether too many gaps means the backfill itself failed).

    `end` (defaults to "now", minus `publish_latency_minutes`) is the anchor
    `historical_cycles()` treats as "the latest cycle that could plausibly have
    published yet" - overridable so callers with a real-time dependency (this
    default) are still deterministically testable; every real caller in this repo
    leaves it as None and gets the original wall-clock behavior.
    """
    source = S3GfsBackfillDataSource(settings, client, rate_limiter, target_latitude, target_longitude)
    days = lookback_days if lookback_days is not None else settings.backfill_lookback_days
    end = (end if end is not None else datetime.now(timezone.utc)) - timedelta(minutes=settings.publish_latency_minutes)

    cycles = historical_cycles(end, days, settings.gfs_cycles)
    logger.info("nwp backfill: %d candidate cycles over %d days", len(cycles), days)

    for issue_time in cycles:
        try:
            raw, point = await source.fetch_cycle(issue_time, settings.backfill_forecast_hour)
            yield raw, point
        except Exception:
            logger.warning("nwp backfill: cycle %s failed, skipping", issue_time.isoformat(), exc_info=True)
            yield None
