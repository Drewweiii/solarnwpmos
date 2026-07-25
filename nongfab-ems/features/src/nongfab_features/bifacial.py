"""The back of the panel is collecting light and nothing here counts it
(2026-07-25, project H).

config/assets.yaml names the installed module: **Trina Vertex N TSM-NEG21C.20,
N-type i-TOPCon BIFACIAL dual glass**. Its rear face converts light too - Trina
rates the power bifaciality at **80 +/- 5%**, meaning a rear-side irradiance of
100 W/m2 produces what 80 W/m2 on the front would. The model here has always
treated these as one-sided, so every yield figure this system publishes leaves
the rear contribution out entirely.

WHY THIS IS NOT SIMPLY SWITCHED ON. Front irradiance needs only geometry, which
this project has. Rear irradiance needs two things nobody measured:

  * ALBEDO - how reflective the ground under the array is. It is the dominant
    term, and it is wildly site-specific: pale concrete returns three times what
    water does. Jetty's panels sit over the sea, where albedo is very low.
  * MOUNTING HEIGHT - how far the panel sits above that ground. Raising a panel
    lets more reflected light reach its rear, and this project's only figure is
    `Solar3DScene`'s assumed 1.0 m ground clearance, itself documented as "not a
    measurement".

So the gain is real but its size rests on two guesses. Publishing a
5-10% uplift to payback on that basis would be exactly the kind of thing this
codebase refuses to do elsewhere. The gain is therefore computed and REPORTED,
clearly labelled, while the published energy figures stay monofacial and
conservative - the same treatment project D gave the unmeasured tilt.

Model: pvlib's `infinite_sheds`, the standard view-factor treatment for a
repeating row array. It accounts for the row in front blocking part of the
rear's view of the ground, which a naive "albedo x GHI" estimate ignores and
which is why that shortcut overstates the gain at close row spacing.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pvlib

from .clearsky import compute_clearsky_and_position, nong_fab_site_location

# Trina's published figure for this module: 80 +/- 5%. The tolerance is why the
# report shows a band rather than a single number.
DATASHEET_BIFACIALITY = 0.80
DATASHEET_BIFACIALITY_TOLERANCE = 0.05

# Ground reflectance by what is actually under each zone. All three are
# standard published ranges, NOT site measurements - the note on every surface
# that shows a bifacial number has to say so.
#   concrete/gravel yard  0.25-0.35
#   light industrial roof 0.30-0.50 (membrane roofs run high)
#   open sea water        0.05-0.10 at the shallow incidence angles here
ALBEDO_BY_GROUND: dict[str, float] = {
    "ground": 0.25,
    "rooftop": 0.35,
    "water": 0.07,
}

# Panel mid-height above the reflecting surface, metres. Ground-mount reuses
# Solar3DScene's assumed 1.0 m clearance; the pier deck sits higher above the
# water it reflects from. Both are assumptions, and both matter: rear gain grows
# with height.
HEIGHT_BY_GROUND: dict[str, float] = {
    "ground": 1.5,
    "rooftop": 1.0,
    "water": 4.0,
}


def ground_kind_for_zone(zone_id: str) -> str:
    """What each zone's rear face is actually looking at.

    Same evidence `Solar3DScene`'s mount-type mapping already relies on: GIS is
    ground-mount in an open yard (assets.yaml's own tilt comment, plus the
    user's Google Earth pins), ISB is rooftop, and Jetty is a trestle over open
    sea - which is the one that matters most here, because water reflects
    barely a fifth of what a pale roof does.
    """
    if zone_id == "Jetty":
        return "water"
    if zone_id == "ISB":
        return "rooftop"
    return "ground"


@dataclass(frozen=True)
class BifacialGain:
    """Annual rear-side contribution, as a percentage of front-side yield."""

    gain_pct: float
    gain_pct_low: float
    gain_pct_high: float
    albedo: float
    height_m: float
    ground_cover_ratio: float
    ground_kind: str

    @property
    def band_label(self) -> str:
        """The datasheet's +/-5% bifaciality tolerance carried through to the
        answer, so the number is never read as more precise than its input."""
        return f"{self.gain_pct_low:.1f}–{self.gain_pct_high:.1f}%"


def _representative_year(year: int, tz: str = "Asia/Bangkok") -> tuple[pd.DatetimeIndex, np.ndarray]:
    frames = []
    weights: list[float] = []
    for month in range(1, 13):
        start = pd.Timestamp(year=year, month=month, day=15, tz=tz)
        idx = pd.date_range(start, periods=24, freq="h", tz=tz)
        frames.append(idx)
        weights.extend([float(calendar.monthrange(year, month)[1])] * 24)
    return pd.DatetimeIndex(np.concatenate([f.values for f in frames]), tz=tz), np.asarray(weights)


def annual_rear_gain(
    tilt_deg: float,
    azimuth_deg: float,
    row_pitch_m: float,
    slant_height_m: float,
    ground_kind: str,
    year: int,
    bifaciality: float = DATASHEET_BIFACIALITY,
    tz: str = "Asia/Bangkok",
) -> BifacialGain:
    """Rear-side energy as a percentage of front-side, over a clear-sky year.

    Reported as a percentage rather than kWh so it composes with whatever the
    front-side model says - if the front figure later changes, this stays valid.
    """
    albedo = ALBEDO_BY_GROUND[ground_kind]
    height = HEIGHT_BY_GROUND[ground_kind]
    gcr = min(0.95, slant_height_m / row_pitch_m) if row_pitch_m > 0 else 0.5

    index, weights = _representative_year(year, tz)
    lat, lon = nong_fab_site_location()
    sky = compute_clearsky_and_position(index, lat, lon, tz=tz)

    result = pvlib.bifacial.infinite_sheds.get_irradiance(
        surface_tilt=tilt_deg,
        surface_azimuth=azimuth_deg,
        solar_zenith=sky["zenith_deg"],
        solar_azimuth=sky["azimuth_deg"],
        gcr=gcr,
        height=height,
        pitch=row_pitch_m,
        ghi=sky["ghi_clearsky"],
        dhi=sky["dhi_clearsky"],
        dni=sky["dni_clearsky"],
        albedo=albedo,
        dni_extra=pvlib.irradiance.get_extra_radiation(index),
        bifaciality=bifaciality,
    )

    front = np.nan_to_num(result["poa_front"].to_numpy(), nan=0.0)
    back = np.nan_to_num(result["poa_back"].to_numpy(), nan=0.0)
    front_energy = float(np.sum(front * weights))
    back_energy = float(np.sum(back * weights))
    if front_energy <= 0.0:
        return BifacialGain(0.0, 0.0, 0.0, albedo, height, gcr, ground_kind)

    # poa_back is already the raw rear irradiance; the bifaciality factor
    # converts it to front-equivalent watts, which is what "gain" means here.
    ratio = back_energy / front_energy
    return BifacialGain(
        gain_pct=100.0 * ratio * bifaciality,
        gain_pct_low=100.0 * ratio * (bifaciality - DATASHEET_BIFACIALITY_TOLERANCE),
        gain_pct_high=100.0 * ratio * (bifaciality + DATASHEET_BIFACIALITY_TOLERANCE),
        albedo=albedo,
        height_m=height,
        ground_cover_ratio=gcr,
        ground_kind=ground_kind,
    )
