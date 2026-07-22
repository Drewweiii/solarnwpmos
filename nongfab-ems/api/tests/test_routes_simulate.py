from fastapi.testclient import TestClient


def test_simulate_requires_auth(app):
    with TestClient(app) as client:
        resp = client.post("/simulate/GIS", json={})
    assert resp.status_code == 401


def test_simulate_rejects_viewer_role(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.post("/simulate/GIS", json={}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_simulate_allows_operator_role(app, token_factory):
    token = token_factory("operator")
    with TestClient(app) as client:
        resp = client.post("/simulate/GIS", json={}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["zone"] == "GIS"
    assert body["simulated_zone"] is False
    assert len(body["points"]) == 24
    assert all(p["lower"] is None for p in body["points"])
    # The app fixture's store is an empty :memory: one, so no real NWP exists
    # for today - the baseline falls back to the synthetic generator and the
    # route labels that honestly (see api/baseline.py).
    assert body["data_source"] == "synthetic"


def test_simulate_allows_admin_role(app, token_factory):
    token = token_factory("admin")
    with TestClient(app) as client:
        resp = client.post("/simulate/GIS", json={}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_simulate_unknown_zone_returns_404(app, token_factory):
    token = token_factory("operator")
    with TestClient(app) as client:
        resp = client.post("/simulate/Nowhere", json={}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_simulate_rejects_invalid_curtailment(app, token_factory):
    token = token_factory("operator")
    with TestClient(app) as client:
        resp = client.post(
            "/simulate/GIS", json={"curtailment_pct": 150}, headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 422


def test_simulate_with_uncertainty_returns_monte_carlo_bounds(app, token_factory):
    token = token_factory("operator")
    with TestClient(app) as client:
        resp = client.post(
            "/simulate/GIS",
            json={"extra_cloud_attenuation_std_pct": 10.0, "monte_carlo_n_samples": 50},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert all(p["lower"] is not None and p["upper"] is not None for p in points)
    assert all(p["lower"] <= p["upper"] for p in points)
    assert any(p["lower"] > 0 for p in points)  # daytime hours should show a meaningful spread


def test_simulate_jetty_reports_simulated_zone_true(app, token_factory):
    token = token_factory("operator")
    with TestClient(app) as client:
        resp = client.post("/simulate/Jetty", json={}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["simulated_zone"] is True
