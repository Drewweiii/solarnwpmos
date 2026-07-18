"""WebSocket /ws/chat - one shared site-wide chat room for visitors, plus a
presence count of currently-connected clients. Auth: JWT via `?token=`, same
pattern as ws_live.py (browser WebSocket clients can't set a handshake
Authorization header).

Every accepted message is persisted (ChatStore) so a newly-connecting client
can be replayed recent history, then broadcast live to every other connected
client via `ConnectionManager` - an in-memory set scoped to this one API
process. There's no cross-process pub-sub layer: this deployment runs a
single API process, so a second process's connections existing somewhere
else isn't a real scenario yet. If that changes, this needs a shared
broadcast layer (e.g. Redis pub/sub) instead of the plain in-memory dict here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from .auth import decode_access_token
from .config import Settings
from .models import ChatMessageORM

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

HISTORY_LIMIT = 50
MAX_MESSAGE_LENGTH = 1000  # guards against a pathological payload bloating the DB/broadcast


@dataclass(frozen=True)
class ChatMessage:
    id: int
    username: str
    role: str
    text: str
    created_at: datetime

    def to_dict(self) -> dict:
        return {
            "type": "message",
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "text": self.text,
            "created_at": self.created_at.isoformat(),
        }


class ChatStore:
    def __init__(self, engine: AsyncEngine):
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def add_message(self, username: str, role: str, text: str) -> ChatMessage:
        async with self._session_factory() as session:
            row = ChatMessageORM(username=username, role=role, text=text, created_at=datetime.now(timezone.utc))
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return ChatMessage(id=row.id, username=row.username, role=row.role, text=row.text, created_at=row.created_at)

    async def recent_messages(self, limit: int = HISTORY_LIMIT) -> list[ChatMessage]:
        async with self._session_factory() as session:
            stmt = select(ChatMessageORM).order_by(ChatMessageORM.id.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
        return [
            ChatMessage(id=row.id, username=row.username, role=row.role, text=row.text, created_at=row.created_at)
            for row in reversed(rows)
        ]


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
            text = str(data.get("text", "")).strip() if isinstance(data, dict) else ""
            if not text:
                continue
            message = await store.add_message(user.username, user.role, text[:MAX_MESSAGE_LENGTH])
            await manager.broadcast(message.to_dict())
    except WebSocketDisconnect:
        logger.debug("ws/chat client disconnected")
    finally:
        manager.disconnect(websocket)
        await manager.broadcast_presence()
