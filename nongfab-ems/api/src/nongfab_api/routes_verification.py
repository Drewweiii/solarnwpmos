"""GET /forecast/{zone}/verification - how good the forecasts this system has
actually issued turned out to be (2026-07-25).

Distinct from everything the dashboard showed before: `rmse_by_lead_hour` and
`candidate_errors` are TRAINING hold-out errors, measured while fitting. This
route scores the forecasts that were really issued against the actual output
that followed, and reports the SKILL SCORE against a persistence baseline -
the reference solar-forecasting work is expected to beat. See
`nongfab_forecast.verification` for the metric definitions and the two honesty
constraints (daylight-only headline figures; pairs only where a real actual
exists).

Both sides come from `forecast_history`: the hour-ahead issuances under the
"hour" horizon, and the recorded output under `serving.GENERATED_POWER_HORIZON`.
**That second side is not a meter.** This site has no metered generation at all
(see `nongfab_forecast.real_data.pv_params_for_zone` - a deliberate, permanent
scope decision), so it is the physics model evaluated on the weather that
actually verified. Scoring against it therefore measures NWP forecast error
propagated through physics - a real and useful thing to measure, but the response
and the UI both say plainly that it is not accuracy against a meter. Because that table keys on
(zone, horizon, target_time), only each hour's freshest issuance survives, so
`lead_time_note` states plainly that the lead-time breakdown covers whichever
issuance each hour last had rather than a full lead matrix.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from nongfab_common.assets import load_assets
from nongfab_forecast.local_store import RealDataStore
from nongfab_forecast.serving import GENERATED_POWER_HORIZON
from nongfab_forecast.verification import (
    IntervalMetrics,
    VerificationMetrics,
    build_pairs,
    compute_interval_metrics,
    compute_metrics,
    daylight_pairs,
    interval_metrics_by_lead,
    metrics_by_lead,
)
from pydantic import BaseModel

from .auth import require_role
from .settings_store import effective

router = APIRouter(tags=["forecast"])

ZONES = ("GIS", "ISB", "Jetty")
DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 90
# The verified horizon. Hour-ahead is the one with both a real issuance history
# and a matching hourly actual to score against.
VERIFIED_HORIZON = "hour"

# Stated in every response so a consumer can't read these figures as
# meter-verified accuracy. See the module docstring.
REFERENCE_NOTE = (
    "ไซต์นี้ไม่มีมิเตอร์วัดกำลังผลิตจริง ฝั่ง 'ค่าจริง' ที่ใช้เทียบคือค่าที่คำนวณจากโมเดลฟิสิกส์ "
    "บวกสภาพอากาศที่เกิดขึ้นจริง ณ ชั่วโมงนั้น จึงเป็นการวัด error ของพยากรณ์อากาศที่ส่งผ่านฟิสิกส์ "
    "ไม่ใช่ความคลาดเคลื่อนเทียบมิเตอร์"
)

_LEAD_NOTE = (
    "forecast_history เก็บเฉพาะ issuance ล่าสุดของแต่ละชั่วโมง (PRIMARY KEY zone+horizon+target_time) "
    "ดังนั้นการแยกตาม lead time คือช่วงเวลาที่ forecast รอบสุดท้ายของชั่วโมงนั้นออก ไม่ใช่ตารางครบทุก lead"
)


class MetricsOut(BaseModel):
    n: int
    mae_kw: float
    rmse_kw: float
    mbe_kw: float
    nrmse_pct: float | None
    persistence_rmse_kw: float | None
    skill_score: float | None


class LeadMetricsOut(BaseModel):
    lead_bucket: str
    metrics: MetricsOut


class IntervalMetricsOut(BaseModel):
    """How the published band behaved. Every field optional-friendly on the
    frontend side: these were added 2026-07-25 and older UI builds must not
    break on their absence."""

    n: int
    nominal_pct: float
    coverage_pct: float
    coverage_gap_pct: float
    mean_width_kw: float
    pinaw_pct: float | None
    pinball_kw: float
    miss_low_pct: float
    miss_high_pct: float


class IntervalLeadOut(BaseModel):
    lead_bucket: str
    interval: IntervalMetricsOut


_INTERVAL_NOTE = (
    "แถบความเชื่อมั่นที่โมเดลเผยแพร่ตั้งไว้ที่ควอนไทล์ 0.05/0.95 คือ 'ควรครอบคลุมความจริง 90%' "
    "ตัวเลข coverage ด้านล่างคือสัดส่วนที่ครอบคลุมได้จริงจากคำพยากรณ์ที่ออกไปแล้ว ไม่ใช่ค่า PICP ตอนเทรน "
    "ต่ำกว่า 90% = แถบแคบเกินจริง (มั่นใจเกินไป) · สูงกว่ามาก = แถบกว้างจนแทบไม่ให้ข้อมูล "
    "จึงต้องอ่านคู่กับความกว้างเฉลี่ยและ pinball loss เสมอ"
)

_PINBALL_NOTE = (
    "pinball loss เป็น proper scoring rule — ขยายแถบให้กว้างขึ้นเฉยๆ ไม่ได้ทำให้คะแนนนี้ดีขึ้น ต่างจาก coverage "
    "ไม่ใช่ CRPS เต็มรูปแบบ เพราะโมเดลเผยแพร่แค่ 2 ควอนไทล์ ไม่ใช่การแจกแจงทั้งก้อน"
)


class VerificationResponse(BaseModel):
    available: bool
    zone: str
    horizon: str
    window_days: int
    reason: str | None = None
    ac_capacity_kw: float | None = None
    # Daylight-only (the headline) and all-hours figures over the same window,
    # so the reader can see how much of the accuracy is just night zeros.
    daylight: MetricsOut | None = None
    all_hours: MetricsOut | None = None
    by_lead: list[LeadMetricsOut] = []
    # The published interval, scored over the same daylight pairs as the
    # headline point metrics (2026-07-25).
    interval: IntervalMetricsOut | None = None
    interval_by_lead: list[IntervalLeadOut] = []
    lead_time_note: str = _LEAD_NOTE
    reference_note: str = REFERENCE_NOTE
    interval_note: str = _INTERVAL_NOTE
    pinball_note: str = _PINBALL_NOTE


def _out(metrics: VerificationMetrics) -> MetricsOut:
    return MetricsOut(
        n=metrics.n,
        mae_kw=metrics.mae_kw,
        rmse_kw=metrics.rmse_kw,
        mbe_kw=metrics.mbe_kw,
        nrmse_pct=metrics.nrmse_pct,
        persistence_rmse_kw=metrics.persistence_rmse_kw,
        skill_score=metrics.skill_score,
    )


def _interval_out(metrics: IntervalMetrics) -> IntervalMetricsOut:
    return IntervalMetricsOut(
        n=metrics.n,
        nominal_pct=metrics.nominal_pct,
        coverage_pct=metrics.coverage_pct,
        coverage_gap_pct=metrics.coverage_gap_pct,
        mean_width_kw=metrics.mean_width_kw,
        pinaw_pct=metrics.pinaw_pct,
        pinball_kw=metrics.pinball_kw,
        miss_low_pct=metrics.miss_low_pct,
        miss_high_pct=metrics.miss_high_pct,
    )


def _parse(when: str) -> datetime:
    parsed = datetime.fromisoformat(when)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _ac_capacity_kw(zone: str) -> float | None:
    """The zone's AC capacity, for normalizing RMSE. Read off the asset registry
    rather than hardcoded; None if the zone somehow isn't in it."""
    try:
        return float(load_assets().zone(zone).ac_capacity_kw)
    except (KeyError, AttributeError, TypeError):
        return None


