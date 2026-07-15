"""GET /energy-report/{zone} - Module 7's Feature D: a per-zone energy
report (system summary, annual generation/specific yield/performance ratio,
full loss breakdown incl. temperature, CO2 saved) plus the real-equipment-
derived interactive SLD topology. Reuses Module 5's pipeline
(`simulate_zone_baseline`, `estimate_annual_ac_energy_kwh`,
`loss_breakdown_with_temperature`) and Module 3's new `nongfab_features.sld.
build_sld()` rather than duplicating any of that - same synthetic-baseline
caveat as `/performance/{zone}` (see that route's own docstring): no real
accumulated history exists yet, so annual figures are a flat extrapolation
of one synthetic clear-sky day, not a real annual simulation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from nongfab_common.assets import load_assets
from nongfab_features.sld import build_sld
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from nongfab_simulation.dev_data import synthetic_day_irradiance_temp
from nongfab_simulation.loss_model import annual_specific_yield, performance_ratio
from nongfab_simulation.pipeline import estimate_annual_ac_energy_kwh, loss_breakdown_with_temperature, simulate_zone_baseline
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["energy-report"])


class SystemSummary(BaseModel):
    ac_capacity_kw: float
    dc_capacity_kwp: float
    dc_ac_ratio: float
    module_count: int
    module_power_w: float
    array_area_m2: float | None
    inverter_model: str
    inverter_count: int


class AnnualSummary(BaseModel):
    ac_energy_kwh: float
    specific_yield_kwh_per_kwp: float
    performance_ratio: float


class SLDStringOut(BaseModel):
    id: str
    modules: int


class SLDBlockOut(BaseModel):
    id: str
    inverter_model: str
    inverter_ac_kw: float
    mppt_count: int
    strings: list[SLDStringOut]


class SLDOut(BaseModel):
    module_model: str | None
    module_power_w: float
    optimizer_model: str | None
    optimizer_ratio_modules_per_optimizer: int | None
    blocks: list[SLDBlockOut]
    approximate_string_distribution: bool


class EnergyReportResponse(BaseModel):
    zone: str
    simulated_zone: bool
    system_summary: SystemSummary
    annual: AnnualSummary
    loss_breakdown_pct: dict[str, float]
    co2_saved_kg_per_year: float
    trees_equivalent_per_year: float
    sld: SLDOut


def _validate_zone(zone: str) -> str:
    capacities = nong_fab_zone_capacities_kwp()
    if zone not in capacities:
        raise HTTPException(status_code=404, detail=f"unknown zone {zone!r}; known zones: {sorted(capacities)}")
    return zone


def _array_area_m2(zone_obj) -> float | None:
    """Module footprint area (not a claim about ground coverage/GCR, just
    modules_count x each module's own real dimensions from its datasheet -
    config/assets.yaml's `module_detail.dimensions_mm`). None if a zone has
    no module_detail on file.
    """
    if zone_obj.module_detail is None:
        return None
    long_m = zone_obj.module_detail.dimensions_mm[0] / 1000
    short_m = zone_obj.module_detail.dimensions_mm[1] / 1000
    return zone_obj.module_count * long_m * short_m


@router.get("/energy-report/{zone}", response_model=EnergyReportResponse)
async def get_energy_report(zone: str, _user=Depends(require_role("viewer"))) -> EnergyReportResponse:
    zone = _validate_zone(zone)
    registry = load_assets()
    zone_obj = registry.zone(zone)

    idx, ssrd, temp = synthetic_day_irradiance_temp()
    baseline = simulate_zone_baseline(zone, ssrd, temp, idx)

    ac_energy_kwh_today = float(baseline.ac_power_kw.sum())
    poa_irradiance_kwh_per_m2_today = float(ssrd.sum() / 1000)
    pr = performance_ratio(ac_energy_kwh_today, poa_irradiance_kwh_per_m2_today, baseline.zone.dc_capacity_kwp)

    annual_ac_energy_kwh = estimate_annual_ac_energy_kwh(baseline)
    specific_yield = annual_specific_yield(annual_ac_energy_kwh, baseline.zone.dc_capacity_kwp)
    loss_breakdown = loss_breakdown_with_temperature(baseline, ssrd, temp)

    co2_saved_kg_per_year = zone_obj.ac_capacity_kw * registry.environmental.co2_saved_kg_per_kw_per_year
    trees_equivalent_per_year = zone_obj.ac_capacity_kw * registry.environmental.trees_equivalent_per_kw_per_year

    sld = build_sld(zone_obj)

    return EnergyReportResponse(
        zone=zone,
        simulated_zone=zone_obj.simulated,
        system_summary=SystemSummary(
            ac_capacity_kw=zone_obj.ac_capacity_kw, dc_capacity_kwp=zone_obj.dc_capacity_kwp,
            dc_ac_ratio=zone_obj.dc_ac_ratio, module_count=zone_obj.module_count,
            module_power_w=zone_obj.module_power_w, array_area_m2=_array_area_m2(zone_obj),
            inverter_model=zone_obj.inverter_model, inverter_count=zone_obj.inverter_count,
        ),
        annual=AnnualSummary(
            ac_energy_kwh=annual_ac_energy_kwh, specific_yield_kwh_per_kwp=specific_yield, performance_ratio=pr,
        ),
        loss_breakdown_pct=loss_breakdown,
        co2_saved_kg_per_year=co2_saved_kg_per_year,
        trees_equivalent_per_year=trees_equivalent_per_year,
        sld=SLDOut(
            module_model=sld.module_model, module_power_w=sld.module_power_w,
            optimizer_model=sld.optimizer_model,
            optimizer_ratio_modules_per_optimizer=sld.optimizer_ratio_modules_per_optimizer,
            blocks=[
                SLDBlockOut(
                    id=b.id, inverter_model=b.inverter_model, inverter_ac_kw=b.inverter_ac_kw,
                    mppt_count=b.mppt_count, strings=[SLDStringOut(id=s.id, modules=s.modules) for s in b.strings],
                )
                for b in sld.blocks
            ],
            approximate_string_distribution=sld.approximate_string_distribution,
        ),
    )
