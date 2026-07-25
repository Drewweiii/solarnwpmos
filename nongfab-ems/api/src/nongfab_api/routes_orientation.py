"""GET /orientation - is the array pointed the right way? (2026-07-25, project D)

Sweeps tilt x azimuth against Nong Fab's own sun path and reports, per zone, the
best orientation next to the one currently modelled. See
`nongfab_simulation.tilt_optimizer` for the physics and for the two limits that
shape what this may claim:

  * The main energy pipeline runs on GHI, so tilt has never affected published
    yield. This route adds a plane-of-array model to make tilt a real variable,
    but does NOT feed it back into /financial or the Energy Report - adopting
    POA site-wide would move the published payback, which is the user's call.
  * config/assets.yaml has `tilt_deg: null` for every zone. The array's real
    angle is unknown, so "current" is an assumed default and `measured` is false
    everywhere today. The response carries that per zone rather than letting a
    reader assume a survey happened.

Viewer-level: it reads config and astronomy, exposes no money, and the honest
caveats are the point of showing it at all.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from nongfab_common.assets import load_assets
from nongfab_simulation.tilt_optimizer import ZoneOrientationReport, optimise_zone
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["orientation"])

METHOD_NOTE = (
    "คำนวณแสงที่ตกบนระนาบแผง (plane-of-array) ด้วยแบบจำลอง Hay-Davies ของ pvlib "
    "จากตำแหน่งดวงอาทิตย์จริงที่พิกัดหนองแฟบ 12 วันตัวแทนรายเดือน แล้วหักเงาที่แถวหน้าบังแถวหลัง "
    "เลือกมุมที่ให้พลังงานสุทธิสูงสุด"
)
PIPELINE_NOTE = (
    "หน้าอื่นของเว็บ (Financial / Savings / Energy Report) ยังคำนวณจากแสงแนวนอน (GHI) เหมือนเดิม "
    "หน้านี้ไม่ได้ไปเปลี่ยนตัวเลขที่เผยแพร่ไว้ — การเปลี่ยนทั้งระบบให้ใช้ POA จะทำให้ payback ขยับ "
    "ซึ่งเป็นการตัดสินใจของเจ้าของโครงการ ไม่ใช่ผลพลอยได้ของการเพิ่มหน้านี้"
)
UNMEASURED_NOTE = (
    "⚠️ มุมเอียงและทิศของแผงจริง ยังไม่เคยวัด — `assets.yaml` ระบุ `tilt_deg: null` ทุกโซน "
    "(เอกสาร SLD เป็นข้อมูลไฟฟ้าอย่างเดียว) ค่า 'ปัจจุบัน' ที่เทียบให้ดูจึงเป็นค่าสมมติของระบบ "
    "ไม่ใช่ของที่วัดมา → ตัวเลข 'ได้เพิ่มกี่ %' ยังใช้อ้างกับแผงที่ติดตั้งจริงไม่ได้ "
    "ส่วน 'มุมที่ดีที่สุด' ไม่กระทบ เพราะขึ้นกับเส้นทางดวงอาทิตย์ ไม่ได้ขึ้นกับสิ่งที่สร้างไปแล้ว"
)
EXPANSION_NOTE = (
    "ประโยชน์ที่ใช้ได้ทันทีคือเฟสขยายที่ยังไม่ได้สร้าง — ควรออกแบบที่มุมที่ดีที่สุดตั้งแต่แรก"
)
JETTY_NOTE = (
    "Jetty เป็นแผงบนสะพาน ทิศของแผงถูกบังคับด้วยแนวสะพานเป็นหลัก "
    "ตัวเลขส่วนต่างจึงเป็นการบอกว่า 'แนวสะพานทำให้เสียไปเท่าไร' ไม่ใช่ข้อเสนอให้หมุนแผง"
)


class OrientationOut(BaseModel):
    tilt_deg: float
    azimuth_deg: float
    poa_kwh_per_m2: float
    shading_loss_pct: float
    effective_kwh_per_m2: float


class ZoneOrientationOut(BaseModel):
    zone_id: str
    current: OrientationOut
    optimum: OrientationOut
    # False everywhere today: no zone's tilt/azimuth was ever surveyed.
    current_is_measured: bool
    gain_pct: float
    gain_kwh_per_m2_year: float
    row_pitch_m: float
    note: str | None = None


class OrientationResponse(BaseModel):
    zones: list[ZoneOrientationOut]
    any_unmeasured: bool
    method_note: str = METHOD_NOTE
    pipeline_note: str = PIPELINE_NOTE
    unmeasured_note: str = UNMEASURED_NOTE
    expansion_note: str = EXPANSION_NOTE


def _out(o) -> OrientationOut:
    return OrientationOut(
        tilt_deg=round(o.tilt_deg, 1),
        azimuth_deg=round(o.azimuth_deg, 1),
        poa_kwh_per_m2=o.poa_kwh_per_m2,
        shading_loss_pct=o.shading_loss_pct,
        effective_kwh_per_m2=o.effective_kwh_per_m2,
    )


def _zone_out(report: ZoneOrientationReport) -> ZoneOrientationOut:
    return ZoneOrientationOut(
        zone_id=report.zone_id,
        current=_out(report.current),
        optimum=_out(report.optimum),
        current_is_measured=report.current_is_measured,
        gain_pct=report.gain_pct,
        gain_kwh_per_m2_year=report.optimum.effective_kwh_per_m2 - report.current.effective_kwh_per_m2,
        row_pitch_m=report.row_pitch_m,
        # Jetty's azimuth follows the trestle, so its gap is a description of a
        # structural constraint rather than something anyone can act on.
        note=JETTY_NOTE if report.zone_id == "Jetty" else None,
    )


@router.get("/orientation", response_model=OrientationResponse)
async def get_orientation(_user=Depends(require_role("viewer"))) -> OrientationResponse:
    zones = [_zone_out(optimise_zone(zone.id)) for zone in load_assets().zones]
    return OrientationResponse(zones=zones, any_unmeasured=any(not z.current_is_measured for z in zones))
