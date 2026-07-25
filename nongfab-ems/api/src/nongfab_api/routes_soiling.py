"""GET /soiling/{zone} - the Soiling & Cleaning Advisor (2026-07-25).

Answers the operational question the placeholder soiling derate never could:
how dirty is this array right now, how fast is it getting dirtier, when did rain
last wash it, what is the dirt costing, and roughly when is a wash worth
scheduling. Everything comes from history the app already ingests - CAMS
PM10/dust, GFS wind/humidity (via the salt-spray index) and GFS rainfall - run
through the Kimber/Coello-style model in `nongfab_features.soiling_dynamics`.
See `soiling_service` for the daily roll-up and the honesty notes on which
numbers are measured (all the inputs) vs. literature-calibrated (the rate
coefficients).

`available=false` with an explanatory `reason` whenever the stores can't yet
support an assessment - the route never invents a soiling level, exactly like
/forecast's feature-importance route never invents an untrained model.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from nongfab_common.assets import load_assets
from nongfab_forecast.local_store import RealDataStore
from nongfab_simulation.loss_model import SOILING_SOURCE_MEASURED, measured_soiling_pct
from nongfab_simulation.pipeline import seasonal_annual_ac_energy_kwh
from pydantic import BaseModel

from .auth import require_role
from .soiling_service import ZONES, assess_zone

router = APIRouter(tags=["soiling"])


class SoilingResponse(BaseModel):
    available: bool
    zone: str
    reason: str | None = None
    # Days of history the assessment walked.
    days_assessed: int = 0
    # Soiling loss (%) as of the most recent day, and the window average - the
    # average is what replaces the loss model's literature soiling placeholder.
    current_loss_pct: float = 0.0
    average_loss_pct: float = 0.0
    # How fast it is accumulating right now, %/day, from today's own PM10/salt.
    current_daily_rate_pct: float = 0.0
    # None when no cleaning rain fell anywhere in the window (unknown, not zero).
    days_since_cleaning_rain: int | None = None
    cleaning_events: int = 0
    # Dry days until soiling would reach `cleaning_trigger_pct`; None when it is
    # already past it (wash now) or nothing is accumulating.
    days_until_trigger: int | None = None
    cleaning_trigger_pct: float = 0.0
    max_loss_pct: float = 0.0
    # What the CURRENT soiling level would cost over a year if left alone. Both
    # None when the tariff isn't known.
    annual_energy_lost_kwh: float | None = None
    annual_cost_lost_thb: float | None = None
    # Whether the loss model is currently using this measured figure or is still
    # on its literature default.
    loss_model_soiling_source: str
    loss_model_soiling_pct: float | None = None
    # Day-by-day series for the panel's chart (ISO dates, oldest first).
    series_days: list[str] = []
    series_loss_pct: list[float] = []


def _implied_tariff_thb_per_kwh() -> float | None:
    """The facility's own implied blended rate: its real annual electricity cost
    divided by its real annual consumption (both user-stated figures in
    config/assets.yaml). Internally consistent, and NOT the placeholder PEA
    tariff the financial module still carries - so this route can price soiling
    losses without inheriting that placeholder. None when either figure is
    missing."""
    site = load_assets().site
    cost = getattr(site, "facility_annual_electricity_cost_thb", None)
    load_kw = getattr(site, "facility_electrical_load_kw", None)
    if not cost or not load_kw:
        return None
    annual_load_kwh = load_kw * 8760
    if annual_load_kwh <= 0:
        return None
    return cost / annual_load_kwh


@router.get("/soiling/{zone}", response_model=SoilingResponse)
async def get_soiling(zone: str, request: Request, _user=Depends(require_role("viewer"))) -> SoilingResponse:
    if zone not in ZONES:
        raise HTTPException(status_code=404, detail=f"unknown zone '{zone}'")
    store: RealDataStore = request.app.state.real_data_store

    published = measured_soiling_pct(zone)
    # Price the loss against this zone's own seasonal annual energy estimate, so
    # the "cost of dirt" scales with the array rather than being site-wide.
    annual_clean_kwh = seasonal_annual_ac_energy_kwh(zone)
    assessment = assess_zone(
        store,
        zone,
        annual_clean_energy_kwh=annual_clean_kwh,
        tariff_thb_per_kwh=_implied_tariff_thb_per_kwh(),
    )
    if not assessment.available:
        return SoilingResponse(
            available=False,
            zone=zone,
            reason="ยังไม่มีข้อมูลคุณภาพอากาศ (CAMS) หรือข้อมูลลม/ฝนย้อนหลังพอที่จะประเมินคราบสกปรก",
            loss_model_soiling_source="literature-default" if published is None else SOILING_SOURCE_MEASURED,
            loss_model_soiling_pct=published,
        )
    return SoilingResponse(
        available=True,
        zone=zone,
        days_assessed=assessment.days_assessed,
        current_loss_pct=assessment.current_loss_pct,
        average_loss_pct=assessment.average_loss_pct,
        current_daily_rate_pct=assessment.current_daily_rate_pct,
        days_since_cleaning_rain=assessment.days_since_cleaning_rain,
        cleaning_events=assessment.cleaning_events,
        days_until_trigger=assessment.days_until_trigger,
        cleaning_trigger_pct=assessment.cleaning_trigger_pct,
        max_loss_pct=assessment.max_loss_pct,
        annual_energy_lost_kwh=assessment.annual_energy_lost_kwh,
        annual_cost_lost_thb=assessment.annual_cost_lost_thb,
        loss_model_soiling_source="literature-default" if published is None else SOILING_SOURCE_MEASURED,
        loss_model_soiling_pct=published,
        series_days=list(assessment.series_days),
        series_loss_pct=list(assessment.series_loss_pct),
    )
