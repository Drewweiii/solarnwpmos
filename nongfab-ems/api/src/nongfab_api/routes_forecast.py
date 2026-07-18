"""GET /forecast/{zone}/{horizon} - delegates to nongfab_forecast.serving.
get_forecast_with_fallback(). Unlike the earlier get_latest_forecast()-only
version of this route (still used as-is by Module 4's own dev API, whose job
is raw model verification, not a friendly public-facing default), this never
404s with "not trained yet" - it falls back to a real-weather physics
baseline (see serving.py's own docstring) while too little history has
accumulated to train an ML model, tagged model_type="physics_baseline" in
the response so the dashboard can label it honestly instead of presenting it
as an ML forecast.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from nongfab_forecast.serving import (
    UnknownHorizonError,
    UnknownZoneError,
    get_forecast_with_fallback,
)
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["forecast"])


class ForecastPointOut(BaseModel):
    timestamp: datetime
    pred: float
    lower: float | None = None
    upper: float | None = None
    algorithm: str | None = None
    error: float | None = None
    candidate_errors: dict[str, float] | None = None


class ForecastResponse(BaseModel):
    zone: str
    horizon: str
    issued_at: datetime
    model_version: int
    points: list[ForecastPointOut]
    data_source: str
    model_type: str


@router.get("/forecast/{zone}/{horizon}", response_model=ForecastResponse)
async def get_forecast(zone: str, horizon: str, request: Request, _user=Depends(require_role("viewer"))) -> ForecastResponse:
    try:
        result = get_forecast_with_fallback(zone, horizon, store=request.app.state.real_data_store)
    except (UnknownZoneError, UnknownHorizonError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ForecastResponse(
        zone=result.zone, horizon=result.horizon, issued_at=result.issued_at, model_version=result.model_version,
        points=[
            ForecastPointOut(
                timestamp=p.timestamp, pred=p.pred, lower=p.lower, upper=p.upper, algorithm=p.algorithm, error=p.error,
                candidate_errors=p.candidate_errors,
            )
            for p in result.points
        ],
        data_source=result.data_source, model_type=result.model_type,
    )
