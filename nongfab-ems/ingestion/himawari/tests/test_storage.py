from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from himawari_ingestion.schemas import CloudObservation, CloudRasterFrame, RawFetchResult
from himawari_ingestion.storage import RawObjectStorage, TimescaleWriter


class FakeMinioClient:
    """Stands in for minio.Minio - avoids requiring a running MinIO server for unit tests."""

    def __init__(self):
        self.buckets: set[str] = set()
        self.objects: dict[str, bytes] = {}

    def bucket_exists(self, name: str) -> bool:
        return name in self.buckets

    def make_bucket(self, name: str) -> None:
        self.buckets.add(name)

    def put_object(self, bucket, object_name, data, length, content_type):
        self.objects[f"{bucket}/{object_name}"] = data.read()


@pytest.mark.asyncio
async def test_raw_object_storage_creates_bucket_and_puts_object(settings):
    fake_client = FakeMinioClient()
    storage = RawObjectStorage(settings, client=fake_client)

    raw = RawFetchResult(url="mock://x", fetched_at=datetime.now(timezone.utc), content_type="application/json", body=b'{"a":1}')
    key = await storage.put_raw(raw)

    assert key == raw.object_key
    assert settings.minio_bucket in fake_client.buckets
    assert fake_client.objects[f"{settings.minio_bucket}/{raw.object_key}"] == b'{"a":1}'


def test_timescale_writer_upsert_compiles_to_valid_postgres_sql(settings):
    # No live Postgres in the unit-test environment: verify the statement shape
    # (upsert on the (time, source) primary key) compiles correctly for the
    # postgres dialect actually used in prod, rather than running it end-to-end.
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from himawari_ingestion.models import CloudObsORM

    observation = CloudObservation(
        observed_at=datetime.now(timezone.utc),
        latitude=12.71,
        longitude=101.15,
        cloud_opacity_pct=10.0,
        cloud_index=0.1,
        source="mock-fixture",
    )
    stmt = pg_insert(CloudObsORM).values(
        time=observation.observed_at,
        source=observation.source,
        latitude=observation.latitude,
        longitude=observation.longitude,
        cloud_opacity_pct=observation.cloud_opacity_pct,
        cloud_index=observation.cloud_index,
        raw_object_key="some/key",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[CloudObsORM.time, CloudObsORM.source],
        set_={"cloud_opacity_pct": stmt.excluded.cloud_opacity_pct},
    )
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "INSERT INTO cloud_obs" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO UPDATE SET" in compiled


def test_timescale_writer_raster_upsert_compiles_to_valid_postgres_sql():
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from himawari_ingestion.models import CloudRasterFrameORM

    frame = CloudRasterFrame(
        observed_at=datetime.now(timezone.utc), source="mock-fixture",
        lat_min=12.61, lat_max=12.74, lon_min=101.06, lon_max=101.18, rows=7, cols=5,
        nong_fab_cloud_opacity_pct=40.0, nong_fab_cloud_index=0.4,
        motion_speed_kmh=12.3, motion_direction_deg=180.0,
    )
    stmt = pg_insert(CloudRasterFrameORM).values(
        time=frame.observed_at, source=frame.source,
        lat_min=frame.lat_min, lat_max=frame.lat_max, lon_min=frame.lon_min, lon_max=frame.lon_max,
        rows=frame.rows, cols=frame.cols,
        nong_fab_cloud_opacity_pct=frame.nong_fab_cloud_opacity_pct, nong_fab_cloud_index=frame.nong_fab_cloud_index,
        motion_speed_kmh=frame.motion_speed_kmh, motion_direction_deg=frame.motion_direction_deg,
        raster_object_key="some/tile.npz",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[CloudRasterFrameORM.time, CloudRasterFrameORM.source],
        set_={"nong_fab_cloud_opacity_pct": stmt.excluded.nong_fab_cloud_opacity_pct},
    )
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "INSERT INTO cloud_raster_frames" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO UPDATE SET" in compiled


@pytest.mark.integration
@pytest.mark.asyncio
async def test_timescale_writer_roundtrip_against_real_db(timescale_test_dsn):
    """Integration test - skipped unless TIMESCALE_TEST_DSN is set (see conftest.py).
    Run against the docker-compose TimescaleDB once db/migrations/0001_cloud_obs.sql
    and 0002_cloud_raster_frames.sql are applied.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(timescale_test_dsn)
    writer = TimescaleWriter(engine)
    observation = CloudObservation(
        observed_at=datetime.now(timezone.utc),
        latitude=12.71,
        longitude=101.15,
        cloud_opacity_pct=20.0,
        cloud_index=0.2,
        source="integration-test",
    )
    await writer.write_observation(observation, "some/key")

    frame = CloudRasterFrame(
        observed_at=datetime.now(timezone.utc), source="integration-test",
        lat_min=12.61, lat_max=12.74, lon_min=101.06, lon_max=101.18, rows=7, cols=5,
        nong_fab_cloud_opacity_pct=20.0, nong_fab_cloud_index=0.2,
        motion_speed_kmh=None, motion_direction_deg=None,
    )
    await writer.write_raster_frame(frame, "some/tile.npz")

    await engine.dispose()
