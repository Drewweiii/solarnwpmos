from fastapi.testclient import TestClient


def test_get_assets_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/assets")
    assert resp.status_code == 401


def test_get_assets_returns_registry_for_viewer(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/assets", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    zone_ids = {z["id"] for z in resp.json()["zones"]}
    assert {"GIS", "ISB", "Jetty"} <= zone_ids


def test_get_zone_returns_single_zone(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/assets/GIS", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == "GIS"


def test_get_zone_marks_jetty_simulated(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/assets/Jetty", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["simulated"] is True


def test_get_zone_unknown_zone_returns_404(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/assets/Nowhere", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
