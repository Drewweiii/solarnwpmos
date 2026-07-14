from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import numpy as np
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .datasource import CloudDataSource, deserialize_raster
from .geolocation import NONG_FAB_COL_SPACING_KM, NONG_FAB_PIXEL, NONG_FAB_ROW_SPACING_KM, CalibratedPixel
from .metrics import FETCH_DURATION_SECONDS, FETCH_FAILURE_TOTAL, FETCH_SUCCESS_TOTAL, LAST_CLOUD_INDEX, LAST_CLOUD_OPACITY_PCT
from .motion import estimate_cloud_motion
from .schemas import CloudObservation, CloudRasterFrame
from .storage import RawObjectStorage, TimescaleWriter

logger = logging.getLogger(__name__)


class IngestionJob:
    """One fetch -> validate -> store cycle. Validation already happened inside the
    datasource (it only returns a CloudRasterFrame once Pydantic accepts it), so this
    class orchestrates: cloud-motion estimation against the previous cycle's tile,
    storage (raster to MinIO + TimescaleDB), and a derived single-point observation
    for simple consumers.

    Keeps the outcome of the most recent cycle in memory (last_observation /
    last_raster_frame / last_error / last_fetched_at) purely so a thin read-only API
    (api.py) can expose "what did the worker last see" for interactive verification.
    """

    def __init__(
        self, datasource: CloudDataSource, raw_storage: RawObjectStorage, timescale: TimescaleWriter, source_label: str,
        nong_fab_pixel: CalibratedPixel = NONG_FAB_PIXEL,
        row_spacing_km: float = NONG_FAB_ROW_SPACING_KM, col_spacing_km: float = NONG_FAB_COL_SPACING_KM,
    ):
        self._datasource = datasource
        self._raw_storage = raw_storage
        self._timescale = timescale
        self._source_label = source_label
        self._nong_fab_pixel = nong_fab_pixel
        self._row_spacing_km = row_spacing_km
        self._col_spacing_km = col_spacing_km

        self._prev_cloud_probability: np.ndarray | None = None
        self._prev_observed_at: datetime | None = None

        self.last_observation: CloudObservation | None = None
        self.last_raster_frame: CloudRasterFrame | None = None
        self.last_raw_object_key: str | None = None
        self.last_fetched_at: datetime | None = None
        self.last_error: str | None = None

    async def run_once(self) -> None:
        start = time.monotonic()
        try:
            raw, frame = await self._datasource.fetch_latest()
            object_key = await self._raw_storage.put_raw(raw)

            frame = self._with_motion(frame, deserialize_raster(raw.body)["cloud_probability"])
            await self._timescale.write_raster_frame(frame, object_key)

            observation = CloudObservation(
                observed_at=frame.observed_at,
                latitude=self._nong_fab_pixel.latitude,
                longitude=self._nong_fab_pixel.longitude,
                cloud_opacity_pct=frame.nong_fab_cloud_opacity_pct,
                cloud_index=frame.nong_fab_cloud_index,
                source=frame.source,
            )
            await self._timescale.write_observation(observation, object_key)

            LAST_CLOUD_OPACITY_PCT.set(observation.cloud_opacity_pct)
            LAST_CLOUD_INDEX.set(observation.cloud_index)
            FETCH_SUCCESS_TOTAL.labels(source=self._source_label).inc()
            logger.info(
                "ingested cloud tile observed_at=%s shape=(%d,%d) nong_fab_opacity=%.1f nong_fab_index=%.2f "
                "motion_speed_kmh=%s motion_dir_deg=%s object_key=%s",
                frame.observed_at, frame.rows, frame.cols, frame.nong_fab_cloud_opacity_pct, frame.nong_fab_cloud_index,
                frame.motion_speed_kmh, frame.motion_direction_deg, object_key,
            )

            self.last_observation = observation
            self.last_raster_frame = frame
            self.last_raw_object_key = object_key
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 - a scheduled job must never crash the process
            FETCH_FAILURE_TOTAL.labels(source=self._source_label, reason=type(exc).__name__).inc()
            logger.exception("ingestion cycle failed: %s", exc)
            self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            self.last_fetched_at = datetime.now(timezone.utc)
            FETCH_DURATION_SECONDS.labels(source=self._source_label).observe(time.monotonic() - start)

    def _with_motion(self, frame: CloudRasterFrame, cloud_probability: np.ndarray) -> CloudRasterFrame:
        """Estimates cloud motion against the previous cycle's tile (in-memory, not
        re-read from storage). Null on the first frame of a run, a shape mismatch
        (e.g. bbox reconfigured mid-run), or a non-positive interval (e.g. a
        re-fetch of the same slot) - never fatal to the ingestion cycle.
        """
        prev, prev_observed_at = self._prev_cloud_probability, self._prev_observed_at
        self._prev_cloud_probability, self._prev_observed_at = cloud_probability, frame.observed_at

        if prev is None or prev.shape != cloud_probability.shape:
            return frame

        interval_minutes = (frame.observed_at - prev_observed_at).total_seconds() / 60
        if interval_minutes <= 0:
            return frame

        try:
            motion = estimate_cloud_motion(prev, cloud_probability, self._row_spacing_km, self._col_spacing_km, interval_minutes)
        except Exception:  # noqa: BLE001 - motion is a bonus signal, must not break ingestion
            logger.exception("cloud motion estimation failed; continuing without it")
            return frame

        return frame.model_copy(update={"motion_speed_kmh": motion.speed_kmh, "motion_direction_deg": motion.direction_deg})


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
