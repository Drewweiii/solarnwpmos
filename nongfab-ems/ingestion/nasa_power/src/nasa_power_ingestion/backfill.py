"""Historical backfill: unlike ingestion/nwp and ingestion/himawari (many small
fetches, one per cycle/slot), NASA POWER's daily point API accepts a full date range
in a *single* request - so backfilling `backfill_lookback_days` is one fetch_range()
call, not a loop. Kept as its own module for interface symmetry with the other two
ingestion modules' backfill.py (same "seeds cold-start history" role), not because
the mechanics need it.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from .compliance import RateLimiter
from .config import Settings
from .datasource import DataUnavailableError, NASAPowerDataSource
from .schemas import RawFetchResult, UVObservation

logger = logging.getLogger(__name__)


async def backfill_range(
    settings: Settings,
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    lookback_days: int | None = None,
    target_latitude: float | None = None,
    target_longitude: float | None = None,
) -> tuple[RawFetchResult, list[UVObservation]] | None:
    """Fetches every available day in [today - lookback_days - publish_latency_days,
    today - publish_latency_days] (NASA POWER's most recent ~publish_latency_days
    aren't published yet - see config.Settings.publish_latency_days). Returns None
    (logged, not raised) if the whole range comes back empty, mirroring the
    per-item failure isolation of the other two modules' backfill_range() - a
    missing UV history shouldn't abort ingestion of NWP/cloud data.
    """
    days = lookback_days if lookback_days is not None else settings.backfill_lookback_days
    end: date = (datetime.now(timezone.utc) - timedelta(days=settings.publish_latency_days)).date()
    start: date = end - timedelta(days=days)

    source = NASAPowerDataSource(settings, client, rate_limiter, target_latitude, target_longitude)
    logger.info("nasa_power backfill: requesting [%s, %s] (%d days)", start, end, days)

    try:
        return await source.fetch_range(start, end)
    except DataUnavailableError:
        logger.warning("nasa_power backfill: no usable data in [%s, %s]", start, end, exc_info=True)
        return None
