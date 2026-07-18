import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def test_ws_chat_rejects_missing_token(app):
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/chat"):
            pass


def test_ws_chat_rejects_invalid_token(app):
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/chat?token=garbage"):
            pass


def test_ws_chat_sends_history_and_presence_on_connect(app, token_factory):
    token = token_factory("viewer", username="pttlng")
    with TestClient(app) as client, client.websocket_connect(f"/ws/chat?token={token}") as ws:
        history = ws.receive_json()
        presence = ws.receive_json()
    assert history == {"type": "history", "messages": []}
    assert presence["type"] == "presence"
    assert presence["count"] == 1
    assert presence["usernames"] == ["pttlng"]


def test_ws_chat_broadcasts_a_sent_message_back_to_the_sender(app, token_factory):
    token = token_factory("viewer", username="pttlng")
    with TestClient(app) as client, client.websocket_connect(f"/ws/chat?token={token}") as ws:
        ws.receive_json()  # history
        ws.receive_json()  # presence
        ws.send_json({"text": "สวัสดีค่ะ"})
        message = ws.receive_json()
    assert message["type"] == "message"
    assert message["text"] == "สวัสดีค่ะ"
    assert message["username"] == "pttlng"
    assert message["role"] == "viewer"
    assert "id" in message and "created_at" in message


def test_ws_chat_broadcasts_between_two_connected_clients(app, token_factory):
    token_a = token_factory("viewer", username="alice")
    token_b = token_factory("admin", username="bob")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token_a}") as ws_a:
            ws_a.receive_json()  # history
            ws_a.receive_json()  # presence (self)
            with client.websocket_connect(f"/ws/chat?token={token_b}") as ws_b:
                ws_b.receive_json()  # history (now includes nothing yet)
                ws_b.receive_json()  # presence (self, count 2)
                ws_a.receive_json()  # presence update from bob joining

                ws_a.send_json({"text": "hello from alice"})
                seen_by_a = ws_a.receive_json()
                seen_by_b = ws_b.receive_json()
    assert seen_by_a["text"] == "hello from alice"
    assert seen_by_b == seen_by_a


def test_ws_chat_ignores_blank_and_malformed_messages(app, token_factory):
    token = token_factory("viewer", username="pttlng")
    with TestClient(app) as client, client.websocket_connect(f"/ws/chat?token={token}") as ws:
        ws.receive_json()  # history
        ws.receive_json()  # presence
        ws.send_text("not json at all")
        ws.send_json({"text": "   "})
        ws.send_json({"text": "real message"})
        message = ws.receive_json()
    assert message["text"] == "real message"


def test_ws_chat_replays_recent_history_to_a_new_connection(app, token_factory):
    token = token_factory("viewer", username="pttlng")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token}") as ws:
            ws.receive_json()  # history (empty)
            ws.receive_json()  # presence
            ws.send_json({"text": "first message"})
            ws.receive_json()  # broadcast of own message

        with client.websocket_connect(f"/ws/chat?token={token}") as ws2:
            history = ws2.receive_json()
    assert history["type"] == "history"
    assert [m["text"] for m in history["messages"]] == ["first message"]
