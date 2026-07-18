"""WebSocket /ws/chat - private 1:1 messaging between visitors, plus an
online-visitor list so a client can actually pick who to talk to. Auth: JWT
via `?token=`, same pattern as ws_live.py (browser WebSocket clients can't
set a handshake Authorization header).

**Not a public/open chat room** (changed 2026-07-18, at the user's explicit
request - the previous version broadcast every message to every connected
client, "openchat" style, which they flagged as a real privacy problem, not
just a UX one). Every message now names a `recipient_client_id` and is only
ever delivered - both the live WebSocket push and the persisted row - to the
two participants' own sockets. There is no server code path left that fans a
message out to everyone; `ConnectionManager.send_to_client()` is the only
delivery primitive, used twice per message (once for the sender's own other
tabs, once for the recipient).

Per-browser identity (display_name/avatar/client_id): the viewer/operator
demo logins are shared credentials (auth.py's DEMO_USERS), so `username`
alone doesn't distinguish two different real people chatting at once. The
client picks a display name/avatar for itself (chatProfile.ts) and sends it
at connect time (as WS query params - not a header, for the same reason the
JWT itself is a query param: browsers can't set custom headers on a WS
upgrade request) plus optionally per-message to reflect a same-session edit
before `update_profile` round-trips. Admin picks a name/avatar the same way
as everyone else, but whatever name they choose always gets
ADMIN_NAME_PREFIX prepended server-side (never trusted from the client to
add it themselves) - both in chat messages and in the online-users list -
so every other visitor can tell an admin apart at a glance.

Everything here is in-memory, scoped to this one API process (no cross-
process pub-sub layer - see the original module's own note on this; still
true, this deployment only ever runs one API process).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from .auth import AuthenticatedUser, decode_access_token, require_role
from .config import Settings
from .models import ChatMessageORM, as_utc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

HISTORY_LIMIT = 50
MAX_MESSAGE_LENGTH = 1000  # guards against a pathological payload bloating the DB/broadcast
MAX_PROFILE_FIELD_LENGTH = 40  # display_name/avatar id/client_id - generous but bounded

ADMIN_NAME_PREFIX = "admin "


def _resolve_display_name(user: AuthenticatedUser, raw_display_name: object) -> str:
    display_name = str(raw_display_name or user.username).strip()[:MAX_PROFILE_FIELD_LENGTH] or user.username
    if user.role == "admin":
        # Never trusted from the client to add/strip this itself - always
        # applied here, both for chat messages and the online-users list.
        display_name = f"{ADMIN_NAME_PREFIX}{display_name}"[:MAX_PROFILE_FIELD_LENGTH]
    return display_name


def _clean_field(raw: object) -> str | None:
    return str(raw).strip()[:MAX_PROFILE_FIELD_LENGTH] if raw else None


@dataclass(frozen=True)
class ChatMessage:
    id: int
    username: str
    role: str
    text: str
    created_at: datetime
    display_name: str
    avatar: str | None
    client_id: str | None
    recipient_client_id: str | None

    def to_dict(self) -> dict:
        return {
            "type": "message",
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "text": self.text,
            "created_at": self.created_at.isoformat(),
            "display_name": self.display_name,
            "avatar": self.avatar,
            "client_id": self.client_id,
            "recipient_client_id": self.recipient_client_id,
        }


def _row_to_message(row: ChatMessageORM) -> ChatMessage:
    return ChatMessage(
        id=row.id,
        username=row.username,
        role=row.role,
        text=row.text,
        created_at=as_utc(row.created_at),
        display_name=row.display_name or row.username,  # pre-migration rows have no display_name
        avatar=row.avatar,
        client_id=row.client_id,
        recipient_client_id=row.recipient_client_id,
    )


class ChatStore:
    def __init__(self, engine: AsyncEngine):
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def add_message(
        self,
        username: str,
        role: str,
        text: str,
        display_name: str,
        avatar: str | None,
        client_id: str | None,
        recipient_client_id: str | None,
    ) -> ChatMessage:
        async with self._session_factory() as session:
            row = ChatMessageORM(
                username=username,
                role=role,
                text=text,
                created_at=datetime.now(timezone.utc),
                display_name=display_name,
                avatar=avatar,
                client_id=client_id,
                recipient_client_id=recipient_client_id,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _row_to_message(row)

    async def conversation_messages(
        self, client_id_a: str, client_id_b: str, before_id: int | None = None, limit: int = HISTORY_LIMIT
    ) -> list[ChatMessage]:
        """The `limit` most recent messages exchanged between these two
        client_ids (in either direction), oldest-first - `before_id` turns
        this into a scroll-back page (strictly older than that id) instead
        of "most recent". Used by `GET /chat/history` for both the initial
        thread load (no `before_id`) and "load older messages".
        """
        async with self._session_factory() as session:
            between_this_pair = or_(
                and_(ChatMessageORM.client_id == client_id_a, ChatMessageORM.recipient_client_id == client_id_b),
                and_(ChatMessageORM.client_id == client_id_b, ChatMessageORM.recipient_client_id == client_id_a),
            )
            stmt = select(ChatMessageORM).where(between_this_pair)
            if before_id is not None:
                stmt = stmt.where(ChatMessageORM.id < before_id)
            stmt = stmt.order_by(ChatMessageORM.id.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_message(row) for row in reversed(rows)]


@dataclass
class ClientInfo:
    username: str
    role: str
    client_id: str
    display_name: str
    avatar: str | None


class ConnectionManager:
    """This process's set of live /ws/chat sockets, keyed by the raw
    WebSocket connection (one browser can have several - each tab is its own
    socket) - `online_users` dedupes those down to one entry per `client_id`
    for display, while `send_to_client` fans a payload out to *every* socket
    sharing that client_id (so a message shows up in every open tab of the
    same browser, not just the one that happened to send/receive it first).
    """

    def __init__(self) -> None:
        self._connections: dict[WebSocket, ClientInfo] = {}

    async def connect(self, websocket: WebSocket, info: ClientInfo) -> None:
        await websocket.accept()
        self._connections[websocket] = info

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    def get_identity(self, websocket: WebSocket) -> ClientInfo | None:
        return self._connections.get(websocket)

    def update_identity(self, websocket: WebSocket, display_name: str, avatar: str | None) -> None:
        info = self._connections.get(websocket)
        if info is None:
            return
        info.display_name = display_name
        info.avatar = avatar

    @property
    def online_users(self) -> list[dict]:
        by_client_id: dict[str, ClientInfo] = {}
        for info in self._connections.values():
            by_client_id[info.client_id] = info  # last-registered tab wins if the same browser has several
        return [
            {"client_id": info.client_id, "display_name": info.display_name, "avatar": info.avatar, "role": info.role}
            for info in sorted(by_client_id.values(), key=lambda i: i.display_name.lower())
        ]

    def _sockets_for_client(self, client_id: str) -> list[WebSocket]:
        return [ws for ws, info in self._connections.items() if info.client_id == client_id]

    async def send_to_client(self, client_id: str, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._sockets_for_client(client_id):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 - a broken/closing socket for one recipient shouldn't affect the other
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_online_users(self) -> None:
        payload = {"type": "online_users", "users": self.online_users}
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 - a broken/closing socket shouldn't stop the update reaching everyone else
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    settings: Settings = websocket.app.state.settings
    deploy_id: str = websocket.app.state.deploy_id
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="missing token")
        return
    try:
        user = decode_access_token(token, settings, deploy_id)
    except HTTPException:
        await websocket.close(code=1008, reason="invalid or expired token")
        return

    client_id = _clean_field(websocket.query_params.get("client_id"))
    if not client_id:
        await websocket.close(code=1008, reason="missing client_id")
        return

    store: ChatStore = websocket.app.state.chat_store
    manager: ConnectionManager = websocket.app.state.chat_manager

    display_name = _resolve_display_name(user, websocket.query_params.get("display_name"))
    avatar = _clean_field(websocket.query_params.get("avatar"))

    info = ClientInfo(username=user.username, role=user.role, client_id=client_id, display_name=display_name, avatar=avatar)
    await manager.connect(websocket, info)
    try:
        await manager.broadcast_online_users()
        while True:
            # Parsed as raw text + json.loads (not receive_json) so a
            # malformed payload from a visitor's browser tab - the one real
            # untrusted-input boundary here - just gets skipped rather than
            # crashing the whole connection.
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue

            if data.get("type") == "update_profile":
                new_display_name = _resolve_display_name(user, data.get("display_name"))
                new_avatar = _clean_field(data.get("avatar"))
                manager.update_identity(websocket, new_display_name, new_avatar)
                await manager.broadcast_online_users()
                continue

            text = str(data.get("text", "")).strip()
            if not text:
                continue
            recipient_client_id = _clean_field(data.get("recipient_client_id"))
            if not recipient_client_id:
                continue  # every message must be addressed to somebody - no public broadcast anymore

            current = manager.get_identity(websocket)
            msg_display_name = _resolve_display_name(user, data["display_name"]) if data.get("display_name") else display_name
            if current is not None and not data.get("display_name"):
                msg_display_name = current.display_name
            msg_avatar = _clean_field(data.get("avatar")) if data.get("avatar") else (current.avatar if current else avatar)

            message = await store.add_message(
                user.username, user.role, text[:MAX_MESSAGE_LENGTH], msg_display_name, msg_avatar, client_id, recipient_client_id
            )
            payload = message.to_dict()
            await manager.send_to_client(client_id, payload)
            if recipient_client_id != client_id:
                await manager.send_to_client(recipient_client_id, payload)
    except WebSocketDisconnect:
        logger.debug("ws/chat client disconnected")
    finally:
        manager.disconnect(websocket)
        await manager.broadcast_online_users()


@router.get("/chat/history")
async def get_chat_history(
    my_client_id: str,
    peer_client_id: str,
    request: Request,
    before_id: int | None = None,
    limit: int = HISTORY_LIMIT,
    _user: AuthenticatedUser = Depends(require_role("viewer")),
) -> dict:
    store: ChatStore = request.app.state.chat_store
    capped_limit = max(1, min(limit, HISTORY_LIMIT))
    messages = await store.conversation_messages(my_client_id, peer_client_id, before_id, capped_limit)
    return {"messages": [m.to_dict() for m in messages]}
