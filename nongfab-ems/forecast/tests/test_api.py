import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    # isolated per-test MLflow tracking DB - registrations from one test must
    # never leak into another.
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")

    from nongfab_forecast.api import app

    with TestClient(app) as c:
        yield c


def test_health_reports_tracking_uri_and_no_trained_models_yet(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["trained"] == []


def test_forecast_rejects_unknown_zone(client):
    resp = client.get("/forecast/Nowhere/hour")
    assert resp.status_code == 404
    assert "unknown zone" in resp.json()["detail"]


def test_forecast_rejects_unknown_horizon(client):
    resp = client.get("/forecast/GIS/century")
    assert resp.status_code == 404
    assert "unknown horizon" in resp.json()["detail"]


def test_forecast_404_before_any_training(client):
    resp = client.get("/forecast/GIS/hour")
    assert resp.status_code == 404
    assert "train-now" in resp.json()["detail"]


def test_train_now_rejects_unknown_zone(client):
    resp = client.post("/train-now/Nowhere/hour")
    assert resp.status_code == 404


@pytest.mark.slow
def test_hour_ahead_train_then_forecast_round_trip(client):
    train_resp = client.post("/train-now/GIS/hour")
    assert train_resp.status_code == 200
    train_body = train_resp.json()
    assert train_body["model_version"] == 1
    assert set(train_body["metrics"]) == {"rmse", "mae", "mbe", "nrmse", "picp", "pinaw"}

    health = client.get("/health").json()
    assert "GIS/hour" in health["trained"]

    forecast_resp = client.get("/forecast/GIS/hour")
    assert forecast_resp.status_code == 200
    body = forecast_resp.json()
    assert body["zone"] == "GIS"
    assert body["horizon"] == "hour"
    assert body["model_version"] == 1
    assert len(body["points"]) == 1
    point = body["points"][0]
    assert point["timestamp"].endswith("Z")
    assert point["lower"] <= point["pred"] <= point["upper"]


@pytest.mark.slow
def test_hour_ahead_retrain_bumps_version(client):
    client.post("/train-now/ISB/hour")
    second = client.post("/train-now/ISB/hour")
    assert second.json()["model_version"] == 2

    forecast = client.get("/forecast/ISB/hour").json()
    assert forecast["model_version"] == 2


@pytest.mark.slow
def test_minute_ahead_train_then_forecast_round_trip(client):
    train_resp = client.post("/train-now/Jetty/minute")
    assert train_resp.status_code == 200
    assert "best_val_loss" in train_resp.json()["metrics"]

    forecast_resp = client.get("/forecast/Jetty/minute")
    assert forecast_resp.status_code == 200
    body = forecast_resp.json()
    assert len(body["points"]) == 6  # default minute-ahead horizon
    assert all(p["lower"] is None and p["upper"] is None for p in body["points"])  # no PI for minute-ahead


@pytest.mark.slow
def test_day_ahead_train_then_forecast_round_trip(client):
    train_resp = client.post("/train-now/GIS/day")
    assert train_resp.status_code == 200
    assert set(train_resp.json()["metrics"]) == {"rmse", "mae", "mbe", "nrmse", "picp", "pinaw"}

    forecast_resp = client.get("/forecast/GIS/day")
    assert forecast_resp.status_code == 200
    body = forecast_resp.json()
    assert len(body["points"]) == 24
    assert all(p["timestamp"].endswith("Z") for p in body["points"])  # tz-awareness bug regression
    assert all(p["lower"] <= p["pred"] <= p["upper"] for p in body["points"])
