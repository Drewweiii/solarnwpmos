import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def test_ws_chat_rejects_missing_token(app):
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/chat?client_id=a"):
            pass


def test_ws_chat_rejects_invalid_token(app):
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/chat?token=garbage&client_id=a"):
            pass


def test_ws_chat_rejects_missing_client_id(app, token_factory):
    token = token_factory("viewer", username="pttlng")
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/chat?token={token}"):
            pass


def test_ws_chat_sends_online_users_on_connect(app, token_factory):
    token = token_factory("viewer", username="pttlng")
    with TestClient(app) as client, client.websocket_connect(
        f"/ws/chat?token={token}&client_id=alice-browser&display_name=Alice&avatar=cat"
    ) as ws:
        online = ws.receive_json()
    assert online == {"type": "online_users", "users": [{"client_id": "alice-browser", "display_name": "Alice", "avatar": "cat", "role": "viewer"}]}


def test_ws_chat_falls_back_to_username_when_no_display_name_given_at_connect(app, token_factory):
    token = token_factory("viewer", username="pttlng")
    with TestClient(app) as client, client.websocket_connect(f"/ws/chat?token={token}&client_id=alice-browser") as ws:
        online = ws.receive_json()
    assert online["users"] == [{"client_id": "alice-browser", "display_name": "pttlng", "avatar": None, "role": "viewer"}]


def test_ws_chat_prefixes_admin_display_name_in_the_online_list(app, token_factory):
    token = token_factory("admin", username="boss")
    with TestClient(app) as client, client.websocket_connect(
        f"/ws/chat?token={token}&client_id=admin-browser&display_name=สมชาย"
    ) as ws:
        online = ws.receive_json()
    assert online["users"][0]["display_name"] == "admin สมชาย"


def test_ws_chat_a_message_is_only_delivered_to_sender_and_recipient_not_broadcast_to_everyone(app, token_factory):
    token_a = token_factory("viewer", username="alice")
    token_b = token_factory("admin", username="bob")
    token_c = token_factory("viewer", username="carol")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token_a}&client_id=a&display_name=Alice") as ws_a:
            ws_a.receive_json()  # online_users (self)
            with client.websocket_connect(f"/ws/chat?token={token_b}&client_id=b&display_name=Bob") as ws_b:
                ws_b.receive_json()  # online_users (a+b)
                ws_a.receive_json()  # online_users update from b joining
                with client.websocket_connect(f"/ws/chat?token={token_c}&client_id=c&display_name=Carol") as ws_c:
                    ws_c.receive_json()  # online_users (a+b+c)
                    ws_a.receive_json()  # online_users update from c joining
                    ws_b.receive_json()  # online_users update from c joining

                    ws_a.send_json({"text": "hi bob, just us", "recipient_client_id": "b"})
                    seen_by_a = ws_a.receive_json()
                    seen_by_b = ws_b.receive_json()

                    # Carol (not a participant) must NOT receive it - this is
                    # the actual privacy property, not just a UI filter.
                    ws_c.send_json({"text": "are you there?", "recipient_client_id": "a"})
                    carol_probe = ws_c.receive_json()
    assert seen_by_a["text"] == "hi bob, just us"
    assert seen_by_a == seen_by_b
    assert seen_by_a["recipient_client_id"] == "b"
    assert seen_by_a["client_id"] == "a"
    # Carol's own message to alice went through fine (proves the socket
    # wasn't just broken), but her identity/traffic never touched bob's
    # conversation with alice above.
    assert carol_probe["text"] == "are you there?"


def test_ws_chat_delivers_to_every_tab_of_the_same_browser(app, token_factory):
    token = token_factory("viewer", username="alice")
    peer_token = token_factory("viewer", username="bob")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token}&client_id=a&display_name=Alice") as tab1:
            tab1.receive_json()  # online_users
            with client.websocket_connect(f"/ws/chat?token={token}&client_id=a&display_name=Alice") as tab2:
                tab2.receive_json()  # online_users
                tab1.receive_json()  # online_users update (still just "a", dedup'd, but re-broadcast)
                with client.websocket_connect(f"/ws/chat?token={peer_token}&client_id=b&display_name=Bob") as ws_b:
                    ws_b.receive_json()
                    tab1.receive_json()
                    tab2.receive_json()

                    ws_b.send_json({"text": "hello alice", "recipient_client_id": "a"})
                    seen_by_tab1 = tab1.receive_json()
                    seen_by_tab2 = tab2.receive_json()
    assert seen_by_tab1["text"] == "hello alice"
    assert seen_by_tab1 == seen_by_tab2


def test_ws_chat_ignores_a_message_with_no_recipient(app, token_factory):
    token_a = token_factory("viewer", username="alice")
    token_b = token_factory("viewer", username="bob")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token_a}&client_id=a") as ws_a:
            ws_a.receive_json()
            with client.websocket_connect(f"/ws/chat?token={token_b}&client_id=b") as ws_b:
                ws_b.receive_json()
                ws_a.receive_json()

                ws_a.send_json({"text": "no recipient set"})  # dropped - no public broadcast anymore
                ws_a.send_json({"text": "now with a recipient", "recipient_client_id": "b"})
                message = ws_b.receive_json()
    assert message["text"] == "now with a recipient"


def test_ws_chat_ignores_blank_and_malformed_messages(app, token_factory):
    token_a = token_factory("viewer", username="alice")
    token_b = token_factory("viewer", username="bob")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token_a}&client_id=a") as ws_a:
            ws_a.receive_json()
            with client.websocket_connect(f"/ws/chat?token={token_b}&client_id=b") as ws_b:
                ws_b.receive_json()
                ws_a.receive_json()

                ws_a.send_text("not json at all")
                ws_a.send_json({"text": "   ", "recipient_client_id": "b"})
                ws_a.send_json({"text": "real message", "recipient_client_id": "b"})
                message = ws_b.receive_json()
    assert message["text"] == "real message"


