"""GET /grid/today - Nong Fab in the context of the whole Thai power system
(2026-07-25), from EGAT's own public plan-vs-actual feed.

Everything else on this dashboard describes 429 kWp in isolation. This route
answers the question that only national data can: *when the country actually
needs power most, is solar producing?* For Thailand the answer is no - the
system peak lands in the evening (2026's was 20:50, well after sunset at this
latitude), so a fully grid-tied site with no battery cannot shave it. That is a
real limitation of PV here, and showing it with EGAT's numbers is more honest
than a dashboard that only ever reports how much the panels made.

See `egat_grid` for the source, its compliance notes, and why every timestamp
in this feed is ICT rather than UTC.

Honest-empty: when the upstream is unreachable the response is
`available=false` with a reason, exactly like the other external-data panels -
never a fabricated curve.
"""

from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends
from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from pydantic import BaseModel

from . import egat_grid
from .auth import require_role
from .egat_grid import ICT

router = APIRouter(tags=["grid"])

# Above this clear-sky GHI the array is meaningfully producing. 20 W/m^2 is
# nominal twilight, not a physical threshold - it just keeps the "solar window"
# from including the numerically noisy minutes either side of the horizon.
SOLAR_WINDOW_MIN_GHI_W_M2 = 20.0

SOURCE_NOTE = (
    "ข้อมูลระบบไฟฟ้าทั้งประเทศจาก EGAT SysGen (กฟผ.) ซึ่งเป็นข้อมูลสาธารณะแบบเรียลไทม์ "
    "เวลาทั้งหมดเป็นเวลาประเทศไทย (ICT) ตามที่ต้นทางเผยแพร่"
)
COMPARISON_NOTE = (
    "กำลังผลิตของหนองแฟบเทียบกับทั้งประเทศเป็นการเทียบ 'กำลังติดตั้ง' กับ 'กำลังผลิตจริงของระบบ' "
    "เพื่อให้เห็นสัดส่วนตามจริง ไม่ได้แปลว่าโซลาร์ที่นี่ป้อนเข้าระบบส่ง (ไซต์นี้ใช้ไฟเองทั้งหมด)"
)


class GridPointOut(BaseModel):
    at: datetime
    mw: float
    ambient_c: float | None = None


class PeakOut(BaseModel):
    label: str
    mw: float
    at: datetime | None
    ambient_c: float | None


class GridTodayResponse(BaseModel):
    available: bool
    reason: str | None = None
    day: str | None = None
    actual: list[GridPointOut] = []
    plan: list[GridPointOut] = []
    peaks: list[PeakOut] = []

    # --- derived context ---
    latest_mw: float | None = None
    latest_at: datetime | None = None
    latest_ambient_c: float | None = None
    # Running maximum so far today, NOT the day's final peak (see egat_grid).
    peak_so_far_mw: float | None = None
    peak_so_far_at: datetime | None = None
    plan_deviation_mw: float | None = None
    # The site's own daylight window today, from the same pvlib clear-sky model
    # the forecast uses - so the "solar was already down" claim is this site's
    # physics, not a rule of thumb.
    solar_window_start: datetime | None = None
    solar_window_end: datetime | None = None
    annual_peak_after_sunset: bool | None = None
    site_dc_capacity_kwp: float | None = None
    site_share_of_system_pct: float | None = None

    source_note: str = SOURCE_NOTE
    comparison_note: str = COMPARISON_NOTE


# One cached snapshot for the whole deployment: the upstream publishes once a
# minute and this is identical for every viewer, so a shared cache is both the
# polite thing to do upstream and the fast thing here.
_cache: dict[str, object] = {"at": 0.0, "snapshot": None}


async def _cached_snapshot() -> egat_grid.GridSnapshot | None:
    now = time.monotonic()
    fetched_at = float(_cache["at"])  # type: ignore[arg-type]
    if _cache["snapshot"] is not None and now - fetched_at < egat_grid.MIN_REFRESH_SECONDS:
        return _cache["snapshot"]  # type: ignore[return-value]
    snapshot = await egat_grid.fetch_snapshot()
    # Keep the previous snapshot on a failed refresh rather than blanking the
    # panel for a single upstream hiccup; only overwrite on success.
    if snapshot is not None:
        _cache["at"] = now
        _cache["snapshot"] = snapshot
    return snapshot or _cache["snapshot"]  # type: ignore[return-value]


def solar_window(day_iso: str) -> tuple[datetime | None, datetime | None]:
    """First and last minute of meaningful clear-sky irradiance at Nong Fab on
    `day_iso`, in ICT. (None, None) if the day won't parse or the model returns
    nothing usable - the caller then simply omits the sunset comparison."""
    try:
        day = datetime.fromisoformat(day_iso).replace(tzinfo=ICT)
    except ValueError:
        return None, None
    index = pd.date_range(start=day, periods=24 * 12, freq="5min", tz=ICT)
    lat, lon = nong_fab_site_location()
    frame = compute_clearsky_and_position(index, lat, lon, tz="Asia/Bangkok")
    lit = frame[frame["ghi_clearsky"] > SOLAR_WINDOW_MIN_GHI_W_M2]
    if len(lit) == 0:
        return None, None
    return lit.index[0].to_pydatetime(), lit.index[-1].to_pydatetime()


def _point_out(point: egat_grid.GridPoint) -> GridPointOut:
    return GridPointOut(at=point.at, mw=point.mw, ambient_c=point.ambient_c)


@router.get("/grid/today", response_model=GridTodayResponse)
async def get_grid_today(_user=Depends(require_role("viewer"))) -> GridTodayResponse:
    snapshot = await _cached_snapshot()
    if snapshot is None:
        return GridTodayResponse(
            available=False,
            reason="ยังดึงข้อมูลระบบไฟฟ้าของประเทศจาก กฟผ. ไม่ได้ในขณะนี้",
        )

    latest = snapshot.actual[-1]
    peak_so_far = egat_grid.series_peak(snapshot.actual)
    start, end = solar_window(snapshot.day)

    # Compared against the ANNUAL peak, not today's running maximum: the point
    # is the shape of Thai demand across a year, and today's partial curve
    # cannot show it before the evening has happened.
    annual_peak = next((p for p in snapshot.peaks if p.label == "สูงสุดปีนี้"), None)
    after_sunset = egat_grid.peak_is_after_sunset(annual_peak.at if annual_peak else None, end)

    capacity_kwp = sum(nong_fab_zone_capacities_kwp().values())

    return GridTodayResponse(
        available=True,
        day=snapshot.day,
        actual=[_point_out(p) for p in snapshot.actual],
        plan=[_point_out(p) for p in snapshot.plan],
        peaks=[PeakOut(label=p.label, mw=p.mw, at=p.at, ambient_c=p.ambient_c) for p in snapshot.peaks],
        latest_mw=latest.mw,
        latest_at=latest.at,
        latest_ambient_c=latest.ambient_c,
        peak_so_far_mw=peak_so_far.mw if peak_so_far else None,
        peak_so_far_at=peak_so_far.at if peak_so_far else None,
        plan_deviation_mw=egat_grid.plan_deviation_mw(snapshot.actual, snapshot.plan),
        solar_window_start=start,
        solar_window_end=end,
        annual_peak_after_sunset=after_sunset,
        site_dc_capacity_kwp=capacity_kwp,
        site_share_of_system_pct=egat_grid.share_of_system_pct(capacity_kwp, latest.mw),
    )
