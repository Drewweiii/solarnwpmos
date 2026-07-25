"""GET /bifacial - the rear face nobody is counting (2026-07-25, project H).

The installed module is a Trina Vertex N bifacial dual-glass panel rated at 80
+/- 5% power bifaciality, and every yield figure this system publishes models it
as one-sided. This route says how much that leaves out.

It does NOT change the published figures, and the reason is in
`nongfab_features.bifacial`: front irradiance needs only geometry, which this
project has, while rear irradiance turns on ground albedo and mounting height,
which nobody measured. A 5-15% uplift to payback resting on two assumed inputs
is precisely what this codebase declines to publish elsewhere - so the gain is
reported, banded by the datasheet's own +/-5% tolerance, and the headline energy
stays monofacial and conservative.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from nongfab_common.assets import load_assets
from nongfab_features.bifacial import DATASHEET_BIFACIALITY, annual_rear_gain, ground_kind_for_zone
from nongfab_simulation.tilt_optimizer import zone_geometry
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["bifacial"])

GROUND_LABELS = {"ground": "พื้นลานโล่ง", "rooftop": "หลังคาอาคาร", "water": "เหนือผิวน้ำทะเล"}

MODULE_NOTE = (
    "แผงที่ติดตั้งจริงคือ Trina Vertex N TSM-NEG21C.20 แบบ bifacial dual-glass "
    "ผู้ผลิตระบุค่า power bifaciality 80 ± 5% แปลว่าแสงที่ตกด้านหลัง 100 W/m² ให้กำลังเท่าแสง 80 W/m² ที่ด้านหน้า"
)
# Plain text, no markdown: the panel renders this straight into a <p>, so a
# `**bold**` here shows up as literal asterisks on screen (it did - caught in the
# 2026-07-25 browser pass). Emphasis comes from the ⚠️ and the .orientation-warning
# styling instead.
NOT_APPLIED_NOTE = (
    "⚠️ ตัวเลขนี้ยังไม่ได้ถูกนำไปบวกในพลังงานที่เว็บเผยแพร่ และตั้งใจไม่บวก — "
    "แสงด้านหน้าคำนวณจากเรขาคณิตล้วน แต่แสงด้านหลังขึ้นกับ 2 ค่าที่ไม่มีใครวัดไว้: "
    "ค่าการสะท้อนแสงของพื้น (albedo) และความสูงที่ติดตั้งเหนือพื้น "
    "การเอา 5–15% ไปบวกใน payback โดยอิงค่าเดา 2 ตัวคือสิ่งที่ระบบนี้ไม่ทำในที่อื่นๆ อยู่แล้ว"
)
METHOD_NOTE = (
    "ใช้แบบจำลอง infinite_sheds ของ pvlib ซึ่งคิดด้วยว่าแถวหน้าบังมุมมองที่ด้านหลังจะเห็นพื้น — "
    "การประมาณแบบง่ายๆ ว่า albedo × GHI จะให้ค่าสูงเกินจริงเมื่อแถวอยู่ชิดกัน"
)
UNLOCK_NOTE = (
    "ถ้าวัดค่า albedo ของพื้นจริงและความสูงติดตั้งจริงมาได้ ตัวเลขนี้จะเลื่อนขั้นจาก 'ประมาณการ' เป็นค่าที่นำไปบวกได้"
)


class ZoneBifacialOut(BaseModel):
    zone_id: str
    ground_kind: str
    ground_label: str
    gain_pct: float
    gain_pct_low: float
    gain_pct_high: float
    albedo_assumed: float
    height_m_assumed: float
    ground_cover_ratio: float


class BifacialResponse(BaseModel):
    zones: list[ZoneBifacialOut]
    bifaciality: float = DATASHEET_BIFACIALITY
    module_note: str = MODULE_NOTE
    not_applied_note: str = NOT_APPLIED_NOTE
    method_note: str = METHOD_NOTE
    unlock_note: str = UNLOCK_NOTE


@router.get("/bifacial", response_model=BifacialResponse)
async def get_bifacial(_user=Depends(require_role("viewer"))) -> BifacialResponse:
    from datetime import datetime, timezone

    year = datetime.now(timezone.utc).year
    zones = []
    for zone in load_assets().zones:
        tilt, azimuth, pitch, slant = zone_geometry(zone.id)
        kind = ground_kind_for_zone(zone.id)
        gain = annual_rear_gain(tilt, azimuth, pitch, slant, kind, year)
        zones.append(
            ZoneBifacialOut(
                zone_id=zone.id,
                ground_kind=kind,
                ground_label=GROUND_LABELS[kind],
                gain_pct=gain.gain_pct,
                gain_pct_low=gain.gain_pct_low,
                gain_pct_high=gain.gain_pct_high,
                albedo_assumed=gain.albedo,
                height_m_assumed=gain.height_m,
                ground_cover_ratio=gain.ground_cover_ratio,
            )
        )
    return BifacialResponse(zones=zones)
