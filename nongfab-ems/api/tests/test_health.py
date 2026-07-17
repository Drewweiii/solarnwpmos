from fastapi.testclient import TestClient

from nongfab_api.main import app, create_app


def test_healthz_returns_ok():
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_version_returns_the_process_deploy_id_unauthenticated():
    client = TestClient(app)
    resp = client.get("/version")
    assert resp.status_code == 200
    assert resp.json() == {"deploy_id": app.state.deploy_id}


def test_version_deploy_id_is_fresh_per_process_start():
    # Each create_app() call is meant to model a fresh process start (e.g. a
    # Railway redeploy) - a new random deploy_id each time is exactly what
    # makes every previously-issued token invalid afterwards (see auth.py's
    # decode_access_token and web/lib/deployWatch.ts).
    other_app = create_app()
    assert other_app.state.deploy_id != app.state.deploy_id
