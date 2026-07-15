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


def test_get_forecast_no_model_trained_falls_back_to_physics_baseline(app, token_factory, monkeypatch, tmp_path):
    """No model registered -> the route no longer 404s (see routes_forecast.py's
    own docstring): get_forecast_with_fallback() serves a real-weather physics
    estimate instead, tagged model_type="physics_baseline" so callers can tell
    it apart from an actual ML forecast.
    """
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/GIS/hour", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_type"] == "physics_baseline"
    assert body["model_version"] == 0
    assert len(body["points"]) == 6  # one per k-step lead hour (+1h..+6h) - see forecast/serving.py's HOUR_LEAD_HOURS
