"""GET /forecast/{zone}/verification (2026-07-25) - auth, honest-empty when the
two histories don't overlap, and a real scored window."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from nongfab_forecast.serving import GENERATED_POWER_HORIZON

from nongfab_api.config import Settings
from nongfab_api.main import create_app


class _Point:
    """Matches what record_forecast_points reads off each item."""

    def __init__(self, timestamp: datetime, pred: float):
        self.timestamp = timestamp
        self.pred = pred
        self.lower = None
        self.upper = None
        self.algorithm = None
        self.error = None


def _file_backed_app(engine, tmp_path):
    settings = Settings(
        jwt_secret_key="test-secret",
        seed_demo_users=True,
        enable_background_ingestion=False,
        real_data_db_path=str(tmp_path / "real_data.db"),
    )
    return create_app(settings=settings, engine=engine), settings


def test_verification_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/forecast/GIS/verification").status_code == 401


def test_verification_404s_on_an_unknown_zone(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/Nowhere/verification", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_verification_rejects_an_out_of_range_window(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/GIS/verification?days=500", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_verification_is_unavailable_with_a_reason_when_there_is_no_history(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/GIS/verification", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["reason"]
    assert body["daylight"] is None
    assert body["by_lead"] == []
    # The capacity is registry data, so it's known even with no history.
    assert body["ac_capacity_kw"] > 0


def test_verification_scores_the_window_once_forecasts_and_actuals_overlap(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        # 12 hours of forecasts, each issued 2h ahead of its target. The actual
        # RISES 1 kW/hour, so persistence ("it'll be what it is now") is wrong by
        # 2 kW at a 2h lead while the forecast is only ever 1 kW high - a model
        # that genuinely beats persistence, i.e. skill = 1 - 1/2 = 0.5. A flat
        # actual would make persistence perfect and leave the skill undefined.
        for h in range(1, 13):
            target = now - timedelta(hours=h)
            actual_kw = 20.0 + h
            store.record_forecast_points("GIS", "hour", target - timedelta(hours=2), [_Point(target, actual_kw + 1)])
            store.record_forecast_points("GIS", GENERATED_POWER_HORIZON, target, [_Point(target, actual_kw)])

        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/verification?days=7", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["horizon"] == "hour"
    assert body["window_days"] == 7
    assert body["daylight"]["n"] == 12
    assert body["daylight"]["mae_kw"] > 0
    assert body["daylight"]["mbe_kw"] > 0  # forecasts ran high
    assert body["daylight"]["nrmse_pct"] > 0
    # Persistence had a real reference here (the actual 2h before each target),
    # and the model beats it 1 kW to 2 kW -> skill 0.5.
    assert body["daylight"]["persistence_rmse_kw"] == pytest.approx(2.0)
    assert body["daylight"]["skill_score"] == pytest.approx(0.5)
    # Every lead bucket is present, and the 1-3h one holds these pairs.
    labels = [row["lead_bucket"] for row in body["by_lead"]]
    assert labels == ["0-1h", "1-3h", "3-6h", "6-24h", "24h+"]
    by_label = {row["lead_bucket"]: row["metrics"] for row in body["by_lead"]}
    assert by_label["1-3h"]["n"] == 12
    assert by_label["24h+"]["n"] == 0
    assert body["lead_time_note"]


def test_verification_reports_no_overlap_distinctly_from_no_data(engine, tmp_path):
    """Both stores have rows, but for different hours - the reason must say so
    rather than reporting a zero-error window."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        forecast_hour = now - timedelta(hours=2)
        actual_hour = now - timedelta(hours=50)
        store.record_forecast_points("GIS", "hour", forecast_hour - timedelta(hours=1), [_Point(forecast_hour, 30.0)])
        store.record_forecast_points("GIS", GENERATED_POWER_HORIZON, actual_hour, [_Point(actual_hour, 28.0)])

        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/verification?days=7", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is False
    assert "ทับกัน" in body["reason"]
