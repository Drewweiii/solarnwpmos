"""Regression test for a real bug caught during Module 7's live browser
verification: the dashboard (a different origin - its own Vite dev server
port) couldn't call this API at all because no CORS policy was configured,
so the browser silently blocked every request before it reached any route.
"""

from fastapi.testclient import TestClient


def test_preflight_allows_the_configured_dashboard_origin(app):
    with TestClient(app) as client:
        resp = client.options(
            "/assets",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_actual_response_carries_cors_header_for_allowed_origin(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/assets", headers={"Authorization": f"Bearer {token}", "Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_response_omits_cors_header_for_a_disallowed_origin(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/assets", headers={"Authorization": f"Bearer {token}", "Origin": "http://evil.example"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
