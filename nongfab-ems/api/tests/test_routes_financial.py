import pytest
from fastapi.testclient import TestClient


def test_financial_requires_auth(app):
    with TestClient(app) as client:
        resp = client.post("/financial", json={})
    assert resp.status_code == 401


def test_financial_rejects_viewer_role(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.post("/financial", json={}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_financial_allows_operator_role_with_default_assumptions(app, token_factory):
    token = token_factory("operator")
    with TestClient(app) as client:
        resp = client.post("/financial", json={}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["installed_dc_capacity_kwp"] > 0
    assert body["year_1_ac_energy_kwh"] > 0
    assert body["capex_thb"] > 0
    assert body["lcoe_thb_per_kwh"] > 0
    assert len(body["cash_flows"]) == 25  # LIFETIME_YEARS default
    assert body["cash_flows"][0]["year"] == 1
    assert body["cash_flows"][-1]["year"] == 25


def test_financial_allows_admin_role(app, token_factory):
    token = token_factory("admin")
    with TestClient(app) as client:
        resp = client.post("/financial", json={}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_financial_only_counts_installed_zones_not_jetty(app, token_factory):
    # GIS (60.06 kWp) + ISB (140.14 kWp) = 200.2 kWp - Jetty is design-mode
    # (no panels installed yet, simulated: true in config/assets.yaml) and
    # should NOT contribute to the capacity/energy basis - see
    # routes_financial.py's own docstring.
    token = token_factory("operator")
    with TestClient(app) as client:
        resp = client.post("/financial", json={}, headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["installed_dc_capacity_kwp"] == pytest.approx(60.06 + 140.14, rel=1e-3)


def test_financial_accepts_overrides(app, token_factory):
    token = token_factory("operator")
    with TestClient(app) as client:
        resp = client.post(
            "/financial",
            json={"capex_thb": 6_000_000.0, "tariff_thb_per_kwh": 5.0, "boi_tax_holiday_years": 3},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["capex_thb"] == 6_000_000.0
    for cf in body["cash_flows"][:3]:
        assert cf["tax_thb"] == 0.0


def test_financial_rejects_invalid_assumptions_with_422(app, token_factory):
    token = token_factory("operator")
    with TestClient(app) as client:
        resp = client.post("/financial", json={"tax_rate_pct": 500.0}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_the_boi_presets_come_from_settings_not_from_hardcoded_ui_numbers(app, token_factory):
    """The /financial page shows one-click 8-year / 12-year buttons for the
    project's confirmed BOI holidays. They are served from here rather than
    hardcoded in the UI so that editing the figure in Settings moves the button
    with it - a preset that disagrees with the published setting is worse than
    no preset at all."""
    token = token_factory("operator")
    with TestClient(app) as client:
        body = client.post("/financial", json={}, headers={"Authorization": f"Bearer {token}"}).json()

    years = [preset["years"] for preset in body["boi_presets"]]
    assert years == [8, 12]
    assert "พื้นที่ทั่วไป" in body["boi_presets"][0]["label"]
    assert "Jetty" in body["boi_presets"][1]["label"]


def test_identical_holidays_collapse_to_one_preset(monkeypatch):
    """If the Jetty ever matched the general area there would be two buttons
    saying the same thing, which reads like a bug to anyone looking at it."""
    from nongfab_api import routes_financial, settings_store

    monkeypatch.setattr(settings_store, "effective", lambda key: 8.0)
    presets = routes_financial._boi_presets()

    assert len(presets) == 1
    assert presets[0].years == 8
