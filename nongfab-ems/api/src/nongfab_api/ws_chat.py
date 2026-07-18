"""WebSocket /ws/chat - one shared site-wide chat room for visitors, plus a
presence count of currently-connected clients. Auth: JWT via `?token=`, same
pattern as ws_live.py (browser WebSocket clients can't set a handshake
Authorization header).

Every accepted message is persisted (ChatStore) so a newly-connecting client
can be replayed recent history (and page further back via `GET
/chat/history`), then broadcast live to every other connected client via
`ConnectionManager` - an in-memory set scoped to this one API process.
There's no cross-process pub-sub layer: this deployment runs a single API
process, so a second process's connections existing somewhere else isn't a
real scenario yet. If that changes, this needs a shared broadcast layer
(e.g. Redis pub/sub) instead of the plain in-memory dict here.

Per-browser identity (display_name/avatar/client_id): the viewer/operator
demo logins are shared credentials (auth.py's DEMO_USERS), so `username`
alone doesn't distinguish two different real people chatting at once. The
client picks a display name/avatar for itself (chatProfile.ts) and sends
them along with every message. Admin picks a name/avatar the same way as
everyone else, but whatever name they choose always gets ADMIN_NAME_PREFIX
prepended server-side (never trusted from the client to add it themselves)
before it's persisted/broadcast - so every other visitor can tell an admin
message apart from a regular one at a glance, even though the admin's own
account can still personalize the rest of the name.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from .auth import AuthenticatedUser, decode_access_token, require_role
from .config import Settings
from .models import ChatMessageORM

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

HISTORY_LIMIT = 50
MAX_MESSAGE_LENGTH = 1000  # guards against a pathological payload bloating the DB/broadcast
MAX_PROFILE_FIELD_LENGTH = 40  # display_name/avatar id - generous but bounded

ADMIN_NAME_PREFIX = "admin "


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
        }


def _row_to_message(row: ChatMessageORM) -> ChatMessage:
    return ChatMessage(
        id=row.id,
        username=row.username,
        role=row.role,
        text=row.text,
        created_at=row.created_at,
        display_name=row.display_name or row.username,  # pre-migration rows have no display_name
        avatar=row.avatar,
        client_id=row.client_id,
    )


class ChatStore:
    def __init__(self, engine: AsyncEngine):
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def add_message(
        self, username: str, role: str, text: str, display_name: str, avatar: str | None, client_id: str | None
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
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _row_to_message(row)

    async def recent_messages(self, limit: int = HISTORY_LIMIT) -> list[ChatMessage]:
        async with self._session_factory() as session:
            stmt = select(ChatMessageORM).order_by(ChatMessageORM.id.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_message(row) for row in reversed(rows)]

    async def messages_before(self, before_id: int, limit: int = HISTORY_LIMIT) -> list[ChatMessage]:
        """Scroll-back page: the `limit` messages immediately preceding
        `before_id`, oldest-first - used by `GET /chat/history` to feed the
        chat panel's "load older messages" infinite scroll.
        """
        async with self._session_factory() as session:
            stmt = select(ChatMessageORM).where(ChatMessageORM.id < before_id).order_by(ChatMessageORM.id.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_message(row) for row in reversed(rows)]


class ConnectionManager:
    """This process's set of live /ws/chat sockets - the "room" the chat and
    presence count are scoped to.
    """

    def __init__(self) -> None:
        self._connections: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, username: str) -> None:
        await websocket.accept()
        self._connections[websocket] = username

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    @property
    def online_count(self) -> int:
        return len(self._connections)

    @property
    def online_usernames(self) -> list[str]:
        return sorted(set(self._connections.values()))

    async def broadcast(self, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 - a broken/closing socket shouldn't stop the fan-out to everyone else
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_presence(self) -> None:
        await self.broadcast({"type": "presence", "count": self.online_count, "usernames": self.online_usernames})


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

    store: ChatStore = websocket.app.state.chat_store
    manager: ConnectionManager = websocket.app.state.chat_manager

    await manager.connect(websocket, user.username)
    try:
        history = await store.recent_messages()
        await websocket.send_json({"type": "history", "messages": [m.to_dict() for m in history]})
        await manager.broadcast_presence()
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
            text = str(data.get("text", "")).strip()
            if not text:
                continue

            display_name = str(data.get("display_name") or user.username).strip()[:MAX_PROFILE_FIELD_LENGTH] or user.username
            if user.role == "admin":
                # The admin picks their own name/avatar same as everyone
                # else, but the "admin " prefix is never trusted from the
                # client - always applied here so it can't be stripped or
                # spoofed, and so every other visitor can tell an admin
                # message apart from a regular one at a glance.
                display_name = f"{ADMIN_NAME_PREFIX}{display_name}"[:MAX_PROFILE_FIELD_LENGTH]
            raw_avatar = data.get("avatar")
            avatar = str(raw_avatar).strip()[:MAX_PROFILE_FIELD_LENGTH] if raw_avatar else None
            raw_client_id = data.get("client_id")
            client_id = str(raw_client_id).strip()[:MAX_PROFILE_FIELD_LENGTH] if raw_client_id else None

            message = await store.add_message(user.username, user.role, text[:MAX_MESSAGE_LENGTH], display_name, avatar, client_id)
            await manager.broadcast(message.to_dict())
    except WebSocketDisconnect:
        logger.debug("ws/chat client disconnected")
    finally:
        manager.disconnect(websocket)
        await manager.broadcast_presence()


@router.get("/chat/history")
async def get_chat_history(
    before_id: int, request: Request, limit: int = HISTORY_LIMIT, _user: AuthenticatedUser = Depends(require_role("viewer"))
) -> dict:
    store: ChatStore = request.app.state.chat_store
    capped_limit = max(1, min(limit, HISTORY_LIMIT))
    messages = await store.messages_before(before_id, capped_limit)
    return {"messages": [m.to_dict() for m in messages]}
