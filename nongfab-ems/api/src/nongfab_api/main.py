"""Module 6 Backend API: REST (/assets, /forecast, /simulate, /performance)
+ WebSocket (/ws/live) + OAuth2/JWT auth with RBAC (admin/operator/viewer).

`create_app()` is a factory (not just a bare module-level `app`) so tests can
inject an in-memory SQLite engine instead of hitting the real TimescaleDB
DSN in `Settings.timescale_dsn` - see tests/conftest.py.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from nongfab_forecast.local_store import RealDataStore
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from . import (
    ingestion_scheduler,
    metrics,
    routes_assets,
    routes_energy_report,
    routes_forecast,
    routes_irradiance_map,
    routes_performance,
    routes_simulate,
    routes_solar3d,
    ws_live,
)
from .auth import UserStore, create_access_token, verify_password
from .config import Settings, get_settings
from .models import Base

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
        if settings.create_tables_on_startup:
            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        user_store = UserStore(eng)
        if settings.seed_demo_users:
            await user_store.seed_demo_users_if_empty()
        app.state.settings = settings
        app.state.user_store = user_store

        # Real-data ingestion (ingestion_scheduler.py) - one store for this
        # process's whole lifetime, not per-request, so its in-memory default
        # (RealDataStore's own default when real_data_db_path is unset) still
        # accumulates real history across requests - see that module's docstring.
        app.state.real_data_store = RealDataStore(db_path=settings.real_data_db_path or None)
        background_tasks: list = []
        if settings.enable_background_ingestion:
            background_tasks = ingestion_scheduler.start_background_ingestion(app.state.real_data_store, settings)
        app.state.background_ingestion_tasks = background_tasks

        yield

        if background_tasks:
            await ingestion_scheduler.stop_background_ingestion(background_tasks)
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def prometheus_metrics_middleware(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        # request.scope["route"] is set by the router as part of call_next()'s
        # dispatch (same scope dict, mutated in place), so it's already
        # populated by the time we get here - using the matched route's
        # template (e.g. "/forecast/{zone}/{horizon}") instead of the raw
        # path keeps per-zone requests aggregated into one series instead of
        # fragmenting into one series per zone id. Unmatched requests (404s)
        # fall back to a fixed label instead of the raw path so a scanner
        # probing random URLs can't blow up label cardinality.
        route = request.scope.get("route")
        path = route.path if route is not None else "not_found"
        duration = time.perf_counter() - start
        metrics.REQUEST_COUNT.labels(method=request.method, path=path, status_code=response.status_code).inc()
        metrics.REQUEST_DURATION_SECONDS.labels(method=request.method, path=path).observe(duration)
        return response

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

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
    app.include_router(routes_solar3d.router)
    app.include_router(routes_energy_report.router)
    app.include_router(routes_irradiance_map.router)
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
