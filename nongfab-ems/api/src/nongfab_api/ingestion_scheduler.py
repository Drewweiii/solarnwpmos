"""Background real-data ingestion, run inside this API process rather than as
separate deployed services - this deployment has no persistent TimescaleDB for
ingestion/nwp's and ingestion/himawari's own storage.py to write to (Railway hosts
only this one container; see root README "Known gaps" and
nongfab_forecast.local_store's own docstring for why a local SQLite-backed store is
used instead). On startup: backfills the last `backfill_lookback_days` if the store
is thin (plus a one-time PVGIS historical-weather seed, gated separately - see
_backfill_pvgis), then runs continuous live polling (Himawari every ~10min, GFS
every ~1h) and periodic retraining for every (zone, horizon) pair - all as plain
asyncio background tasks (no new scheduler dependency; APScheduler is already used
by the standalone ingestion modules for their own separate-deploy path, but this
process just needs a handful of sleep loops, not a cron-like scheduler).

Every network/training call is wrapped so one failure (a source unreachable from
wherever this actually runs - see ingestion/nasa_power/README's own "not reachable
from this dev sandbox" caveat, whose scope elsewhere is unconfirmed) never crashes
the loop or the app - logged and retried next tick.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

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

    `_backfill_forecast_history` runs *first*, ahead of every network-
    dependent step below - a pure local computation (no HTTP calls at all)
    with no dependency on any of them, so there is no reason for the
    dashboard's Forecast/Prediction-interval history to sit blocked behind
    however long NWP/Himawari/PVGIS take to succeed or fail (each is a real
    network call to an external source, no fixed upper bound on that here)
    when it could already be showing something the moment the process is
    ready to serve.

    `_backfill_generated_power_history` runs right after, but (2026-07-19)
    is no longer a pure local computation itself - it does its own small,
    bounded Himawari historical fetch first (~72 slots, a few minutes) so
    the actual-power backfill can use each hour's *own* real cloud reading
    instead of today's single snapshot - see that function's own docstring
    and `nongfab_forecast.serving.backfill_generated_power_history`'s for
    the full reasoning. Still bounded and still non-fatal on failure (falls
    back to the old clear-sky-per-hour behavior), just no longer instant.
    """
    await _backfill_forecast_history(store)
    await _backfill_generated_power_history(store)

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

    await _backfill_pvgis(store)


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


async def _backfill_pvgis(store: RealDataStore) -> None:
    """One-time seed of real historical weather (PVGIS's seriescalc API - ERA5-
    reanalysis irradiance/temperature for Nong Fab's own coordinates), gated on
    the pvgis-era5-tagged row count specifically (count_nwp_rows_by_source), not
    the shared nwp_history total `run_startup_backfill` already gates
    `_backfill_nwp` on - so this seeds Day-ahead training with real weather even
    in a deployment where GFS's own S3 backfill is thin/unreachable, and doesn't
    re-run on every restart once it has already seeded once.

    Unlike Himawari/GFS's continuous near-real-time polling, PVGIS returns a
    whole already-published year of hourly data in a single call - there is
    nothing to keep polling, so this has no `_poll_pvgis_forever` counterpart.

    IMPORTANT: every row this writes has issue_time == valid_time (see
    pvgis_ingestion.schemas.PVGISHourlyPoint's own docstring) - real_data.py's
    k-step hour-ahead builders filter on lead_hours = valid_time - issue_time,
    which is always 0 here, so these rows are invisible to Intra-day training by
    construction. This is a deliberate 2026-07-16 scope decision (PVGIS is
    historical reanalysis, not a multi-lead forecast - duplicating one reading
    across 6 lead-hour buckets would teach the k-step models nothing real about
    lead-time-dependent forecast skill), not an oversight - see forecast/
    README.md's matching dated entry.
    """
    from pvgis_ingestion.backfill import backfill_year
    from pvgis_ingestion.config import Settings
    from pvgis_ingestion.schemas import SOURCE_NAME

    if store.count_nwp_rows_by_source(SOURCE_NAME) > 0:
        logger.info("startup backfill: pvgis already seeded, skipping")
        return

    settings = Settings(source_mode="http")
    logger.info("startup backfill: pvgis starting (year=%d)", settings.year)
    try:
        async with httpx.AsyncClient() as client:
            result = await backfill_year(settings, client)
    except Exception:
        logger.warning("startup backfill: pvgis unreachable from this deployment, skipping (non-fatal)", exc_info=True)
        return
    if result is None:
        logger.info("startup backfill: pvgis returned no usable data")
        return
    _, points = result
    store.insert_nwp_points(points)
    logger.info("startup backfill: pvgis done, %d hourly rows ingested", len(points))


