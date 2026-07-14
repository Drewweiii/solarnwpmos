from fastapi.testclient import TestClient

from nongfab_api.main import app


def test_healthz_returns_ok():
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
