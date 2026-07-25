"""GET /expansion - what each planned phase actually buys (2026-07-25).

config/assets.yaml already records the real planned phases (Jetty phase 1.5 =
+100 kW AC, phase 2 = +300 kW, "target total 600kW AC"), and nothing on the site
answered the question they raise: how much of the terminal's own 13.5 MW load does
each phase move, and what does the LAST kilowatt buy compared with the first.

Every input is a real figure except CAPEX, which is still the documented
placeholder ฿30,000/kWp from `nongfab_financial.model` - so `simple_payback_years`
inherits that placeholder and the response flags it in `capex_note`. The tariff
used is the facility's OWN implied rate (its real annual cost / real annual load),
not the financial module's placeholder PEA tariff.

See `nongfab_financial.expansion` for the scenario math and its documented
proportional-scaling assumption.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from nongfab_common.assets import load_assets
from nongfab_financial.expansion import (
    ExpansionPhase,
    build_scenarios,
    capacity_for_target_offset,
)
from nongfab_financial.model import DEFAULT_CAPEX_PER_KWP_THB
from nongfab_simulation.pipeline import seasonal_annual_ac_energy_kwh
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["expansion"])

ZONES = ("GIS", "ISB", "Jetty")
# Offsets worth pricing out next to a 600-800 kW plan, for a site drawing 13.5 MW.
TARGET_OFFSETS_PCT = (5.0, 10.0, 25.0)

CAPEX_NOTE = (
    "ค่า CAPEX ฿30,000/kWp เป็นค่าประมาณ (placeholder) ที่ยังไม่ได้ยืนยันกับโครงการนี้ "
    "ดังนั้นตัวเลข 'คืนทุนกี่ปี' จึงเป็นค่าประมาณตามไปด้วย ส่วนกำลังผลิต/พลังงาน/ค่าไฟที่ประหยัดได้ "
    "คำนวณจากข้อมูลจริงของไซต์"
)
METHOD_NOTE = (
    "พลังงานของแต่ละเฟสประมาณโดยขยายตามสัดส่วนกำลังติดตั้งจากค่าพลังงานรายปีของอาร์เรย์ปัจจุบัน "
    "(ไซต์เดียวกัน มุมเอียง/รุ่นแผงเดียวกัน) ไม่ใช่การจำลองผังใหม่ของเฟสนั้นๆ ซึ่งยังไม่มีแบบ"
)


class ScenarioOut(BaseModel):
    label: str
    phase: str | None
    ac_capacity_kw: float
    dc_capacity_kwp: float
    annual_energy_kwh: float
    solar_offset_pct: float | None
    annual_bill_saving_thb: float | None
    marginal_ac_capacity_kw: float | None
    marginal_annual_energy_kwh: float | None
    marginal_bill_saving_thb: float | None
    marginal_energy_per_kwp: float | None
    capex_estimate_thb: float | None
    simple_payback_years: float | None


class TargetOut(BaseModel):
    target_offset_pct: float
    required_dc_capacity_kwp: float
    times_current_capacity: float


class ExpansionResponse(BaseModel):
    available: bool
    reason: str | None = None
    facility_load_kw: float | None = None
    implied_tariff_thb_per_kwh: float | None = None
    capex_per_kwp_thb: float = DEFAULT_CAPEX_PER_KWP_THB
    scenarios: list[ScenarioOut] = []
    targets: list[TargetOut] = []
    capex_note: str = CAPEX_NOTE
    method_note: str = METHOD_NOTE


def _implied_tariff(site) -> float | None:
    """The facility's own blended rate from its real annual cost and real annual
    load. None when either figure is missing - never the placeholder PEA tariff."""
    cost = getattr(site, "facility_annual_electricity_cost_thb", None)
    load_kw = getattr(site, "facility_electrical_load_kw", None)
    if not cost or not load_kw:
        return None
    return cost / (load_kw * 8760)


def _planned_phases(registry) -> list[ExpansionPhase]:
    """Every zone's `future_phases`, in zone order. Today only Jetty has any."""
    phases: list[ExpansionPhase] = []
    for zone_id in ZONES:
        try:
            zone = registry.zone(zone_id)
        except KeyError:
            continue
        for phase in getattr(zone, "future_phases", []) or []:
            phases.append(
                ExpansionPhase(phase=phase.phase, additional_ac_capacity_kw=phase.additional_ac_capacity_kw, note=phase.note)
            )
    return phases


@router.get("/expansion", response_model=ExpansionResponse)
async def get_expansion(request: Request, _user=Depends(require_role("viewer"))) -> ExpansionResponse:
    registry = load_assets()
    site = registry.site

    current_ac = 0.0
    current_dc = 0.0
    current_energy = 0.0
    for zone_id in ZONES:
        try:
            zone = registry.zone(zone_id)
        except KeyError:
            continue
        current_ac += float(zone.ac_capacity_kw)
        current_dc += float(zone.dc_capacity_kwp)
        current_energy += seasonal_annual_ac_energy_kwh(zone_id)

    phases = _planned_phases(registry)
    if current_ac <= 0 or not phases:
        return ExpansionResponse(
            available=False,
            reason="ยังไม่มีข้อมูลเฟสขยายใน config/assets.yaml (future_phases) หรือกำลังติดตั้งปัจจุบันเป็นศูนย์",
            facility_load_kw=getattr(site, "facility_electrical_load_kw", None),
        )

    load_kw = getattr(site, "facility_electrical_load_kw", None)
    tariff = _implied_tariff(site)
    scenarios = build_scenarios(
        current_ac_capacity_kw=current_ac,
        current_dc_capacity_kwp=current_dc,
        current_annual_energy_kwh=current_energy,
        phases=phases,
        facility_load_kw=load_kw,
        tariff_thb_per_kwh=tariff,
    )

    targets = []
    if load_kw:
        for target in TARGET_OFFSETS_PCT:
            needed = capacity_for_target_offset(target, current_energy, current_dc, float(load_kw))
            if needed is None:
                continue
            targets.append(
                TargetOut(target_offset_pct=target, required_dc_capacity_kwp=needed, times_current_capacity=needed / current_dc)
            )

    return ExpansionResponse(
        available=True,
        facility_load_kw=load_kw,
        implied_tariff_thb_per_kwh=tariff,
        scenarios=[ScenarioOut(**vars(s)) for s in scenarios],
        targets=targets,
    )
