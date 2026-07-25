"""Integration tests for GET /savings/summary."""

from fastapi.testclient import TestClient


def test_savings_summary_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/savings/summary")
    assert resp.status_code == 401


def test_savings_summary_has_three_zones_plus_combined(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/savings/summary", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    ids = [z["zone"] for z in body["zones"]]
    assert ids == ["ISB", "GIS", "Jetty", "combined"]


def test_combined_energy_equals_sum_of_zones(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/savings/summary", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    zones = {z["zone"]: z for z in body["zones"]}
    for horizon in ("day", "month", "year", "lifetime"):
        parts = sum(zones[z]["periods"][horizon]["energy_kwh"] for z in ("ISB", "GIS", "Jetty"))
        assert zones["combined"]["periods"][horizon]["energy_kwh"] == parts
        assert zones["combined"]["dc_capacity_kwp"] == sum(
            zones[z]["dc_capacity_kwp"] for z in ("ISB", "GIS", "Jetty")
        )


def test_lifetime_energy_exceeds_annual_but_less_than_flat_25x(app, token_factory):
    # Degradation means 25-yr < 25 * year-1, but still > one year.
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/savings/summary", headers={"Authorization": f"Bearer {token}"})
    combined = [z for z in resp.json()["zones"] if z["zone"] == "combined"][0]
    year = combined["periods"]["year"]["energy_kwh"]
    lifetime = combined["periods"]["lifetime"]["energy_kwh"]
    assert year < lifetime < 25 * year


def test_assumptions_present(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/savings/summary", headers={"Authorization": f"Bearer {token}"})
    a = resp.json()["assumptions"]
    assert a["ugt2_portfolio"] == "Portfolio A"
    assert a["ef_scope2_kg_per_kwh"] == 0.4758
