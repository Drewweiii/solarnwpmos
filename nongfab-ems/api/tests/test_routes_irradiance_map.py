from fastapi.testclient import TestClient


def test_get_irradiance_map_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/irradiance-map")
    assert resp.status_code == 401


def test_get_irradiance_map_returns_grid_and_zone_pins(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/irradiance-map", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["grid"]) == 100  # DEFAULT_GRID_SIZE (10) squared
    zone_ids = {z["id"] for z in body["zones"]}
    assert zone_ids == {"GIS", "ISB", "Jetty"}


def test_get_irradiance_map_grid_values_within_display_range(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/irradiance-map", params={"at": "2026-07-14T05:00:00Z"}, headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert all(0.0 <= p["ghi_w_m2"] <= 1000.0 for p in body["grid"])
    assert all(0.0 <= p["cloud_factor"] <= 1.0 for p in body["grid"])


def test_get_irradiance_map_at_midnight_is_all_zero(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/irradiance-map", params={"at": "2026-07-14T18:00:00Z"}, headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["sun"]["elevation_deg"] <= 0
    assert all(p["ghi_w_m2"] == 0.0 for p in body["grid"])


def test_get_irradiance_map_zone_pins_include_jetty_simulated_flag(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/irradiance-map", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    jetty = next(z for z in body["zones"] if z["id"] == "Jetty")
    assert jetty["simulated"] is True
    gis = next(z for z in body["zones"] if z["id"] == "GIS")
    assert gis["simulated"] is False


def test_get_irradiance_map_defaults_to_now(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/irradiance-map", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
