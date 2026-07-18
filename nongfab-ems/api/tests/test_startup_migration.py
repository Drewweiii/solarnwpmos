"""Regression test (2026-07-18): production's chat_messages table was
created before recipient_client_id existed, and Base.metadata.create_all
never alters an already-existing table - only a fresh one. Reproduces that
exact scenario (an old-shape table, not a fresh in-memory DB) and asserts
create_app()'s lifespan patches the column in automatically, since this
deployment's API_TIMESCALE_DSN turned out to be a plain SQLite file with no
migration console available (unlike Railway's own Postgres plugin).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from nongfab_api.auth import create_access_token
from nongfab_api.config import Settings
from nongfab_api.main import create_app


async def _make_pre_migration_engine():
    """An engine with chat_messages already created in its *old* shape (no
    recipient_client_id) - simulates production's real state, not a fresh
    Base.metadata.create_all DB where every column already exists.
    """
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    display_name TEXT,
                    avatar TEXT,
                    client_id TEXT
                )
                """
            )
        )
        await conn.execute(
            text(
                "INSERT INTO chat_messages (username, role, text, created_at, client_id) "
                "VALUES ('alice', 'viewer', 'hi from before the migration', :created_at, 'a')"
            ),
            {"created_at": datetime.now(timezone.utc)},
        )
    return eng


async def test_startup_adds_missing_recipient_client_id_column_to_an_existing_table():
    eng = await _make_pre_migration_engine()
    async with eng.connect() as conn:
        cols_before = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("chat_messages")})
    assert "recipient_client_id" not in cols_before

    settings = Settings(jwt_secret_key="test-secret", seed_demo_users=True, enable_background_ingestion=False)
    app = create_app(settings=settings, engine=eng)
    with TestClient(app):
        pass  # entering/exiting the context runs the lifespan startup (and shutdown)

    async with eng.connect() as conn:
        cols_after = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("chat_messages")})
        rows = (await conn.execute(text("SELECT username, text, recipient_client_id FROM chat_messages"))).all()
    assert "recipient_client_id" in cols_after
    # the pre-existing row survived the patch, with a NULL (not an error) in the new column
    assert rows == [("alice", "hi from before the migration", None)]

    await eng.dispose()


async def test_a_new_message_after_the_patch_round_trips_through_the_column():
    eng = await _make_pre_migration_engine()
    settings = Settings(jwt_secret_key="test-secret", seed_demo_users=True, enable_background_ingestion=False)
    app = create_app(settings=settings, engine=eng)

    with TestClient(app) as client:
        token_a = create_access_token("alice", "viewer", settings, app.state.deploy_id)
        token_b = create_access_token("bob", "viewer", settings, app.state.deploy_id)
        with client.websocket_connect(f"/ws/chat?token={token_a}&client_id=a") as ws_a:
            ws_a.receive_json()
            with client.websocket_connect(f"/ws/chat?token={token_b}&client_id=b") as ws_b:
                ws_b.receive_json()
                ws_a.receive_json()
                ws_a.send_json({"text": "after the patch", "recipient_client_id": "b"})
                message = ws_b.receive_json()
    assert message["text"] == "after the patch"
    assert message["recipient_client_id"] == "b"

    await eng.dispose()
