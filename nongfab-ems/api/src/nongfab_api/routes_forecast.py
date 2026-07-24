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


# The features added in the 2026-07-24 marine round (checkpoints 1-2) - the
# frontend highlights these so the user can see how much the *new* inputs
# contribute vs the original irradiance/temperature/lag features.
NEW_MARINE_FEATURES = frozenset(
    {"wind_speed_ms", "relative_humidity_pct", "precip_mm", "salt_soiling_index", "aod_550nm", "dust", "pm2_5", "pm10"}
)


class FeatureImportanceItem(BaseModel):
    feature: str
    importance: float  # 0..1, all items sum to ~1
    is_new: bool  # one of the 2026-07-24 marine/aerosol features


class FeatureImportanceResponse(BaseModel):
    available: bool
    zone: str
    # Most-important first. Empty (available=False) when no tree-based hour-ahead
    # model is trained yet (cold start, or every lead won by the Sum-k LSTM,
    # which has no split-based importance).
    items: list[FeatureImportanceItem] = []
    # Summed importance of the new marine/aerosol features - a one-number "how
    # much do the new inputs matter" the frontend can headline.
    new_features_total: float | None = None


@router.get("/forecast/{zone}/feature-importance", response_model=FeatureImportanceResponse)
async def get_feature_importance(
    zone: str, request: Request, _user=Depends(require_role("viewer"))
) -> FeatureImportanceResponse:
    """Relative feature importance of the hour-ahead k-step model for `zone`,
    so the dashboard can show how much the new marine/aerosol inputs contribute.
    Loads the latest trained model (same registry the forecast route serves
    from) and aggregates its tree-based sub-models' importances (see
    nongfab_forecast.hour_ahead.aggregate_feature_importances). Returns
    available=False with an empty list when nothing is trained yet, so the
    frontend renders an honest "not enough data yet" state - never a fabricated
    chart."""
    try:
        from nongfab_forecast import registry
        from nongfab_forecast.hour_ahead import aggregate_feature_importances

        model = registry.load_model("hour", zone, version="latest")
    except Exception:  # noqa: BLE001 - no trained model / registry miss -> honest empty
        return FeatureImportanceResponse(available=False, zone=zone)

    if not hasattr(model, "models_by_lead_hour"):
        return FeatureImportanceResponse(available=False, zone=zone)

    pairs = aggregate_feature_importances(model)
    if not pairs:
        return FeatureImportanceResponse(available=False, zone=zone)

    items = [
        FeatureImportanceItem(feature=name, importance=value, is_new=name in NEW_MARINE_FEATURES)
        for name, value in pairs
    ]
    new_total = sum(value for name, value in pairs if name in NEW_MARINE_FEATURES)
    return FeatureImportanceResponse(available=True, zone=zone, items=items, new_features_total=new_total)


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
