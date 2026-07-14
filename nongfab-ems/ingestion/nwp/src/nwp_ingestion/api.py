"""Dev-only FastAPI wrapper around the Module 2 ingestion worker.

This is NOT the production Backend API (that's Module 6). Exists purely so the
worker built in this module - normally headless (scheduler + Prometheus metrics,
see main.py) - can be poked interactively via Swagger UI during development.

Run with: uvicorn nwp_ingestion.api:app --reload --port 8001
Then open: http://localhost:8001/docs
"""

from __future__ import annotations

import io
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine

from .compliance import RateLimiter
from .config import Settings, get_settings
from .datasource import build_datasource
from .scheduler import IngestionJob, build_scheduler
from .schemas import NWPForecastPoint
from .storage import RawObjectStorage, TimescaleWriter

logger = logging.getLogger(__name__)


class _LocalDiskRawStore:
    """Dev-only stand-in for a running MinIO server - mirrors
    himawari_ingestion.api._LocalDiskRawStore.
    """

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._buckets: set[str] = set()

    def bucket_exists(self, name: str) -> bool:
        return name in self._buckets or (self._base_dir / name).exists()

    def make_bucket(self, name: str) -> None:
        (self._base_dir / name).mkdir(parents=True, exist_ok=True)
        self._buckets.add(name)

    def put_object(self, bucket: str, object_name: str, data: io.BytesIO, length: int, content_type: str) -> None:
        path = self._base_dir / bucket / object_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.read())


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    http_client = httpx.AsyncClient()
    rate_limiter = RateLimiter(settings.min_seconds_between_requests)
    datasource = build_datasource(settings, http_client, rate_limiter)
    engine = create_async_engine(settings.timescale_dsn)

    raw_store_dir = Path(".dev-minio-data")
    raw_storage = RawObjectStorage(settings, client=_LocalDiskRawStore(raw_store_dir))

    job = IngestionJob(
        datasource=datasource,
        raw_storage=raw_storage,
        timescale=TimescaleWriter(engine),
        source_label=settings.source_mode,
    )
    scheduler = build_scheduler(job, settings.gfs_cycles, settings.publish_latency_minutes)
    scheduler.start()

    app.state.settings = settings
    app.state.job = job
    app.state.scheduler = scheduler
    app.state.raw_store_dir = raw_store_dir

    logger.info(
        "dev API started: source_mode=%s raw_storage=local-disk(%s) timescale_dsn=%s",
        settings.source_mode, raw_store_dir, settings.timescale_dsn,
    )

    yield

    scheduler.shutdown()
    await http_client.aclose()
    await engine.dispose()


app = FastAPI(
    title="Nong Fab EMS - Module 2 NWP Ingestion (dev verification API)",
    description=(
        "Thin wrapper around the Module 2 ingestion worker for interactive verification "
        "during development. Not Module 6's production Backend API. Raw storage here is a "
        "local-disk stand-in for MinIO; TimescaleDB writes go to a real Postgres database "
        "but without the TimescaleDB extension applied (also unavailable here) - see README "
        "for the production setup via docker-compose."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


class HealthResponse(BaseModel):
    status: str
    source_mode: str
    gfs_cycles: list[int]
    last_fetched_at: datetime | None
    last_cycle_issue_time: datetime | None
    last_error: str | None
    raw_storage_backend: str
    timescale_dsn: str


class ForecastCycleResponse(BaseModel):
    cycle_issue_time: datetime | None
    forecast_hours_count: int
    points: list[NWPForecastPoint]


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings: Settings = app.state.settings
    job: IngestionJob = app.state.job
    return HealthResponse(
        status="ok",
        source_mode=settings.source_mode,
        gfs_cycles=settings.gfs_cycles,
        last_fetched_at=job.last_fetched_at,
        last_cycle_issue_time=job.last_cycle_issue_time,
        last_error=job.last_error,
        raw_storage_backend=f"local-disk (dev stand-in for MinIO): {app.state.raw_store_dir}",
        timescale_dsn=settings.timescale_dsn,
    )


@app.get("/latest-cycle", response_model=ForecastCycleResponse)
async def latest_cycle() -> ForecastCycleResponse:
    job: IngestionJob = app.state.job
    if not job.last_points:
        raise HTTPException(status_code=404, detail="no cycle ingested yet - try POST /fetch-now")
    return ForecastCycleResponse(
        cycle_issue_time=job.last_cycle_issue_time, forecast_hours_count=len(job.last_points), points=job.last_points
    )


@app.post("/fetch-now", response_model=ForecastCycleResponse)
async def fetch_now() -> ForecastCycleResponse:
    """Triggers one ingestion cycle immediately (bypasses the GFS-cycle schedule) -
    the same IngestionJob.run_once() the APScheduler cron calls, so this is a
    genuine end-to-end run: fetch (all configured forecast hours) -> decode ->
    validate -> store raw -> upsert into TimescaleDB.
    """
    job: IngestionJob = app.state.job
    await job.run_once()
    if not job.last_points:
        raise HTTPException(status_code=502, detail=job.last_error or "fetch failed for an unknown reason")
    return ForecastCycleResponse(
        cycle_issue_time=job.last_cycle_issue_time, forecast_hours_count=len(job.last_points), points=job.last_points
    )
