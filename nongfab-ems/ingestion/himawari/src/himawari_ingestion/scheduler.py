from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .datasource import CloudDataSource
from .metrics import FETCH_DURATION_SECONDS, FETCH_FAILURE_TOTAL, FETCH_SUCCESS_TOTAL, LAST_CLOUD_INDEX, LAST_CLOUD_OPACITY_PCT
from .schemas import CloudObservation
from .storage import RawObjectStorage, TimescaleWriter

logger = logging.getLogger(__name__)


class IngestionJob:
    """One fetch -> validate -> store cycle. Validation already happened inside the
    datasource (it only returns a CloudObservation once Pydantic accepts it), so this
    class just orchestrates storage and observability.

    Keeps the outcome of the most recent cycle in memory (last_observation /
    last_error / last_fetched_at) purely so a thin read-only API (api.py) can expose
    "what did the worker last see" for interactive verification - the scheduler
    itself only needs the try/except/finally below.
    """

    def __init__(self, datasource: CloudDataSource, raw_storage: RawObjectStorage, timescale: TimescaleWriter, source_label: str):
        self._datasource = datasource
        self._raw_storage = raw_storage
        self._timescale = timescale
        self._source_label = source_label

        self.last_observation: CloudObservation | None = None
        self.last_raw_object_key: str | None = None
        self.last_fetched_at: datetime | None = None
        self.last_error: str | None = None

    async def run_once(self) -> None:
        start = time.monotonic()
        try:
            raw, observation = await self._datasource.fetch_latest()
            object_key = await self._raw_storage.put_raw(raw)
            await self._timescale.write_observation(observation, object_key)

            LAST_CLOUD_OPACITY_PCT.set(observation.cloud_opacity_pct)
            LAST_CLOUD_INDEX.set(observation.cloud_index)
            FETCH_SUCCESS_TOTAL.labels(source=self._source_label).inc()
            logger.info(
                "ingested cloud_obs observed_at=%s opacity=%.1f index=%.2f object_key=%s",
                observation.observed_at, observation.cloud_opacity_pct, observation.cloud_index, object_key,
            )

            self.last_observation = observation
            self.last_raw_object_key = object_key
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 - a scheduled job must never crash the process
            FETCH_FAILURE_TOTAL.labels(source=self._source_label, reason=type(exc).__name__).inc()
            logger.exception("ingestion cycle failed: %s", exc)
            self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            self.last_fetched_at = datetime.now(timezone.utc)
            FETCH_DURATION_SECONDS.labels(source=self._source_label).observe(time.monotonic() - start)


def build_scheduler(job: IngestionJob, poll_interval_minutes: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        job.run_once,
        trigger=CronTrigger(minute=f"*/{poll_interval_minutes}"),
        id="himawari_ingestion",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
