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

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import registry
from .day_ahead import predict_day_ahead, train_day_ahead_model
from .hour_ahead import predict_hour_ahead, train_hour_ahead_model
from .metrics import evaluate_point_forecast, evaluate_prediction_interval
from .minute_ahead import train_minute_ahead_model
from .pv_conversion import nong_fab_zone_capacities_kwp
from .serving import (
    ModelNotTrainedError,
    UnknownHorizonError,
    UnknownZoneError,
    _synthetic_day_df,
    _synthetic_hour_df,
    _synthetic_minute_df,
    get_latest_forecast,
)

logger = logging.getLogger(__name__)

VALID_HORIZONS = ("minute", "hour", "day")


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


def _validate_zone(zone: str) -> str:
    capacities = nong_fab_zone_capacities_kwp()
    if zone not in capacities:
        raise HTTPException(status_code=404, detail=f"unknown zone {zone!r}; known zones: {sorted(capacities)}")
    return zone


def _validate_horizon(horizon: str) -> str:
    if horizon not in VALID_HORIZONS:
        raise HTTPException(status_code=404, detail=f"unknown horizon {horizon!r}; expected one of {VALID_HORIZONS}")
    return horizon


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok", tracking_uri=registry.get_tracking_uri(),
        trained=sorted(f"{zone}/{horizon}" for zone, horizon in app.state.trained),
    )


@app.post("/train-now/{zone}/{horizon}", response_model=TrainResponse)
async def train_now(zone: str, horizon: str) -> TrainResponse:
    zone = _validate_zone(zone)
    horizon = _validate_horizon(horizon)

    if horizon == "minute":
        train_df = _synthetic_minute_df(n=400, seed=0)
        model = train_minute_ahead_model(
            train_df, ["cloud_opacity_pct", "cloud_index"], "cloud_opacity_pct", epochs=30, patience=6,
        )
        params = {"lookback": model.lookback, "horizon": model.horizon}
        metrics = {"best_val_loss": min(model.train_history)}

    elif horizon == "hour":
        X, y = _synthetic_hour_df(n=300, seed=0)
        X_train, y_train, X_val, y_val = X.iloc[:200], y.iloc[:200], X.iloc[200:], y.iloc[200:]
        model = train_hour_ahead_model(X_train, y_train, X_val, y_val, n_trials=5)

        X_test, y_test = _synthetic_hour_df(n=100, seed=1)
        pred = predict_hour_ahead(model, X_test)
        params = dict(model.best_params)
        metrics = {**evaluate_point_forecast(y_test, pred["pred"]), **evaluate_prediction_interval(y_test, pred["lower"], pred["upper"])}

    else:  # day
        train_df = _synthetic_day_df(n_hours=24 * 20, seed=0)
        model = train_day_ahead_model(train_df, "power_kw", ["ssrd_w_m2", "temp2m_c"], epochs=15)

        test_df = _synthetic_day_df(n_hours=24, seed=1)
        test_df.index = train_df.index[-1] + pd.to_timedelta(np.arange(1, 25), unit="h")
        pred = predict_day_ahead(model, train_df, test_df[["ssrd_w_m2", "temp2m_c"]], periods=24)
        params = {"quantiles": str(model.quantiles)}
        metrics = {
            **evaluate_point_forecast(test_df["power_kw"], pred["pred"]),
            **evaluate_prediction_interval(test_df["power_kw"], pred["lower"], pred["upper"]),
        }

    run_id, version = registry.log_run(horizon, zone, model, params=params, metrics=metrics)
    app.state.trained.add((zone, horizon))
    logger.info("trained %s/%s -> version %d (run_id=%s)", zone, horizon, version, run_id)
    return TrainResponse(zone=zone, horizon=horizon, run_id=run_id, model_version=version, metrics=metrics)


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
