"""GET /forecast/{zone}/ramp (2026-07-25, project B) - auth, honest-empty, an
upcoming down-ramp alert, and the measured history behind it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from nongfab_forecast.serving import GENERATED_POWER_HORIZON

from nongfab_api.config import Settings
from nongfab_api.main import create_app


class _Point:
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


def test_ramp_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/forecast/GIS/ramp").status_code == 401


def test_ramp_404s_on_an_unknown_zone(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/NOPE/ramp", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_ramp_is_unavailable_with_a_reason_when_there_is_nothing_to_difference(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/GIS/ramp", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["available"] is False
    assert body["reason"]
    assert body["alert"] is None


def test_ramp_flags_the_sharpest_upcoming_fall(engine, tmp_path):
    """GIS is 50 kW AC, so a 30 kW drop in one hour is 60%/h - well past the
    steep threshold and exactly the cliff a level-only forecast hides."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        # Steady, then a cliff between +2h and +3h, then steady again.
        forward = [(1, 40.0), (2, 39.0), (3, 9.0), (4, 8.0)]
        store.record_forecast_points(
            "GIS", "hour", now, [_Point(now + timedelta(hours=h), kw) for h, kw in forward]
        )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/ramp", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is True
    assert body["ac_capacity_kw"] == 50.0
    assert len(body["upcoming"]) == 3
    alert = body["alert"]
    assert alert is not None
    assert alert["delta_kw"] == pytest.approx(-30.0)
    assert alert["pct_of_capacity_per_h"] == pytest.approx(-60.0)
    assert alert["direction"] == "down"
    assert alert["severity"] == "steep"
    # And it must say plainly that nobody is expected to act on it.
    assert "ไม่ใช่สัญญาณให้ไปสั่งการ" in body["no_action_note"]


def test_ramp_raises_no_alert_on_an_ordinary_afternoon_decline(engine, tmp_path):
    """A warning that fires every day is one nobody reads."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        gentle = [(1, 40.0), (2, 38.0), (3, 36.0), (4, 34.0)]
        store.record_forecast_points(
            "GIS", "hour", now, [_Point(now + timedelta(hours=h), kw) for h, kw in gentle]
        )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/ramp", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is True
    assert len(body["upcoming"]) == 3
    assert body["alert"] is None


def test_ramp_history_comes_from_recorded_output_not_the_forecast(engine, tmp_path):
    """The history half is measured. It is what tells a reader whether an
    upcoming 60%/h fall is routine here or remarkable."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        # Three past days, each with one steep collapse at the same hour.
        for day in range(1, 4):
            base = now - timedelta(days=day)
            store.record_forecast_points(
                "GIS",
                GENERATED_POWER_HORIZON,
                base,
                [_Point(base, 45.0), _Point(base + timedelta(hours=1), 5.0)],
            )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/ramp?days=7", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is True
    history = body["history"]
    assert history["n_steep_down"] == 3
    assert history["worst_down_pct_per_h"] == pytest.approx(-80.0)
    # All three fell at the same clock hour, so the cluster is unambiguous.
    assert history["busiest_down_hour_count"] == 3
    assert 0 <= history["busiest_down_hour_ict"] <= 23
