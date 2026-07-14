"""Dev-only FastAPI wrapper exposing POST /simulate/{zone} and
POST /simulate/{zone}/compare.

This is NOT the production Backend API (that's Module 6, not built yet -
its own spec lists /simulate too). Builds a synthetic baseline day (same
"no real accumulated history yet" caveat as Modules 3/4) via `pipeline.
simulate_zone_baseline()`, then layers a what-if scenario and (optionally) a
scenario-uncertainty Monte Carlo prediction interval on top - exercising the
whole Module 5 pipeline in one request.

Run with: uvicorn nongfab_simulation.api:app --reload --port 8003
Then open: http://localhost:8003/docs
"""

from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from pydantic import BaseModel

from .dev_data import synthetic_day_irradiance_temp as _synthetic_day_irradiance_temp
from .monte_carlo import ScenarioDistribution, monte_carlo_scenario_simulation
from .pipeline import simulate_zone_baseline
from .what_if import ScenarioParams, apply_scenario, compare_scenarios


app = FastAPI(
    title="Nong Fab EMS - Module 5 Simulation Engine (dev verification API)",
    description=(
        "Thin wrapper around the Module 5 what-if/Monte-Carlo/loss-model pipeline for "
        "interactive verification during development. Not Module 6's production Backend "
        "API. Baseline generation is synthetic (no real accumulated history yet); the "
        "system is fully on-grid, no battery/BESS (confirmed 2026-07-14, not implemented "
        "anywhere in this module)."
    ),
    version="0.2.0",
)


class SimulateRequest(BaseModel):
    extra_cloud_attenuation_pct: float = 0.0
    curtailment_pct: float = 0.0
    degradation_pct_per_year: float = 0.0
    years_since_commissioning: float = 0.0
    # Monte Carlo uncertainty (std, same units as the mean field above) around
    # each what-if parameter - 0.0 (the default) means that parameter is
    # treated as fixed, not sampled. If every std is 0.0, no Monte Carlo
    # interval is computed (points' lower/upper stay null).
    extra_cloud_attenuation_std_pct: float = 0.0
    curtailment_std_pct: float = 0.0
    degradation_std_pct_per_year: float = 0.0
    monte_carlo_n_samples: int = 1000


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


class ScenarioIn(BaseModel):
    extra_cloud_attenuation_pct: float = 0.0
    curtailment_pct: float = 0.0
    degradation_pct_per_year: float = 0.0


class CompareScenariosRequest(BaseModel):
    scenarios: dict[str, ScenarioIn]
    years_since_commissioning: float = 0.0


class CompareScenariosResponse(BaseModel):
    zone: str
    timestamps: list[datetime]
    series_kw: dict[str, list[float]]


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
    idx, ssrd, temp = _synthetic_day_irradiance_temp()
    baseline = simulate_zone_baseline(zone, ssrd, temp, idx)

    scenario = ScenarioParams(
        extra_cloud_attenuation_pct=req.extra_cloud_attenuation_pct,
        curtailment_pct=req.curtailment_pct,
        degradation_pct_per_year=req.degradation_pct_per_year,
    )
    has_uncertainty = bool(req.extra_cloud_attenuation_std_pct or req.curtailment_std_pct or req.degradation_std_pct_per_year)

    try:
        adjusted = apply_scenario(baseline.ac_power_kw, scenario, years_since_commissioning=req.years_since_commissioning)

        mc_result = None
        if has_uncertainty:
            distribution = ScenarioDistribution(
                extra_cloud_attenuation=(req.extra_cloud_attenuation_pct, req.extra_cloud_attenuation_std_pct),
                curtailment=(req.curtailment_pct, req.curtailment_std_pct),
                degradation_per_year=(req.degradation_pct_per_year, req.degradation_std_pct_per_year),
            )
            mc_result = monte_carlo_scenario_simulation(
                baseline.ac_power_kw, distribution, years_since_commissioning=req.years_since_commissioning,
                n_samples=req.monte_carlo_n_samples,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    points = [
        SimulatePointOut(
            timestamp=ts.to_pydatetime(),
            baseline_ac_kw=float(baseline.ac_power_kw.iloc[i]),
            adjusted_ac_kw=float(adjusted.iloc[i]),
            lower=float(mc_result["lower"].iloc[i]) if mc_result is not None else None,
            upper=float(mc_result["upper"].iloc[i]) if mc_result is not None else None,
        )
        for i, ts in enumerate(idx)
    ]

    return SimulateResponse(zone=zone, simulated_zone=baseline.zone.simulated, points=points, loss_breakdown=baseline.loss_breakdown)


@app.post("/simulate/{zone}/compare", response_model=CompareScenariosResponse)
async def simulate_compare(zone: str, req: CompareScenariosRequest) -> CompareScenariosResponse:
    """Sensitivity-analysis view: apply several named scenarios to the same
    baseline day and return them side by side - the preset-comparison a
    Simulation Playground UI needs (e.g. {"typical": {}, "cloudy_day":
    {"extra_cloud_attenuation_pct": 40}, "grid_curtailed": {"curtailment_pct": 30}}).
    """
    zone = _validate_zone(zone)
    idx, ssrd, temp = _synthetic_day_irradiance_temp()
    baseline = simulate_zone_baseline(zone, ssrd, temp, idx)

    scenarios = {
        name: ScenarioParams(
            extra_cloud_attenuation_pct=s.extra_cloud_attenuation_pct,
            curtailment_pct=s.curtailment_pct,
            degradation_pct_per_year=s.degradation_pct_per_year,
        )
        for name, s in req.scenarios.items()
    }

    try:
        result = compare_scenarios(baseline.ac_power_kw, scenarios, years_since_commissioning=req.years_since_commissioning)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CompareScenariosResponse(
        zone=zone, timestamps=[ts.to_pydatetime() for ts in idx],
        series_kw={name: result[name].tolist() for name in result.columns},
    )
