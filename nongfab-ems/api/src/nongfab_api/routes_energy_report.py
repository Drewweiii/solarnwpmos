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

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from nongfab_common.assets import load_assets
from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location
from nongfab_features.panel_geometry import generate_zone_layout
from nongfab_features.shading import average_solar_access_pct, zone_solar_access
from nongfab_features.sld import build_sld
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from nongfab_simulation.dev_data import synthetic_day_irradiance_temp
from nongfab_simulation.loss_model import annual_specific_yield, performance_ratio
from nongfab_simulation.pipeline import (
    NONG_FAB_TZ,
    lifecycle_ac_energy_estimate,
    loss_breakdown_with_temperature,
    monthly_ac_energy_estimates,
    simulate_zone_baseline,
)
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


class MonthlyOut(BaseModel):
    month: int
    ac_energy_kwh: float
    is_rainy_season: bool


class LifecycleOut(BaseModel):
    year_1_ac_energy_kwh: float
    year_25_ac_energy_kwh: float
    year_25_pct_of_year_1: float
    lifetime_ac_energy_kwh: float
    degradation_pct_per_year_assumed: float


class EnergyReportResponse(BaseModel):
    zone: str
    simulated_zone: bool
    system_summary: SystemSummary
    annual: AnnualSummary
    loss_breakdown_pct: dict[str, float]
    # Where loss_breakdown_pct["soiling_pct"] came from: "measured-airquality-
    # rainfall" once the soiling advisor has published a figure derived from this
    # site's own PM10/salt/rainfall history, else "literature-default"
    # (2026-07-25). Surfaced so the losses table can say which it is rather than
    # letting a literature constant read as a measurement.
    soiling_source: str
    co2_saved_kg_per_year: float
    trees_equivalent_per_year: float
    avg_solar_access_pct: float
    monthly: list[MonthlyOut]
    lifecycle: LifecycleOut
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

    # Annual energy = sum of the 12 representative-month estimates (real pvlib
    # seasonal swing + rainy-season derate), not the old x365 of one clear-sky
    # day - so this headline agrees with the monthly chart right below it
    # (2026-07-22). `monthly` is computed once here and reused for both the
    # annual total and the chart, rather than paying for the 12x
    # simulate_zone_baseline twice.
    monthly = monthly_ac_energy_estimates(zone, year=datetime.now().year)
    annual_ac_energy_kwh = sum(m.ac_energy_kwh for m in monthly)
    specific_yield = annual_specific_yield(annual_ac_energy_kwh, baseline.zone.dc_capacity_kwp)
    loss_breakdown = loss_breakdown_with_temperature(baseline, ssrd, temp)

    co2_saved_kg_per_year = zone_obj.ac_capacity_kw * registry.environmental.co2_saved_kg_per_kw_per_year
    trees_equivalent_per_year = zone_obj.ac_capacity_kw * registry.environmental.trees_equivalent_per_kw_per_year

    # Solar access at local solar noon today (Asia/Bangkok) - a stable,
    # well-defined snapshot rather than "whenever the request happens to
    # land" (which would make the same report show a different number
    # depending on time of day); not a true annual energy-weighted average
    # across the whole year's sun path (that's a follow-up, not this pass).
    layout = generate_zone_layout(zone, registry)
    lat, lon = nong_fab_site_location()
    local_noon = pd.Timestamp.now(tz=NONG_FAB_TZ).normalize() + pd.Timedelta(hours=12)
    solpos = compute_clearsky_and_position(pd.DatetimeIndex([local_noon]), lat, lon, tz=NONG_FAB_TZ)
    access = zone_solar_access(layout, float(solpos["elevation_deg"].iloc[0]), float(solpos["azimuth_deg"].iloc[0]))
    avg_access_pct = average_solar_access_pct(access)

    lifecycle = lifecycle_ac_energy_estimate(annual_ac_energy_kwh)

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
        soiling_source=baseline.loss_factors.soiling_source,
        co2_saved_kg_per_year=co2_saved_kg_per_year,
        trees_equivalent_per_year=trees_equivalent_per_year,
        avg_solar_access_pct=avg_access_pct,
        monthly=[MonthlyOut(month=m.month, ac_energy_kwh=m.ac_energy_kwh, is_rainy_season=m.is_rainy_season) for m in monthly],
        lifecycle=LifecycleOut(
            year_1_ac_energy_kwh=lifecycle.year_1_ac_energy_kwh,
            year_25_ac_energy_kwh=lifecycle.year_25_ac_energy_kwh,
            year_25_pct_of_year_1=lifecycle.year_25_pct_of_year_1,
            lifetime_ac_energy_kwh=lifecycle.lifetime_ac_energy_kwh,
            degradation_pct_per_year_assumed=lifecycle.degradation_pct_per_year_assumed,
        ),
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
