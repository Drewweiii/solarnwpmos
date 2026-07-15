import pytest
from fastapi.testclient import TestClient


def test_get_performance_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/performance/GIS")
    assert resp.status_code == 401


def test_get_performance_returns_metrics_for_viewer(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/performance/GIS", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["zone"] == "GIS"
    assert body["simulated_zone"] is False
    assert body["ac_energy_kwh_today"] > 0
    assert 0 < body["performance_ratio"] <= 1.0
    assert body["specific_yield_kwh_per_kwp_today"] > 0
    assert "soiling_pct" in body["loss_breakdown"]
    assert len(body["hourly"]) == 24
    assert {"timestamp", "ac_kw", "ssrd_w_m2", "temp_c"} <= body["hourly"][0].keys()
    assert sum(p["ac_kw"] for p in body["hourly"]) == pytest.approx(body["ac_energy_kwh_today"])


def test_get_performance_includes_zone_coordinates_and_cloud_factor(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/performance/GIS", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["latitude"] == pytest.approx(12.68336875)
    assert body["longitude"] == pytest.approx(101.11986459)
    assert 0.0 <= body["cloud_factor"] <= 1.0


def test_get_performance_jetty_reports_simulated_zone_true(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/performance/Jetty", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["simulated_zone"] is True


def test_get_performance_unknown_zone_returns_404(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/performance/Nowhere", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
