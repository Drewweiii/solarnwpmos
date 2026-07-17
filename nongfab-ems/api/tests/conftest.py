"""Shared fixtures: an in-memory SQLite engine (tables created from
nongfab_api.models.Base), a test Settings (short-lived JWT secret, fast
WebSocket push interval), and a `create_app()`-built FastAPI app wired to
that engine instead of a real TimescaleDB DSN - so the whole route/websocket
test suite runs without a live Postgres instance.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from nongfab_api.auth import create_access_token
from nongfab_api.config import Settings
from nongfab_api.main import create_app
from nongfab_api.models import Base


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def settings():
    # enable_background_ingestion=False: the test suite must stay hermetic/fast
    # (no real network calls, no multi-second model retraining loop) - real
    # deployments get it on by default, see config.Settings' own docstring.
    return Settings(
        jwt_secret_key="test-secret", seed_demo_users=True, live_push_interval_seconds=0.05, enable_background_ingestion=False
    )


@pytest.fixture
def app(settings, engine):
    return create_app(settings=settings, engine=engine)


@pytest.fixture
def token_factory(app, settings):
    # Depends on `app` (not just `settings`) so minted tokens carry the same
    # `deploy_id` the test's own `app` instance generated at creation time -
    # otherwise every authenticated test request would 401 on the new
    # deploy_id check (see auth.py's decode_access_token docstring).
    def _make(role: str, username: str = "tester") -> str:
        return create_access_token(username, role, settings, app.state.deploy_id)

    return _make