@router.get("/forecast/{zone}/verification", response_model=VerificationResponse)
async def get_forecast_verification(
    zone: str,
    request: Request,
    days: int | None = Query(None, ge=1, le=MAX_WINDOW_DAYS, description="ไม่ใส่ = ใช้ค่าที่ตั้งไว้ในระบบ (windows.verification_days)"),
    _user=Depends(require_role("viewer")),
) -> VerificationResponse:
    if zone not in ZONES:
        raise HTTPException(status_code=404, detail=f"unknown zone '{zone}'")
    # An explicit ?days= still wins (it is how the UI offers a one-off look);
    # otherwise use whatever window the user configured.
    days = int(effective("windows.verification_days")) if days is None else days
    store: RealDataStore = request.app.state.real_data_store
    since = datetime.now(timezone.utc) - timedelta(days=days)
    capacity = _ac_capacity_kw(zone)

    issuance_rows = store.forecast_history_issuances(zone, VERIFIED_HORIZON, since)
    actual_rows = store.forecast_history_points(zone, GENERATED_POWER_HORIZON, since)
    if not issuance_rows or not actual_rows:
        return VerificationResponse(
            available=False,
            zone=zone,
            horizon=VERIFIED_HORIZON,
            window_days=days,
            ac_capacity_kw=capacity,
            reason="ยังไม่มีทั้งประวัติ forecast และค่ากำลังผลิตจริงในช่วงนี้พอที่จะตรวจสอบความแม่นยำ",
        )

    actual_by_time = {_parse(row[0]): float(row[1]) for row in actual_rows}
    # lower/upper stay None where the row came from the physics-baseline
    # fallback - it publishes no interval, and a None must reach the metrics as
    # "no band claimed" rather than as a zero-width one.
    issuances = [
        (_parse(row[0]), _parse(row[1]), float(row[2]), row[3], row[4]) for row in issuance_rows
    ]
    pairs = build_pairs(issuances, actual_by_time)
    if not pairs:
        return VerificationResponse(
            available=False,
            zone=zone,
            horizon=VERIFIED_HORIZON,
            window_days=days,
            ac_capacity_kw=capacity,
            reason="มีข้อมูลทั้งสองฝั่ง แต่ยังไม่มีชั่วโมงที่ทับกัน (forecast กับค่าจริงคนละช่วงเวลา)",
        )

    day_pairs = daylight_pairs(pairs, floor_kw=effective("diagnostics.daylight_floor_kw"))
    return VerificationResponse(
        available=True,
        zone=zone,
        horizon=VERIFIED_HORIZON,
        window_days=days,
        ac_capacity_kw=capacity,
        daylight=_out(compute_metrics(day_pairs, capacity)),
        all_hours=_out(compute_metrics(pairs, capacity)),
        by_lead=[LeadMetricsOut(lead_bucket=label, metrics=_out(m)) for label, m in metrics_by_lead(day_pairs, capacity)],
        # Scored over the same daylight pairs as the headline point metrics, so
        # the two sections describe the same forecasts. Night hours would push
        # coverage toward 100% for free (everyone predicts zero and is right).
        interval=_interval_out(compute_interval_metrics(day_pairs, capacity)),
        interval_by_lead=[
            IntervalLeadOut(lead_bucket=label, interval=_interval_out(m))
            for label, m in interval_metrics_by_lead(day_pairs, capacity)
        ],
    )
