"""How much is the inverter throwing away, and how much more could it take?
(2026-07-25, project F)

An array is almost always built with more DC than its inverter can pass. That is
deliberate - modules are cheap, inverters are not, and the array only reaches
nameplate for a few hours a year - but past some point the inverter starts
clipping away midday peaks and the next module pays for less than it costs.
Nothing here has ever quantified where that point is, or how much this site is
losing to it today.

Two questions, and they are different:

  1. CLIPPING TODAY. Every zone already runs `clip_to_inverter_capacity`, so
     clipping is happening in the model; it simply was never measured. Pre-clip
     minus post-clip is the answer, and it needs no assumptions at all.
  2. HEADROOM. `assets.yaml` gives ISB DC:AC = 0.93 - the inverter is LARGER
     than the array. That is unusual and it is free capacity: modules can be
     added there without buying an inverter. This module says how many, and
     what they would produce.

Deliberately NOT an economic optimum. More DC always yields more energy, just
with diminishing returns, so "maximise energy" would answer "add modules
forever". The economically right ratio depends on module cost per kWp, which is
this project's remaining placeholder (CAPEX THB 30,000/kWp is an estimate the
user chose to keep). Rather than dress a guess as an optimum, this reports the
curve and the MARGINAL yield of the next kWp at each ratio, so the knee is
visible and can be priced against whatever CAPEX turns out to be real.

Built on the same seasonal representative days and the same POA transposition
the main pipeline uses, so these figures are comparable with the published
annual yield rather than a parallel estimate of it.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as dt_timezone
from functools import lru_cache

import pandas as pd
from nongfab_common.assets import load_assets
from nongfab_features.poa import poa_from_ghi
from nongfab_forecast.pv_conversion import default_params_from_capacity, predict_power_kw

from .loss_model import apply_losses, clip_to_inverter_capacity, default_loss_factors
from .pipeline import (
    DEFAULT_INVERTER_EFFICIENCY_PCT,
    _representative_day_irradiance_temp,
    _zone_orientation,
)

# How far past the built ratio to sweep. 1.6 is beyond anything anyone would
# design at this latitude - the point is to show the curve flattening, not to
# propose it.
MAX_RATIO = 1.6
RATIO_STEP = 0.05


@dataclass(frozen=True)
class RatioPoint:
    """One DC:AC ratio and what the array would deliver at it."""

    dc_ac_ratio: float
    dc_capacity_kwp: float
    # AC energy the inverter would pass if it had no limit.
    unclipped_kwh: float
    # What actually leaves the inverter.
    delivered_kwh: float

    @property
    def clipped_kwh(self) -> float:
        return max(0.0, self.unclipped_kwh - self.delivered_kwh)

    @property
    def clipping_loss_pct(self) -> float:
        if self.unclipped_kwh <= 0.0:
            return 0.0
        return 100.0 * self.clipped_kwh / self.unclipped_kwh

    @property
    def specific_yield_kwh_per_kwp(self) -> float:
        """Delivered energy per kWp installed. Falls as the ratio rises - the
        headline symptom of over-sizing, and the number that makes two arrays of
        different size comparable."""
        if self.dc_capacity_kwp <= 0.0:
            return 0.0
        return self.delivered_kwh / self.dc_capacity_kwp


@dataclass(frozen=True)
class ZoneRatioReport:
    zone_id: str
    ac_capacity_kw: float
    built: RatioPoint
    curve: list[RatioPoint]

    @property
    def has_headroom(self) -> bool:
        """True when the inverter is bigger than the array, i.e. DC could be
        added before clipping even begins. ISB is the case this exists for."""
        return self.built.dc_ac_ratio < 1.0

    def marginal_kwh_per_added_kwp(self, at_ratio: float) -> float | None:
        """Annual energy the NEXT kWp would deliver at `at_ratio`.

        The number to price a module against, and the reason this module does
        not pick an optimum itself: divide the module's cost by this and compare
        with the tariff, and the answer falls out of real figures rather than
        out of a placeholder CAPEX.
        """
        ordered = sorted(self.curve, key=lambda p: p.dc_ac_ratio)
        for lower, upper in zip(ordered, ordered[1:]):
            if lower.dc_ac_ratio <= at_ratio <= upper.dc_ac_ratio:
                added_kwp = upper.dc_capacity_kwp - lower.dc_capacity_kwp
                if added_kwp <= 0:
                    return None
                return (upper.delivered_kwh - lower.delivered_kwh) / added_kwp
        return None


def _reference_ac_series(zone_id: str, reference_kwp: float, year: int) -> list[tuple[pd.Series, int]]:
    """Unclipped AC power for each representative month at `reference_kwp`,
    paired with that month's day count.

    Computed ONCE and scaled per candidate ratio, which is exact rather than an
    approximation: `predict_power_kw` is strictly linear in installed capacity
    (verified - doubling kWp doubles every sample), so a 1.4x array is a 1.4x
    series. Only the CLIPPING is non-linear, and that is applied after scaling,
    which is the whole point. Sweeping the ratio by re-running the pipeline
    instead took ninety seconds for an answer that never varies.
    """
    zone = load_assets().zone(zone_id)
    tilt_deg, azimuth_deg = _zone_orientation(zone)
    factors = default_loss_factors(zone_id)
    efficiency = zone.inverter_detail.efficiency_pct if zone.inverter_detail else DEFAULT_INVERTER_EFFICIENCY_PCT
    params = default_params_from_capacity(reference_kwp)

    months: list[tuple[pd.Series, int]] = []
    for month in range(1, 13):
        index, ghi, temp = _representative_day_irradiance_temp(month, year=year)
        poa = poa_from_ghi(ghi, index, tilt_deg, azimuth_deg)
        dc = pd.Series(predict_power_kw(poa, temp, params), index=index)
        months.append((apply_losses(dc, factors, efficiency), calendar.monthrange(year, month)[1]))
    return months


def _energy_at(
    reference: list[tuple[pd.Series, int]], reference_kwp: float, dc_capacity_kwp: float, ac_capacity_kw: float
) -> tuple[float, float]:
    """(unclipped, delivered) annual AC energy for a hypothetical DC size."""
    scale = dc_capacity_kwp / reference_kwp if reference_kwp else 0.0
    unclipped_total = 0.0
    delivered_total = 0.0
    for series, days in reference:
        scaled = series * scale
        # Hourly samples, so summing kW over the day gives that day's kWh.
        unclipped_total += float(scaled.sum()) * days
        delivered_total += float(clip_to_inverter_capacity(scaled, ac_capacity_kw).sum()) * days
    return unclipped_total, delivered_total


@lru_cache(maxsize=8)
def analyse_zone(zone_id: str, year: int | None = None) -> ZoneRatioReport:
    """Clipping as built, plus the whole DC:AC curve for this zone.

    Cached: 12 representative days x ~30 ratios is seconds of work whose answer
    depends only on the zone geometry and the sun. Cleared by
    `settings_service.apply_effective_settings`, since capacity, tilt and loss
    factors are all user-editable.
    """
    year = year or datetime.now(dt_timezone.utc).year
    zone = load_assets().zone(zone_id)
    ac_capacity_kw = zone.ac_capacity_kw
    built_dc = zone.dc_capacity_kwp
    reference = _reference_ac_series(zone_id, built_dc, year)

    def point(dc_kwp: float) -> RatioPoint:
        unclipped, delivered = _energy_at(reference, built_dc, dc_kwp, ac_capacity_kw)
        return RatioPoint(
            dc_ac_ratio=dc_kwp / ac_capacity_kw if ac_capacity_kw else 0.0,
            dc_capacity_kwp=dc_kwp,
            unclipped_kwh=unclipped,
            delivered_kwh=delivered,
        )

    ratios = [round(MAX_RATIO - i * RATIO_STEP, 2) for i in range(int((MAX_RATIO - 0.6) / RATIO_STEP) + 1)]
    curve = [point(ratio * ac_capacity_kw) for ratio in sorted(ratios)]
    return ZoneRatioReport(zone_id=zone_id, ac_capacity_kw=ac_capacity_kw, built=point(built_dc), curve=curve)


def headroom_kwp(zone_id: str, year: int | None = None) -> float:
    """DC that could be added before the array even reaches its inverter's
    rating. Zero for a zone already at or past 1.0 - "no free room" rather than
    a negative number that would read as a deficit to make up."""
    report = analyse_zone(zone_id, year)
    return max(0.0, report.ac_capacity_kw - report.built.dc_capacity_kwp)
