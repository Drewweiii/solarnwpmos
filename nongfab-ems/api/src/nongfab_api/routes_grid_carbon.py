"""GET /grid/carbon - what the grid's carbon intensity is doing hour by hour,
and which factor this array actually earns (2026-07-25).

The Energy Report values every avoided kWh at one flat annual factor. This
route asks the sharper question: solar here only produces between roughly 06:00
and 18:00 ICT, so does it displace the clean part of the Thai grid or the dirty
part? Answering it needs the day's real load curve (EGAT SysGen) plus a model
of which plant is on the margin at each load - see `grid_carbon` for exactly
which pieces are measured, which are cited literature, and which are modelled.

Honest by construction: the model is calibrated so its load-weighted mean equals
the published GEF, so this page can only ever redistribute the official number
across the day - it cannot publish a competing headline. The fuel mix behind the
shape is EPPO's real 2566 national split, but an ANNUAL average rather than the
monthly table that would capture hydrology and gas seasonality - the response
says which of the two it is in `mix_origin` / `mix_note`.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends
from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location
from nongfab_forecast.pv_conversion import nong_fab_zone_capacities_kwp
from nongfab_simulation.pipeline import simulate_zone_baseline
from pydantic import BaseModel

from . import grid_carbon
from .auth import require_role
from .egat_grid import ICT
from .routes_grid import _cached_snapshot
from .settings_store import effective, is_overridden

router = APIRouter(tags=["grid"])

METHOD_NOTE = (
    "เส้นโหลดของระบบเป็นข้อมูลจริงรายนาทีจาก กฟผ. (EGAT SysGen) · ค่าการปล่อยคาร์บอนต่อเชื้อเพลิงใช้ค่ากลาง "
    "ตลอดวัฏจักรชีวิตของ IPCC AR5 · ส่วน 'เชื้อเพลิงตัวไหนเดินเครื่องอยู่ชั่วโมงไหน' เป็นแบบจำลอง merit-order "
    "เพราะไทยไม่เปิดเผยสัดส่วนเชื้อเพลิงรายชั่วโมงแบบเรียลไทม์ (สนพ./กฟผ. เผยแพร่ย้อนหลังเป็นรายเดือน/รายปี)"
)
CALIBRATION_NOTE = (
    "ค่าเฉลี่ยถ่วงน้ำหนักของเส้นนี้ถูกตรึงให้เท่ากับ GEF ที่เผยแพร่จริงเสมอ กราฟนี้จึงเป็นการ 'กระจาย' "
    "ตัวเลขทางการไปตามชั่วโมง ไม่ใช่การเสนอตัวเลขใหม่ที่ขัดกับหน้า Energy Report"
)
MARGINAL_NOTE = (
    "ค่า marginal คือคาร์บอนของโรงไฟฟ้าที่จะลดกำลังลงถ้าเราผลิตเพิ่มอีก 1 kWh ณ ขณะนั้น "
    "ซึ่งเป็นค่าที่ตรงกับคำถามว่า 'โซลาร์ของเราไปแทนที่อะไร' ส่วนค่า average คือความเข้มคาร์บอนของระบบโดยรวม"
)
PROFILE_NOTE = (
    "รูปการผลิตรายชั่วโมงของไซต์คำนวณจากตำแหน่งดวงอาทิตย์จริงที่พิกัดหนองแฟบแบบท้องฟ้าใส "
    "(ไซต์นี้ไม่มีมิเตอร์วัดจริง) จึงเป็นรูปของวันฟ้าโปร่ง ไม่ใช่การผลิตที่วัดได้จริงของวันนี้"
)


class CarbonHourOut(BaseModel):
    hour: int
    load_mw: float
    average_kg_per_kwh: float
    marginal_kg_per_kwh: float
    marginal_fuel_key: str
    marginal_fuel_label: str
    samples: int
    site_generation_kwh: float


class MixShareOut(BaseModel):
    key: str
    label: str
    share_pct: float
    ef_kg_per_kwh: float


class GridCarbonResponse(BaseModel):
    available: bool
    reason: str | None = None
    day: str | None = None
    hours: list[CarbonHourOut] = []
    mix: list[MixShareOut] = []
    mix_origin: str = grid_carbon.MIX_ORIGIN_ANNUAL
    mix_note: str = grid_carbon.MIX_ANNUAL_NOTE

    published_ef_kg_per_kwh: float | None = None
    solar_weighted_marginal_kg_per_kwh: float | None = None
    solar_weighted_average_kg_per_kwh: float | None = None
    # How much the timing of this array's output is worth, as a percentage
    # difference against the flat published factor. Positive = solar displaces
    # dirtier-than-average plant.
    marginal_uplift_pct: float | None = None

    method_note: str = METHOD_NOTE
    calibration_note: str = CALIBRATION_NOTE
    marginal_note: str = MARGINAL_NOTE
    profile_note: str = PROFILE_NOTE


def _mix_from_settings() -> dict[str, float]:
    """The fuel-mix shares as configured, falling back per-fuel to EPPO's
    published annual figures. Read per request so publishing a share takes
    effect without a restart, the same as every other settings-driven figure
    here."""
    shares: dict[str, float] = {}
    for key, fallback in grid_carbon.DEFAULT_MIX.items():
        try:
            shares[key] = float(effective(f"gridmix.{key}_pct")) / 100.0
        except KeyError:
            shares[key] = fallback
    return shares


def _mix_is_published() -> bool:
    """True once ANY share has been deliberately entered - that is the moment
    the table stops being the shipped EPPO ANNUAL average and becomes whatever
    figures somebody put in (ideally a monthly one), which is what the origin
    label distinguishes."""
    return any(is_overridden(f"gridmix.{key}_pct") for key in grid_carbon.DEFAULT_MIX)


def site_hourly_generation_kwh(day: datetime) -> dict[int, float]:
    """Clear-sky AC energy per ICT hour, summed over every zone.

    Clear-sky rather than measured because this site has no generation meter
    (see `PROFILE_NOTE`); it is the same pvlib solar-position machinery the
    monthly estimates use, so the SHAPE - which is all this weighting needs - is
    real astronomy at Nong Fab's own coordinates.
    """
    index = pd.date_range(day, periods=24, freq="h", tz=ICT)
    lat, lon = nong_fab_site_location()
    solpos = compute_clearsky_and_position(index, lat, lon, tz="Asia/Bangkok")
    ghi = solpos["ghi_clearsky"].to_numpy()
    # Same synthetic diurnal temperature shape the monthly estimates use (peak
    # at local noon). Temperature barely moves the SHAPE that this weighting
    # needs, so reusing it keeps the two paths from disagreeing.
    temp = 28.0 + 5.0 * np.sin(np.pi * (index.hour.to_numpy() - 6) / 12.0)

    totals: dict[int, float] = {hour: 0.0 for hour in range(24)}
    for zone_id in nong_fab_zone_capacities_kwp():
        baseline = simulate_zone_baseline(zone_id, ghi, temp, index)
        for timestamp, kw in baseline.ac_power_kw.items():
            # Hourly samples, so kW over one hour is kWh directly.
            totals[timestamp.hour] += float(kw)
    return totals


@router.get("/grid/carbon", response_model=GridCarbonResponse)
async def get_grid_carbon(_user=Depends(require_role("viewer"))) -> GridCarbonResponse:
    snapshot = await _cached_snapshot()
    if snapshot is None:
        return GridCarbonResponse(
            available=False,
            reason="ยังดึงเส้นโหลดของระบบไฟฟ้าจาก กฟผ. ไม่ได้ จึงยังคำนวณคาร์บอนรายชั่วโมงไม่ได้",
        )

    published_ef = float(effective("green.ef_scope2_kg_per_kwh"))
    shares = _mix_from_settings()
    curve = grid_carbon.carbon_curve(snapshot.actual, shares, published_ef)
    if not curve:
        return GridCarbonResponse(
            available=False,
            reason="เส้นโหลดที่ได้มายังไม่พอสำหรับสร้างลำดับการเดินเครื่อง (merit-order)",
            published_ef_kg_per_kwh=published_ef,
        )

    hours = grid_carbon.hourly_means(curve)

    try:
        day_start = datetime.fromisoformat(snapshot.day).replace(tzinfo=ICT)
        generation = site_hourly_generation_kwh(day_start)
    except (ValueError, KeyError):
        # A bad day label or an unknown zone must not take down the grid curve,
        # which is useful on its own; only the solar weighting is lost.
        generation = {}

    marginal = grid_carbon.solar_weighted_ef(hours, generation, "marginal_kg_per_kwh")
    average = grid_carbon.solar_weighted_ef(hours, generation, "average_kg_per_kwh")
    uplift = None if marginal is None or published_ef <= 0 else (marginal / published_ef - 1.0) * 100.0

    normalised = grid_carbon.normalised_shares(shares)
    published_mix = _mix_is_published()

    return GridCarbonResponse(
        available=True,
        day=snapshot.day,
        hours=[
            CarbonHourOut(
                hour=int(row["hour"]),  # type: ignore[arg-type]
                load_mw=float(row["load_mw"]),  # type: ignore[arg-type]
                average_kg_per_kwh=float(row["average_kg_per_kwh"]),  # type: ignore[arg-type]
                marginal_kg_per_kwh=float(row["marginal_kg_per_kwh"]),  # type: ignore[arg-type]
                marginal_fuel_key=str(row["marginal_fuel_key"]),
                marginal_fuel_label=str(row["marginal_fuel_label"]),
                samples=int(row["samples"]),  # type: ignore[arg-type]
                site_generation_kwh=generation.get(int(row["hour"]), 0.0),  # type: ignore[arg-type]
            )
            for row in hours
        ],
        mix=[
            MixShareOut(
                key=key,
                label=grid_carbon.BY_KEY[key].label,
                share_pct=share * 100.0,
                ef_kg_per_kwh=grid_carbon.BY_KEY[key].ef_kg_per_kwh,
            )
            for key, share in sorted(normalised.items(), key=lambda kv: -kv[1])
        ],
        mix_origin=grid_carbon.MIX_ORIGIN_PUBLISHED if published_mix else grid_carbon.MIX_ORIGIN_ANNUAL,
        mix_note="สัดส่วนเชื้อเพลิงชุดนี้ถูกกรอกไว้ในระบบเอง (ไม่ใช่ค่าเริ่มต้นรายปีของ สนพ.)" if published_mix else grid_carbon.MIX_ANNUAL_NOTE,
        published_ef_kg_per_kwh=published_ef,
        solar_weighted_marginal_kg_per_kwh=marginal,
        solar_weighted_average_kg_per_kwh=average,
        marginal_uplift_pct=uplift,
    )
