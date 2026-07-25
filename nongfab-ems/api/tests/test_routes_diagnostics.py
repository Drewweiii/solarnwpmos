"""GET /diagnostics/feeds + /diagnostics/{zone}/anomalies (2026-07-25)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from nongfab_forecast.serving import GENERATED_POWER_HORIZON

from nongfab_api.config import Settings
from nongfab_api.main import create_app


@dataclass
class _NWPPoint:
    valid_time: datetime
    issue_time: datetime
    ssrd_w_m2: float
    temp2m_c: float
    wind10m_u_ms: float
    wind10m_v_ms: float
    relative_humidity_pct: float
    source: str
    precip_mm: float | None = None


@dataclass
class _AerosolPoint:
    valid_time: datetime
    aod_550nm: float | None
    dust: float | None
    pm2_5: float | None
    pm10: float | None
    source: str = "test-aq"


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


def test_feed_health_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/diagnostics/feeds").status_code == 401


def test_feed_health_reports_every_feed_as_missing_on_an_empty_store(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/diagnostics/feeds", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_status"] == "missing"
    names = {feed["name"] for feed in body["feeds"]}
    assert names == {"nwp_history", "cloud_history", "aerosol_history", "uv_history", "uv_hourly_history"}
    for feed in body["feeds"]:
        assert feed["status"] == "missing"
        assert feed["rows"] == 0
        assert feed["label"]  # a Thai label, so the UI needn't map names itself


def test_feed_health_flags_a_forecast_feed_that_has_stopped_reaching_forward(engine, tmp_path):
    """The aerosol bug's signature: rows exist and are recent, but the forward
    coverage the hour-ahead leads need has run out."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        # NWP reaching a healthy 12h forward.
        store.insert_nwp_points(
            [
                _NWPPoint(now + timedelta(hours=h), now, 400.0, 30.0, 0.0, 5.0, 80.0, "test-real", 0.0)
                for h in range(-24, 13)
            ]
        )
        # Aerosol that stopped an hour ago - recent, but no forward coverage.
        store.insert_aerosol_points([_AerosolPoint(now - timedelta(hours=h), 0.2, 8.0, 20.0, 40.0) for h in range(1, 200)])

        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/diagnostics/feeds", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    by_name = {feed["name"]: feed for feed in body["feeds"]}
    assert by_name["nwp_history"]["status"] == "ok"
    assert by_name["nwp_history"]["kind"] == "coverage"
    assert by_name["nwp_history"]["lead_minutes"] > 0

    assert by_name["aerosol_history"]["status"] == "stale"
    assert by_name["aerosol_history"]["lead_minutes"] < 0
    assert "ล่วงหน้าไม่พอ" in by_name["aerosol_history"]["detail"]
    # One stale feed is enough to make the overall verdict non-ok.
    assert body["overall_status"] in {"stale", "missing"}


def test_anomalies_404s_on_an_unknown_zone(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/diagnostics/Nowhere/anomalies", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_anomalies_is_unavailable_with_a_reason_when_there_is_no_history(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/diagnostics/GIS/anomalies", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["reason"]
    assert body["anomalies"] == []
    # The no-meter caveat is carried even in the empty case.
    assert "ไม่มีมิเตอร์" in body["basis_note"]


def test_anomalies_flags_a_bad_day_and_names_a_weather_cause(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        # 20 normal days of ~200 kWh/day, then one day at a fraction of that.
        for d in range(1, 21):
            day = today - timedelta(days=d)
            per_hour = 8.0 if d != 3 else 0.4
            for h in range(8, 18):
                store.record_forecast_points(
                    "GIS", GENERATED_POWER_HORIZON, day + timedelta(hours=h), [_Point(day + timedelta(hours=h), per_hour * 2.5)]
                )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/diagnostics/GIS/anomalies?days=30", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["days_assessed"] >= 19
    assert body["norm_kwh_per_day"] > 0
    bad_day = (today - timedelta(days=3)).date().isoformat()
    flagged = {a["day"] for a in body["anomalies"]}
    assert bad_day in flagged
    entry = next(a for a in body["anomalies"] if a["day"] == bad_day)
    assert entry["ratio"] < 0.7
    assert entry["shortfall_kwh"] > 0
    # With no weather rows seeded, the cause must be 'unknown' - never guessed.
    assert entry["likely_cause"] == "unknown"
