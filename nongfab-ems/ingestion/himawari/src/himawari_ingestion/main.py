from __future__ import annotations

import asyncio
import logging

import httpx
from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import create_async_engine

from .compliance import RateLimiter
from .config import get_settings
from .datasource import build_datasource
from .scheduler import IngestionJob, build_scheduler
from .storage import RawObjectStorage, TimescaleWriter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()

    http_client = httpx.AsyncClient()
    rate_limiter = RateLimiter(settings.min_seconds_between_requests)
    datasource = build_datasource(settings, http_client, rate_limiter)

    engine = create_async_engine(settings.timescale_dsn)
    job = IngestionJob(
        datasource=datasource,
        raw_storage=RawObjectStorage(settings),
        timescale=TimescaleWriter(engine),
        source_label=settings.source_mode,
    )

    start_http_server(settings.metrics_port)
    logger.info("metrics exposed on :%d/metrics", settings.metrics_port)

    scheduler = build_scheduler(job, settings.poll_interval_minutes)
    scheduler.start()
    logger.info("himawari ingestion scheduler started (every %d min, source_mode=%s)", settings.poll_interval_minutes, settings.source_mode)

    # Run once immediately on startup so operators don't wait a full interval to see data.
    await job.run_once()

    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown()
        await http_client.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
