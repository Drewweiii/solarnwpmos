"""These test the flow wrapper's own contract (build settings/client/engine,
construct exactly one job, call run_once() exactly once, translate
job.last_error into either a raised exception or a clean result dict, clean
up resources) - not IngestionJob.run_once()'s own fetch/store logic, which
Module 1/2's own test suites already cover. RawObjectStorage's real
constructor makes a synchronous MinIO bucket_exists() call, and the real
IngestionJob would need a real Postgres-compatible engine to actually write
- neither exists in this dev sandbox (no Docker daemon), so both are faked
here rather than skipped outright.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nongfab_orchestration import ingestion_flows


class _FakeSettings:
    timescale_dsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/nongfab_test"
    min_seconds_between_requests = 0.0
    source_mode = "mock"


class _FakeStorage:
    def __init__(self, *args, **kwargs):
        pass


class _FakeJob:
    SHOULD_FAIL: bool = False
    instances: list["_FakeJob"] = []

    def __init__(self, *, datasource, raw_storage, timescale, source_label):
        self.source_label = source_label
        self.run_once_calls = 0
        self.last_error: str | None = None
        self.last_fetched_at = None
        type(self).instances.append(self)

    async def run_once(self) -> None:
        self.run_once_calls += 1
        self.last_fetched_at = datetime.now(timezone.utc)
        if type(self).SHOULD_FAIL:
            self.last_error = "BoomError: simulated failure"


@pytest.fixture(autouse=True)
def _reset_fake_job():
    _FakeJob.instances.clear()
    _FakeJob.SHOULD_FAIL = False
    yield
    _FakeJob.instances.clear()
    _FakeJob.SHOULD_FAIL = False


@pytest.fixture
def patch_himawari(monkeypatch):
    monkeypatch.setattr(ingestion_flows, "himawari_settings", lambda: _FakeSettings())
    monkeypatch.setattr(ingestion_flows, "build_himawari_datasource", lambda *a, **k: object())
    monkeypatch.setattr(ingestion_flows, "HimawariRawObjectStorage", _FakeStorage)
    monkeypatch.setattr(ingestion_flows, "HimawariTimescaleWriter", _FakeStorage)
    monkeypatch.setattr(ingestion_flows, "HimawariIngestionJob", _FakeJob)


@pytest.fixture
def patch_nwp(monkeypatch):
    monkeypatch.setattr(ingestion_flows, "nwp_settings", lambda: _FakeSettings())
    monkeypatch.setattr(ingestion_flows, "build_nwp_datasource", lambda *a, **k: object())
    monkeypatch.setattr(ingestion_flows, "NwpRawObjectStorage", _FakeStorage)
    monkeypatch.setattr(ingestion_flows, "NwpTimescaleWriter", _FakeStorage)
    monkeypatch.setattr(ingestion_flows, "NwpIngestionJob", _FakeJob)


async def test_himawari_ingestion_flow_returns_ok_result_on_success(patch_himawari):
    result = await ingestion_flows.himawari_ingestion_flow()

    assert result == {"source": "himawari", "ok": True, "error": None, "fetched_at": result["fetched_at"]}
    assert result["fetched_at"] is not None
    assert len(_FakeJob.instances) == 1
    job = _FakeJob.instances[0]
    assert job.run_once_calls == 1
    assert job.source_label == "mock"


async def test_himawari_ingestion_flow_raises_on_job_failure(patch_himawari):
    _FakeJob.SHOULD_FAIL = True

    with pytest.raises(RuntimeError, match="simulated failure"):
        await ingestion_flows.himawari_ingestion_flow()

    assert _FakeJob.instances[0].run_once_calls == 1


async def test_nwp_ingestion_flow_returns_ok_result_on_success(patch_nwp):
    result = await ingestion_flows.nwp_ingestion_flow()

    assert result == {"source": "nwp", "ok": True, "error": None, "fetched_at": result["fetched_at"]}
    assert len(_FakeJob.instances) == 1
    assert _FakeJob.instances[0].run_once_calls == 1


async def test_nwp_ingestion_flow_raises_on_job_failure(patch_nwp):
    _FakeJob.SHOULD_FAIL = True

    with pytest.raises(RuntimeError, match="simulated failure"):
        await ingestion_flows.nwp_ingestion_flow()
