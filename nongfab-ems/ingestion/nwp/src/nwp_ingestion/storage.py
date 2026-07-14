from __future__ import annotations

import asyncio
import io
import logging

from minio import Minio
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .config import Settings
from .models import NWPForecastORM
from .schemas import NWPForecastPoint, RawFetchResult

logger = logging.getLogger(__name__)


class RawObjectStorage:
    """Thin async wrapper around the (synchronous) MinIO client - mirrors
    himawari_ingestion.storage.RawObjectStorage.
    """

    def __init__(self, settings: Settings, client: Minio | None = None):
        self._settings = settings
        self._client = client or Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def _ensure_bucket_sync(self) -> None:
        if not self._client.bucket_exists(self._settings.minio_bucket):
            self._client.make_bucket(self._settings.minio_bucket)

    def _put_sync(self, raw: RawFetchResult) -> str:
        self._ensure_bucket_sync()
        self._client.put_object(
            self._settings.minio_bucket,
            raw.object_key,
            data=io.BytesIO(raw.body),
            length=len(raw.body),
            content_type=raw.content_type,
        )
        return raw.object_key

    async def put_raw(self, raw: RawFetchResult) -> str:
        return await asyncio.to_thread(self._put_sync, raw)

    def _get_sync(self, object_key: str) -> bytes:
        resp = self._client.get_object(self._settings.minio_bucket, object_key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    async def get_raw(self, object_key: str) -> bytes:
        return await asyncio.to_thread(self._get_sync, object_key)


class TimescaleWriter:
    """Writes parsed forecast points into the `nwp_forecast` hypertable.

    Upserts on (issue_time, valid_time, source) - a re-run of the same cycle
    overwrites its own rows (idempotent retries), but a *different* issue_time for
    the same valid_time is a distinct row (see models.NWPForecastORM docstring).
    """

    def __init__(self, engine: AsyncEngine):
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def write_forecast_point(self, point: NWPForecastPoint, raw_object_key: str | None) -> None:
        session: AsyncSession
        async with self._session_factory() as session:
            stmt = pg_insert(NWPForecastORM).values(
                issue_time=point.issue_time,
                valid_time=point.valid_time,
                source=point.source,
                latitude=point.latitude,
                longitude=point.longitude,
                ssrd_w_m2=point.ssrd_w_m2,
                temp2m_c=point.temp2m_c,
                wind10m_u_ms=point.wind10m_u_ms,
                wind10m_v_ms=point.wind10m_v_ms,
                relative_humidity_pct=point.relative_humidity_pct,
                raw_object_key=raw_object_key,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[NWPForecastORM.issue_time, NWPForecastORM.valid_time, NWPForecastORM.source],
                set_={
                    "ssrd_w_m2": stmt.excluded.ssrd_w_m2,
                    "temp2m_c": stmt.excluded.temp2m_c,
                    "wind10m_u_ms": stmt.excluded.wind10m_u_ms,
                    "wind10m_v_ms": stmt.excluded.wind10m_v_ms,
                    "relative_humidity_pct": stmt.excluded.relative_humidity_pct,
                    "raw_object_key": stmt.excluded.raw_object_key,
                },
            )
            await session.execute(stmt)
            await session.commit()
