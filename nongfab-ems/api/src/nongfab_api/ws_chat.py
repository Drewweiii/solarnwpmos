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
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
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

    async def inbox_messages(self, my_client_id: str, after_id: int, limit: int = HISTORY_LIMIT) -> list[ChatMessage]:
        """Every message involving `my_client_id` (sent by or addressed to it,
        across all peers) with id strictly greater than `after_id`, oldest-
        first. This is the REST-polling counterpart to the old WebSocket push:
        a client polls this with the highest id it has already seen to pick up
        both new incoming messages and echoes of its own sends from other tabs
        (same "message delivery that provably works like /feedback" approach
        the WebSocket version kept failing at in production)."""
        async with self._session_factory() as session:
            involves_me = or_(
                ChatMessageORM.client_id == my_client_id,
                ChatMessageORM.recipient_client_id == my_client_id,
            )
            stmt = (
                select(ChatMessageORM)
                .where(and_(involves_me, ChatMessageORM.id > after_id))
                .order_by(ChatMessageORM.id.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_message(row) for row in rows]


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
            # Everything from here down is wrapped so that a failure handling
            # ONE message (a DB write that raises, an unexpected payload shape,
            # etc.) is logged and reported back to the sender instead of
            # silently killing the whole socket. Found live 2026-07-19: on
            # production every send dropped the connection with "no close frame"
            # and the message was neither delivered, persisted, nor
            # acknowledged - the classic signature of an unhandled exception in
            # `store.add_message` (e.g. a full volume / locked or read-only
            # SQLite file) propagating past the `except WebSocketDisconnect`
            # below, hitting `finally`, and disconnecting. A WebSocketDisconnect
            # itself must still bubble up to end the loop, so it's re-raised.
            try:
                await _handle_chat_frame(raw, websocket, user, store, manager, client_id, display_name, avatar)
            except WebSocketDisconnect:
                raise
            except Exception:  # noqa: BLE001 - one bad message must not tear down the socket
                logger.exception("ws/chat: failed to handle a message frame; keeping socket open")
                try:
                    await websocket.send_json(
                        {"type": "error", "message": "ส่งข้อความไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"}
                    )
                except Exception:  # noqa: BLE001 - if even the error notice can't be sent, just wait for the next frame
                    pass
    except WebSocketDisconnect:
        logger.debug("ws/chat client disconnected")
    finally:
        manager.disconnect(websocket)
        await manager.broadcast_online_users()


async def _handle_chat_frame(
    raw: str,
    websocket: WebSocket,
    user: AuthenticatedUser,
    store: "ChatStore",
    manager: "ConnectionManager",
    client_id: str,
    display_name: str,
    avatar: str | None,
) -> None:
    """Handle a single received /ws/chat text frame: a profile update, or a
    private message (persist it, then push to the sender's own tabs and the
    recipient's). Kept a separate function purely so `ws_chat`'s loop can wrap
    exactly this in a per-frame try/except (see its call site) - any exception
    here is caught there, logged, and surfaced to the sender rather than
    killing the connection."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return

    if data.get("type") == "update_profile":
        new_display_name = _resolve_display_name(user, data.get("display_name"))
        new_avatar = _clean_field(data.get("avatar"))
        manager.update_identity(websocket, new_display_name, new_avatar)
        await manager.broadcast_online_users()
        return

    text = str(data.get("text", "")).strip()
    if not text:
        return
    recipient_client_id = _clean_field(data.get("recipient_client_id"))
    if not recipient_client_id:
        return  # every message must be addressed to somebody - no public broadcast anymore

    # Optional per-message token the client made up before sending, so it can
    # match the confirmed server copy back to the optimistic bubble it already
    # drew (LINE/Messenger-style send). Echoed straight back to the sender; the
    # recipient never needs it. Also attached to an error frame below so a
    # failed send flips exactly that one bubble to "failed" instead of leaving
    # the visitor staring at a silent, stuck message.
    client_temp_id = _clean_field(data.get("client_temp_id"))

    current = manager.get_identity(websocket)
    msg_display_name = _resolve_display_name(user, data["display_name"]) if data.get("display_name") else display_name
    if current is not None and not data.get("display_name"):
        msg_display_name = current.display_name
    msg_avatar = _clean_field(data.get("avatar")) if data.get("avatar") else (current.avatar if current else avatar)

    try:
        message = await store.add_message(
            user.username, user.role, text[:MAX_MESSAGE_LENGTH], msg_display_name, msg_avatar, client_id, recipient_client_id
        )
    except Exception:  # noqa: BLE001 - a failed persist must reach the sender as a precise, per-message error
        logger.exception("ws/chat: failed to persist a message; telling the sender it did not send")
        await websocket.send_json(
            {"type": "error", "client_temp_id": client_temp_id, "message": "ส่งข้อความไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"}
        )
        return

    payload = message.to_dict()
    # Sender's own tabs get the client_temp_id so the originating tab can
    # reconcile its optimistic bubble; the recipient gets the plain payload.
    sender_payload = {**payload, "client_temp_id": client_temp_id} if client_temp_id else payload
    await manager.send_to_client(client_id, sender_payload)
    if recipient_client_id != client_id:
        await manager.send_to_client(recipient_client_id, payload)


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


# --- REST transport (2026-07-20) ------------------------------------------
# The WebSocket path above kept failing in production (sends silently going
# nowhere, no error, no delivery - reported repeatedly). These plain
# request/response endpoints are the exact same shape as the feedback flow the
# user pointed out *does* work reliably: POST to send, GET to poll for new
# messages, POST a heartbeat for presence. The frontend (useChatSocket.ts) now
# drives chat entirely through these, with no WebSocket.

PRESENCE_WINDOW_SECONDS = 25.0  # a client is "online" if it heartbeated within this


class PresenceRegistry:
    """In-memory, single-process record of who has recently heartbeated -
    the REST replacement for the WebSocket connection set's online list. Same
    single-process caveat as everything else here (this deployment runs one
    API process)."""

    def __init__(self) -> None:
        self._seen: dict[str, tuple[float, dict]] = {}

    def heartbeat(self, client_id: str, display_name: str, avatar: str | None, role: str) -> None:
        self._seen[client_id] = (time.monotonic(), {"client_id": client_id, "display_name": display_name, "avatar": avatar, "role": role})

    def online_users(self) -> list[dict]:
        now = time.monotonic()
        fresh = [info for ts, info in self._seen.values() if now - ts < PRESENCE_WINDOW_SECONDS]
        # Drop stale entries opportunistically so the dict can't grow forever.
        self._seen = {cid: v for cid, v in self._seen.items() if now - v[0] < PRESENCE_WINDOW_SECONDS}
        return sorted(fresh, key=lambda i: str(i["display_name"]).lower())


class PresenceIn(BaseModel):
    client_id: str
    display_name: str | None = None
    avatar: str | None = None


class SendMessageIn(BaseModel):
    client_id: str
    recipient_client_id: str
    text: str
    display_name: str | None = None
    avatar: str | None = None


@router.post("/chat/presence")
async def post_presence(
    body: PresenceIn, request: Request, user: AuthenticatedUser = Depends(require_role("viewer"))
) -> dict:
    """Heartbeat 'I'm online' and get back who else is - the REST presence
    poll. Admin identity/prefix is forced server-side, same as the chat/WS
    paths, never trusted from the client."""
    client_id = _clean_field(body.client_id)
    if not client_id:
        raise HTTPException(status_code=422, detail="missing client_id")
    presence: PresenceRegistry = request.app.state.chat_presence
    presence.heartbeat(client_id, _resolve_display_name(user, body.display_name), _clean_field(body.avatar), user.role)
    return {"users": presence.online_users()}


@router.post("/chat/send")
async def post_send(
    body: SendMessageIn, request: Request, user: AuthenticatedUser = Depends(require_role("viewer"))
) -> dict:
    """Send a private message over plain REST (persists it, returns the stored
    row). Delivery to the recipient happens by their own `GET /chat/inbox`
    poll - there is no server push. Mirrors POST /feedback, which works."""
    text = body.text.strip()
    client_id = _clean_field(body.client_id)
    recipient_client_id = _clean_field(body.recipient_client_id)
    if not text or not client_id or not recipient_client_id:
        raise HTTPException(status_code=422, detail="text, client_id and recipient_client_id are required")
    store: ChatStore = request.app.state.chat_store
    display_name = _resolve_display_name(user, body.display_name)
    message = await store.add_message(
        user.username, user.role, text[:MAX_MESSAGE_LENGTH], display_name, _clean_field(body.avatar), client_id, recipient_client_id
    )
    return {"message": message.to_dict()}


@router.get("/chat/inbox")
async def get_inbox(
    my_client_id: str,
    request: Request,
    after_id: int = 0,
    limit: int = HISTORY_LIMIT,
    _user: AuthenticatedUser = Depends(require_role("viewer")),
) -> dict:
    """Poll for any messages involving me newer than `after_id` (incoming from
    any peer + echoes of my own sends). The REST replacement for the WebSocket
    message push."""
    store: ChatStore = request.app.state.chat_store
    capped_limit = max(1, min(limit, HISTORY_LIMIT))
    messages = await store.inbox_messages(my_client_id, after_id, capped_limit)
    return {"messages": [m.to_dict() for m in messages]}
