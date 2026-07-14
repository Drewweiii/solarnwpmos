import pytest
from fastapi.testclient import TestClient

from nongfab_simulation.api import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_simulate_rejects_unknown_zone(client):
    resp = client.post("/simulate/Nowhere", json={})
    assert resp.status_code == 404
    assert "unknown zone" in resp.json()["detail"]


def test_simulate_baseline_scenario_returns_24_points(client):
    resp = client.post("/simulate/GIS", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["zone"] == "GIS"
    assert body["simulated_zone"] is False
    assert len(body["points"]) == 24
    # baseline == adjusted when no scenario deltas are given
    for point in body["points"]:
        assert point["baseline_ac_kw"] == pytest.approx(point["adjusted_ac_kw"])
        assert point["lower"] is None
        assert point["upper"] is None


def test_simulate_marks_jetty_as_simulated_zone(client):
    resp = client.post("/simulate/Jetty", json={})
    assert resp.status_code == 200
    assert resp.json()["simulated_zone"] is True


def test_simulate_jetty_has_higher_soiling_loss_than_gis(client):
    jetty = client.post("/simulate/Jetty", json={}).json()
    gis = client.post("/simulate/GIS", json={}).json()
    assert jetty["loss_breakdown"]["soiling_pct"] > gis["loss_breakdown"]["soiling_pct"]


def test_simulate_curtailment_reduces_adjusted_power(client):
    resp = client.post("/simulate/ISB", json={"curtailment_pct": 50.0})
    body = resp.json()
    for point in body["points"]:
        assert point["adjusted_ac_kw"] <= point["baseline_ac_kw"] + 1e-6


def test_simulate_with_monte_carlo_returns_interval(client):
    resp = client.post("/simulate/GIS", json={"extra_cloud_attenuation_std_pct": 15.0, "monte_carlo_n_samples": 200})
    body = resp.json()
    for point in body["points"]:
        assert point["lower"] is not None
        assert point["upper"] is not None
        assert point["lower"] <= point["upper"] + 1e-6


def test_simulate_without_uncertainty_std_omits_interval(client):
    # no *_std_pct field set -> no Monte Carlo run, lower/upper stay null
    resp = client.post("/simulate/GIS", json={"curtailment_pct": 10.0})
    body = resp.json()
    for point in body["points"]:
        assert point["lower"] is None
        assert point["upper"] is None


def test_simulate_rejects_invalid_scenario_params_with_422(client):
    resp = client.post("/simulate/GIS", json={"curtailment_pct": 150.0})
    assert resp.status_code == 422
    assert "curtailment_pct" in resp.json()["detail"]


def test_simulate_compare_returns_one_series_per_scenario(client):
    resp = client.post(
        "/simulate/GIS/compare",
        json={"scenarios": {"typical": {}, "cloudy_day": {"extra_cloud_attenuation_pct": 40.0}, "curtailed": {"curtailment_pct": 30.0}}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["zone"] == "GIS"
    assert set(body["series_kw"]) == {"typical", "cloudy_day", "curtailed"}
    assert len(body["timestamps"]) == 24
    for series in body["series_kw"].values():
        assert len(series) == 24

    # cloudy_day should produce less energy than typical at every hour
    typical = body["series_kw"]["typical"]
    cloudy = body["series_kw"]["cloudy_day"]
    assert all(c <= t + 1e-6 for c, t in zip(cloudy, typical))


def test_simulate_compare_rejects_empty_scenarios_with_422(client):
    resp = client.post("/simulate/GIS/compare", json={"scenarios": {}})
    assert resp.status_code == 422


def test_simulate_compare_rejects_unknown_zone(client):
    resp = client.post("/simulate/Nowhere/compare", json={"scenarios": {"typical": {}}})
    assert resp.status_code == 404


def test_simulate_gis_ac_power_never_exceeds_inverter_capacity(client):
    # GIS DC/AC ratio 1.20 -> clipping should keep AC output <= 50kW even at midday peak
    resp = client.post("/simulate/GIS", json={})
    body = resp.json()
    assert all(point["baseline_ac_kw"] <= 50.0 + 1e-6 for point in body["points"])


def test_simulate_loss_breakdown_has_expected_keys(client):
    resp = client.post("/simulate/ISB", json={})
    breakdown = resp.json()["loss_breakdown"]
    assert set(breakdown) == {
        "soiling_pct", "shading_pct", "mismatch_pct", "dc_wiring_pct",
        "connections_pct", "availability_pct", "inverter_loss_pct", "total_system_loss_pct",
    }
