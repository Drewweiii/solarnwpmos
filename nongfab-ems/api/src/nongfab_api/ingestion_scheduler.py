"""Background real-data ingestion, run inside this API process rather than as
separate deployed services - this deployment has no persistent TimescaleDB for
ingestion/nwp's and ingestion/himawari's own storage.py to write to (Railway hosts
only this one container; see root README "Known gaps" and
nongfab_forecast.local_store's own docstring for why a local SQLite-backed store is
used instead). On startup: backfills the last `backfill_lookback_days` if the store
is thin, then runs continuous live polling (Himawari every ~10min, GFS every ~1h)
and periodic retraining for every (zone, horizon) pair - all as plain asyncio
background tasks (no new scheduler dependency; APScheduler is already used by the
standalone ingestion modules for their own separate-deploy path, but this process
just needs a handful of sleep loops, not a cron-like scheduler).

Every network/training call is wrapped so one failure (a source unreachable from
wherever this actually runs - see ingestion/nasa_power/README's own "not reachable
from this dev sandbox" caveat, whose scope elsewhere is unconfirmed) never crashes
the loop or the app - logged and retried next tick.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from nongfab_forecast import training
from nongfab_forecast.local_store import RealDataStore

logger = logging.getLogger(__name__)

ZONES = ("GIS", "ISB", "Jetty")
HORIZONS = ("minute", "hour", "day")


async def run_startup_backfill(store: RealDataStore, lookback_days: int) -> None:
    """Seeds cold-start history once, on boot - a no-op (skipped entirely) for
    a table that already has a reasonable amount of data, so a redeploy with a
    persistent store (API_REAL_DATA_DB_PATH pointed at a real volume) doesn't
    re-backfill from scratch every restart.
    """
    counts = store.counts()

    if counts["nwp_history"] < 100:
        await _backfill_nwp(store, lookback_days)
    else:
        logger.info("startup backfill: nwp_history already has %d rows, skipping", counts["nwp_history"])

    if counts["cloud_history"] < 100:
        await _backfill_himawari(store, lookback_days)
    else:
        logger.info("startup backfill: cloud_history already has %d rows, skipping", counts["cloud_history"])

    if counts["uv_history"] == 0:
        await _backfill_uv(store, lookback_days)


async def _backfill_nwp(store: RealDataStore, lookback_days: int) -> None:
    from nwp_ingestion.backfill import backfill_range
    from nwp_ingestion.compliance import RateLimiter
    from nwp_ingestion.config import Settings

    settings = Settings(source_mode="http")
    logger.info("startup backfill: nwp starting (%d days)", lookback_days)
    n_ok = n_total = 0
    try:
        async with httpx.AsyncClient() as client:
            async for result in backfill_range(settings, client, RateLimiter(settings.min_seconds_between_requests), lookback_days=lookback_days):
                n_total += 1
                if result is not None:
                    _, point = result
                    store.insert_nwp_points([point])
                    n_ok += 1
    except Exception:
        logger.warning("startup backfill: nwp failed partway (%d/%d cycles ingested before the error)", n_ok, n_total, exc_info=True)
        return
    logger.info("startup backfill: nwp done, %d/%d cycles ingested", n_ok, n_total)


def _frame_with_motion(raw, frame, prev_arrays: dict | None, prev_observed_at: datetime | None):
    """Deserializes raw.body's raster and, if a previous frame's arrays are
    available at a matching shape, computes a real cloud motion vector
    (himawari_ingestion.motion.estimate_cloud_motion, FFT phase correlation)
    between them - the "ต่อยอด" extension real_data.py's minute-ahead feature
    layer now consumes (MINUTE_FEATURE_COLS' motion_u_kmh/motion_v_kmh).

    Returns (frame_with_motion_filled_in, this_frame's_own_arrays - pass as
    `prev_arrays` on the *next* call). Motion is left null (frame returned
    unchanged) on the first call in a run, whenever shapes mismatch, or
    whenever the interval isn't positive (a same/out-of-order frame - nothing
    real to diff) - same documented cases as CloudRasterFrame.motion_speed_kmh's
    own docstring. Shared by both the live poll loop and the backfill path
    below so cold-start history gets real (if coarser-cadence) motion too, not
    just data accumulated after this deploys.
    """
    from himawari_ingestion.datasource import deserialize_raster
    from himawari_ingestion.geolocation import NONG_FAB_COL_SPACING_KM, NONG_FAB_ROW_SPACING_KM
    from himawari_ingestion.motion import estimate_cloud_motion

    arrays = deserialize_raster(raw.body)
    if prev_arrays is None or prev_observed_at is None:
        return frame, arrays
    if arrays["cloud_probability"].shape != prev_arrays["cloud_probability"].shape:
        return frame, arrays

    interval_minutes = (frame.observed_at - prev_observed_at).total_seconds() / 60
    if interval_minutes <= 0:
        return frame, arrays

    motion = estimate_cloud_motion(
        prev_arrays["cloud_probability"], arrays["cloud_probability"], NONG_FAB_ROW_SPACING_KM, NONG_FAB_COL_SPACING_KM, interval_minutes
    )
    updated = frame.model_copy(update={"motion_speed_kmh": motion.speed_kmh, "motion_direction_deg": motion.direction_deg})
    return updated, arrays


async def _backfill_himawari(store: RealDataStore, lookback_days: int) -> None:
    from himawari_ingestion.backfill import backfill_range
    from himawari_ingestion.compliance import RateLimiter
    from himawari_ingestion.config import Settings

    settings = Settings(source_mode="http")
    logger.info("startup backfill: himawari starting (%d days)", lookback_days)
    n_ok = n_total = 0
    prev_arrays: dict | None = None
    prev_observed_at: datetime | None = None
    try:
        async with httpx.AsyncClient() as client:
            async for result in backfill_range(settings, client, RateLimiter(settings.min_seconds_between_requests), lookback_days=lookback_days):
                n_total += 1
                if result is not None:
                    raw, frame = result
                    frame, prev_arrays = _frame_with_motion(raw, frame, prev_arrays, prev_observed_at)
                    prev_observed_at = frame.observed_at
                    store.insert_cloud_frames([frame])
                    n_ok += 1
    except Exception:
        logger.warning("startup backfill: himawari failed partway (%d/%d slots ingested before the error)", n_ok, n_total, exc_info=True)
        return
    logger.info("startup backfill: himawari done, %d/%d slots ingested", n_ok, n_total)


async def _backfill_uv(store: RealDataStore, lookback_days: int) -> None:
    """Best-effort: NASA POWER's real endpoint has never been reached from any
    environment this repo was built in (see ingestion/nasa_power/README's "Data
    source & ToS") - a failure here is expected in some deployments and must
    never take down the rest of ingestion.
    """
    from nasa_power_ingestion.backfill import backfill_range
    from nasa_power_ingestion.compliance import RateLimiter
    from nasa_power_ingestion.config import Settings

    settings = Settings(source_mode="http")
    logger.info("startup backfill: nasa_power UV starting (%d days)", lookback_days)
    try:
        async with httpx.AsyncClient() as client:
            result = await backfill_range(settings, client, RateLimiter(settings.min_seconds_between_requests), lookback_days=lookback_days)
    except Exception:
        logger.warning("startup backfill: nasa_power UV unreachable from this deployment, skipping (non-fatal)", exc_info=True)
        return
    if result is None:
        logger.info("startup backfill: nasa_power UV returned no usable data")
        return
    _, observations = result
    store.insert_uv_observations(observations)
    logger.info("startup backfill: nasa_power UV done, %d days ingested", len(observations))


async def _poll_himawari_forever(store: RealDataStore, interval_seconds: float) -> None:
    from himawari_ingestion.compliance import RateLimiter
    from himawari_ingestion.config import Settings
    from himawari_ingestion.datasource import HimawariAHICloudSource

    settings = Settings(source_mode="http")
    prev_arrays: dict | None = None
    prev_observed_at: datetime | None = None
    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(settings.min_seconds_between_requests))
        while True:
            try:
                raw, frame = await source.fetch_latest()
                frame, prev_arrays = _frame_with_motion(raw, frame, prev_arrays, prev_observed_at)
                prev_observed_at = frame.observed_at
                store.insert_cloud_frames([frame])
                logger.debug(
                    "himawari live poll: ingested frame observed_at=%s motion_speed_kmh=%s",
                    frame.observed_at, frame.motion_speed_kmh,
                )
            except Exception:
                logger.warning("himawari live poll failed, retrying next tick", exc_info=True)
            await asyncio.sleep(interval_seconds)


async def _poll_nwp_forever(store: RealDataStore, interval_seconds: float, forecast_hours: list[int]) -> None:
    from nwp_ingestion.compliance import RateLimiter
    from nwp_ingestion.config import Settings
    from nwp_ingestion.datasource import S3GfsBackfillDataSource, _most_recent_published_cycle

    settings = Settings(source_mode="http")
    async with httpx.AsyncClient() as client:
        source = S3GfsBackfillDataSource(settings, client, RateLimiter(settings.min_seconds_between_requests))
        while True:
            try:
                issue_time = _most_recent_published_cycle(datetime.now(timezone.utc), settings.gfs_cycles, settings.publish_latency_minutes)
                points = []
                for fhour in forecast_hours:
                    try:
                        _, point = await source.fetch_cycle(issue_time, fhour)
                        points.append(point)
                    except Exception:
                        logger.warning("nwp live poll: cycle=%s fhour=%d failed", issue_time.isoformat(), fhour, exc_info=True)
                if points:
                    store.insert_nwp_points(points)
                    logger.debug(
                        "nwp live poll: ingested %d/%d forecast hours for cycle %s", len(points), len(forecast_hours), issue_time.isoformat()
                    )
            except Exception:
                logger.warning("nwp live poll failed, retrying next tick", exc_info=True)
            await asyncio.sleep(interval_seconds)


async def _retrain_forever(store: RealDataStore, cold_interval_seconds: float, warm_interval_seconds: float, warm_threshold_rows: int) -> None:
    """Retrains every (zone, horizon), then sleeps `cold_interval_seconds` if
    real history is still thin or `warm_interval_seconds` once it isn't - see
    config.py's own docstring on `retrain_interval_cold_seconds` for why. The
    regime is re-checked every cycle (not decided once at startup), so a
    deployment that starts cold and accumulates real data live transitions to
    the warm cadence on its own.
    """
    while True:
        for zone in ZONES:
            for horizon in HORIZONS:
                try:
                    result = await asyncio.to_thread(training.train_now, zone, horizon, store)
                    logger.info("retrained %s/%s: data_source=%s version=%d", zone, horizon, result.data_source, result.model_version)
                except Exception:
                    logger.warning("retrain failed for %s/%s, will retry next cycle", zone, horizon, exc_info=True)

        nwp_rows = store.counts()["nwp_history"]
        if nwp_rows >= warm_threshold_rows:
            interval_seconds = warm_interval_seconds
            regime = "warm"
        else:
            interval_seconds = cold_interval_seconds
            regime = "cold"
        logger.info(
            "retrain cycle done: nwp_history=%d rows, regime=%s, next retrain in %.0fs", nwp_rows, regime, interval_seconds
        )
        await asyncio.sleep(interval_seconds)


def start_background_ingestion(store: RealDataStore, settings) -> list[asyncio.Task]:
    """Spawns every background task and returns the handles - the caller
    (main.py's lifespan) owns cancelling them on shutdown. Does not block: the
    startup backfill runs as its own task, not awaited inline, so the app
    becomes ready to serve requests immediately (existing forecasts just fall
    back to the synthetic/physics-baseline path - see serving.py - until it
    completes).
    """
    return [
        asyncio.create_task(run_startup_backfill(store, settings.backfill_lookback_days), name="ingestion-startup-backfill"),
        asyncio.create_task(_poll_himawari_forever(store, settings.himawari_poll_interval_seconds), name="ingestion-poll-himawari"),
        asyncio.create_task(
            _poll_nwp_forever(store, settings.nwp_poll_interval_seconds, settings.nwp_poll_forecast_hours), name="ingestion-poll-nwp"
        ),
        asyncio.create_task(
            _retrain_forever(
                store, settings.retrain_interval_cold_seconds, settings.retrain_interval_warm_seconds, settings.retrain_warm_threshold_rows
            ),
            name="ingestion-retrain",
        ),
    ]


async def stop_background_ingestion(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
