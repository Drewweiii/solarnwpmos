"""JWT/RBAC auth: OAuth2 password flow (username+password -> JWT access
token), bcrypt password hashing, and role-based endpoint guards.

Three roles, ordered least-to-most privileged: viewer < operator < admin.
`require_role(min_role)` returns a FastAPI dependency that accepts any role
at or above `min_role` - e.g. `require_role("operator")` lets both operator
and admin through, but rejects viewer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from .config import Settings
from .models import UserORM

ROLE_HIERARCHY = {"viewer": 0, "operator": 1, "admin": 2}

# Demo accounts seeded into the `users` table on startup if it's empty - dev/
# demo convenience ONLY (see README "Auth"). These are throwaway accounts for
# interactive API verification, not real credentials. A real deployment must
# set API_SEED_DEMO_USERS=false and provision real users via UserStore.create_user().
DEMO_USERS = (
    ("admin", "admin-demo-pw", "admin"),
    ("operator", "operator-demo-pw", "operator"),
    ("viewer", "viewer-demo-pw", "viewer"),
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str


class UserStore:
    def __init__(self, engine: AsyncEngine):
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def get_by_username(self, username: str) -> UserORM | None:
        async with self._session_factory() as session:
            stmt = select(UserORM).where(UserORM.username == username)
            return (await session.execute(stmt)).scalar_one_or_none()

    async def create_user(self, username: str, password: str, role: str) -> None:
        if role not in ROLE_HIERARCHY:
            raise ValueError(f"unknown role {role!r}; expected one of {sorted(ROLE_HIERARCHY)}")
        async with self._session_factory() as session:
            session.add(
                UserORM(username=username, hashed_password=hash_password(password), role=role, created_at=datetime.now(timezone.utc))
            )
            await session.commit()

    async def seed_demo_users_if_empty(self) -> None:
        """Dev/demo convenience - see DEMO_USERS docstring. No-op if the table
        already has at least one row (never overwrites a real deployment's users).
        """
        async with self._session_factory() as session:
            existing = (await session.execute(select(UserORM.id).limit(1))).first()
        if existing is not None:
            return
        for username, password, role in DEMO_USERS:
            await self.create_user(username, password, role)


def create_access_token(username: str, role: str, settings: Settings, deploy_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {"sub": username, "role": role, "exp": expire, "deploy_id": deploy_id}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings, deploy_id: str) -> AuthenticatedUser:
    """`deploy_id` is the API process's own boot-time identity (see main.py's
    `app.state.deploy_id`, a fresh random value generated once per process
    start) - a token minted by a previous process (i.e. before the most
    recent deploy) carries the *old* value and is rejected here, forcing
    every session to sign back in after any Railway redeploy. This is the
    user's own explicit request (2026-07-17): any code Claude ships to
    either GitHub or Railway should auto-log-out anyone currently signed in,
    not leave them running against a mismatched frontend/backend pairing.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc

    username = payload.get("sub")
    role = payload.get("role")
    if not username or role not in ROLE_HIERARCHY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="malformed token")
    if payload.get("deploy_id") != deploy_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session invalidated by a server redeploy")
    return AuthenticatedUser(username=username, role=role)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)) -> AuthenticatedUser:
    settings: Settings = request.app.state.settings
    deploy_id: str = request.app.state.deploy_id
    return decode_access_token(token, settings, deploy_id)


def require_role(min_role: str):
    if min_role not in ROLE_HIERARCHY:
        raise ValueError(f"unknown role {min_role!r}; expected one of {sorted(ROLE_HIERARCHY)}")

    async def _dependency(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if ROLE_HIERARCHY[user.role] < ROLE_HIERARCHY[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"requires role '{min_role}' or higher, have '{user.role}'"
            )
        return user

    return _dependency
