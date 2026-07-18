from fastapi.testclient import TestClient

from nongfab_api.auth import DEMO_USERS


def test_login_with_demo_credentials_returns_bearer_token(app):
    with TestClient(app) as client:
        resp = client.post("/auth/token", data={"username": "admin", "password": "admin-demo-pw"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_token_authorizes_requests(app):
    with TestClient(app) as client:
        token = client.post("/auth/token", data={"username": "pttlng", "password": "12345"}).json()["access_token"]
        resp = client.get("/assets", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_login_wrong_password_returns_401(app):
    with TestClient(app) as client:
        resp = client.post("/auth/token", data={"username": "admin", "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_unknown_username_returns_401(app):
    with TestClient(app) as client:
        resp = client.post("/auth/token", data={"username": "nobody", "password": "whatever"})
    assert resp.status_code == 401


def test_all_demo_users_can_log_in(app):
    with TestClient(app) as client:
        for username, password, _role in DEMO_USERS:
            resp = client.post("/auth/token", data={"username": username, "password": password})
            assert resp.status_code == 200, f"{username} failed to log in"
