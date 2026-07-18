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


async def test_seed_demo_users_populates_empty_table(engine):
    store = UserStore(engine)
    await store.seed_demo_users()
    for username, password, role in DEMO_USERS:
        user = await store.get_by_username(username)
        assert user is not None
        assert user.role == role
        assert verify_password(password, user.hashed_password)


async def test_seed_demo_users_does_not_touch_existing_real_users(engine):
    store = UserStore(engine)
    await store.create_user("real_user", "realpw", "admin")
    await store.seed_demo_users()
    # A non-DEMO_USERS username already in the table is left alone...
    real_user = await store.get_by_username("real_user")
    assert real_user is not None
    assert verify_password("realpw", real_user.hashed_password)
    # ...but the demo accounts still get created even though the table
    # already had a row (this is the bug that left `pttlng`/`12345` missing
    # from Railway's already-seeded production database - see seed_demo_users'
    # docstring).
    for username, password, role in DEMO_USERS:
        user = await store.get_by_username(username)
        assert user is not None
        assert user.role == role
        assert verify_password(password, user.hashed_password)


async def test_seed_demo_users_is_idempotent(engine):
    store = UserStore(engine)
    await store.seed_demo_users()
    await store.seed_demo_users()
    admin = await store.get_by_username("admin")
    assert admin is not None
    assert verify_password("admin-demo-pw", admin.hashed_password)


def test_create_and_decode_access_token_roundtrip(settings):
    token = create_access_token("alice", "operator", settings, "deploy-1")
    user = decode_access_token(token, settings, "deploy-1")
    assert user == AuthenticatedUser(username="alice", role="operator")


def test_decode_access_token_rejects_expired_token(settings):
    expired_payload = {
        "sub": "alice",
        "role": "operator",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        "deploy_id": "deploy-1",
    }
    token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token, settings, "deploy-1")
    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_garbage_token(settings):
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not-a-real-token", settings, "deploy-1")
    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_token_signed_with_different_secret(settings):
    other_settings = Settings(jwt_secret_key="different-secret")
    token = create_access_token("alice", "admin", other_settings, "deploy-1")
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token, settings, "deploy-1")
    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_missing_role_claim(settings):
    payload = {"sub": "alice", "exp": datetime.now(timezone.utc) + timedelta(minutes=5), "deploy_id": "deploy-1"}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token, settings, "deploy-1")
    assert exc_info.value.status_code == 401


def test_decode_access_token_rejects_token_from_a_different_deploy(settings):
    # Simulates a token minted by the API process *before* a Railway
    # redeploy: same signing secret, same claims, but the old process's
    # deploy_id. The whole point of this check is that a still-signature-
    # valid, still-unexpired token is rejected anyway once the server has
    # moved on to a new deploy_id (2026-07-17 auto-logout-on-deploy feature).
    token = create_access_token("alice", "operator", settings, "old-deploy")
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token, settings, "new-deploy")
    assert exc_info.value.status_code == 401


def test_decode_access_token_accepts_token_matching_the_current_deploy(settings):
    token = create_access_token("alice", "operator", settings, "deploy-7")
    user = decode_access_token(token, settings, "deploy-7")
    assert user == AuthenticatedUser(username="alice", role="operator")


def test_require_role_rejects_unknown_role_at_setup_time():
    with pytest.raises(ValueError):
        require_role("superadmin")


TEST_DEPLOY_ID = "test-deploy"


def _make_test_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.state.deploy_id = TEST_DEPLOY_ID

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
    token = create_access_token("someone", caller_role, settings, TEST_DEPLOY_ID)
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
    expired_payload = {
        "sub": "someone",
        "role": "admin",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        "deploy_id": TEST_DEPLOY_ID,
    }
    token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    client = TestClient(app)
    resp = client.get("/admin-endpoint", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_protected_endpoint_rejects_a_token_from_before_a_redeploy(settings):
    # End-to-end version of test_decode_access_token_rejects_token_from_a_
    # different_deploy - a real request through require_role's dependency
    # chain, not just a direct decode_access_token() call.
    app = _make_test_app(settings)
    token = create_access_token("someone", "admin", settings, "old-deploy-before-restart")
    client = TestClient(app)
    resp = client.get("/admin-endpoint", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
