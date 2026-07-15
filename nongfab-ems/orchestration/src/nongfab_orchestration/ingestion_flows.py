"""Prefect flows wrapping Module 1/2's existing IngestionJob.run_once().
Construction mirrors each module's own main.py `run()` almost exactly (same
datasource/storage/job wiring) - the only difference is there's no
AsyncIOScheduler + infinite `asyncio.Event().wait()` loop here, since a
Prefect deployment's own schedule (see deploy.py) decides when this runs
instead of the module's internal cron. Each ingestion module's Prometheus
Counters (module-level globals in its own metrics.py) still increment
exactly as they do when run via that module's own main() - run_once()
itself owns that, not its caller - so infra/prometheus/prometheus.yml's
existing himawari-ingestion/nwp-ingestion scrape jobs keep working
regardless of which driver (the module's own scheduler, or this flow)
called run_once().
"""

from __future__ import annotations

from typing import Any

import httpx
from himawari_ingestion.compliance import RateLimiter as HimawariRateLimiter
from himawari_ingestion.config import get_settings as himawari_settings
from himawari_ingestion.datasource import build_datasource as build_himawari_datasource
from himawari_ingestion.scheduler import IngestionJob as HimawariIngestionJob
from himawari_ingestion.storage import RawObjectStorage as HimawariRawObjectStorage
from himawari_ingestion.storage import TimescaleWriter as HimawariTimescaleWriter
from nwp_ingestion.compliance import RateLimiter as NwpRateLimiter
from nwp_ingestion.config import get_settings as nwp_settings
from nwp_ingestion.datasource import build_datasource as build_nwp_datasource
from nwp_ingestion.scheduler import IngestionJob as NwpIngestionJob
from nwp_ingestion.storage import RawObjectStorage as NwpRawObjectStorage
from nwp_ingestion.storage import TimescaleWriter as NwpTimescaleWriter
from prefect import flow, get_run_logger
from sqlalchemy.ext.asyncio import create_async_engine


def _job_result(source: str, job: HimawariIngestionJob | NwpIngestionJob) -> dict[str, Any]:
    return {
        "source": source,
        "ok": job.last_error is None,
        "error": job.last_error,
        "fetched_at": job.last_fetched_at.isoformat() if job.last_fetched_at else None,
    }


@flow(name="himawari-ingestion")
async def himawari_ingestion_flow() -> dict[str, Any]:
    """One fetch -> validate -> store cycle for Module 1 (cloud observation)."""
    logger = get_run_logger()
    settings = himawari_settings()

    http_client = httpx.AsyncClient()
    engine = create_async_engine(settings.timescale_dsn)
    try:
        rate_limiter = HimawariRateLimiter(settings.min_seconds_between_requests)
        datasource = build_himawari_datasource(settings, http_client, rate_limiter)
        job = HimawariIngestionJob(
            datasource=datasource,
            raw_storage=HimawariRawObjectStorage(settings),
            timescale=HimawariTimescaleWriter(engine),
            source_label=settings.source_mode,
        )
        await job.run_once()
    finally:
        await http_client.aclose()
        await engine.dispose()

    result = _job_result("himawari", job)
    if not result["ok"]:
        logger.error("himawari ingestion cycle failed: %s", result["error"])
        raise RuntimeError(result["error"])
    logger.info("himawari ingestion cycle ok, fetched_at=%s", result["fetched_at"])
    return result


@flow(name="nwp-ingestion")
async def nwp_ingestion_flow() -> dict[str, Any]:
    """One fetch-cycle -> validate -> store run for Module 2 (GFS NWP forecast)."""
    logger = get_run_logger()
    settings = nwp_settings()

    http_client = httpx.AsyncClient()
    engine = create_async_engine(settings.timescale_dsn)
    try:
        rate_limiter = NwpRateLimiter(settings.min_seconds_between_requests)
        datasource = build_nwp_datasource(settings, http_client, rate_limiter)
        job = NwpIngestionJob(
            datasource=datasource,
            raw_storage=NwpRawObjectStorage(settings),
            timescale=NwpTimescaleWriter(engine),
            source_label=settings.source_mode,
        )
        await job.run_once()
    finally:
        await http_client.aclose()
        await engine.dispose()

    result = _job_result("nwp", job)
    if not result["ok"]:
        logger.error("nwp ingestion cycle failed: %s", result["error"])
        raise RuntimeError(result["error"])
    logger.info("nwp ingestion cycle ok, fetched_at=%s", result["fetched_at"])
    return result
