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


def test_feedback_created_at_carries_a_utc_offset_not_a_naive_timestamp(app, token_factory):
    """Regression test (2026-07-18): the test `app` fixture's SQLite backend
    reads a stored tz-aware datetime back as tz-naive (confirmed directly -
    see models.as_utc's docstring), which used to serialize `created_at`
    with no UTC offset - a browser's `new Date(...)` then silently
    misreads it as local time, shifting every feedback timestamp by the
    viewer's UTC offset. Both POST's own response and GET /feedback's list
    must carry an explicit offset (`+00:00`) so this can never regress.
    """
    token = token_factory("viewer", username="pttlng")
    admin_token = token_factory("admin", username="boss")
    with TestClient(app) as client:
        post_resp = client.post("/feedback", json={"text": "hi"}, headers={"Authorization": f"Bearer {token}"})
        list_resp = client.get("/feedback", headers={"Authorization": f"Bearer {admin_token}"})
    assert post_resp.json()["created_at"].endswith(("Z", "+00:00"))
    assert list_resp.json()[0]["created_at"].endswith(("Z", "+00:00"))
