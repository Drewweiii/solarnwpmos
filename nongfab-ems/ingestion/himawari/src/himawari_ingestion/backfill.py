"""Historical backfill orchestration: loops HimawariAHICloudSource.fetch_at() over
the last `backfill_lookback_days` to seed cold-start training history - mirrors
nwp_ingestion.backfill's design (same "why a separate one-shot module, not
scheduler.py" reasoning: backfill is bounded, the live poll loop isn't).

Samples every `backfill_cadence_minutes` (default hourly) rather than every native
10-min slot: a 30-day backfill at 10-min cadence is 4320 fetches, impractical for a
boot-time job; hourly is 720, still enough to give Module 4's lag/EMA features (and
the minute-ahead CNN-LSTM's short lookback, once enough *recent* live-polled 10-min
data has accumulated on top of this) a real multi-week baseline instead of nothing.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx

from .compliance import RateLimiter
from .config import Settings
from .datasource import HimawariAHICloudSource
from .geolocation import NONG_FAB_BBOX, NONG_FAB_PIXEL, CalibratedBBox, CalibratedPixel
from .schemas import CloudRasterFrame, RawFetchResult

logger = logging.getLogger(__name__)


def historical_slots(end: datetime, lookback_days: int, cadence_minutes: int) -> list[datetime]:
    """Every `cadence_minutes`-spaced timestamp in [end - lookback_days, end],
    oldest first, aligned to :00 seconds - the set of anchors backfill_range()
    will attempt to fetch (each resolved to its nearest published 10-min slot by
    HimawariAHICloudSource._find_object_key_at_or_before).
    """
    start = (end - timedelta(days=lookback_days)).replace(second=0, microsecond=0)
    out = []
    cursor = start
    step = timedelta(minutes=cadence_minutes)
    while cursor <= end:
        out.append(cursor)
        cursor += step
    return out


async def backfill_range(
    settings: Settings,
    client: httpx.AsyncClient,
    rate_limiter: RateLimiter,
    lookback_days: int | None = None,
    cadence_minutes: int | None = None,
    bbox: CalibratedBBox = NONG_FAB_BBOX,
    pixel: CalibratedPixel = NONG_FAB_PIXEL,
) -> AsyncIterator[tuple[RawFetchResult, CloudRasterFrame] | None]:
    """Yields one (raw, frame) pair per successfully-fetched historical slot, in
    chronological order, or None for a slot that failed after retries (logged, not
    raised - same per-slot failure isolation as nwp_ingestion.backfill.backfill_range).
    """
    source = HimawariAHICloudSource(settings, client, rate_limiter, bbox=bbox, pixel=pixel)
    days = lookback_days if lookback_days is not None else settings.backfill_lookback_days
    cadence = cadence_minutes if cadence_minutes is not None else settings.backfill_cadence_minutes
    end = datetime.now(timezone.utc) - timedelta(minutes=settings.publish_latency_minutes)

    slots = historical_slots(end, days, cadence)
    logger.info("himawari backfill: %d candidate slots over %d days at %d-min cadence", len(slots), days, cadence)

    for anchor in slots:
        try:
            raw, frame = await source.fetch_at(anchor)
            yield raw, frame
        except Exception:
            logger.warning("himawari backfill: slot %s failed, skipping", anchor.isoformat(), exc_info=True)
            yield None
