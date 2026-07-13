"""
backend/app/api/v1/forecast.py
Dynamic multi-horizon forecast router.

    POST /api/v1/forecast
        body: ForecastRequest {site_code, horizon_type, pi_nominal, ...}
        → routes to the model bound to horizon_type, attaches prediction
          intervals and GTG operational signals (spinning reserve / ramp).

The handler functions are thin adapters. Real model loading/inference lives in
`app/ml/{minute_ahead,hour_ahead,day_ahead}.py`; here we only demonstrate the
routing pattern, PI handling, and reserve logic. TODOs mark where trained
artifacts and live feature fetches plug in.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from fastapi import APIRouter, HTTPException

# from ..db.deps import get_session            # wire in your async session dependency
# from ..ml.registry import load_model         # cached model loader
# from ..ml.conversion import clip_aware_power # I->P with inverter cap (GIS)
from ..schemas.forecast import (
    ForecastPoint, ForecastRequest, ForecastResponse, HorizonType, ReserveSignal,
)

router = APIRouter(prefix="/api/v1", tags=["forecast"])

# Per-horizon defaults (lead resolution + count). Tune per site.
HORIZON_CFG = {
    HorizonType.minute_ahead: dict(step_min=15, steps=8,   model="cnn_lstm"),      # up to 120 min
    HorizonType.hour_ahead:   dict(step_min=60, steps=6,   model="lightgbm"),      # 1-6 h
    HorizonType.day_ahead:    dict(step_min=60, steps=168, model="neuralprophet"), # 1-7 d
}

# GTG capability — MOVE TO config/plant.yaml (placeholder until 20 MW claim confirmed).
GTG_RAMP_KW_PER_MIN = 500.0
PLANT_NET_LOAD_KW = 3000.0  # rough net consumption; drives zero-export guard


# ---------------------------------------------------------------------------
# Model handlers (adapters). Each returns list[ForecastPoint].
# ---------------------------------------------------------------------------
async def run_minute_ahead(req: ForecastRequest, cfg: dict) -> tuple[list[ForecastPoint], str]:
    """neuralforecast CNN-LSTM / DilatedRNN with Himawari cloud-index exogenous."""
    # TODO: features = await fetch_himawari_features(req.site_code, lookback, cfg["steps"])
    # TODO: model = load_model("cnn_lstm", req.site_code); yhat, q = model.predict(features, req.pi_nominal)
    return _stub_points(req, cfg), cfg["model"]


async def run_hour_ahead(req: ForecastRequest, cfg: dict) -> tuple[list[ForecastPoint], str]:
    """LightGBM on NWP (DSWRF/T/wind/RH) + net-load lags. One sub-model per lead step."""
    # TODO: X = await build_nwp_feature_frame(req.site_code, cfg["steps"])
    # TODO: per-lead LightGBM quantile models → p10/p50/p90
    return _stub_points(req, cfg), cfg["model"]


async def run_day_ahead(req: ForecastRequest, cfg: dict) -> tuple[list[ForecastPoint], str]:
    """NeuralProphet with future NWP regressors + daily seasonality/AR."""
    # TODO: m = load_model("neuralprophet", req.site_code); future = make_future_df(...)
    return _stub_points(req, cfg), cfg["model"]


ROUTES: dict[HorizonType, Callable[[ForecastRequest, dict], Awaitable[tuple[list[ForecastPoint], str]]]] = {
    HorizonType.minute_ahead: run_minute_ahead,
    HorizonType.hour_ahead: run_hour_ahead,
    HorizonType.day_ahead: run_day_ahead,
}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post("/forecast", response_model=ForecastResponse)
async def forecast(req: ForecastRequest):
    horizon = HorizonType(req.horizon_type)
    handler = ROUTES.get(horizon)
    if handler is None:
        raise HTTPException(400, f"Unsupported horizon_type: {horizon}")

    cfg = dict(HORIZON_CFG[horizon])
    if req.steps:
        cfg["steps"] = req.steps

    points, model_name = await handler(req, cfg)
    reserve = compute_reserve(points)

    return ForecastResponse(
        site_code=req.site_code,
        horizon_type=horizon,
        model_name=model_name,
        generated_at=datetime.now(timezone.utc),
        pi_nominal=req.pi_nominal,
        points=points,
        reserve=reserve,
    )


# ---------------------------------------------------------------------------
# GTG operational signals
# ---------------------------------------------------------------------------
def compute_reserve(points: list[ForecastPoint]) -> ReserveSignal:
    """
    Spinning reserve must cover the plausible solar *shortfall* against the point
    forecast, i.e. (p_hat - p_lower). Sharper PIs (smaller p_hat-p_lower) directly
    reduce the reserve the GTG must carry ⇒ less part-load fuel burn.
    """
    if not points:
        return ReserveSignal(spinning_reserve_kw=0.0, max_ramp_down_kw_per_min=0.0,
                             ramp_warning=False, zero_export_risk=False)

    reserve_kw = max((p.p_hat_kw - (p.p_lower_kw if p.p_lower_kw is not None else p.p_hat_kw))
                     for p in points)

    # steepest expected downward ramp between consecutive lead steps
    max_ramp = 0.0
    for a, b in zip(points, points[1:]):
        dt_min = max((b.target_time - a.target_time).total_seconds() / 60.0, 1e-6)
        drop = (a.p_hat_kw - b.p_hat_kw) / dt_min          # +ve = solar falling
        max_ramp = max(max_ramp, drop)

    zero_export = any(p.p_hat_kw > PLANT_NET_LOAD_KW for p in points)

    return ReserveSignal(
        spinning_reserve_kw=round(reserve_kw, 2),
        max_ramp_down_kw_per_min=round(max_ramp, 2),
        ramp_warning=max_ramp > GTG_RAMP_KW_PER_MIN,
        zero_export_risk=zero_export,
    )


# ---------------------------------------------------------------------------
# Placeholder generator (delete once real models are wired)
# ---------------------------------------------------------------------------
def _stub_points(req: ForecastRequest, cfg: dict) -> list[ForecastPoint]:
    import math
    t0 = (req.issued_at or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    half = (1.0 - req.pi_nominal) / 2.0  # crude symmetric band width factor for the stub
    pts: list[ForecastPoint] = []
    for k in range(1, cfg["steps"] + 1):
        tgt = t0 + timedelta(minutes=cfg["step_min"] * k)
        hour = tgt.hour + tgt.minute / 60.0
        # toy diurnal bell (replace with model output)
        p = max(0.0, 150.0 * math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0.0
        band = p * (0.15 + half)  # widen with lower nominal coverage — illustrative only
        pts.append(ForecastPoint(
            target_time=tgt, lead_minutes=cfg["step_min"] * k,
            p_hat_kw=round(p, 2),
            p_lower_kw=round(max(0.0, p - band), 2),
            p_upper_kw=round(p + band, 2),
        ))
    return pts
