import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    # Deterministic regardless of ambient local infra: mock datasource, and a
    # TimescaleDB DSN guaranteed not to connect, so /fetch-now's storage step
    # fails predictably rather than depending on whether Postgres happens to be
    # reachable in whatever environment the suite runs in.
    monkeypatch.setenv("HIMAWARI_SOURCE_MODE", "mock")
    monkeypatch.setenv("HIMAWARI_TIMESCALE_DSN", "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/does_not_exist")

    from himawari_ingestion.api import app

    with TestClient(app) as c:
        yield c


def test_health_reports_mock_source_mode(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_mode"] == "mock"
    assert body["last_fetched_at"] is None
    assert "local-disk" in body["raw_storage_backend"]


def test_latest_observation_404_before_any_fetch(client):
    resp = client.get("/latest-observation")
    assert resp.status_code == 404


def test_latest_raster_404_before_any_fetch(client):
    resp = client.get("/latest-raster")
    assert resp.status_code == 404


def test_fetch_now_reports_storage_failure_gracefully(client):
    # Datasource (mock) succeeds, but TimescaleDB is unreachable by design here -
    # the endpoint must report that clearly (502) rather than crash or hang.
    resp = client.post("/fetch-now")
    assert resp.status_code == 502
    assert resp.json()["detail"]  # some error message, not empty

    health = client.get("/health").json()
    assert health["last_error"] is not None
    assert health["last_fetched_at"] is not None

    # storage never completed, so neither read-back endpoint should report stale/partial data
    assert client.get("/latest-observation").status_code == 404
    assert client.get("/latest-raster").status_code == 404
