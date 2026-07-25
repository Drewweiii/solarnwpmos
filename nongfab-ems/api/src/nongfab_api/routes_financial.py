"""POST /financial - plant-wide NPV/IRR/LCOE/payback investment analysis,
built on Module 11's (`nongfab_financial.model`) financial engine.

Plant-wide, not per-zone, unlike every other route in this API: CAPEX,
financing, and payback are evaluated at the investment level, not one
number per sub-array. Only the currently-installed zones (GIS, ISB) feed
the year-1 energy estimate - Jetty is excluded (`simulated: true` in
config/assets.yaml - design-mode, no panels installed yet, so it isn't a
real capital outlay to analyze the payback of).

Gated at "operator" or higher, same reasoning as /simulate: a heavier
what-if computation carrying business-sensitive assumptions, not a plain
read like /assets or /performance.

Every request field is optional and overrides one of
`nongfab_financial.model.FinancialAssumptions`'s own documented-placeholder
defaults (CAPEX/tariff/WACC/BOI/tax) - see that module's own docstring for
which of those are real facts (Thailand's standard corporate tax rate) vs.
placeholders pending the user's real figures.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from nongfab_common.assets import load_assets
from nongfab_financial.model import FinancialAssumptions, compute_financial_analysis
from nongfab_financial.uncertainty import (
    FinancialDistribution,
    YieldUncertainty,
    exceedance_levels,
    monte_carlo_financial_analysis,
)
from nongfab_simulation.pipeline import seasonal_annual_ac_energy_kwh
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["financial"])

# Zones with real installed panels to analyze the investment of - see this
# file's own docstring for why Jetty is excluded.
INSTALLED_ZONE_IDS = ("GIS", "ISB")


class FinancialRequest(BaseModel):
    capex_thb: float | None = None
    opex_pct_of_capex_per_year: float | None = None
    tariff_thb_per_kwh: float | None = None
    tariff_escalation_pct_per_year: float | None = None
    opex_escalation_pct_per_year: float | None = None
    discount_rate_pct: float | None = None
    tax_rate_pct: float | None = None
    boi_tax_holiday_years: int | None = None
    degradation_pct_per_year: float | None = None
    degradation_first_year_pct: float | None = None
    lifetime_years: int | None = None


class CashFlowYearOut(BaseModel):
    year: int
    ac_energy_kwh: float
    avoided_cost_thb: float
    opex_thb: float
    tax_thb: float
    net_cash_flow_thb: float
    cumulative_undiscounted_cash_flow_thb: float
    cumulative_discounted_cash_flow_thb: float


class BoiPresetOut(BaseModel):
    """One BOI holiday the project actually holds, for the page's quick-set
    buttons. Sent from the server rather than hardcoded in the UI so that
    editing the figure in Settings moves the button too - a preset that
    disagrees with the published setting is worse than no preset."""

    label: str
    years: int


UNCERTAINTY_NOTE = (
    "สองแถบนี้มาจากคนละที่ · P50/P90 คือความผันผวนของแดดแต่ละปี คำนวณจากข้อมูลจริง "
    "ของ NASA POWER ที่พิกัดหนองแฟบเอง ครบ 26 ปี (2000-2025) ได้ 2.11% ไม่ใช่ค่าที่ยืม"
    "มาจากงานวิจัยที่อื่น (แต่ก็ยังเป็นความผันผวนของ 'แสง' ไม่ใช่ของมิเตอร์หน้างาน) · "
    "ส่วนช่วงของ NPV/IRR ยังเป็น 'ความไม่แน่ใจ' ล้วนๆ เพราะ CAPEX และ WACC ยังเป็น"
    "ค่าประมาณ ไม่ใช่ราคาจริงของโครงการ · ปรับค่าความไม่แน่นอนได้ในหน้า Settings "
    "กลุ่มสมมติฐานการเงิน"
)


class ExceedanceYieldOut(BaseModel):
    label: str
    exceedance: float
    annual_energy_kwh: float


class MetricPercentilesOut(BaseModel):
    metric: str
    p10: float | None
    p50: float | None
    p90: float | None
    mean: float | None
    undefined_trials: int


class UncertaintyOut(BaseModel):
    """P50/P90 yield and the Monte Carlo spread, reported separately - the sun
    is the predictable part here, the price of the project is not."""

    available: bool
    reason: str | None = None
    yield_levels: list[ExceedanceYieldOut] = []
    samples: int = 0
    metrics: list[MetricPercentilesOut] = []
    probability_npv_negative_pct: float = 0.0
    probability_no_payback_pct: float = 0.0
    method_note: str = UNCERTAINTY_NOTE


class FinancialResponse(BaseModel):
    installed_dc_capacity_kwp: float
    year_1_ac_energy_kwh: float
    capex_thb: float
    npv_thb: float
    irr_pct: float | None
    lcoe_thb_per_kwh: float
    simple_payback_years: float | None
    discounted_payback_years: float | None
    cash_flows: list[CashFlowYearOut]
    boi_presets: list[BoiPresetOut] = []
    uncertainty: UncertaintyOut | None = None



# settings key -> FinancialAssumptions field. `capex_thb` is deliberately absent:
# the settings registry holds CAPEX per kWp (which is how it is quoted, and what
# /expansion needs), so the total is derived below from the installed capacity.
_ASSUMPTION_KEYS = {
    "financial.opex_pct_of_capex_per_year": "opex_pct_of_capex_per_year",
    "financial.tariff_thb_per_kwh": "tariff_thb_per_kwh",
    "financial.tariff_escalation_pct_per_year": "tariff_escalation_pct_per_year",
    "financial.opex_escalation_pct_per_year": "opex_escalation_pct_per_year",
    "financial.discount_rate_pct": "discount_rate_pct",
    "financial.tax_rate_pct": "tax_rate_pct",
    "financial.boi_tax_holiday_years": "boi_tax_holiday_years",
    "financial.degradation_pct_per_year": "degradation_pct_per_year",
    "financial.degradation_first_year_pct": "degradation_first_year_pct",
    "financial.lifetime_years": "lifetime_years",
}


def _boi_presets() -> list[BoiPresetOut]:
    """The BOI holidays this project actually holds, read live from settings.

    Confirmed by the user 2026-07-25: 8 years in the general areas, 12 for the
    Jetty. Read rather than hardcoded so an edit in Settings reaches the page's
    quick-set buttons; duplicates are collapsed so setting both to the same
    number shows one button instead of two identical ones.
    """
    from .settings_store import effective

    wanted = [
        ("พื้นที่ทั่วไป (GIS, ISB)", "financial.boi_tax_holiday_years"),
        ("Jetty", "financial.boi_tax_holiday_years_jetty"),
    ]
    presets: list[BoiPresetOut] = []
    seen: set[int] = set()
    for label, key in wanted:
        try:
            years = int(effective(key))
        except KeyError:
            continue
        if years in seen:
            continue
        seen.add(years)
        presets.append(BoiPresetOut(label=f"{years} ปี — {label}", years=years))
    return presets


def _configured_assumptions(installed_dc_capacity_kwp: float) -> dict[str, float]:
    """The financial assumptions as the user has them set (settings_registry).

    Only keys an admin actually published are returned, so an untouched system
    still gets `FinancialAssumptions`' own documented defaults rather than a
    restatement of them. CAPEX is the one translation: the registry holds it per
    kWp (how it is quoted, and what /expansion needs), so it becomes a total here
    against the installed capacity.
    """
    from .settings_store import effective, is_overridden

    configured = {field: effective(key) for key, field in _ASSUMPTION_KEYS.items() if is_overridden(key)}
    if is_overridden("financial.capex_per_kwp_thb") and installed_dc_capacity_kwp > 0:
        configured["capex_thb"] = effective("financial.capex_per_kwp_thb") * installed_dc_capacity_kwp
    return configured

def _configured_distribution() -> FinancialDistribution:
    """The uncertainty spreads as the user has them set. Defaults come from the
    registry, so an admin widens or (once real figures land) collapses the bands
    without a deploy."""
    from .settings_store import effective

    return FinancialDistribution(
        capex_per_kwp_std_thb=effective("financial.capex_std_per_kwp_thb"),
        tariff_std_thb_per_kwh=effective("financial.tariff_std_thb_per_kwh"),
        discount_rate_std_pct=effective("financial.discount_rate_std_pct"),
        annual_yield_cv_pct=effective("financial.annual_yield_cv_pct"),
    )


def _uncertainty_block(
    year_1_ac_energy_kwh: float, installed_dc_capacity_kwp: float, assumptions: FinancialAssumptions
) -> UncertaintyOut:
    """P50/P90 + Monte Carlo for this request's assumptions.

    Honest-empty when every spread is zero: with nothing declared uncertain
    there is no distribution to show, and drawing a flat band would suggest a
    confidence the inputs do not support.
    """
    from .settings_store import effective

    distribution = _configured_distribution()
    if not distribution.any_uncertainty():
        return UncertaintyOut(
            available=False,
            reason="ยังไม่ได้ตั้งค่าความไม่แน่นอนของสมมติฐานใดเลย จึงไม่มีช่วงให้แสดง (ตั้งได้ในหน้า Settings)",
        )

    levels = exceedance_levels(
        year_1_ac_energy_kwh, YieldUncertainty(annual_cv_pct=distribution.annual_yield_cv_pct)
    )
    mc = monte_carlo_financial_analysis(
        year_1_ac_energy_kwh,
        installed_dc_capacity_kwp,
        assumptions,
        distribution,
        n_samples=int(effective("financial.monte_carlo_samples")),
    )
    return UncertaintyOut(
        available=True,
        yield_levels=[
            ExceedanceYieldOut(label=lv.label, exceedance=lv.exceedance, annual_energy_kwh=lv.annual_energy_kwh)
            for lv in levels
        ],
        samples=mc.samples,
        metrics=[
            MetricPercentilesOut(
                metric=m.metric, p10=m.p10, p50=m.p50, p90=m.p90, mean=m.mean, undefined_trials=m.undefined_trials
            )
            for m in mc.metrics.values()
        ],
        probability_npv_negative_pct=mc.probability_npv_negative_pct,
        probability_no_payback_pct=mc.probability_no_payback_pct,
    )


@router.post("/financial", response_model=FinancialResponse)
async def get_financial_analysis(req: FinancialRequest, _user=Depends(require_role("operator"))) -> FinancialResponse:
    registry = load_assets()

    # Year-1 energy is the seasonal annual estimate (real pvlib per-month
    # swing + rainy-season derate - see seasonal_annual_ac_energy_kwh), summed
    # across the installed zones, not the old x365 of one clear-sky day
    # (2026-07-22). This feeds NPV/IRR/LCOE/payback, so a seasonally honest
    # year-1 yield matters more here than anywhere - the rainy-season months
    # this now accounts for are a real drag on the payback the crude x365
    # silently ignored.
    year_1_ac_energy_kwh = 0.0
    installed_dc_capacity_kwp = 0.0
    for zone_id in INSTALLED_ZONE_IDS:
        year_1_ac_energy_kwh += seasonal_annual_ac_energy_kwh(zone_id)
        installed_dc_capacity_kwp += registry.zone(zone_id).dc_capacity_kwp

    # Start from the values the user has configured for this system, then let
    # the request's own fields win - so /financial's sliders still work as a
    # per-request what-if playground (2026-07-25), while an untouched request now
    # answers with the admin-published assumptions instead of the compiled
    # defaults.
    overrides = {**_configured_assumptions(installed_dc_capacity_kwp), **req.model_dump(exclude_none=True)}
    try:
        assumptions = FinancialAssumptions(**overrides)
        result = compute_financial_analysis(year_1_ac_energy_kwh, installed_dc_capacity_kwp, assumptions)
        uncertainty = _uncertainty_block(year_1_ac_energy_kwh, installed_dc_capacity_kwp, assumptions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FinancialResponse(
        installed_dc_capacity_kwp=installed_dc_capacity_kwp,
        year_1_ac_energy_kwh=year_1_ac_energy_kwh,
        capex_thb=result.capex_thb,
        npv_thb=result.npv_thb,
        irr_pct=result.irr_pct,
        lcoe_thb_per_kwh=result.lcoe_thb_per_kwh,
        simple_payback_years=result.simple_payback_years,
        discounted_payback_years=result.discounted_payback_years,
        cash_flows=[
            CashFlowYearOut(
                year=cf.year,
                ac_energy_kwh=cf.ac_energy_kwh,
                avoided_cost_thb=cf.avoided_cost_thb,
                opex_thb=cf.opex_thb,
                tax_thb=cf.tax_thb,
                net_cash_flow_thb=cf.net_cash_flow_thb,
                cumulative_undiscounted_cash_flow_thb=cf.cumulative_undiscounted_cash_flow_thb,
                cumulative_discounted_cash_flow_thb=cf.cumulative_discounted_cash_flow_thb,
            )
            for cf in result.cash_flows
        ],
        boi_presets=_boi_presets(),
        uncertainty=uncertainty,
    )
