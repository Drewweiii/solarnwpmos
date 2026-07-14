"""GET /forecast/{zone}/{horizon} - delegates to nongfab_forecast.serving.
get_latest_forecast(), the same function Module 4's own dev API calls, so
this production route and that dev route never drift apart in behavior.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from nongfab_forecast.serving import (
    ModelNotTrainedError,
    UnknownHorizonError,
    UnknownZoneError,
    get_latest_forecast,
)
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["forecast"])


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


@router.get("/forecast/{zone}/{horizon}", response_model=ForecastResponse)
async def get_forecast(zone: str, horizon: str, _user=Depends(require_role("viewer"))) -> ForecastResponse:
    try:
        result = get_latest_forecast(zone, horizon)
    except (UnknownZoneError, UnknownHorizonError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelNotTrainedError as exc:
        raise HTTPException(status_code=404, detail=f"{exc} - no model has been trained yet for this zone/horizon") from exc

    return ForecastResponse(
        zone=result.zone, horizon=result.horizon, issued_at=result.issued_at, model_version=result.model_version,
        points=[ForecastPointOut(timestamp=p.timestamp, pred=p.pred, lower=p.lower, upper=p.upper) for p in result.points],
    )
