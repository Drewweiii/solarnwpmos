"""GET /tou: the split reaches the wire, and shipping it changes nothing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_tou_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/tou").status_code == 401


def test_it_reports_the_share_falling_outside_the_peak_window(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/tou", headers={"Authorization": f"Bearer {token}"}).json()

    assert 25.0 < body["offpeak_share_pct"] < 40.0
    assert body["total_peak_kwh"] > 0 and body["total_offpeak_kwh"] > 0
    assert {z["zone_id"] for z in body["zones"]} == {"GIS", "ISB", "Jetty"}


def test_shipping_this_route_does_not_move_the_published_saving(app, token_factory):
    """The point of defaulting the off-peak rate to the peak rate: the blended
    figure must reproduce today's flat one exactly, so adding this page cannot
    silently change what the Savings page reports."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/tou", headers={"Authorization": f"Bearer {token}"}).json()

    assert body["offpeak_rate_is_set"] is False
    assert body["blended_rate_thb_per_kwh"] == pytest.approx(body["peak_rate_thb_per_kwh"])
    assert body["overstatement_pct"] == pytest.approx(0.0, abs=1e-9)


def test_entering_a_real_off_peak_rate_reveals_the_overstatement(engine, tmp_path):
    """And once the real rate is supplied, the gap the flat assumption was
    hiding becomes visible - which is the whole reason for the route."""
    from nongfab_api.auth import create_access_token
    from nongfab_api.config import Settings
    from nongfab_api.main import create_app

    settings = Settings(
        jwt_secret_key="test-secret",
        seed_demo_users=True,
        enable_background_ingestion=False,
        real_data_db_path=str(tmp_path / "real_data.db"),
    )
    app = create_app(settings=settings, engine=engine)
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {create_access_token('tester', 'admin', settings, app.state.deploy_id)}"}
        client.put("/settings", json={"values": {"green.offpeak_rate_thb_per_kwh": 2.6}}, headers=headers)
        body = client.get("/tou", headers=headers).json()

    assert body["offpeak_rate_is_set"] is True
    assert body["blended_rate_thb_per_kwh"] < body["peak_rate_thb_per_kwh"]
    assert body["overstatement_pct"] > 5.0


def test_it_explains_that_holidays_are_not_counted_yet(app, token_factory):
    """Zero holidays makes the reported peak share a ceiling, not an estimate -
    a reader has to know which direction the remaining error runs."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/tou", headers={"Authorization": f"Bearer {token}"}).json()

    assert body["offpeak_holiday_days"] == 0
    assert "วันหยุด" in body["holiday_note"]
    assert "09:00" in body["window_note"]
