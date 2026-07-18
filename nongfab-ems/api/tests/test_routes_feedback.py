from fastapi.testclient import TestClient


def test_post_feedback_requires_login(app):
    with TestClient(app) as client:
        resp = client.post("/feedback", json={"text": "hello"})
    assert resp.status_code == 401


def test_viewer_can_submit_feedback(app, token_factory):
    token = token_factory("viewer", username="pttlng")
    with TestClient(app) as client:
        resp = client.post("/feedback", json={"text": "เว็บใช้งานดีค่ะ"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "เว็บใช้งานดีค่ะ"
    assert body["username"] == "pttlng"
    assert body["role"] == "viewer"
    assert "id" in body and "created_at" in body


def test_blank_feedback_is_rejected(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.post("/feedback", json={"text": "   "}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_viewer_cannot_list_feedback(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/feedback", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_admin_can_list_submitted_feedback(app, token_factory):
    viewer_token = token_factory("viewer", username="pttlng")
    admin_token = token_factory("admin", username="boss")
    with TestClient(app) as client:
        client.post("/feedback", json={"text": "first"}, headers={"Authorization": f"Bearer {viewer_token}"})
        client.post("/feedback", json={"text": "second"}, headers={"Authorization": f"Bearer {viewer_token}"})
        resp = client.get("/feedback", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    texts = [item["text"] for item in resp.json()]
    assert texts == ["second", "first"]  # newest first
