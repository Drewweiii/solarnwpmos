"""POST /simulate/{zone} - what-if scenario + optional Monte Carlo interval,
built on Module 5's pipeline (`nongfab_simulation.pipeline.
simulate_zone_baseline`) and mirroring Module 5's dev API's own request/
response shape, so a client that already speaks that dev API needs no
changes to call this production route.

Gated at "operator" or higher (not just "viewer") since it's a heavier
what-if computation, not a plain read - unlike /assets/forecast/performance
which are read-only and open to any authenticated role.

Baseline generation is synthetic (no real accumulated irradiance/temperature
history exists yet - see forecast/README "Known gaps"), same caveat as every
other module's dev-time behavior.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from nongfab_simulation.monte_carlo import ScenarioDistribution, monte_carlo_scenario_simulation
from nongfab_simulation.pipeline import simulate_zone_baseline
from nongfab_simulation.what_if import ScenarioParams, apply_scenario
from pydantic import BaseModel

from .auth import require_role
from .baseline import day_baseline_conditions

router = APIRouter(tags=["simulate"])


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
    # "real" when the what-if baseline was built on today's real ingested NWP
    # (via nongfab_forecast.real_data.real_day_conditions), "synthetic" when
    # too little real history has accumulated for today and the synthetic
    # generator was used instead - see api/baseline.py. The scenario
    # adjustments (cloud/curtailment/degradation) are applied on top of
    # whichever baseline this is.
    data_source: str


def _validate_zone(zone: str) -> str:
    capacities = nong_fab_zone_capacities_kwp()
    if zone not in capacities:
        raise HTTPException(status_code=404, detail=f"unknown zone {zone!r}; known zones: {sorted(capacities)}")
    return zone


@router.post("/simulate/{zone}", response_model=SimulateResponse)
async def simulate(zone: str, req: SimulateRequest, request: Request, _user=Depends(require_role("operator"))) -> SimulateResponse:
    zone = _validate_zone(zone)
    idx, ssrd, temp, data_source = day_baseline_conditions(request.app.state.real_data_store)
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

    return SimulateResponse(
        zone=zone, simulated_zone=baseline.zone.simulated, points=points,
        loss_breakdown=baseline.loss_breakdown, data_source=data_source,
    )
