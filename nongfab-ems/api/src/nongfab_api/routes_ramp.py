"""GET /forecast/{zone}/ramp - how fast the output is about to change, and how
often it really has (2026-07-25, project B).

Two halves, and the second is what makes the first readable:

  UPCOMING - ramps between consecutive hours of the intra-day forecast the
  system has already issued, with the sharpest qualifying fall singled out.
  Nothing is recomputed; this reads the same stored series the chart draws.

  HISTORY - the same arithmetic over the recorded output of the last N days.
  Measured, not forecast. It answers "is a 35%/h drop unusual here, or does that
  happen twice a week", which a single upcoming number cannot.

Stated in the response and on screen: this site is fully grid-tied with no
battery and no curtailment control, so a ramp warning here is INFORMATION, not
a call to act. There is nothing to dispatch. Saying otherwise would dress a
number up as an operational product this plant cannot use.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from nongfab_common.assets import load_assets
from nongfab_forecast.local_store import RealDataStore
from nongfab_forecast.ramp import (
    Ramp,
    RampStatistics,
    ramp_statistics,
    ramps_from_series,
    steepest_down_ramp,
)
from nongfab_forecast.serving import GENERATED_POWER_HORIZON
from pydantic import BaseModel

from .auth import require_role
from .settings_store import effective

router = APIRouter(tags=["forecast"])

ZONES = ("GIS", "ISB", "Jetty")
# The intra-day horizon is the one that carries ramps: day-ahead is too coarse
# to resolve a cloud front, and minute-ahead does not reach far enough to warn.
RAMP_HORIZON = "hour"
DEFAULT_HISTORY_DAYS = 30
MAX_HISTORY_DAYS = 90

_NO_ACTION_NOTE = (
    "ไซต์นี้ต่อเข้ากริดอย่างเดียว ไม่มีแบตเตอรี่และไม่มีระบบสั่งลดกำลังผลิต "
    "ตัวเลขชุดนี้จึงเป็น 'ข้อมูลให้รู้ล่วงหน้า' ไม่ใช่สัญญาณให้ไปสั่งการอะไร — "
    "ประโยชน์คือทำให้ความผันผวนของแผงเป็นตัวเลขที่วัดได้ แทนที่จะเป็นความรู้สึก"
)

_METHOD_NOTE = (
    "คำนวณจากผลต่างของกำลังผลิตระหว่างชั่วโมงที่ติดกันในชุดพยากรณ์ที่ระบบออกไปแล้ว หารด้วยจำนวนชั่วโมง "
    "แล้วเทียบเป็น % ของกำลังติดตั้ง AC ของโซนนั้น เพื่อให้เกณฑ์เดียวกันใช้ได้ทั้ง GIS (50 kW) และ Jetty (200 kW) "
    "ส่วน 'สถิติย้อนหลัง' ใช้ค่ากำลังผลิตที่บันทึกไว้จริง ไม่ใช่ค่าพยากรณ์"
)


class RampOut(BaseModel):
    from_time: datetime
    to_time: datetime
    from_kw: float
    to_kw: float
    delta_kw: float
    rate_kw_per_h: float
    pct_of_capacity_per_h: float | None
    direction: str
    severity: str


class RampStatsOut(BaseModel):
    n_steps: int
    n_moderate_down: int
    n_steep_down: int
    n_moderate_up: int
    n_steep_up: int
    worst_down_pct_per_h: float | None
    worst_up_pct_per_h: float | None
    busiest_down_hour_ict: int | None
    busiest_down_hour_count: int


class RampResponse(BaseModel):
    available: bool
    zone: str
    reason: str | None = None
    ac_capacity_kw: float | None = None
    history_days: int
    upcoming: list[RampOut] = []
    # The sharpest qualifying fall ahead, or null when nothing reaches the
    # moderate band. Null is the common case on a clear day and must read as
    # "nothing notable", not as a missing value.
    alert: RampOut | None = None
    history: RampStatsOut | None = None
    moderate_pct_per_h: float
    steep_pct_per_h: float
    no_action_note: str = _NO_ACTION_NOTE
    method_note: str = _METHOD_NOTE


def _ac_capacity_kw(zone: str) -> float | None:
    try:
        return float(load_assets().zone(zone).ac_capacity_kw)
    except (KeyError, AttributeError, TypeError):
        return None


def _parse(when: str) -> datetime:
    parsed = datetime.fromisoformat(when)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _out(ramp: Ramp, capacity: float | None, moderate: float, steep: float) -> RampOut:
    return RampOut(
        from_time=ramp.from_time,
        to_time=ramp.to_time,
        from_kw=ramp.from_kw,
        to_kw=ramp.to_kw,
        delta_kw=ramp.delta_kw,
        rate_kw_per_h=ramp.rate_kw_per_h,
        pct_of_capacity_per_h=ramp.pct_of_capacity_per_h(capacity),
        direction=ramp.direction(capacity),
        severity=ramp.severity(capacity, moderate, steep),
    )


def _stats_out(stats: RampStatistics) -> RampStatsOut:
    return RampStatsOut(
        n_steps=stats.n_steps,
        n_moderate_down=stats.n_moderate_down,
        n_steep_down=stats.n_steep_down,
        n_moderate_up=stats.n_moderate_up,
        n_steep_up=stats.n_steep_up,
        worst_down_pct_per_h=stats.worst_down_pct_per_h,
        worst_up_pct_per_h=stats.worst_up_pct_per_h,
        busiest_down_hour_ict=stats.busiest_down_hour_ict,
        busiest_down_hour_count=stats.busiest_down_hour_count,
    )


@router.get("/forecast/{zone}/ramp", response_model=RampResponse)
async def get_forecast_ramp(
    zone: str,
    request: Request,
    days: int | None = Query(None, ge=1, le=MAX_HISTORY_DAYS, description="ช่วงย้อนหลังของสถิติ ramp"),
    _user=Depends(require_role("viewer")),
) -> RampResponse:
    if zone not in ZONES:
        raise HTTPException(status_code=404, detail=f"unknown zone '{zone}'")
    history_days = DEFAULT_HISTORY_DAYS if days is None else days
    store: RealDataStore = request.app.state.real_data_store
    capacity = _ac_capacity_kw(zone)
    moderate = float(effective("diagnostics.ramp_moderate_pct")) / 100.0
    steep = float(effective("diagnostics.ramp_steep_pct")) / 100.0
    now = datetime.now(timezone.utc)

    # Upcoming: the forward part of the stored intra-day series. `since=now`
    # would also admit the current partial hour, which is a step the viewer has
    # already lived through - the filter below keeps only what is still ahead.
    forecast_rows = store.forecast_history_points(zone, RAMP_HORIZON, now - timedelta(hours=1))
    upcoming_series = [(_parse(row[0]), float(row[1])) for row in forecast_rows]
    upcoming_series = [(t, v) for t, v in upcoming_series if t >= now.replace(minute=0, second=0, microsecond=0)]
    upcoming = ramps_from_series(upcoming_series)

    # History: recorded output, not forecast.
    actual_rows = store.forecast_history_points(zone, GENERATED_POWER_HORIZON, now - timedelta(days=history_days))
    history_ramps = ramps_from_series([(_parse(row[0]), float(row[1])) for row in actual_rows])

    if not upcoming and not history_ramps:
        return RampResponse(
            available=False,
            zone=zone,
            reason="ยังไม่มีทั้งชุดพยากรณ์ล่วงหน้าและประวัติกำลังผลิตมากพอที่จะคำนวณอัตราการเปลี่ยนแปลง",
            ac_capacity_kw=capacity,
            history_days=history_days,
            moderate_pct_per_h=moderate * 100.0,
            steep_pct_per_h=steep * 100.0,
        )

    alert = steepest_down_ramp(upcoming, capacity, moderate, steep)
    return RampResponse(
        available=True,
        zone=zone,
        ac_capacity_kw=capacity,
        history_days=history_days,
        upcoming=[_out(r, capacity, moderate, steep) for r in upcoming],
        alert=_out(alert, capacity, moderate, steep) if alert else None,
        history=_stats_out(ramp_statistics(history_ramps, capacity, moderate, steep)),
        moderate_pct_per_h=moderate * 100.0,
        steep_pct_per_h=steep * 100.0,
    )
