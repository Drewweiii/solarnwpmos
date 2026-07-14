from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from nwp_ingestion.schemas import NWPForecastPoint, RawFetchResult
from nwp_ingestion.storage import RawObjectStorage, TimescaleWriter


class _FakeMinioResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


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

    def get_object(self, bucket, object_name):
        return _FakeMinioResponse(self.objects[f"{bucket}/{object_name}"])


def _sample_raw(**overrides) -> RawFetchResult:
    kwargs = dict(
        url="mock://x",
        fetched_at=datetime.now(timezone.utc),
        content_type="application/x-grib2",
        body=b"fake-grib-bytes",
        issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc),
        forecast_hour=1,
    )
    kwargs.update(overrides)
    return RawFetchResult(**kwargs)


@pytest.mark.asyncio
async def test_raw_object_storage_creates_bucket_and_puts_object(settings):
    fake_client = FakeMinioClient()
    storage = RawObjectStorage(settings, client=fake_client)

    raw = _sample_raw()
    key = await storage.put_raw(raw)

    assert key == raw.object_key
    assert settings.minio_bucket in fake_client.buckets
    assert fake_client.objects[f"{settings.minio_bucket}/{raw.object_key}"] == b"fake-grib-bytes"


@pytest.mark.asyncio
async def test_raw_object_storage_get_raw_roundtrips(settings):
    fake_client = FakeMinioClient()
    storage = RawObjectStorage(settings, client=fake_client)

    raw = _sample_raw(body=b"roundtrip-bytes")
    key = await storage.put_raw(raw)

    fetched = await storage.get_raw(key)
    assert fetched == b"roundtrip-bytes"


def test_timescale_writer_upsert_compiles_to_valid_postgres_sql():
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from nwp_ingestion.models import NWPForecastORM

    point = NWPForecastPoint(
        issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc),
        valid_time=datetime(2026, 7, 14, 1, tzinfo=timezone.utc),
        latitude=12.71, longitude=101.15,
        ssrd_w_m2=500.0, temp2m_c=28.0, wind10m_u_ms=2.0, wind10m_v_ms=-1.5,
        relative_humidity_pct=70.0, source="mock-fixture",
    )
    stmt = pg_insert(NWPForecastORM).values(
        issue_time=point.issue_time, valid_time=point.valid_time, source=point.source,
        latitude=point.latitude, longitude=point.longitude,
        ssrd_w_m2=point.ssrd_w_m2, temp2m_c=point.temp2m_c,
        wind10m_u_ms=point.wind10m_u_ms, wind10m_v_ms=point.wind10m_v_ms,
        relative_humidity_pct=point.relative_humidity_pct, raw_object_key="some/key.grib2",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[NWPForecastORM.issue_time, NWPForecastORM.valid_time, NWPForecastORM.source],
        set_={"ssrd_w_m2": stmt.excluded.ssrd_w_m2},
    )
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "INSERT INTO nwp_forecast" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO UPDATE SET" in compiled


@pytest.mark.integration
@pytest.mark.asyncio
async def test_timescale_writer_roundtrip_against_real_db(timescale_test_dsn):
    """Integration test - skipped unless TIMESCALE_TEST_DSN is set (see conftest.py).
    Run against the docker-compose TimescaleDB once db/migrations/0003_nwp_forecast.sql
    is applied.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from nwp_ingestion.models import NWPForecastORM

    engine = create_async_engine(timescale_test_dsn)
    writer = TimescaleWriter(engine)
    point = NWPForecastPoint(
        issue_time=datetime.now(timezone.utc),
        valid_time=datetime.now(timezone.utc),
        latitude=12.71, longitude=101.15,
        ssrd_w_m2=400.0, temp2m_c=29.5, wind10m_u_ms=1.0, wind10m_v_ms=0.5,
        relative_humidity_pct=65.0, source="integration-test",
    )
    await writer.write_forecast_point(point, "some/key.grib2")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(NWPForecastORM).where(
                    NWPForecastORM.source == "integration-test",
                    NWPForecastORM.issue_time == point.issue_time,
                    NWPForecastORM.valid_time == point.valid_time,
                )
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].ssrd_w_m2 == pytest.approx(400.0)

    await engine.dispose()
