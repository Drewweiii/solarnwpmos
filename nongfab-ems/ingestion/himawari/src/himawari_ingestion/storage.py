from __future__ import annotations

import asyncio
import io
import logging

from minio import Minio
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .config import Settings
from .models import CloudObsORM
from .schemas import CloudObservation, RawFetchResult

logger = logging.getLogger(__name__)


class RawObjectStorage:
    """Thin async wrapper around the (synchronous) MinIO client."""

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


class TimescaleWriter:
    """Upserts parsed observations into the `cloud_obs` hypertable."""

    def __init__(self, engine: AsyncEngine):
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def write_observation(self, observation: CloudObservation, raw_object_key: str | None) -> None:
        session: AsyncSession
        async with self._session_factory() as session:
            stmt = pg_insert(CloudObsORM).values(
                time=observation.observed_at,
                source=observation.source,
                latitude=observation.latitude,
                longitude=observation.longitude,
                cloud_opacity_pct=observation.cloud_opacity_pct,
                cloud_index=observation.cloud_index,
                raw_object_key=raw_object_key,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[CloudObsORM.time, CloudObsORM.source],
                set_={
                    "cloud_opacity_pct": stmt.excluded.cloud_opacity_pct,
                    "cloud_index": stmt.excluded.cloud_index,
                    "raw_object_key": stmt.excluded.raw_object_key,
                },
            )
            await session.execute(stmt)
            await session.commit()
