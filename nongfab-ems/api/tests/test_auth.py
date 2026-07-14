from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from nongfab_api.auth import (
    DEMO_USERS,
    AuthenticatedUser,
    UserStore,
    create_access_token,
    decode_access_token,
    hash_password,
    require_role,
    verify_password,
)
from nongfab_api.config import Settings
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
    return Settings(jwt_secret_key="test-secret", jwt_access_token_expire_minutes=60)


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("s3cret")
    assert hashed != "s3cret"
    assert verify_password("s3cret", hashed)
    assert not verify_password("wrong", hashed)


async def test_user_store_create_and_get(engine):
    store = UserStore(engine)
    await store.create_user("alice", "alicepw", "operator")
    user = await store.get_by_username("alice")
    assert user is not None
    assert user.username == "alice"
    assert user.role == "operator"
    assert verify_password("alicepw", user.hashed_password)


async def test_user_store_get_unknown_user_returns_none(engine):
    store = UserStore(engine)
    assert await store.get_by_username("nobody") is None


async def test_user_store_create_user_rejects_unknown_role(engine):
    store = UserStore(engine)
    with pytest.raises(ValueError):
        await store.create_user("bob", "bobpw", "superadmin")


async def test_seed_demo_users_if_empty_populates_table(engine):
    store = UserStore(engine)
    await store.seed_demo_users_if_empty()
    for username, password, role in DEMO_USERS:
        user = await store.get_by_username(username)
        assert user is not None
        assert user.role == role
        assert verify_password(password, user.hashed_password)


async def test_seed_demo_users_if_empty_is_noop_when_table_nonempty(engine):
    store = UserStore(engine)
    await store.create_user("real_user", "realpw", "admin")
    await store.seed_demo_users_if_empty()
    assert await store.get_by_username("admin") is None


def test_create_and_decode_access_token_roundtrip(settings):
    token = create_access_token("alice", "operator", settings)
    user = decode_access_token(token, settings)
    assert user == AuthenticatedUser(username="alice", role="operator")


def test_decode_access_token_rejects_expired_token(settings):
    expired_payload = {"sub": "alice", "role": "operator", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}
    token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token, settings)
    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_garbage_token(settings):
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not-a-real-token", settings)
    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_token_signed_with_different_secret(settings):
    other_settings = Settings(jwt_secret_key="different-secret")
    token = create_access_token("alice", "admin", other_settings)
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token, settings)
    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_missing_role_claim(settings):
    payload = {"sub": "alice", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token, settings)
    assert exc_info.value.status_code == 401


def test_require_role_rejects_unknown_role_at_setup_time():
    with pytest.raises(ValueError):
        require_role("superadmin")


def _make_test_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings

    for role in ("viewer", "operator", "admin"):

        def _endpoint(user: AuthenticatedUser = Depends(require_role(role))) -> dict[str, str]:
            return {"username": user.username, "role": user.role}

        app.add_api_route(f"/{role}-endpoint", _endpoint, methods=["GET"])

    return app


@pytest.mark.parametrize(
    ("caller_role", "endpoint", "expected_status"),
    [
        ("viewer", "/viewer-endpoint", 200),
        ("viewer", "/operator-endpoint", 403),
        ("viewer", "/admin-endpoint", 403),
        ("operator", "/viewer-endpoint", 200),
        ("operator", "/operator-endpoint", 200),
        ("operator", "/admin-endpoint", 403),
        ("admin", "/viewer-endpoint", 200),
        ("admin", "/operator-endpoint", 200),
        ("admin", "/admin-endpoint", 200),
    ],
)
def test_require_role_enforces_role_hierarchy(settings, caller_role, endpoint, expected_status):
    app = _make_test_app(settings)
    token = create_access_token("someone", caller_role, settings)
    client = TestClient(app)
    resp = client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == expected_status


def test_protected_endpoint_without_token_returns_401(settings):
    app = _make_test_app(settings)
    client = TestClient(app)
    resp = client.get("/viewer-endpoint")
    assert resp.status_code == 401


def test_protected_endpoint_with_expired_token_returns_401(settings):
    app = _make_test_app(settings)
    expired_payload = {"sub": "someone", "role": "admin", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}
    token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    client = TestClient(app)
    resp = client.get("/admin-endpoint", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
