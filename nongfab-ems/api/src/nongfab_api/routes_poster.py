"""GET /poster/{zone} - a year of light at Nong Fab, as data (2026-07-26, project S).

Feeds a single generated image: one radial dial where each of the year's days
is a spoke spanning its own sunrise to sunset, and the twelve months are
coloured by how much this array produces in each.

THE HONESTY CONSTRAINT THAT SHAPED THE WHOLE THING. The obvious poster is a
365 x 24 grid of cells coloured by output - beautiful, and a lie. This project's
annual energy model is **twelve representative days**, one per calendar month,
scaled by that month's real day count (see
`nongfab_simulation.pipeline.monthly_ac_energy_estimates`, which says so in its
own docstring). Interpolating that into 8,760 coloured cells would invent
8,748 values nobody computed. The rule this project recorded during project L
applies here too: a picture that renders more detail than the data supports is
fabrication, just in pixels rather than digits.

So the poster is built from two layers at two honestly different resolutions:

* **per day, exact** - sunrise, sunset and solar-noon elevation for all 365 (or
  366) days, from pvlib at the site's real coordinates. This is astronomy, not
  measurement or modelling: it is as exact as the coordinates are, and it is
  what gives the image its shape.
* **per month, modelled** - the twelve AC energy figures, which drive colour
  only, and are labelled as monthly everywhere they appear.

The response says which is which, and the poster prints it.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

import pandas as pd
import pvlib
from fastapi import APIRouter, Depends, HTTPException
from nongfab_common.assets import load_assets
from nongfab_features.clearsky import nong_fab_site_location
from nongfab_simulation.pipeline import monthly_ac_energy_estimates
from pydantic import BaseModel

from .auth import require_role

router = APIRouter(tags=["poster"])

# Thailand only, no DST, so a fixed offset is exact rather than a simplification.
ICT_OFFSET_HOURS = 7

THAI_MONTHS = (
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
)

_GEOMETRY_NOTE = (
    "เส้นรายวันทั้ง 365 เส้นคือเวลาขึ้น-ตกของดวงอาทิตย์จริงที่พิกัดของไซต์นี้ "
    "คำนวณด้วย pvlib เป็นดาราศาสตร์ล้วน ไม่ใช่การวัดหรือการประมาณ"
)

_ENERGY_NOTE = (
    "สีของแต่ละเดือนมาจากพลังงานรายเดือน 12 ค่า ซึ่งเป็นผลจากโมเดล "
    "(วันตัวแทนเดือนละ 1 วัน คูณจำนวนวันจริงของเดือนนั้น) — "
    "ไม่ได้ไล่สีรายวัน เพราะไม่มีข้อมูลรายวันจริงให้ไล่"
)

_WHY_NOTE = (
    "ภาพนี้จงใจแสดงสองความละเอียดแยกกัน: รูปทรงเป็นรายวันและแม่นยำ ส่วนสีเป็นรายเดือนและเป็นแบบจำลอง "
    "การไล่สีรายวันจะดูดีกว่านี้ แต่ต้องเดาค่าขึ้นมาเอง 353 วัน"
)


class PosterDay(BaseModel):
    day_of_year: int
    """Local sunrise/sunset in decimal hours ICT. None on the (impossible at
    this latitude, but pvlib can return NaT) day with no sunrise."""
    sunrise_hour: float | None
    sunset_hour: float | None
    daylight_hours: float | None
    noon_elevation_deg: float | None


class PosterMonth(BaseModel):
    month: int
    label: str
    ac_energy_kwh: float
    is_rainy_season: bool
    days_in_month: int


class PosterResponse(BaseModel):
    zone: str
    year: int
    lat: float
    lon: float
    days: list[PosterDay]
    months: list[PosterMonth]
    annual_ac_energy_kwh: float
    longest_day: int
    shortest_day: int
    geometry_note: str = _GEOMETRY_NOTE
    energy_note: str = _ENERGY_NOTE
    why_note: str = _WHY_NOTE


def _decimal_hour_ict(value: object) -> float | None:
    """A pandas timestamp (UTC) as decimal hours in Thai local time.

    pvlib hands back NaT where the sun does not rise or set; at 12.7°N that
    never happens, but returning None rather than a nonsense float means a bad
    input surfaces as a gap in the drawing instead of a spike in it.
    """
    if value is None or pd.isna(value):
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    local = ts.tz_convert(dt_timezone.utc) + timedelta(hours=ICT_OFFSET_HOURS)
    return local.hour + local.minute / 60 + local.second / 3600


def build_poster(zone: str, year: int) -> PosterResponse:
    lat, lon = nong_fab_site_location()

    # One timestamp per day at local solar-ish noon; pvlib's rise/set/transit
    # only needs a date, but a mid-day stamp keeps it unambiguous about which
    # local day is meant once converted out of UTC.
    days_in_year = 366 if calendar.isleap(year) else 365
    stamps = pd.DatetimeIndex(
        [
            datetime(year, 1, 1, 12 - ICT_OFFSET_HOURS, tzinfo=dt_timezone.utc) + timedelta(days=d)
            for d in range(days_in_year)
        ]
    )
    rise_set = pvlib.solarposition.sun_rise_set_transit_spa(stamps, lat, lon)
    transits = pd.DatetimeIndex(pd.to_datetime(rise_set["transit"], utc=True))
    noon_positions = pvlib.solarposition.get_solarposition(transits, lat, lon)
    elevations = noon_positions["apparent_elevation"].tolist()

    days: list[PosterDay] = []
    for i in range(days_in_year):
        sunrise = _decimal_hour_ict(rise_set["sunrise"].iloc[i])
        sunset = _decimal_hour_ict(rise_set["sunset"].iloc[i])
        daylight = None if sunrise is None or sunset is None else round(sunset - sunrise, 4)
        elevation = elevations[i]
        days.append(
            PosterDay(
                day_of_year=i + 1,
                sunrise_hour=None if sunrise is None else round(sunrise, 4),
                sunset_hour=None if sunset is None else round(sunset, 4),
                daylight_hours=daylight,
                noon_elevation_deg=None if pd.isna(elevation) else round(float(elevation), 3),
            )
        )

    estimates = monthly_ac_energy_estimates(zone, year=year)
    months = [
        PosterMonth(
            month=m.month,
            label=THAI_MONTHS[m.month - 1],
            ac_energy_kwh=round(m.ac_energy_kwh, 1),
            is_rainy_season=m.is_rainy_season,
            days_in_month=calendar.monthrange(year, m.month)[1],
        )
        for m in estimates
    ]

    # Longest and shortest day, read off the computed geometry rather than
    # assumed to be the solstices - the site is north of the equator but the
    # answer should come from the same numbers the drawing uses.
    lit = [d for d in days if d.daylight_hours is not None]
    longest = max(lit, key=lambda d: d.daylight_hours or 0).day_of_year if lit else 1
    shortest = min(lit, key=lambda d: d.daylight_hours or 0).day_of_year if lit else 1

    return PosterResponse(
        zone=zone,
        year=year,
        lat=lat,
        lon=lon,
        days=days,
        months=months,
        annual_ac_energy_kwh=round(sum(m.ac_energy_kwh for m in months), 1),
        longest_day=longest,
        shortest_day=shortest,
    )


@router.get("/poster/{zone}", response_model=PosterResponse)
async def get_poster(zone: str, year: int | None = None, _user=Depends(require_role("viewer"))) -> PosterResponse:
    known = {z.id for z in load_assets().zones}
    if zone not in known:
        raise HTTPException(status_code=404, detail=f"unknown zone '{zone}'. known: {sorted(known)}")
    target = year or date.today().year
    # A poster for year 3 or year 9999 is a pvlib call that will happily run and
    # return something meaningless; the array was commissioned this decade.
    if not (2000 <= target <= 2100):
        raise HTTPException(status_code=400, detail=f"year {target} out of range (2000-2100)")
    return build_poster(zone, target)
