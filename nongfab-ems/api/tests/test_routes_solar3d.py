import pytest
from fastapi.testclient import TestClient


def test_get_geometry_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/geometry/GIS")
    assert resp.status_code == 401


def test_get_geometry_returns_panels_matching_module_count(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/geometry/GIS", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["zone"] == "GIS"
    assert body["simulated_zone"] is False
    assert len(body["panels"]) == 84
    assert 0.0 <= body["average_solar_access_pct"] <= 100.0
    assert "azimuth_deg" in body["sun"] and "elevation_deg" in body["sun"]


def test_get_geometry_at_noon_reports_daylight_sun(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get(
            "/geometry/GIS", params={"at": "2026-07-14T05:00:00Z"}, headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 200
    assert resp.json()["sun"]["elevation_deg"] > 0


def test_get_geometry_at_midnight_reports_night_and_full_shading(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get(
            "/geometry/GIS", params={"at": "2026-07-14T18:00:00Z"}, headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sun"]["elevation_deg"] <= 0
    assert body["average_solar_access_pct"] == 0.0


def test_get_geometry_jetty_reports_real_sub_array_block_ids(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/geometry/Jetty", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulated_zone"] is True
    assert len(body["panels"]) == 320
    block_ids = {p["block_id"] for p in body["panels"]}
    assert block_ids == {"01A.L", "02A.L", "03A.R", "04A.R"}


def test_get_geometry_gis_has_no_string_balance(app, token_factory):
    """GIS's block layout is a visualization approximation whose `row` isn't
    a real electrical string - see shading.string_power_balance()'s docstring."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/geometry/GIS", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["string_balance"] == []


def test_get_geometry_jetty_has_string_balance_per_sub_array(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get(
            "/geometry/Jetty", params={"at": "2026-07-14T05:00:00Z"}, headers={"Authorization": f"Bearer {token}"}
        )
    body = resp.json()
    balance = body["string_balance"]
    block_ids = {b["block_id"] for b in balance}
    assert block_ids == {"01A.L", "02A.L", "03A.R", "04A.R"}
    for block in balance:
        assert len(block["strings"]) == 4  # each Jetty sub-array has 4 real strings
        assert block["max_allowed_kw"] == pytest.approx(2.0)  # config/assets.yaml's design_constraints
        assert all(s["module_count"] == 20 for s in block["strings"])


def test_get_geometry_jetty_string_balance_flags_imbalance_at_low_sun(app, token_factory):
    """Low sun roughly aligned with Jetty's west-facing (270deg) azimuth =
    strong row-to-row shading = a real power imbalance across its strings,
    which should exceed the 2kW design constraint. 2026-07-14T11:15:00Z is
    ~18:15 local (Nong Fab, UTC+7): sun at ~6deg elevation, ~291deg azimuth."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get(
            "/geometry/Jetty", params={"at": "2026-07-14T11:15:00Z"}, headers={"Authorization": f"Bearer {token}"}
        )
    body = resp.json()
    assert body["sun"]["elevation_deg"] > 0
    balance = body["string_balance"]
    assert any(b["exceeds_limit"] for b in balance)


def test_get_geometry_includes_moon_position(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get(
            "/geometry/GIS", params={"at": "2026-07-14T05:00:00Z"}, headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 200
    moon = resp.json()["moon"]
    assert 0.0 <= moon["azimuth_deg"] < 360.0
    assert -90.0 <= moon["elevation_deg"] <= 90.0


def test_get_geometry_unknown_zone_returns_404(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/geometry/Nowhere", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_get_sun_path_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/sun-path/GIS")
    assert resp.status_code == 401


def test_get_sun_path_returns_only_daylight_points(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/sun-path/GIS", params={"date": "2026-07-14"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-07-14"
    assert len(body["points"]) > 0
    assert all(p["elevation_deg"] > 0 for p in body["points"])
    # points should be chronologically sorted
    times = [p["time"] for p in body["points"]]
    assert times == sorted(times)


def test_get_sun_path_defaults_to_today(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/sun-path/GIS", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_get_sun_path_rejects_malformed_date(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/sun-path/GIS", params={"date": "not-a-date"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_get_sun_path_unknown_zone_returns_404(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/sun-path/Nowhere", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_sun_path_is_identical_across_zones(app, token_factory):
    """Solar position comes from the shared site location (see routes_solar3d.py's
    docstring), not a true per-zone calculation - documenting that explicitly here."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        gis = client.get("/sun-path/GIS", params={"date": "2026-07-14"}, headers={"Authorization": f"Bearer {token}"}).json()
        jetty = client.get(
            "/sun-path/Jetty", params={"date": "2026-07-14"}, headers={"Authorization": f"Bearer {token}"}
        ).json()
    assert gis["points"] == jetty["points"]


def test_get_moon_path_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/moon-path/GIS")
    assert resp.status_code == 401


def test_get_moon_path_returns_full_24h_sweep_unfiltered(app, token_factory):
    """Unlike /sun-path, /moon-path is NOT filtered to elevation > 0 - see the
    endpoint's own docstring for why (the frontend needs the moon's position
    even while it's below the horizon, to know when to fade it in/out around
    moonrise/moonset)."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/moon-path/GIS", params={"date": "2026-07-14"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-07-14"
    assert len(body["points"]) == 96  # 24h at 15-minute resolution, no daylight filter
    assert any(p["elevation_deg"] <= 0 for p in body["points"])  # proves it isn't silently daylight-filtered
    times = [p["time"] for p in body["points"]]
    assert times == sorted(times)


def test_get_moon_path_defaults_to_today(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/moon-path/GIS", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_get_moon_path_rejects_malformed_date(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/moon-path/GIS", params={"date": "not-a-date"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_get_moon_path_unknown_zone_returns_404(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/moon-path/Nowhere", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
