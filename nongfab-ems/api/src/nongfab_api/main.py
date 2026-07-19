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
    routes_energy_report,
    routes_feedback,
    routes_financial,
    routes_forecast,
    routes_irradiance_map,
    routes_performance,
    routes_savings,
    routes_simulate,
    routes_solar3d,
    routes_weather,
    ws_chat,
    ws_live,
)
from .auth import UserStore, create_access_token, verify_password
from .config import Settings, get_settings
from .models import Base
from .routes_feedback import FeedbackStore
from .ws_chat import ChatStore, ConnectionManager

logger = logging.getLogger(__name__)


async def _ensure_recipient_client_id_column(conn: AsyncConnection) -> None:
    """`Base.metadata.create_all` (below) only creates brand-new tables - it
    never alters one that already exists, so a `chat_messages` table
    created before `recipient_client_id` was added to the model (2026-07-18's
    private-messaging rework) never picks up the new column just from a
    redeploy. This was meant to be a one-off manual `psql` migration (see
    db/migrations/0007_chat_direct_messages.sql), but discovered live the
    same day that this deployment's `API_TIMESCALE_DSN` is a plain SQLite
    file on a Railway volume, not Postgres - Railway has no SQL console for
    that the way it does for its own Postgres plugin, so "run this SQL by
    hand" had no actual UI to do it in. Patching it in automatically here
    instead removes the manual step entirely. Uses SQLAlchemy's
    dialect-agnostic inspector (not raw `PRAGMA`/`information_schema`), so
    this keeps working unchanged if a deployment ever does move to Postgres.
    """

    def _needs_column(sync_conn) -> bool:
        insp = inspect(sync_conn)
        if "chat_messages" not in insp.get_table_names():
            return False  # brand new - create_all above already made it with every current column
        return "recipient_client_id" not in {c["name"] for c in insp.get_columns("chat_messages")}

    if await conn.run_sync(_needs_column):
        await conn.execute(text("ALTER TABLE chat_messages ADD COLUMN recipient_client_id TEXT"))
        logger.info("startup schema patch: added chat_messages.recipient_client_id")


async def _ensure_feedback_display_name_column(conn: AsyncConnection) -> None:
    """Same self-healing pattern as `_ensure_recipient_client_id_column` above,
    for `feedback_messages.display_name` (2026-07-19): `create_all` never alters
    an existing table, and this deployment's store is a SQLite file on a Railway
    volume with no SQL console to run a manual migration in, so patch it here."""

    def _needs_column(sync_conn) -> bool:
        insp = inspect(sync_conn)
        if "feedback_messages" not in insp.get_table_names():
            return False
        return "display_name" not in {c["name"] for c in insp.get_columns("feedback_messages")}

    if await conn.run_sync(_needs_column):
        await conn.execute(text("ALTER TABLE feedback_messages ADD COLUMN display_name TEXT"))
        logger.info("startup schema patch: added feedback_messages.display_name")


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
                await _ensure_recipient_client_id_column(conn)
                await _ensure_feedback_display_name_column(conn)
        user_store = UserStore(eng)
        if settings.seed_demo_users:
            await user_store.seed_demo_users()
        app.state.settings = settings
        app.state.user_store = user_store
        app.state.chat_store = ChatStore(eng)
        app.state.chat_manager = ConnectionManager()
        app.state.feedback_store = FeedbackStore(eng)

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
    app.include_router(routes_forecast.router)
    app.include_router(routes_simulate.router)
    app.include_router(routes_performance.router)
    app.include_router(routes_solar3d.router)
    app.include_router(routes_energy_report.router)
    app.include_router(routes_savings.router)
    app.include_router(routes_financial.router)
    app.include_router(routes_irradiance_map.router)
    app.include_router(routes_weather.router)
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