async def _backfill_forecast_history(store: RealDataStore) -> None:
    """One-time cold-start seed of `forecast_history` so a freshly-booted
    process (a Railway redeploy, or any container restart) doesn't show a
    blank Forecast/Prediction interval history for recent past hours until
    enough real polling has happened to rebuild it organically - see
    `nongfab_forecast.serving.backfill_forecast_history`'s own docstring for
    the full reasoning (physics-baseline-only, an honest approximation, not
    a claimed ML measurement).

    Gated per (zone, horizon) on whether that pair already has any
    persisted history within its own lookback window - a deployment with a
    real persistent volume for `NONGFAB_REAL_DATA_DB` should never have
    this silently overwrite real accumulated ML-quality history with a
    lesser physics-only seed on every restart.
    """
    from nongfab_forecast.serving import FORECAST_HISTORY_LOOKBACK_HOURS, backfill_forecast_history

    now = datetime.now(timezone.utc)
    for zone in ZONES:
        for horizon, lookback_hours in FORECAST_HISTORY_LOOKBACK_HOURS.items():
            existing = store.forecast_history_points(zone, horizon, since=now - timedelta(hours=lookback_hours))
            if existing:
                logger.info("startup backfill: forecast_history already has data for %s/%s, skipping", zone, horizon)
                continue
            try:
                inserted = backfill_forecast_history(zone, horizon, store, now=now)
                logger.info("startup backfill: forecast_history seeded %d rows for %s/%s", inserted, zone, horizon)
            except Exception:
                logger.warning(
                    "startup backfill: forecast_history failed for %s/%s, skipping (non-fatal)", zone, horizon, exc_info=True
                )


_GENERATED_POWER_CLOUD_LOOKBACK_DAYS = 3  # covers GENERATED_POWER_BACKFILL_HOURS (72h) with a day to spare


async def _backfill_himawari_bounded(store: RealDataStore, days: int) -> None:
    """A small, fast historical Himawari fetch (default 3 days = 72 hourly
    slots, ~2.5 min at the 2s rate limit) - run ahead of
    `backfill_generated_power_history`'s own `physics_baseline_series(
    use_historical_cloud=True)` call specifically, so it has real per-hour
    cloud data to look up instead of falling back to clear-sky for the
    whole window. Deliberately NOT the full `backfill_lookback_days`
    (default 30 = 720 slots, ~24 min) `_backfill_himawari` below already
    does for ML training features - that would make actual-power history
    wait far longer than this one narrow purpose needs.

    Same non-fatal failure handling as every other network step here: on
    failure this just leaves `cloud_history` thin for the affected hours,
    which `backfill_generated_power_history`'s historical lookup already
    degrades gracefully from (falls back to clear-sky per hour - see
    `real_data._historical_cloud_attenuation`'s docstring), not a crash.
    """
    from himawari_ingestion.backfill import backfill_range
    from himawari_ingestion.compliance import RateLimiter
    from himawari_ingestion.config import Settings

    settings = Settings(source_mode="http")
    logger.info("startup backfill: himawari (bounded, %d days) starting for generated-power history", days)
    n_ok = n_total = 0
    prev_arrays: dict | None = None
    prev_observed_at: datetime | None = None
    try:
        async with httpx.AsyncClient() as client:
            async for result in backfill_range(
                settings, client, RateLimiter(settings.min_seconds_between_requests), lookback_days=days, cadence_minutes=60
            ):
                n_total += 1
                if result is not None:
                    raw, frame = result
                    frame, prev_arrays = _frame_with_motion(raw, frame, prev_arrays, prev_observed_at)
                    prev_observed_at = frame.observed_at
                    store.insert_cloud_frames([frame])
                    n_ok += 1
    except Exception:
        logger.warning(
            "startup backfill: bounded himawari failed partway (%d/%d slots ingested) - "
            "generated-power history will fall back to clear-sky for hours with no match",
            n_ok, n_total, exc_info=True,
        )
        return
    logger.info("startup backfill: bounded himawari done, %d/%d slots ingested", n_ok, n_total)


async def _backfill_generated_power_history(store: RealDataStore) -> None:
    """One-time cold-start seed of the actual/generated-power history (see
    `nongfab_forecast.serving.backfill_generated_power_history`'s own
    docstring) - same "gated per zone on whether it already has data"
    pattern as `_backfill_forecast_history` above, so a deployment with a
    real persistent volume never overwrites real accumulated live readings
    (from `record_generated_power()`, called on every `/performance` poll)
    with a lesser physics-only seed on every restart.

    Runs `_backfill_himawari_bounded` first (2026-07-19), but only if at
    least one zone actually still needs seeding - skips it entirely on a
    redeploy with a persistent volume where every zone already has real
    accumulated history, same "don't pay for network calls nothing needs"
    reasoning as every gate in this module.
    """
    from nongfab_forecast.serving import (
        GENERATED_POWER_BACKFILL_HOURS,
        GENERATED_POWER_HORIZON,
        backfill_generated_power_history,
    )

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=GENERATED_POWER_BACKFILL_HOURS)
    existing_by_zone = {zone: store.forecast_history_points(zone, GENERATED_POWER_HORIZON, since=since) for zone in ZONES}

    if not all(existing_by_zone.values()):
        await _backfill_himawari_bounded(store, _GENERATED_POWER_CLOUD_LOOKBACK_DAYS)

    for zone in ZONES:
        if existing_by_zone[zone]:
            logger.info("startup backfill: generated-power history already has data for %s, skipping", zone)
            continue
        try:
            inserted = backfill_generated_power_history(zone, store, now=now)
            logger.info("startup backfill: generated-power history seeded %d rows for %s", inserted, zone)
        except Exception:
            logger.warning("startup backfill: generated-power history failed for %s, skipping (non-fatal)", zone, exc_info=True)


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
