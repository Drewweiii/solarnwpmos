"""GET /forecast/{zone}/evolution - how the forecast for one hour changed as
that hour approached (2026-07-25, project D).

The chart on the dashboard shows the newest answer for every hour. This shows
every answer for one hour, oldest to newest, which is how a reader tells a model
that knew early from one that guessed late and got lucky.

Reads `forecast_evolution`, a table that exists solely for this: `forecast_history`
replaces on (zone, horizon, target_time) so the superseded issuances it would
have needed were already gone. Nothing is ever served to a chart from here.

Stated in the response: the table began filling at deploy time, so early on it
legitimately has nothing to show, and that is reported as such rather than as an
absence of revision.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from nongfab_forecast.evolution import (
    MIN_ISSUANCES_FOR_A_TREND,
    TargetEvolution,
    build_evolution,
    most_revised_target,
)
from nongfab_forecast.local_store import RealDataStore
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["forecast"])

ZONES = ("GIS", "ISB", "Jetty")
DEFAULT_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 14
# Day-ahead is where revision is visible: it is issued repeatedly over days, so
# one target hour accumulates many answers. Intra-day only reaches +6h, which
# leaves too few issuances per hour for a convergence line to say much.
EVOLUTION_HORIZON = "day"

_COLLECTION_NOTE = (
    "ตารางนี้เริ่มเก็บตั้งแต่ตอนที่ฟีเจอร์นี้ถูก deploy เท่านั้น จึงยังไม่มีประวัติของคำพยากรณ์ที่ออกไปก่อนหน้านั้น "
    "และต้องมีคำพยากรณ์ของชั่วโมงเดียวกันหลายรอบก่อน เส้นการลู่เข้าจึงจะมีความหมาย"
)

_METHOD_NOTE = (
    "แต่ละจุดคือคำพยากรณ์ 1 รอบที่ระบบออกสำหรับชั่วโมงเป้าหมายเดียวกัน เรียงจากรอบที่ออกไกลที่สุดไปหารอบล่าสุด "
    "'แกว่งมากสุด' คือช่วงห่างระหว่างคำตอบที่สูงสุดกับต่ำสุด ซึ่งต่างจาก 'ปรับรวม' ที่เทียบแค่รอบแรกกับรอบสุดท้าย — "
    "โมเดลที่ทำนาย 180 → 90 → 175 ปรับรวมแค่ -5 kW แต่แกว่งถึง 90 kW"
)


class IssuanceOut(BaseModel):
    issued_at: datetime
    lead_hours: float
    pred_kw: float
    lower_kw: float | None
    upper_kw: float | None


class EvolutionOut(BaseModel):
    target_time: datetime
    n_issuances: int
    issuances: list[IssuanceOut]
    first_pred_kw: float | None
    latest_pred_kw: float | None
    total_revision_kw: float | None
    max_swing_kw: float | None
    # None below the minimum issuance count - a verdict from one revision would
    # be a verdict from a single data point.
    is_converging: bool | None


class EvolutionResponse(BaseModel):
    available: bool
    zone: str
    horizon: str
    window_days: int
    reason: str | None = None
    min_issuances: int = MIN_ISSUANCES_FOR_A_TREND
    # The most-revised target hour in the window, which is the one worth looking
    # at. Null while nothing has accumulated enough issuances yet.
    highlight: EvolutionOut | None = None
    # How many target hours have enough issuances to be worth charting.
    n_targets_with_trend: int = 0
    collection_note: str = _COLLECTION_NOTE
    method_note: str = _METHOD_NOTE


def _parse(when: str) -> datetime:
    parsed = datetime.fromisoformat(when)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_query_target(raw: str) -> datetime:
    """Parse the ?target= timestamp from a URL.

    Separate from `_parse` because a query string is not a stored value. A
    caller who does not URL-encode an ISO timestamp sends `+00:00`, and the `+`
    is decoded as a SPACE - "2026-07-26T23:00:00 00:00", which
    `datetime.fromisoformat` rejects with a ValueError that would surface as a
    500. Repairing it here is friendlier than demanding the caller encode, and a
    genuinely malformed string still gets a 400 saying so rather than a stack
    trace.
    """
    candidate = raw.strip()
    if " " in candidate and "T" in candidate:
        head, _, tail = candidate.rpartition(" ")
        candidate = f"{head}+{tail}"
    try:
        return _parse(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"target is not a valid ISO timestamp: '{raw}'") from exc


def _out(evolution: TargetEvolution) -> EvolutionOut:
    return EvolutionOut(
        target_time=evolution.target_time,
        n_issuances=evolution.n,
        issuances=[
            IssuanceOut(
                issued_at=i.issued_at,
                lead_hours=i.lead_hours,
                pred_kw=i.pred_kw,
                lower_kw=i.lower_kw,
                upper_kw=i.upper_kw,
            )
            for i in evolution.issuances
        ],
        first_pred_kw=evolution.first.pred_kw if evolution.first else None,
        latest_pred_kw=evolution.latest.pred_kw if evolution.latest else None,
        total_revision_kw=evolution.total_revision_kw,
        max_swing_kw=evolution.max_swing_kw,
        is_converging=evolution.is_converging(),
    )


@router.get("/forecast/{zone}/evolution", response_model=EvolutionResponse)
async def get_forecast_evolution(
    zone: str,
    request: Request,
    days: int | None = Query(None, ge=1, le=MAX_WINDOW_DAYS),
    target: str | None = Query(None, description="ISO timestamp ของชั่วโมงเป้าหมาย · ไม่ใส่ = เลือกชั่วโมงที่แกว่งมากสุดให้"),
    _user=Depends(require_role("viewer")),
) -> EvolutionResponse:
    if zone not in ZONES:
        raise HTTPException(status_code=404, detail=f"unknown zone '{zone}'")
    window_days = DEFAULT_WINDOW_DAYS if days is None else days
    store: RealDataStore = request.app.state.real_data_store
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    raw = store.forecast_evolution_rows(zone, EVOLUTION_HORIZON, since)
    rows = [(_parse(r[0]), _parse(r[1]), float(r[2]), r[3], r[4]) for r in raw]

    if not rows:
        return EvolutionResponse(
            available=False,
            zone=zone,
            horizon=EVOLUTION_HORIZON,
            window_days=window_days,
            reason="ยังไม่มีประวัติคำพยากรณ์หลายรอบสำหรับช่วงนี้ — ตารางเพิ่งเริ่มเก็บ ต้องรอให้ระบบออกคำพยากรณ์อีกหลายรอบก่อน",
        )

    if target is not None:
        chosen = build_evolution(rows, _parse_query_target(target))
        if chosen.n == 0:
            raise HTTPException(status_code=404, detail=f"no stored issuances for target '{target}'")
    else:
        found = most_revised_target(rows)
        if found is None:
            return EvolutionResponse(
                available=False,
                zone=zone,
                horizon=EVOLUTION_HORIZON,
                window_days=window_days,
                reason=(
                    f"มีข้อมูลแล้วแต่ยังไม่มีชั่วโมงไหนที่ถูกพยากรณ์ครบ {MIN_ISSUANCES_FOR_A_TREND} รอบ "
                    "จึงยังบอกไม่ได้ว่าคำทำนายลู่เข้าหรือแกว่ง"
                ),
            )
        chosen = found

    n_with_trend = sum(
        1 for t in {r[0] for r in rows} if build_evolution(rows, t).n >= MIN_ISSUANCES_FOR_A_TREND
    )
    return EvolutionResponse(
        available=True,
        zone=zone,
        horizon=EVOLUTION_HORIZON,
        window_days=window_days,
        highlight=_out(chosen),
        n_targets_with_trend=n_with_trend,
    )
