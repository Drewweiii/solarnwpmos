"""GET /performance/{zone} - performance-ratio / specific-yield snapshot for
today, built on the same Module 5 pipeline (`simulate_zone_baseline`) the
simulate route uses. No real accumulated (I, T, P) history exists yet (see
forecast/README "Known gaps"), so - like every other module's dev-time
behavior - this computes against a synthetic "today" rather than reading
TimescaleDB; swapping the synthetic generator for a real query is a
follow-up once Modules 1-3 have accumulated enough history, not a change to
this route's shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from nongfab_simulation.dev_data import synthetic_day_irradiance_temp
from nongfab_simulation.loss_model import performance_ratio
from nongfab_simulation.pipeline import simulate_zone_baseline
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["performance"])


class PerformanceResponse(BaseModel):
    zone: str
    simulated_zone: bool
    ac_energy_kwh_today: float
    poa_irradiance_kwh_per_m2_today: float
    performance_ratio: float
    specific_yield_kwh_per_kwp_today: float
    loss_breakdown: dict[str, float]


def _validate_zone(zone: str) -> str:
    capacities = nong_fab_zone_capacities_kwp()
    if zone not in capacities:
        raise HTTPException(status_code=404, detail=f"unknown zone {zone!r}; known zones: {sorted(capacities)}")
    return zone


@router.get("/performance/{zone}", response_model=PerformanceResponse)
async def get_performance(zone: str, _user=Depends(require_role("viewer"))) -> PerformanceResponse:
    zone = _validate_zone(zone)
    idx, ssrd, temp = synthetic_day_irradiance_temp()
    baseline = simulate_zone_baseline(zone, ssrd, temp, idx)

    ac_energy_kwh = float(baseline.ac_power_kw.sum())  # hourly samples -> sum of kW == kWh
    poa_irradiance_kwh_per_m2 = float(ssrd.sum() / 1000)  # W/m^2 hourly samples -> kWh/m^2

    try:
        pr = performance_ratio(ac_energy_kwh, poa_irradiance_kwh_per_m2, baseline.zone.dc_capacity_kwp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PerformanceResponse(
        zone=zone, simulated_zone=baseline.zone.simulated, ac_energy_kwh_today=ac_energy_kwh,
        poa_irradiance_kwh_per_m2_today=poa_irradiance_kwh_per_m2, performance_ratio=pr,
        specific_yield_kwh_per_kwp_today=ac_energy_kwh / baseline.zone.dc_capacity_kwp,
        loss_breakdown=baseline.loss_breakdown,
    )
