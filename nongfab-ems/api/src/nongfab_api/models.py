from datetime import datetime

from sqlalchemy import TIMESTAMP, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserORM(Base):
    """Maps to the `users` table created by db/migrations/0004_users.sql.

    Passwords are stored as bcrypt hashes (auth.py), never plaintext. `role`
    is one of admin/operator/viewer (RBAC.ROLE_HIERARCHY in auth.py defines
    what each role can do) - enforced by a CHECK constraint in the migration,
    not re-validated here (ORM trusts the DB schema it maps).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    hashed_password: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class ChatMessageORM(Base):
    """Maps to `chat_messages` (db/migrations/0005_chat_and_feedback.sql,
    extended by 0006_chat_profile_and_history.sql, then 0007_chat_direct_
    messages.sql) - persisted history for ws_chat.py's private 1:1 visitor
    messaging, so a client re-opening a conversation gets its past messages
    instead of a blank thread.

    `display_name`/`avatar`/`client_id` are nullable: the viewer/operator
    demo logins are shared credentials (see auth.py's DEMO_USERS), so
    `username` alone can't tell two different real people apart - these
    columns carry the per-browser identity the frontend lets each person
    pick for themselves (nongfab web/src/lib/chatProfile.ts). Rows written
    before this column existed simply have NULLs here; application code
    falls back to `username`/a default avatar for those.

    `recipient_client_id` (2026-07-18): who a message is privately addressed
    to - see ws_chat.py's module docstring for why this exists (the chat
    used to broadcast every message to every connected visitor, "openchat"
    style, which the user flagged as an actual privacy problem). Nullable
    only because pre-2026-07-18 rows predate the column and have no sensible
    value to backfill (they were public broadcasts with no single intended
    recipient) - every row written from that date on always has one.
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)
    client_id: Mapped[str | None] = mapped_column(String, nullable=True)
    recipient_client_id: Mapped[str | None] = mapped_column(String, nullable=True)


class FeedbackMessageORM(Base):
    """Maps to `feedback_messages` (db/migrations/0005_chat_and_feedback.sql)
    - a one-way visitor-to-admin message inbox (routes_feedback.py). No
    reply/resolve workflow, just submit (any signed-in role) and list
    (admin-only).
    """

    __tablename__ = "feedback_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
