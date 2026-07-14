from fastapi.testclient import TestClient


def test_get_forecast_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/forecast/GIS/hour")
    assert resp.status_code == 401


def test_get_forecast_unknown_zone_returns_404(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/Nowhere/hour", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_get_forecast_unknown_horizon_returns_404(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/GIS/century", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_get_forecast_no_model_trained_returns_404(app, token_factory, monkeypatch, tmp_path):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/GIS/hour", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
