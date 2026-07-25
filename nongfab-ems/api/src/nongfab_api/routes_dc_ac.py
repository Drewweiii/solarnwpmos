"""GET /dc-ac - what the inverters throw away, and what they could still take
(2026-07-25, project F).

Two questions this site had never asked. How much midday energy is lost to
inverter clipping - which the model already performs but never measured - and
where is there DC headroom left under an inverter that is already paid for.

See `nongfab_simulation.dc_ac_ratio` for why this stops short of naming an
"optimal" ratio: more DC always yields more energy, so the honest optimum needs
a real module cost, and CAPEX here is still the user's chosen placeholder. The
curve and the marginal yield of the next kWp are reported instead, which is what
anyone with a real EPC quote actually needs.

Viewer-level: capacities and astronomy, no money.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from nongfab_common.assets import load_assets
from nongfab_simulation.dc_ac_ratio import ZoneRatioReport, analyse_zone, headroom_kwp
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["dc-ac"])

METHOD_NOTE = (
    "คำนวณจากวันตัวแทน 12 เดือนด้วยแสงบนระนาบแผง (POA) และชุดการสูญเสียเดียวกับที่หน้า Energy Report ใช้ "
    "แล้วเทียบพลังงานก่อนถูกจำกัดด้วยพิกัดอินเวอร์เตอร์ กับหลังถูกจำกัด — ส่วนต่างคือพลังงานที่ถูกตัดทิ้ง"
)
NO_OPTIMUM_NOTE = (
    "จงใจไม่บอกว่า 'อัตราส่วนที่ดีที่สุด' คือเท่าไร — ใส่แผงเพิ่มยังไงพลังงานก็เพิ่มเสมอ แค่เพิ่มน้อยลงเรื่อยๆ "
    "จุดคุ้มจริงขึ้นกับราคาแผงต่อ kWp ซึ่งตอนนี้ยังเป็นค่าประมาณ (฿30,000/kWp) "
    "จึงแสดง 'kWp ถัดไปให้พลังงานกี่ kWh/ปี' แทน เอาไปหารกับราคาจริงที่ได้มาแล้วตัดสินใจเองได้เลย"
)


class RatioPointOut(BaseModel):
    dc_ac_ratio: float
    dc_capacity_kwp: float
    delivered_kwh: float
    clipped_kwh: float
    clipping_loss_pct: float
    specific_yield_kwh_per_kwp: float


class ZoneRatioOut(BaseModel):
    zone_id: str
    ac_capacity_kw: float
    built: RatioPointOut
    curve: list[RatioPointOut]
    # True when the inverter is larger than the array - DC can be added with no
    # inverter spend at all.
    has_headroom: bool
    headroom_kwp: float
    marginal_kwh_per_added_kwp: float | None


class DcAcResponse(BaseModel):
    zones: list[ZoneRatioOut]
    total_clipped_kwh: float
    total_headroom_kwp: float
    method_note: str = METHOD_NOTE
    no_optimum_note: str = NO_OPTIMUM_NOTE


def _point(p) -> RatioPointOut:
    return RatioPointOut(
        dc_ac_ratio=round(p.dc_ac_ratio, 3),
        dc_capacity_kwp=p.dc_capacity_kwp,
        delivered_kwh=p.delivered_kwh,
        clipped_kwh=p.clipped_kwh,
        clipping_loss_pct=p.clipping_loss_pct,
        specific_yield_kwh_per_kwp=p.specific_yield_kwh_per_kwp,
    )


def _zone_out(report: ZoneRatioReport) -> ZoneRatioOut:
    return ZoneRatioOut(
        zone_id=report.zone_id,
        ac_capacity_kw=report.ac_capacity_kw,
        built=_point(report.built),
        curve=[_point(p) for p in report.curve],
        has_headroom=report.has_headroom,
        headroom_kwp=headroom_kwp(report.zone_id),
        marginal_kwh_per_added_kwp=report.marginal_kwh_per_added_kwp(report.built.dc_ac_ratio),
    )


@router.get("/dc-ac", response_model=DcAcResponse)
async def get_dc_ac(_user=Depends(require_role("viewer"))) -> DcAcResponse:
    zones = [_zone_out(analyse_zone(zone.id)) for zone in load_assets().zones]
    return DcAcResponse(
        zones=zones,
        total_clipped_kwh=sum(z.built.clipped_kwh for z in zones),
        total_headroom_kwp=sum(z.headroom_kwp for z in zones),
    )
