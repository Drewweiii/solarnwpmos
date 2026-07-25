"""GET /tou - does this array produce during the expensive hours?
(2026-07-25, project G)

`green_savings.py` values every kWh at the TOU Peak rate and its own docstring
called that "a documented approximation - it does not net out weekend/holiday
off-peak hours". This route measures the approximation.

Peak is 09:00-22:00 Monday to Friday; everything else, including all of Saturday
and Sunday, is off-peak. The array does not care, but the bill does - and two
consequences fall out that are easy to miss: weekends produce entirely at the
off-peak rate, and the 06:00-09:00 morning production is off-peak even on a
working day.

Nothing published moves because of this route: `green.offpeak_rate_thb_per_kwh`
ships EQUAL to the peak rate, so the blended rate reproduces today's figure
exactly until somebody enters the real Off-Peak rate from the announcement. The
energy split, which needs no tariff at all, is real either way.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from nongfab_common.assets import load_assets
from nongfab_simulation.tou import (
    PEAK_END_HOUR,
    PEAK_START_HOUR,
    TouSplit,
    blended_rate_thb_per_kwh,
    zone_tou_split,
)
from pydantic import BaseModel

from .auth import require_role
from .settings_store import effective, is_overridden

router = APIRouter(tags=["tou"])

WINDOW_NOTE = (
    f"ช่วง On Peak คือ {PEAK_START_HOUR:02d}:00–{PEAK_END_HOUR:02d}:00 เฉพาะวันจันทร์–ศุกร์ · "
    "นอกนั้นเป็น Off-Peak ทั้งหมด รวมถึงเสาร์–อาทิตย์เต็มวัน (อัตราประเภทที่ 4 ของ กฟภ./กฟน.)"
)
FINDING_NOTE = (
    "สองเรื่องที่มองข้ามง่าย: เสาร์-อาทิตย์ผลิตเป็น Off-Peak ทั้งวัน และช่วง 06:00–09:00 ของวันทำงาน "
    "ก็เป็น Off-Peak เพราะ Peak เพิ่งเริ่ม 09:00 ทั้งที่แผงเริ่มผลิตตั้งแต่ราว 06:00"
)
HOLIDAY_NOTE = (
    "ยังไม่ได้นับวันหยุด — กฟภ./กฟน. คิดเฉพาะวันหยุดในรายการที่ประกาศ ไม่ใช่ทุกวันหยุด "
    "ตั้งค่าเป็น 0 ไว้ สัดส่วน Peak ที่เห็นจึงเป็นเพดานบน ของจริง Off-Peak มีแต่จะมากกว่านี้"
)


class ZoneTouOut(BaseModel):
    zone_id: str
    peak_kwh: float
    offpeak_kwh: float
    peak_share_pct: float
    offpeak_share_pct: float


class TouResponse(BaseModel):
    zones: list[ZoneTouOut]
    total_peak_kwh: float
    total_offpeak_kwh: float
    offpeak_share_pct: float
    peak_rate_thb_per_kwh: float
    offpeak_rate_thb_per_kwh: float
    blended_rate_thb_per_kwh: float
    # How far the flat peak-rate assumption sits from the blended truth, in
    # percent. Zero while the off-peak rate has not been supplied.
    overstatement_pct: float
    offpeak_rate_is_set: bool
    offpeak_holiday_days: int
    window_note: str = WINDOW_NOTE
    finding_note: str = FINDING_NOTE
    holiday_note: str = HOLIDAY_NOTE


@router.get("/tou", response_model=TouResponse)
async def get_tou(_user=Depends(require_role("viewer"))) -> TouResponse:
    year = datetime.now(timezone.utc).year
    holidays = int(effective("green.offpeak_holiday_days"))
    peak_rate = float(effective("green.normal_rate_thb_per_kwh"))
    offpeak_rate = float(effective("green.offpeak_rate_thb_per_kwh"))

    zones = []
    total = TouSplit(0.0, 0.0, holidays)
    for zone in load_assets().zones:
        split = zone_tou_split(zone.id, year, holidays)
        zones.append(
            ZoneTouOut(
                zone_id=zone.id,
                peak_kwh=split.peak_kwh,
                offpeak_kwh=split.offpeak_kwh,
                peak_share_pct=split.peak_share_pct,
                offpeak_share_pct=split.offpeak_share_pct,
            )
        )
        total = TouSplit(total.peak_kwh + split.peak_kwh, total.offpeak_kwh + split.offpeak_kwh, holidays)

    blended = blended_rate_thb_per_kwh(total, peak_rate, offpeak_rate)
    return TouResponse(
        zones=zones,
        total_peak_kwh=total.peak_kwh,
        total_offpeak_kwh=total.offpeak_kwh,
        offpeak_share_pct=total.offpeak_share_pct,
        peak_rate_thb_per_kwh=peak_rate,
        offpeak_rate_thb_per_kwh=offpeak_rate,
        blended_rate_thb_per_kwh=blended,
        overstatement_pct=0.0 if peak_rate <= 0 else (peak_rate / blended - 1.0) * 100.0,
        offpeak_rate_is_set=is_overridden("green.offpeak_rate_thb_per_kwh"),
        offpeak_holiday_days=holidays,
    )
