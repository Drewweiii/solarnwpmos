"""GET /savings/summary - the Energy Report page's bottom "savings & carbon"
table. For each real zone (ISB, GIS, Jetty) plus a combined "all three" row,
and for each horizon (1 day / 1 month / 1 year / 25-year lifetime), it reports
the solar generation and the money/CO2/carbon-credit figures computed by the
pure `green_savings` module.

Generation figures reuse Module 5's existing pipeline - no new physics:
  * month  = the current calendar month's seasonal estimate
             (`monthly_ac_energy_estimates`, so it "updates" as the month/
             season advances, per the user's 2026-07-19 "1วัน+1เดือน update
             ตลอด" request)
  * day    = that month's estimate / its real day count
  * year   = sum of all 12 monthly estimates (seasonal, incl. rainy-season
             derate - more faithful than a flat one-day extrapolation)
  * 25-yr  = `lifecycle_ac_energy_estimate` of the annual figure, i.e. the
             degraded 25-year sum (degradation %/yr from the project's
             documented datasheet-range constant), matching "1ปี กับ 25ปี ให้
             คำนวณคร่าวๆ".

Same synthetic-baseline caveat as `/energy-report/{zone}`: no real accumulated
generation history exists yet, so these are model estimates, not metered
figures.
"""

from __future__ import annotations

import calendar

import pandas as pd
from fastapi import APIRouter, Depends
from nongfab_common.assets import load_assets
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from nongfab_simulation.pipeline import (
    NONG_FAB_TZ,
    lifecycle_ac_energy_estimate,
    monthly_ac_energy_estimates,
)
from pydantic import BaseModel

from . import green_savings
from .auth import require_role
from .settings_store import effective

router = APIRouter(tags=["savings"])

# The three physically-defined zones, in the order the UI shows their tabs.
REAL_ZONE_IDS = ("ISB", "GIS", "Jetty")
_COMBINED_ID = "combined"

# Capacity-based horizon lengths in years (for the carbon-credit / trees rule
# of thumb only - generation figures carry their own seasonal/degradation).
_YEARS = {"day": 1.0 / 365.0, "month": 1.0 / 12.0, "year": 1.0, "lifetime": 25.0}


class SavingsMetricsOut(BaseModel):
    energy_kwh: float
    bill_saving_thb: float
    ugt1_units_kwh: float
    ugt1_saving_thb: float
    ugt2_units_kwh: float
    ugt2_saving_thb: float
    carbon_credit_units: float
    carbon_credit_value_thb: float
    trees_equivalent: float
    scope2_co2_avoided_kg: float


class SavingsPeriodsOut(BaseModel):
    day: SavingsMetricsOut
    month: SavingsMetricsOut
    year: SavingsMetricsOut
    lifetime: SavingsMetricsOut


class ZoneSavingsOut(BaseModel):
    zone: str
    label: str
    simulated: bool
    dc_capacity_kwp: float
    periods: SavingsPeriodsOut


class SavingsSummaryResponse(BaseModel):
    zones: list[ZoneSavingsOut]
    assumptions: dict[str, float | str]


def _zone_generation_kwh(zone_id: str, year: int, month: int) -> dict[str, float]:
    """Day / month / year / lifetime generation (kWh) for one zone."""
    monthly = monthly_ac_energy_estimates(zone_id, year=year)
    annual_kwh = sum(m.ac_energy_kwh for m in monthly)
    month_kwh = monthly[month - 1].ac_energy_kwh
    days_in_month = calendar.monthrange(year, month)[1]
    day_kwh = month_kwh / days_in_month if days_in_month else 0.0
    lifecycle = lifecycle_ac_energy_estimate(annual_kwh)
    return {
        "day": day_kwh,
        "month": month_kwh,
        "year": annual_kwh,
        "lifetime": lifecycle.lifetime_ac_energy_kwh,
    }


def _green_assumptions() -> green_savings.GreenAssumptions:
    """The tariff/carbon figures as the user has them set (settings_registry's
    `green.*` group), defaulting to the constants green_savings ships with.

    These are all published national rates and factors that change on somebody
    else's schedule, which is why they are editable at all - see the registry's
    note on `green.ef_scope2_kg_per_kwh`, where two official Thai sources
    disagree and the choice is deliberately left to the user.
    """
    return green_savings.GreenAssumptions(
        normal_rate_thb_per_kwh=effective("green.normal_rate_thb_per_kwh"),
        ugt1_premium_thb_per_kwh=effective("green.ugt1_premium_thb_per_kwh"),
        ugt2_rate_thb_per_kwh=effective("green.ugt2_rate_thb_per_kwh"),
        ef_scope2_kg_per_kwh=effective("green.ef_scope2_kg_per_kwh"),
        carbon_credit_unit_per_kwp_year=effective("green.carbon_credit_unit_per_kwp_year"),
        trees_per_kwp_year=effective("green.trees_per_kwp_year"),
        carbon_price_thb_per_tonne=effective("green.carbon_price_thb_per_tonne"),
    )


def _periods(generation: dict[str, float], dc_capacity_kwp: float, params: green_savings.GreenAssumptions) -> SavingsPeriodsOut:
    cells = {
        horizon: SavingsMetricsOut(
            **green_savings.compute_metrics(
                generation[horizon], dc_capacity_kwp, _YEARS[horizon], params
            ).as_dict()
        )
        for horizon in ("day", "month", "year", "lifetime")
    }
    return SavingsPeriodsOut(**cells)


@router.get("/savings/summary", response_model=SavingsSummaryResponse)
async def get_savings_summary(_user=Depends(require_role("viewer"))) -> SavingsSummaryResponse:
    registry = load_assets()
    capacities = nong_fab_zone_capacities_kwp()
    now = pd.Timestamp.now(tz=NONG_FAB_TZ)
    year, month = now.year, now.month

    zones: list[ZoneSavingsOut] = []
    combined_gen = {"day": 0.0, "month": 0.0, "year": 0.0, "lifetime": 0.0}
    combined_kwp = 0.0
    # Resolved once per request, so every zone row and the combined row are all
    # priced with the same figures.
    params = _green_assumptions()

    for zone_id in REAL_ZONE_IDS:
        zone_obj = registry.zone(zone_id)
        dc_kwp = capacities.get(zone_id, zone_obj.dc_capacity_kwp)
        generation = _zone_generation_kwh(zone_id, year, month)
        for horizon in combined_gen:
            combined_gen[horizon] += generation[horizon]
        combined_kwp += dc_kwp
        zones.append(
            ZoneSavingsOut(
                zone=zone_id,
                label=zone_obj.name_full or zone_id,
                simulated=zone_obj.simulated,
                dc_capacity_kwp=dc_kwp,
                periods=_periods(generation, dc_kwp, params),
            )
        )

    zones.append(
        ZoneSavingsOut(
            zone=_COMBINED_ID,
            label="รวม 3 กลุ่ม (ISB + GIS + Jetty)",
            simulated=any(registry.zone(z).simulated for z in REAL_ZONE_IDS),
            dc_capacity_kwp=combined_kwp,
            periods=_periods(combined_gen, combined_kwp, params),
        )
    )

    return SavingsSummaryResponse(zones=zones, assumptions=green_savings.assumptions(params))
