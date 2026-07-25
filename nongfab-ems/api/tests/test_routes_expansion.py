"""GET /expansion (2026-07-25) - the planned phases priced against the terminal's
own real load and implied tariff."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_expansion_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/expansion").status_code == 401


def test_expansion_reports_the_real_planned_phases_with_marginal_figures(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/expansion", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True

    # The baseline plus config/assets.yaml's real Jetty phases (1.5 and 2).
    labels = [s["phase"] for s in body["scenarios"]]
    assert labels[0] is None
    assert "1.5" in labels and "2" in labels

    baseline, *phases = body["scenarios"]
    # Today's plant: 400 kW AC across the three zones.
    assert baseline["ac_capacity_kw"] == 400
    assert baseline["annual_energy_kwh"] > 0
    assert baseline["marginal_ac_capacity_kw"] is None
    assert baseline["capex_estimate_thb"] is None

    # Capacity accumulates to the documented 800 kW end state (400 + 100 + 300).
    assert phases[-1]["ac_capacity_kw"] == 800
    for phase in phases:
        assert phase["marginal_ac_capacity_kw"] > 0
        assert phase["marginal_annual_energy_kwh"] > 0
        assert phase["capex_estimate_thb"] > 0
        assert phase["marginal_energy_per_kwp"] > 0


def test_expansion_prices_against_the_facilitys_own_implied_tariff(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/expansion", headers={"Authorization": f"Bearer {token}"}).json()

    # The real user-stated load, and a tariff derived from it plus the real annual
    # cost - NOT the financial module's placeholder 4.0 THB/kWh.
    assert body["facility_load_kw"] == 13500
    tariff = body["implied_tariff_thb_per_kwh"]
    assert 2.0 < tariff < 3.5
    assert tariff != 4.0

    baseline = body["scenarios"][0]
    assert baseline["annual_bill_saving_thb"] > 0
    assert baseline["solar_offset_pct"] > 0
    # 400 kW against a 13.5 MW load: well under 1%, which is the point.
    assert baseline["solar_offset_pct"] < 1


def test_expansion_shows_what_a_meaningful_offset_would_actually_take(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/expansion", headers={"Authorization": f"Bearer {token}"}).json()

    targets = {t["target_offset_pct"]: t for t in body["targets"]}
    assert set(targets) == {5.0, 10.0, 25.0}
    # Each target needs many times today's capacity, and more for a bigger target.
    assert targets[5.0]["times_current_capacity"] > 1
    assert targets[25.0]["required_dc_capacity_kwp"] > targets[5.0]["required_dc_capacity_kwp"]


def test_expansion_flags_the_capex_placeholder_and_the_scaling_method(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/expansion", headers={"Authorization": f"Bearer {token}"}).json()
    assert body["capex_per_kwp_thb"] == 30000
    assert "placeholder" in body["capex_note"]
    assert "ขยายตามสัดส่วน" in body["method_note"]
