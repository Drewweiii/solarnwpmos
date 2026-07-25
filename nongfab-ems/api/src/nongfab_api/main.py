"""Module 6 Backend API: REST (/assets, /forecast, /simulate, /performance)
+ WebSocket (/ws/live) + OAuth2/JWT auth with RBAC (admin/operator/viewer).

`create_app()` is a factory (not just a bare module-level `app`) so tests can
inject an in-memory SQLite engine instead of hitting the real TimescaleDB
DSN in `Settings.timescale_dsn` - see tests/conftest.py.
"""

from __future__ import annotations

import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from nongfab_forecast.local_store import RealDataStore
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from . import (
    ingestion_scheduler,
    metrics,
    routes_assets,
    routes_diagnostics,
    routes_energy_report,
    routes_expansion,
    routes_feedback,
    routes_financial,
    routes_forecast,
    routes_grid,
    routes_grid_carbon,
    routes_irradiance_map,
    routes_performance,
    routes_savings,
    routes_settings,
    routes_simulate,
    routes_soiling,
    routes_solar3d,
    routes_sources,
    routes_verification,
    routes_weather,
    ws_chat,
    ws_live,
)
from .auth import UserStore, create_access_token, verify_password
from .config import Settings, get_settings
from .models import Base
from .routes_feedback import FeedbackStore
from .settings_service import apply_effective_settings
from .settings_store import SettingsStore
from .ws_chat import ChatStore, ConnectionManager, PresenceRegistry

logger = logging.getLogger(__name__)


# Every column the current ORM maps that `Base.metadata.create_all` cannot
# retrofit onto a table that already exists on the production volume (it only
# creates brand-new tables, never ALTERs). This started as two one-off patch
# functions (recipient_client_id 2026-07-18, feedback display_name
# 2026-07-19) - then on 2026-07-20 a live probe showed /chat/send and
# /chat/inbox both 500ing in production because the deployed chat_messages
# table STILL predated `display_name`/`avatar`/`client_id` (only
# recipient_client_id had ever been patched), so every INSERT and full-row
# SELECT failed. That was the true root cause of "chat never delivers" across
# both the WebSocket and REST transports. Lesson learned: heal the FULL
# required-column set, not whichever single column last broke.
_REQUIRED_COLUMNS: dict[str, dict[str, str]] = {
    "chat_messages": {
        "display_name": "TEXT",
        "avatar": "TEXT",
        "client_id": "TEXT",
        "recipient_client_id": "TEXT",
    },
    "feedback_messages": {
        "display_name": "TEXT",
    },
}


async def _ensure_required_columns(conn: AsyncConnection) -> None:
    """Self-healing startup schema patch: add any `_REQUIRED_COLUMNS` entry
    missing from an existing table. Needed because this deployment's store is
    a SQLite file on a Railway volume with no SQL console to run manual
    migrations in (see the note above). Uses SQLAlchemy's dialect-agnostic
    inspector (not raw `PRAGMA`/`information_schema`), so it keeps working
    unchanged if a deployment ever moves to Postgres. Tables that don't exist
    yet are skipped - `create_all` just made them with every current column.
    """

    def _missing(sync_conn) -> list[tuple[str, str, str]]:
        insp = inspect(sync_conn)
        existing_tables = set(insp.get_table_names())
        out: list[tuple[str, str, str]] = []
        for table, cols in _REQUIRED_COLUMNS.items():
            if table not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            out.extend((table, name, ddl) for name, ddl in cols.items() if name not in have)
        return out

    for table, name, ddl in await conn.run_sync(_missing):
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        logger.info("startup schema patch: added %s.%s", table, name)


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
                await _ensure_required_columns(conn)
        user_store = UserStore(eng)
        if settings.seed_demo_users:
            await user_store.seed_demo_users()
        app.state.settings = settings
        app.state.user_store = user_store
        app.state.chat_store = ChatStore(eng)
        app.state.chat_manager = ConnectionManager()
        app.state.chat_presence = PresenceRegistry()
        app.state.feedback_store = FeedbackStore(eng)

        # User-editable system values (2026-07-25). Loaded into the process cache
        # BEFORE ingestion starts, so the very first backfill/retrain already runs
        # against whatever figures an admin published rather than the compiled
        # defaults, then pushed into the pure packages that need injection rather
        # than a per-request read (see settings_service).
        settings_store = SettingsStore(eng)
        await settings_store.load_into_cache()
        app.state.settings_store = settings_store
        apply_effective_settings()

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
    # A fresh random identity per process start (not per-request) - every JWT
    # minted by this process embeds it (see auth.create_access_token), and
    # every request re-checks it (auth.decode_access_token), so a Railway
    # redeploy (which restarts this process) invalidates every token issued
    # by the previous process, forcing an auto-logout - see /version below
    # and web/lib/deployWatch.ts for the frontend half of this.
    app.state.deploy_id = secrets.token_hex(8)

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

    @app.get("/version")
    async def version() -> dict[str, str]:
        """Unauthenticated on purpose - the frontend's deploy watcher
        (web/lib/deployWatch.ts) polls this to auto-log-out idle sessions
        too, not just ones actively mid-request (which already get a 401
        the moment they call any real endpoint - see auth.decode_access_token).
        """
        return {"deploy_id": app.state.deploy_id}

    @app.post("/auth/token")
    async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> dict[str, str]:
        user_store: UserStore = app.state.user_store
        user = await user_store.get_by_username(form_data.username)
        if user is None or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="incorrect username or password")
        token = create_access_token(user.username, user.role, settings, app.state.deploy_id)
        return {"access_token": token, "token_type": "bearer"}

    app.include_router(routes_assets.router)
    # BEFORE routes_forecast: that router's catch-all /forecast/{zone}/{horizon}
    # would otherwise match /forecast/{zone}/verification first and 404 it as an
    # unknown horizon (FastAPI matches in registration order).
    app.include_router(routes_verification.router)
    app.include_router(routes_forecast.router)
    app.include_router(routes_simulate.router)
    app.include_router(routes_performance.router)
    app.include_router(routes_solar3d.router)
    app.include_router(routes_energy_report.router)
    app.include_router(routes_savings.router)
    app.include_router(routes_financial.router)
    app.include_router(routes_irradiance_map.router)
    app.include_router(routes_weather.router)
    app.include_router(routes_soiling.router)
    app.include_router(routes_diagnostics.router)
    app.include_router(routes_expansion.router)
    app.include_router(routes_grid.router)
    app.include_router(routes_grid_carbon.router)
    app.include_router(routes_sources.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_feedback.router)
    app.include_router(ws_live.router)
    app.include_router(ws_chat.router)

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
