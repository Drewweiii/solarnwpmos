"""GET /diagnostics/feeds and GET /diagnostics/{zone}/anomalies (2026-07-25).

The operational blind spot this closes: when an external source silently stops,
the model keeps answering - it just falls back to defaults, and nothing on the
dashboard says so. That is precisely how the aerosol feed broke earlier the same
day (a startup backfill with no refresh loop; the only symptom was five cells
reading "no data"). `/diagnostics/feeds` names each source, its freshness, and
whether it is still good enough for the model to use.

`/diagnostics/{zone}/anomalies` flags days whose expected energy fell well below
the norm for that month and RANKS the likely weather driver. With no metered
output at this site (see routes_verification's docstring), this cannot and does
not claim the array itself underperformed - both the expected energy and the norm
are model estimates, and the cause is an inference from measured weather. The
response says so in `basis_note`, and the panel repeats it.

See `nongfab_forecast.health` for the pure verdict/ranking logic, including why
observation feeds and coverage (forecast) feeds have to be judged differently.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from nongfab_forecast.health import (
    DayEnergy,
    FeedHealth,
    evaluate_coverage_feed,
    evaluate_observation_feed,
    find_output_anomalies,
    worst_status,
)
from nongfab_forecast.local_store import RealDataStore
from nongfab_forecast.serving import GENERATED_POWER_HORIZON
from nongfab_simulation.pipeline import monthly_ac_energy_estimates
from pydantic import BaseModel

from .auth import require_role
from .soiling_service import daily_conditions

router = APIRouter(tags=["diagnostics"])

ZONES = ("GIS", "ISB", "Jetty")

# Freshness limits per feed, derived from each source's own publish + poll
# cadence (see ingestion_scheduler's poll intervals), with room for one missed
# tick so a single transient failure isn't reported as a broken feed.
#
# The two forecast-carrying feeds are judged on FORWARD coverage instead of age:
# nwp needs to reach past the day-ahead horizon's near end, and aerosol past
# real_data._AEROSOL_MAX_AGE_MINUTES (180) or the hour-ahead leads silently
# revert to neutral defaults - the exact bug fixed on 2026-07-25.
CLOUD_MAX_AGE_MINUTES = 90.0  # Himawari ~10 min cadence, polled every ~10 min
UV_MAX_AGE_MINUTES = 48 * 60.0  # daily values, polled every 6h
UV_HOURLY_MAX_AGE_MINUTES = 18 * 60.0
NWP_MIN_LEAD_MINUTES = 6 * 60.0
AEROSOL_MIN_LEAD_MINUTES = 180.0

DEFAULT_ANOMALY_WINDOW_DAYS = 45
MAX_ANOMALY_WINDOW_DAYS = 90

BASIS_NOTE = (
    "ไซต์นี้ไม่มีมิเตอร์วัดกำลังผลิตจริง ตัวเลข 'พลังงานที่คาดว่าได้' และ 'ค่าปกติของเดือน' "
    "เป็นค่าจากแบบจำลองทั้งคู่ ส่วน 'สาเหตุที่เป็นไปได้' เป็นการอนุมานจากตัวแปรอากาศที่วัดได้จริงของวันนั้น "
    "ไม่ใช่การยืนยันว่าแผงหรืออินเวอร์เตอร์มีปัญหา"
)


class FeedHealthOut(BaseModel):
    name: str
    label: str
    kind: str
    status: str
    rows: int
    latest: datetime | None
    age_minutes: float | None
    lead_minutes: float | None
    limit_minutes: float
    detail: str


class FeedsResponse(BaseModel):
    overall_status: str
    checked_at: datetime
    feeds: list[FeedHealthOut]


class AnomalyOut(BaseModel):
    day: str
    energy_kwh: float
    norm_kwh: float
    ratio: float
    shortfall_kwh: float
    likely_cause: str
    cause_detail: str


class AnomaliesResponse(BaseModel):
    available: bool
    zone: str
    window_days: int
    reason: str | None = None
    days_assessed: int = 0
    norm_kwh_per_day: float | None = None
    anomalies: list[AnomalyOut] = []
    basis_note: str = BASIS_NOTE


# Thai labels, kept beside the machine names so the UI doesn't have to hardcode
# a parallel mapping that can drift.
FEED_LABELS = {
    "nwp_history": "พยากรณ์อากาศ GFS (แสงอาทิตย์/อุณหภูมิ/ลม/ฝน)",
    "cloud_history": "ภาพเมฆดาวเทียม Himawari",
    "aerosol_history": "คุณภาพอากาศ CAMS (AOD/ฝุ่น/PM)",
    "uv_history": "ดัชนี UV รายวัน",
    "uv_hourly_history": "ดัชนี UV รายชั่วโมง",
}


def _latest(df: pd.DataFrame, column: str) -> datetime | None:
    if len(df) == 0 or column not in df.columns:
        return None
    value = df[column].max()
    return None if pd.isna(value) else value.to_pydatetime()


def _out(feed: FeedHealth) -> FeedHealthOut:
    return FeedHealthOut(
        name=feed.name,
        label=FEED_LABELS.get(feed.name, feed.name),
        kind=feed.kind,
        status=feed.status,
        rows=feed.rows,
        latest=feed.latest,
        age_minutes=feed.age_minutes,
        lead_minutes=feed.lead_minutes,
        limit_minutes=feed.limit_minutes,
        detail=feed.detail,
    )


@router.get("/diagnostics/feeds", response_model=FeedsResponse)
async def get_feed_health(request: Request, _user=Depends(require_role("viewer"))) -> FeedsResponse:
    store: RealDataStore = request.app.state.real_data_store
    now = datetime.now(timezone.utc)

    nwp = store.nwp_history_df()
    cloud = store.cloud_history_df()
    aerosol = store.aerosol_history_df()
    uv = store.uv_history_df()
    uv_hourly = store.uv_hourly_history_df()

    feeds = [
        evaluate_coverage_feed("nwp_history", _latest(nwp, "valid_time"), len(nwp), now, NWP_MIN_LEAD_MINUTES),
        evaluate_observation_feed("cloud_history", _latest(cloud, "observed_at"), len(cloud), now, CLOUD_MAX_AGE_MINUTES),
        evaluate_coverage_feed("aerosol_history", _latest(aerosol, "valid_time"), len(aerosol), now, AEROSOL_MIN_LEAD_MINUTES),
        evaluate_observation_feed("uv_history", _latest_uv_date(uv), len(uv), now, UV_MAX_AGE_MINUTES),
        evaluate_observation_feed("uv_hourly_history", _latest(uv_hourly, "observed_at"), len(uv_hourly), now, UV_HOURLY_MAX_AGE_MINUTES),
    ]
    return FeedsResponse(overall_status=worst_status(feeds), checked_at=now, feeds=[_out(f) for f in feeds])


def _latest_uv_date(uv: pd.DataFrame) -> datetime | None:
    """uv_history is keyed by DATE, not a timestamp, so its freshness is measured
    from the end of its newest day (a value dated today is current all day, not
    'already 18 hours old' at 18:00)."""
    if len(uv) == 0 or "observation_date" not in uv.columns:
        return None
    newest = pd.to_datetime(uv["observation_date"], utc=True).max()
    if pd.isna(newest):
        return None
    return newest.to_pydatetime() + timedelta(days=1)


@router.get("/diagnostics/{zone}/anomalies", response_model=AnomaliesResponse)
async def get_output_anomalies(
    zone: str,
    request: Request,
    days: int = Query(DEFAULT_ANOMALY_WINDOW_DAYS, ge=7, le=MAX_ANOMALY_WINDOW_DAYS),
    _user=Depends(require_role("viewer")),
) -> AnomaliesResponse:
    if zone not in ZONES:
        raise HTTPException(status_code=404, detail=f"unknown zone '{zone}'")
    store: RealDataStore = request.app.state.real_data_store
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = store.forecast_history_points(zone, GENERATED_POWER_HORIZON, since)
    if not rows:
        return AnomaliesResponse(
            available=False,
            zone=zone,
            window_days=days,
            reason="ยังไม่มีประวัติกำลังผลิตย้อนหลังพอที่จะเทียบกับค่าปกติของเดือน",
        )

    # Hourly kW -> daily kWh. One row per hour, so a row's kW IS its kWh.
    hourly = pd.DataFrame({"target_time": [pd.to_datetime(r[0], utc=True) for r in rows], "kw": [float(r[1]) for r in rows]})
    daily_energy = hourly.groupby(hourly["target_time"].dt.floor("D"))["kw"].sum()
    if len(daily_energy) < 2:
        return AnomaliesResponse(
            available=False,
            zone=zone,
            window_days=days,
            days_assessed=len(daily_energy),
            reason="มีข้อมูลย้อนหลังน้อยกว่า 2 วัน ยังเทียบหาความผิดปกติไม่ได้",
        )

    # Drop the newest day: it is still in progress, so its partial total would
    # look like a dramatic shortfall every single time this is called.
    daily_energy = daily_energy.iloc[:-1]
    if len(daily_energy) == 0:
        return AnomaliesResponse(
            available=False, zone=zone, window_days=days, reason="มีเฉพาะข้อมูลของวันนี้ที่ยังไม่จบวัน"
        )

    drivers = {d.day.date().isoformat(): d for d in daily_conditions(store, window_days=days)}
    soiling_by_day = _soiling_by_day(store, zone, days)
    day_rows = [
        DayEnergy(
            day=day.date().isoformat(),
            energy_kwh=float(kwh),
            cloud_pct=_cloud_pct_for(store, day),
            precip_mm=drivers[day.date().isoformat()].precip_mm if day.date().isoformat() in drivers else None,
            soiling_pct=soiling_by_day.get(day.date().isoformat()),
            aod=None,
        )
        for day, kwh in daily_energy.items()
    ]

    # The norm is this zone's own estimate for the CURRENT month, per day - the
    # same seasonal model the Energy Report's monthly chart shows, so the two
    # can't disagree.
    norm = _monthly_norm_kwh_per_day(zone)
    if norm is None:
        return AnomaliesResponse(
            available=False,
            zone=zone,
            window_days=days,
            days_assessed=len(day_rows),
            reason="ยังคำนวณค่าปกติรายเดือนของโซนนี้ไม่ได้",
        )

    anomalies = find_output_anomalies(day_rows, norm)
    return AnomaliesResponse(
        available=True,
        zone=zone,
        window_days=days,
        days_assessed=len(day_rows),
        norm_kwh_per_day=norm,
        anomalies=[
            AnomalyOut(
                day=a.day,
                energy_kwh=a.energy_kwh,
                norm_kwh=a.norm_kwh,
                ratio=a.ratio,
                shortfall_kwh=a.shortfall_kwh,
                likely_cause=a.likely_cause,
                cause_detail=a.cause_detail,
            )
            for a in anomalies
        ],
    )


def _monthly_norm_kwh_per_day(zone: str) -> float | None:
    """Expected kWh/day for the current month, from the same seasonal monthly
    estimates the Energy Report chart uses. None if that can't be computed."""
    try:
        monthly = monthly_ac_energy_estimates(zone)
    except Exception:
        return None
    month = datetime.now(timezone.utc).month
    for estimate in monthly:
        if getattr(estimate, "month", None) == month:
            days_in_month = pd.Timestamp(year=datetime.now(timezone.utc).year, month=month, day=1).days_in_month
            return float(estimate.ac_energy_kwh) / days_in_month
    return None


def _cloud_pct_for(store: RealDataStore, day: pd.Timestamp) -> float | None:
    """Mean satellite cloud opacity for one UTC day, or None with no coverage."""
    cloud = store.cloud_history_df()
    if len(cloud) == 0 or "observed_at" not in cloud.columns:
        return None
    same_day = cloud[cloud["observed_at"].dt.floor("D") == day]
    if len(same_day) == 0:
        return None
    return float(same_day["cloud_opacity_pct"].mean())


def _soiling_by_day(store: RealDataStore, zone: str, days: int) -> dict[str, float]:
    """The soiling timeline for this zone keyed by ISO date, so a dirty stretch
    can be offered as a candidate cause. Empty when the advisor can't assess."""
    from .soiling_service import assess_zone

    try:
        assessment = assess_zone(store, zone, window_days=days)
    except Exception:
        return {}
    if not assessment.available:
        return {}
    return dict(zip(assessment.series_days, assessment.series_loss_pct))
