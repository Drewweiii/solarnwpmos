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
    # k-step: one LightGBM-vs-RF-vs-Sum-k-LSTM-vs-bias-correction metric bundle
    # per lead hour (HOUR_LEAD_HOURS = 1..6), not a single flat metrics dict -
    # see training.py's _train_hour_ahead_kstep. sum_k_rmse is present here
    # because this test's fixed synthetic fallback data (300 rows/lead,
    # deterministic seeds) always clears sum_k_lstm.train_sum_k_lstm_model's
    # own minimum-aligned-rows bar - a real deployment with thin history could
    # have it (harmlessly) missing for a given training run instead, see that
    # function's own docstring on why a Sum-k LSTM training failure is
    # non-fatal to the other two candidates.
    per_lead_metric_keys = {"rmse", "mae", "mbe", "nrmse", "picp", "pinaw", "lgbm_rmse", "rf_rmse", "sum_k_rmse", "residual_std"}
    expected_metrics = {f"lead{lead}_{key}" for lead in range(1, 7) for key in per_lead_metric_keys}
    assert set(train_body["metrics"]) == expected_metrics

    health = client.get("/health").json()
    assert "GIS/hour" in health["trained"]

    forecast_resp = client.get("/forecast/GIS/hour")
    assert forecast_resp.status_code == 200
    body = forecast_resp.json()
    assert body["zone"] == "GIS"
    assert body["horizon"] == "hour"
    assert body["model_version"] == 1
    assert len(body["points"]) == 6  # one point per k-step lead hour (+1h..+6h)
    for point in body["points"]:
        assert point["timestamp"].endswith("Z")
        assert point["lower"] <= point["pred"] <= point["upper"]
        # each lead hour's winning candidate (LightGBM vs Random Forest vs
        # Sum-k LSTM, see training.py's per-lead competition) and its own
        # validation RMSE travel with the point - this is what lets the
        # dashboard color-code which model won and show a real (not invented)
        # error line.
        assert point["algorithm"] in ("lightgbm", "random_forest", "sum_k_lstm")
        assert point["error"] >= 0


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
    assert all(p["algorithm"] == "cnn_lstm" for p in body["points"])  # fixed architecture, not auto-selected


@pytest.mark.slow
def test_day_ahead_train_then_forecast_round_trip(client):
    train_resp = client.post("/train-now/GIS/day")
    assert train_resp.status_code == 200
    # residual_std: the day-ahead bias-correction cascade's own validation
    # residual std (training.py's train_now, day branch) - present whenever
    # there's enough held-out history to train it (always true here).
    assert set(train_resp.json()["metrics"]) == {"rmse", "mae", "mbe", "nrmse", "picp", "pinaw", "residual_std"}

    forecast_resp = client.get("/forecast/GIS/day")
    assert forecast_resp.status_code == 200
    body = forecast_resp.json()
    assert len(body["points"]) == 72  # MAX_DAY_AHEAD_HOURS (3 days), not literally "one day" - see serving.py
    assert all(p["timestamp"].endswith("Z") for p in body["points"])  # tz-awareness bug regression
    assert all(p["lower"] <= p["pred"] <= p["upper"] for p in body["points"])
    assert all(p["algorithm"] == "neuralprophet" for p in body["points"])  # fixed architecture, not auto-selected
