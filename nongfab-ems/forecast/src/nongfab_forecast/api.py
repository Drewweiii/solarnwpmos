"""Dev-only FastAPI wrapper exposing GET /forecast/{zone}/{horizon}.

This is NOT the production Backend API (that's Module 6, not built yet - its
own spec lists the same route). Exists so the three horizon models built in
this module can be trained and queried interactively during development,
mirroring the ingestion modules' api.py pattern.

No real accumulated history exists yet (Module 1/2/3's caveat applies here
too - see README "Known gaps"), so /train-now/{zone}/{horizon} trains against
synthetic data shaped like the real thing (same generators the test suite
uses) rather than reading from TimescaleDB. /forecast/{zone}/{horizon} then
loads the most recently trained model back out of the MLflow registry (a
genuine round-trip through registry.py, not an in-memory shortcut) and
produces a forecast against a freshly synthesized "current conditions" input.

Run with: uvicorn nongfab_forecast.api:app --reload --port 8002
Then open: http://localhost:8002/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import registry, training
from .serving import (
    ModelNotTrainedError,
    UnknownHorizonError,
    UnknownZoneError,
    get_latest_forecast,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.trained: set[tuple[str, str]] = set()
    yield


app = FastAPI(
    title="Nong Fab EMS - Module 4 Forecast Engine (dev verification API)",
    description=(
        "Thin wrapper around the Module 4 forecast models for interactive verification during "
        "development. Not Module 6's production Backend API. Trains against synthetic data (no "
        "real accumulated history yet); MLflow tracking uses a local sqlite file, not the "
        "docker-compose mlflow service, unless MLFLOW_TRACKING_URI is set."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


class ForecastPointOut(BaseModel):
    timestamp: datetime
    pred: float
    lower: float | None = None
    upper: float | None = None


class ForecastResponse(BaseModel):
    zone: str
    horizon: str
    issued_at: datetime
    model_version: int
    points: list[ForecastPointOut]


class TrainResponse(BaseModel):
    zone: str
    horizon: str
    run_id: str
    model_version: int
    metrics: dict[str, float]


class HealthResponse(BaseModel):
    status: str
    tracking_uri: str
    trained: list[str]


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok", tracking_uri=registry.get_tracking_uri(),
        trained=sorted(f"{zone}/{horizon}" for zone, horizon in app.state.trained),
    )


@app.post("/train-now/{zone}/{horizon}", response_model=TrainResponse)
async def train_now(zone: str, horizon: str) -> TrainResponse:
    """Delegates to training.train_now() - the same function the STEP 10
    Prefect retrain flow (orchestration/) calls, so this dev endpoint and
    that flow never drift apart in behavior.
    """
    try:
        result = training.train_now(zone, horizon)
    except (UnknownZoneError, UnknownHorizonError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    app.state.trained.add((result.zone, result.horizon))
    logger.info("trained %s/%s -> version %d (run_id=%s)", result.zone, result.horizon, result.model_version, result.run_id)
    return TrainResponse(
        zone=result.zone, horizon=result.horizon, run_id=result.run_id, model_version=result.model_version, metrics=result.metrics,
    )


@app.get("/forecast/{zone}/{horizon}", response_model=ForecastResponse)
async def get_forecast(zone: str, horizon: str) -> ForecastResponse:
    """Delegates to serving.get_latest_forecast() - the same function Module
    6's production API calls, so this dev endpoint and the real one never
    drift apart in behavior.
    """
    try:
        result = get_latest_forecast(zone, horizon)
    except (UnknownZoneError, UnknownHorizonError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelNotTrainedError as exc:
        raise HTTPException(status_code=404, detail=f"{exc} - try POST /train-now/{zone}/{horizon} first") from exc

    return ForecastResponse(
        zone=result.zone, horizon=result.horizon, issued_at=result.issued_at, model_version=result.model_version,
        points=[ForecastPointOut(timestamp=p.timestamp, pred=p.pred, lower=p.lower, upper=p.upper) for p in result.points],
    )
