"""Dev-only FastAPI wrapper exposing POST /simulate/{zone}.

This is NOT the production Backend API (that's Module 6, not built yet -
its own spec lists /simulate too). Builds a synthetic baseline day (same
"no real accumulated history yet" caveat as Modules 3/4), applies the
PVWatts-style loss model + DC/AC clipping to get baseline AC power, then
layers a what-if scenario and (optionally) a Monte Carlo prediction
interval on top - exercising the whole Module 5 pipeline in one request.

Run with: uvicorn nongfab_simulation.api:app --reload --port 8003
Then open: http://localhost:8003/docs
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from nongfab_common.assets import load_assets
from nongfab_forecast.pv_conversion import default_params_from_capacity, nong_fab_zone_capacities_kwp, predict_power_kw
from pydantic import BaseModel

from .loss_model import apply_losses, clip_to_inverter_capacity, default_loss_factors, loss_breakdown_summary
from .monte_carlo import monte_carlo_prediction_interval
from .what_if import ScenarioParams, apply_scenario

DEFAULT_INVERTER_EFFICIENCY_PCT = 99.0  # Huawei SUN2000-50KTL-M3 datasheet value, all 3 zones use this model


def _synthetic_day_irradiance_temp(n_hours: int = 24, seed: int = 0) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    idx = pd.date_range(start, periods=n_hours, freq="h", tz="UTC")
    hour = idx.hour.to_numpy()
    ssrd = np.clip(1000 * np.sin(np.pi * (hour - 6) / 12), 0, None)
    temp = 28 + 5 * np.sin(np.pi * (hour - 6) / 12) + rng.normal(0, 0.5, size=n_hours)
    return idx, ssrd, temp


app = FastAPI(
    title="Nong Fab EMS - Module 5 Simulation Engine (dev verification API)",
    description=(
        "Thin wrapper around the Module 5 what-if/Monte-Carlo/loss-model pipeline for "
        "interactive verification during development. Not Module 6's production Backend "
        "API. Baseline generation is synthetic (no real accumulated history yet); the "
        "system is fully on-grid, no battery/BESS (confirmed 2026-07-14)."
    ),
    version="0.1.0",
)


class SimulateRequest(BaseModel):
    extra_cloud_attenuation_pct: float = 0.0
    curtailment_pct: float = 0.0
    degradation_pct_per_year: float = 0.0
    years_since_commissioning: float = 0.0
    monte_carlo_error_std_kw: float | None = None
    monte_carlo_n_samples: int = 500


class SimulatePointOut(BaseModel):
    timestamp: datetime
    baseline_ac_kw: float
    adjusted_ac_kw: float
    lower: float | None = None
    upper: float | None = None


class SimulateResponse(BaseModel):
    zone: str
    simulated_zone: bool
    points: list[SimulatePointOut]
    loss_breakdown: dict[str, float]


def _validate_zone(zone: str) -> str:
    capacities = nong_fab_zone_capacities_kwp()
    if zone not in capacities:
        raise HTTPException(status_code=404, detail=f"unknown zone {zone!r}; known zones: {sorted(capacities)}")
    return zone


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/simulate/{zone}", response_model=SimulateResponse)
async def simulate(zone: str, req: SimulateRequest) -> SimulateResponse:
    zone = _validate_zone(zone)
    registry = load_assets()
    z = registry.zone(zone)

    idx, ssrd, temp = _synthetic_day_irradiance_temp()
    pv_params = default_params_from_capacity(z.dc_capacity_kwp)
    dc_power = pd.Series(predict_power_kw(ssrd, temp, pv_params), index=idx)

    factors = default_loss_factors(zone)
    inverter_efficiency_pct = z.inverter_detail.efficiency_pct if z.inverter_detail else DEFAULT_INVERTER_EFFICIENCY_PCT
    ac_power = apply_losses(dc_power, factors, inverter_efficiency_pct)
    ac_power = clip_to_inverter_capacity(ac_power, z.ac_capacity_kw)

    scenario = ScenarioParams(
        extra_cloud_attenuation_pct=req.extra_cloud_attenuation_pct,
        curtailment_pct=req.curtailment_pct,
        degradation_pct_per_year=req.degradation_pct_per_year,
    )
    adjusted = apply_scenario(ac_power, scenario, years_since_commissioning=req.years_since_commissioning)

    mc_result = None
    if req.monte_carlo_error_std_kw is not None:
        mc_result = monte_carlo_prediction_interval(
            adjusted, error_std=req.monte_carlo_error_std_kw, n_samples=req.monte_carlo_n_samples
        )

    points = [
        SimulatePointOut(
            timestamp=ts.to_pydatetime(),
            baseline_ac_kw=float(ac_power.iloc[i]),
            adjusted_ac_kw=float(adjusted.iloc[i]),
            lower=float(mc_result["lower"].iloc[i]) if mc_result is not None else None,
            upper=float(mc_result["upper"].iloc[i]) if mc_result is not None else None,
        )
        for i, ts in enumerate(idx)
    ]

    return SimulateResponse(
        zone=zone, simulated_zone=z.simulated, points=points,
        loss_breakdown=loss_breakdown_summary(factors, inverter_efficiency_pct),
    )
