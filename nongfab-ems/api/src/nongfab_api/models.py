from datetime import datetime, timezone

from sqlalchemy import TIMESTAMP, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def as_utc(dt: datetime) -> datetime:
    """Guarantee a tz-aware (UTC) datetime before it reaches a JSON response.

    Every `created_at` here is written as `datetime.now(timezone.utc)`, but
    what a row reads back as depends on the DB driver: asyncpg round-trips a
    `TIMESTAMPTZ` column's tzinfo correctly, but aiosqlite silently drops it
    (confirmed directly - a value stored tz-aware reads back tz-naive). A
    naive datetime serializes with no UTC offset in the JSON (e.g.
    `"2026-07-18T15:23:32"` instead of `"...+00:00"`), and a browser's `new
    Date(...)` then reads a timezone-less ISO string as *local* time, not
    UTC - every timestamp ends up wrong by exactly the viewer's UTC offset
    (reported 2026-07-18: feedback timestamps not matching real send time).
    Since the value was always UTC to begin with, attaching `timezone.utc`
    when it comes back naive is correct, not a guess.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


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
    # The sender's self-chosen display name (2026-07-19) - the shared demo
    # username can't identify who really wrote a note, so admin sees the name
    # they picked. Nullable: rows written before this column existed have none,
    # and application code falls back to `username` for those.
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)


class SystemSettingORM(Base):
    """One admin-published override of a value from `settings_registry.SPECS`
    (2026-07-25 - the user asked for the system's numbers to be editable rather
    than baked into code and YAML).

    Deliberately a narrow key/value table rather than a column per setting: the
    registry already owns the schema (bounds, units, labels, defaults), so a new
    editable value should not need a migration. Only overrides are stored - a
    setting left at its default has NO row here, which is what makes "reset to
    default" a plain DELETE and keeps the registry the single source of truth for
    what a default IS.

    `value` is a float because every setting in the registry is numeric (see that
    module's own docstring for why that limit is deliberate).

    Lives in the app database, not the ephemeral `RealDataStore`: an override is a
    decision somebody made, and it has to survive the container being recycled the
    way user accounts and feedback do. `updated_by`/`updated_at` are kept because
    an edit here changes money and physics figures site-wide - who moved a number
    and when is part of being able to trust the dashboard.
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    updated_by: Mapped[str] = mapped_column(String)
