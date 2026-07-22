import pytest
from fastapi.testclient import TestClient


def test_get_energy_report_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/energy-report/GIS")
    assert resp.status_code == 401


def test_get_energy_report_unknown_zone_returns_404(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/Nowhere", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_get_energy_report_gis_system_summary_matches_assets(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/GIS", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["zone"] == "GIS"
    assert body["simulated_zone"] is False
    summary = body["system_summary"]
    assert summary["ac_capacity_kw"] == 50
    assert summary["dc_capacity_kwp"] == 60.06
    assert summary["module_count"] == 84
    assert summary["array_area_m2"] > 0


def test_get_energy_report_annual_figures_are_positive(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/GIS", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["annual"]["ac_energy_kwh"] > 0
    assert body["annual"]["specific_yield_kwh_per_kwp"] > 0
    assert 0 < body["annual"]["performance_ratio"] <= 1.0


def test_get_energy_report_annual_equals_sum_of_monthly_chart(app, token_factory):
    # The 2026-07-22 seasonal-annual fix: the headline annual figure is now the
    # sum of the 12 monthly estimates shown right below it, not a x365 of one
    # clear-sky day that silently disagreed with the chart.
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/GIS", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["annual"]["ac_energy_kwh"] == pytest.approx(sum(m["ac_energy_kwh"] for m in body["monthly"]))


def test_get_energy_report_loss_breakdown_includes_temperature(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/GIS", headers={"Authorization": f"Bearer {token}"})
    breakdown = resp.json()["loss_breakdown_pct"]
    for key in ("temperature_pct", "soiling_pct", "shading_pct", "mismatch_pct", "dc_wiring_pct", "inverter_loss_pct", "total_system_loss_pct"):
        assert key in breakdown


def test_get_energy_report_jetty_has_higher_soiling_than_gis(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        gis = client.get("/energy-report/GIS", headers={"Authorization": f"Bearer {token}"}).json()
        jetty = client.get("/energy-report/Jetty", headers={"Authorization": f"Bearer {token}"}).json()
    assert jetty["loss_breakdown_pct"]["soiling_pct"] > gis["loss_breakdown_pct"]["soiling_pct"]
    assert jetty["simulated_zone"] is True


def test_get_energy_report_co2_saved_matches_environmental_constant(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/GIS", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    # 50 kW * 901 kg/kW/year (config/assets.yaml environmental block)
    assert body["co2_saved_kg_per_year"] == 50 * 901


def test_get_energy_report_sld_totals_match_module_count(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/ISB", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    sld = body["sld"]
    total = sum(s["modules"] for block in sld["blocks"] for s in block["strings"])
    assert total == body["system_summary"]["module_count"] == 196
    assert sld["approximate_string_distribution"] is True


def test_get_energy_report_jetty_sld_uses_real_sub_array_ids(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/Jetty", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    block_ids = {b["id"] for b in body["sld"]["blocks"]}
    assert block_ids == {"01A.L", "02A.L", "03A.R", "04A.R"}
    assert body["sld"]["approximate_string_distribution"] is False


def test_get_energy_report_avg_solar_access_pct_in_valid_range(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/GIS", headers={"Authorization": f"Bearer {token}"})
    assert 0 <= resp.json()["avg_solar_access_pct"] <= 100


def test_get_energy_report_monthly_has_12_months_with_rainy_season_flagged(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/GIS", headers={"Authorization": f"Bearer {token}"})
    monthly = resp.json()["monthly"]
    assert [m["month"] for m in monthly] == list(range(1, 13))
    assert all(m["ac_energy_kwh"] > 0 for m in monthly)
    rainy_months = {m["month"] for m in monthly if m["is_rainy_season"]}
    assert rainy_months == {6, 7, 8, 9, 10}


def test_get_energy_report_lifecycle_year_25_is_less_than_year_1(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/energy-report/GIS", headers={"Authorization": f"Bearer {token}"})
    lifecycle = resp.json()["lifecycle"]
    assert lifecycle["year_1_ac_energy_kwh"] == pytest.approx(resp.json()["annual"]["ac_energy_kwh"])
    assert lifecycle["year_25_ac_energy_kwh"] < lifecycle["year_1_ac_energy_kwh"]
    assert 0 < lifecycle["year_25_pct_of_year_1"] < 100
    assert lifecycle["lifetime_ac_energy_kwh"] > lifecycle["year_1_ac_energy_kwh"]
