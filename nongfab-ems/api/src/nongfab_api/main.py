"""Module 6 Backend API: REST (/assets, /forecast, /simulate, /performance)
+ WebSocket (/ws/live) + OAuth2/JWT auth with RBAC (admin/operator/viewer).

`create_app()` is a factory (not just a bare module-level `app`) so tests can
inject an in-memory SQLite engine instead of hitting the real TimescaleDB
DSN in `Settings.timescale_dsn` - see tests/conftest.py.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from . import routes_assets, routes_forecast, routes_performance, routes_simulate, ws_live
from .auth import UserStore, create_access_token, verify_password
from .config import Settings, get_settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, engine: AsyncEngine | None = None) -> FastAPI:
    """`engine`, if given, is used as-is and never disposed by this app's
    lifespan (the caller owns it - e.g. a test fixture's in-memory sqlite
    engine). If omitted, a real engine is created from `settings.
    timescale_dsn` on startup and disposed on shutdown.
    """
    settings = settings or get_settings()
    owns_engine = engine is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        eng = engine or create_async_engine(settings.timescale_dsn)
        user_store = UserStore(eng)
        if settings.seed_demo_users:
            await user_store.seed_demo_users_if_empty()
        app.state.settings = settings
        app.state.user_store = user_store
        yield
        if owns_engine:
            await eng.dispose()

    app = FastAPI(
        title="Nong Fab EMS - Backend API",
        description=(
            "Module 6: REST (/assets, /forecast/{zone}/{horizon}, /simulate/{zone}, "
            "/performance/{zone}) + WebSocket (/ws/live) + OAuth2/JWT auth with RBAC "
            "(admin/operator/viewer). Fully on-grid - no battery/BESS anywhere in this "
            "system. Read routes reuse Module 4's forecast serving and Module 5's "
            "simulation pipeline directly, so behavior never drifts from those modules' "
            "own dev APIs."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )
    # Available even before lifespan runs (e.g. a bare TestClient(app) request
    # that never enters the `with TestClient(app) as client:` context).
    app.state.settings = settings

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/token")
    async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> dict[str, str]:
        user_store: UserStore = app.state.user_store
        user = await user_store.get_by_username(form_data.username)
        if user is None or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="incorrect username or password")
        token = create_access_token(user.username, user.role, settings)
        return {"access_token": token, "token_type": "bearer"}

    app.include_router(routes_assets.router)
    app.include_router(routes_forecast.router)
    app.include_router(routes_simulate.router)
    app.include_router(routes_performance.router)
    app.include_router(ws_live.router)

    return app


app = create_app()


def main() -> None:
    """Console-script entrypoint (`nongfab-api`, see pyproject.toml) - runs
    the app with uvicorn against `Settings.port`.
    """
    import uvicorn

    uvicorn.run("nongfab_api.main:app", host="0.0.0.0", port=get_settings().port)


if __name__ == "__main__":
    main()
