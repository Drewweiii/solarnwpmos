from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .datasource import NWPDataSource
from .metrics import CYCLE_FORECAST_HOURS_TOTAL, FETCH_DURATION_SECONDS, FETCH_FAILURE_TOTAL, FETCH_SUCCESS_TOTAL, LAST_SSRD_W_M2, LAST_TEMP2M_C
from .schemas import NWPForecastPoint
from .storage import RawObjectStorage, TimescaleWriter

logger = logging.getLogger(__name__)


class IngestionJob:
    """One fetch-cycle -> validate -> store run. Each run ingests every configured
    forecast hour of the most recently published GFS cycle (not a single point in
    time), since the whole point is to hand Module 4 a full future-regressor curve.
    """

    def __init__(self, datasource: NWPDataSource, raw_storage: RawObjectStorage, timescale: TimescaleWriter, source_label: str):
        self._datasource = datasource
        self._raw_storage = raw_storage
        self._timescale = timescale
        self._source_label = source_label

        self.last_points: list[NWPForecastPoint] = []
        self.last_cycle_issue_time: datetime | None = None
        self.last_fetched_at: datetime | None = None
        self.last_error: str | None = None

    async def run_once(self) -> None:
        start = time.monotonic()
        try:
            pairs = await self._datasource.fetch_latest_cycle()

            points: list[NWPForecastPoint] = []
            for raw, point in pairs:
                object_key = await self._raw_storage.put_raw(raw)
                await self._timescale.write_forecast_point(point, object_key)
                points.append(point)
                FETCH_SUCCESS_TOTAL.labels(source=self._source_label).inc()

            if points:
                first = min(points, key=lambda p: p.valid_time)
                LAST_SSRD_W_M2.set(first.ssrd_w_m2)
                LAST_TEMP2M_C.set(first.temp2m_c)
                self.last_cycle_issue_time = points[0].issue_time

            CYCLE_FORECAST_HOURS_TOTAL.set(len(points))
            logger.info(
                "ingested GFS cycle issue_time=%s forecast_hours=%d source=%s",
                self.last_cycle_issue_time, len(points), self._source_label,
            )

            self.last_points = points
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 - a scheduled job must never crash the process
            FETCH_FAILURE_TOTAL.labels(source=self._source_label, reason=type(exc).__name__).inc()
            logger.exception("NWP ingestion cycle failed: %s", exc)
            self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            self.last_fetched_at = datetime.now(timezone.utc)
            FETCH_DURATION_SECONDS.labels(source=self._source_label).observe(time.monotonic() - start)


def build_scheduler(job: IngestionJob, gfs_cycles: list[int], publish_latency_minutes: int) -> AsyncIOScheduler:
    """Triggers once per GFS cycle (00/06/12/18 UTC), offset by the expected publish
    latency - not a fixed-interval poll like Module 1's every-10-minutes, since a new
    cycle simply doesn't exist yet between runs.
    """
    trigger_hours = sorted((h + publish_latency_minutes // 60) % 24 for h in gfs_cycles)
    trigger_minute = publish_latency_minutes % 60

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        job.run_once,
        trigger=CronTrigger(hour=",".join(str(h) for h in trigger_hours), minute=trigger_minute),
        id="nwp_ingestion",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