def test_ws_chat_update_profile_changes_the_online_list_live(app, token_factory):
    token_a = token_factory("viewer", username="alice")
    token_b = token_factory("viewer", username="bob")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token_a}&client_id=a&display_name=Alice&avatar=cat") as ws_a:
            ws_a.receive_json()
            with client.websocket_connect(f"/ws/chat?token={token_b}&client_id=b&display_name=Bob") as ws_b:
                ws_b.receive_json()
                ws_a.receive_json()

                ws_a.send_json({"type": "update_profile", "display_name": "Alice Updated", "avatar": "fox"})
                updated_seen_by_a = ws_a.receive_json()
                updated_seen_by_b = ws_b.receive_json()

    updated_alice = next(u for u in updated_seen_by_b["users"] if u["client_id"] == "a")
    assert updated_alice["display_name"] == "Alice Updated"
    assert updated_alice["avatar"] == "fox"
    assert updated_seen_by_a == updated_seen_by_b


def test_ws_chat_admin_prefix_cannot_be_stripped_by_the_client_on_update_profile(app, token_factory):
    token = token_factory("admin", username="boss")
    with TestClient(app) as client, client.websocket_connect(f"/ws/chat?token={token}&client_id=admin-browser") as ws:
        ws.receive_json()
        ws.send_json({"type": "update_profile", "display_name": "not prefixed"})
        online = ws.receive_json()
    assert online["users"][0]["display_name"] == "admin not prefixed"


def test_online_users_removes_a_client_on_disconnect(app, token_factory):
    token_a = token_factory("viewer", username="alice")
    token_b = token_factory("viewer", username="bob")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token_a}&client_id=a") as ws_a:
            ws_a.receive_json()
            with client.websocket_connect(f"/ws/chat?token={token_b}&client_id=b") as ws_b:
                ws_b.receive_json()
                joined = ws_a.receive_json()
            left = ws_a.receive_json()
    assert {u["client_id"] for u in joined["users"]} == {"a", "b"}
    assert {u["client_id"] for u in left["users"]} == {"a"}


def test_get_chat_history_returns_the_conversation_between_two_client_ids(app, token_factory):
    token_a = token_factory("viewer", username="alice")
    token_b = token_factory("viewer", username="bob")
    token_c = token_factory("viewer", username="carol")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token_a}&client_id=a") as ws_a:
            ws_a.receive_json()
            with client.websocket_connect(f"/ws/chat?token={token_b}&client_id=b") as ws_b:
                ws_b.receive_json()
                ws_a.receive_json()
                with client.websocket_connect(f"/ws/chat?token={token_c}&client_id=c") as ws_c:
                    ws_c.receive_json()
                    ws_a.receive_json()
                    ws_b.receive_json()

                    ws_a.send_json({"text": "to bob", "recipient_client_id": "b"})
                    ws_a.receive_json()
                    ws_b.receive_json()
                    ws_a.send_json({"text": "to carol, unrelated", "recipient_client_id": "c"})
                    ws_a.receive_json()
                    ws_c.receive_json()
                    ws_b.send_json({"text": "reply to alice", "recipient_client_id": "a"})
                    ws_a.receive_json()
                    ws_b.receive_json()

        resp = client.get("/chat/history?my_client_id=a&peer_client_id=b", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    texts = [m["text"] for m in resp.json()["messages"]]
    assert texts == ["to bob", "reply to alice"]  # not "to carol" - that's a different conversation


def test_get_chat_history_pages_older_messages_within_one_conversation(app, token_factory):
    token_a = token_factory("viewer", username="alice")
    token_b = token_factory("viewer", username="bob")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token_a}&client_id=a") as ws_a:
            ws_a.receive_json()
            with client.websocket_connect(f"/ws/chat?token={token_b}&client_id=b") as ws_b:
                ws_b.receive_json()
                ws_a.receive_json()
                for text in ("one", "two", "three"):
                    ws_a.send_json({"text": text, "recipient_client_id": "b"})
                    last = ws_a.receive_json()
                    ws_b.receive_json()

        resp = client.get(
            f"/chat/history?my_client_id=a&peer_client_id=b&before_id={last['id']}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
    assert resp.status_code == 200
    texts = [m["text"] for m in resp.json()["messages"]]
    assert texts == ["one", "two"]


def test_get_chat_history_requires_login(app):
    with TestClient(app) as client:
        resp = client.get("/chat/history?my_client_id=a&peer_client_id=b")
    assert resp.status_code == 401


def test_message_created_at_carries_a_utc_offset_not_a_naive_timestamp(app, token_factory):
    """Regression test (2026-07-18) - see models.as_utc's docstring and
    test_routes_feedback.py's matching test: the SQLite-backed test `app`
    reads a stored tz-aware datetime back as tz-naive, which used to
    serialize `created_at` with no UTC offset and get silently misread as
    local time by a browser's `new Date(...)`.
    """
    token_a = token_factory("viewer", username="alice")
    token_b = token_factory("viewer", username="bob")
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token_a}&client_id=a") as ws_a:
            ws_a.receive_json()
            with client.websocket_connect(f"/ws/chat?token={token_b}&client_id=b") as ws_b:
                ws_b.receive_json()
                ws_a.receive_json()
                ws_a.send_json({"text": "hi", "recipient_client_id": "b"})
                message = ws_a.receive_json()
    assert "+00:00" in message["created_at"]
