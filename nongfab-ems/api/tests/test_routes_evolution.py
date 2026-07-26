"""GET /forecast/{zone}/evolution (2026-07-25, project D) - auth, the
honest-empty states while the new table fills, and a real convergence story."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from nongfab_api.config import Settings
from nongfab_api.main import create_app


class _Point:
    def __init__(self, timestamp: datetime, pred: float, lower=None, upper=None):
        self.timestamp = timestamp
        self.pred = pred
        self.lower = lower
        self.upper = upper
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


def test_evolution_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/forecast/GIS/evolution").status_code == 401


def test_evolution_404s_on_an_unknown_zone(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/NOPE/evolution", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_evolution_says_the_table_is_still_filling_rather_than_showing_nothing(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/GIS/evolution", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["available"] is False
    assert "เพิ่งเริ่มเก็บ" in body["reason"]
    assert body["highlight"] is None
    assert body["collection_note"]


def test_evolution_distinguishes_too_few_issuances_from_no_data(engine, tmp_path):
    """Rows exist, but no hour has been forecast enough times to say whether the
    prediction settled. That is a different answer from "nothing recorded" and
    must not be reported as the same thing."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    target = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=20)

    with TestClient(app) as client:
        store = app.state.real_data_store
        for lead in (30, 6):
            store.record_forecast_evolution("GIS", "day", target - timedelta(hours=lead), [_Point(target, 100.0)])
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/evolution", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is False
    assert "รอบ" in body["reason"]
    assert body["min_issuances"] == 3


def test_evolution_surfaces_the_hour_the_model_changed_its_mind_about(engine, tmp_path):
    """Two target hours: one drifting steadily, one that swung 90 kW and came
    back. The second is the interesting one even though its net revision is
    smaller - the route must pick it."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    quiet = now + timedelta(hours=20)
    dramatic = now + timedelta(hours=21)

    with TestClient(app) as client:
        store = app.state.real_data_store
        for lead, value in ((60, 180.0), (30, 160.0), (6, 140.0)):
            store.record_forecast_evolution("GIS", "day", quiet - timedelta(hours=lead), [_Point(quiet, value)])
        for lead, value in ((60, 180.0), (30, 90.0), (6, 175.0)):
            store.record_forecast_evolution(
                "GIS", "day", dramatic - timedelta(hours=lead), [_Point(dramatic, value)]
            )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/evolution", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is True
    highlight = body["highlight"]
    assert highlight["n_issuances"] == 3
    assert highlight["max_swing_kw"] == pytest.approx(90.0)
    assert highlight["total_revision_kw"] == pytest.approx(-5.0)
    assert highlight["first_pred_kw"] == pytest.approx(180.0)
    assert highlight["latest_pred_kw"] == pytest.approx(175.0)
    # Both hours have enough issuances to chart.
    assert body["n_targets_with_trend"] == 2
    # Oldest issuance first, so the reader follows the story forward in time.
    leads = [i["lead_hours"] for i in highlight["issuances"]]
    assert leads == sorted(leads, reverse=True)


def test_evolution_can_be_asked_about_one_specific_hour(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    wanted = now + timedelta(hours=20)
    other = now + timedelta(hours=21)

    with TestClient(app) as client:
        store = app.state.real_data_store
        for lead, value in ((48, 100.0), (24, 110.0), (6, 108.0)):
            store.record_forecast_evolution("GIS", "day", wanted - timedelta(hours=lead), [_Point(wanted, value)])
        store.record_forecast_evolution("GIS", "day", other - timedelta(hours=6), [_Point(other, 999.0)])
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get(
            f"/forecast/GIS/evolution?target={wanted.isoformat()}",
            headers={"Authorization": f"Bearer {token}"},
        )

    body = resp.json()
    assert body["highlight"]["target_time"].startswith(wanted.isoformat()[:13])
    assert body["highlight"]["n_issuances"] == 3


def test_the_evolution_table_keeps_what_forecast_history_overwrites(engine, tmp_path):
    """The reason this table exists: forecast_history keys on
    (zone, horizon, target_time) and replaces, so the superseded issuances this
    view needs were already gone. Recording both must leave one row in the first
    and three in the second."""
    app, _ = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    target = now + timedelta(hours=20)

    with TestClient(app):
        store = app.state.real_data_store
        for lead, value in ((48, 100.0), (24, 110.0), (6, 108.0)):
            issued = target - timedelta(hours=lead)
            store.record_forecast_points("GIS", "day", issued, [_Point(target, value)])
            store.record_forecast_evolution("GIS", "day", issued, [_Point(target, value)])

        since = now - timedelta(days=7)
        assert len(store.forecast_history_points("GIS", "day", since)) == 1
        assert len(store.forecast_evolution_rows("GIS", "day", since)) == 3


def test_evolution_tolerates_an_unencoded_plus_in_the_target_timestamp(engine, tmp_path):
    """A caller who does not URL-encode sends "+00:00" and the + arrives as a
    space. That used to raise a ValueError and surface as a 500."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    target = now + timedelta(hours=20)

    with TestClient(app) as client:
        store = app.state.real_data_store
        for lead, value in ((48, 100.0), (24, 110.0), (6, 108.0)):
            store.record_forecast_evolution("GIS", "day", target - timedelta(hours=lead), [_Point(target, value)])
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        mangled = target.isoformat().replace("+", " ")
        resp = client.get(
            f"/forecast/GIS/evolution?target={mangled}", headers={"Authorization": f"Bearer {token}"}
        )

    assert resp.status_code == 200
    assert resp.json()["highlight"]["n_issuances"] == 3


def test_evolution_rejects_a_malformed_target_with_a_message_not_a_stack_trace(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    target = now + timedelta(hours=20)

    with TestClient(app) as client:
        store = app.state.real_data_store
        store.record_forecast_evolution("GIS", "day", target - timedelta(hours=6), [_Point(target, 100.0)])
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get(
            "/forecast/GIS/evolution?target=not-a-timestamp", headers={"Authorization": f"Bearer {token}"}
        )

    assert resp.status_code == 400
    assert "ISO timestamp" in resp.json()["detail"]
