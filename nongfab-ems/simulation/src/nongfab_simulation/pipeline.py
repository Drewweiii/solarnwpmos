"""High-level orchestration tying Modules 3/4/5 together: irradiance/temp ->
PV conversion (Module 4) -> loss model + DC/AC clipping (Module 5) -> one
zone's baseline AC power series. Extracted from api.py so any other caller
(a future Module 6 endpoint, a batch precompute job) gets the same pipeline
for free instead of re-deriving the fetch/convert/derate/clip chain by hand.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as dt_timezone

import numpy as np
import pandas as pd
from nongfab_common.assets import Zone, load_assets
from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location
from nongfab_forecast.pv_conversion import STC_TEMP_C, default_params_from_capacity, predict_power_kw

from .loss_model import LossFactors, apply_losses, clip_to_inverter_capacity, default_loss_factors, loss_breakdown_summary
from .what_if import ScenarioParams, apply_scenario

# Thailand's one timezone, UTC+7, no DST - used for the monthly estimate below
# so "hour 12" in the representative day actually means local solar noon, not
# UTC noon (which is ~7h off from Nong Fab's real solar noon - a mismatch the
# older synthetic_day_irradiance_temp()/api.py generators still have, since
# they build a tz="UTC" index and shape the sine curve against its raw hour
# number; out of scope to fix everywhere in this pass, but not repeated here).
NONG_FAB_TZ = "Asia/Bangkok"

# Thai Meteorological Department's conventional 3-season year has the rainy
# season mid-May through mid-October; approximated to whole calendar months
# since monthly_ac_energy_estimates() operates at monthly resolution.
RAINY_SEASON_MONTHS = (6, 7, 8, 9, 10)

# Not a measured climatology - no historical monthly cloud-cover dataset
# exists anywhere in this system (same "documented approximation" pattern as
# pv_conversion.py's temperature coefficient, see that module's own
# docstring). A plausible extra cloud attenuation during Thailand's rainy
# season, applied via what_if.apply_scenario so the monthly chart shows a
# real (if approximate) rainy-season dip instead of a flat line.
RAINY_SEASON_EXTRA_CLOUD_ATTENUATION_PCT = 15.0

# Typical modern crystalline-silicon linear degradation warranty figure
# (~0.4-0.7%/year is a common manufacturer range per what_if.py's own
# docstring) - not a Trina Vertex N-specific measured value (config/
# assets.yaml doesn't carry one, the same gap pv_conversion.py's temperature
# coefficient documents).
DEFAULT_DEGRADATION_PCT_PER_YEAR = 0.55
LIFETIME_YEARS = 25

# Days per year, for the flat annual-energy extrapolation below - not a
# calendar-accurate 365.25, just matching the same "one representative day"
# granularity the extrapolation itself already operates at.
DAYS_PER_YEAR = 365

# Huawei SUN2000-50KTL-M3 datasheet value - the fallback if a zone's config
# doesn't carry inverter_detail (all 3 current zones do, but future zones
# added to config/assets.yaml might not have it filled in yet).
DEFAULT_INVERTER_EFFICIENCY_PCT = 99.0


@dataclass(frozen=True)
class ZoneBaseline:
    zone: Zone
    ac_power_kw: pd.Series
    loss_factors: LossFactors
    inverter_efficiency_pct: float

    @property
    def loss_breakdown(self) -> dict[str, float]:
        return loss_breakdown_summary(self.loss_factors, self.inverter_efficiency_pct)


def simulate_zone_baseline(
    zone_id: str, irradiance_w_m2: np.ndarray | pd.Series, temp_c: np.ndarray | pd.Series, index: pd.DatetimeIndex,
) -> ZoneBaseline:
    """DC power (Module 4's PV conversion, capacity-driven defaults - see
    `nongfab_forecast.pv_conversion.default_params_from_capacity`) -> loss-
    derated, DC/AC-clipped AC power for one zone.

    `irradiance_w_m2`/`temp_c` can be real (once Module 1/2 accumulate
    enough history) or synthetic (today - see api.py's
    `_synthetic_day_irradiance_temp`); this function doesn't care which.
    """
    registry = load_assets()
    zone = registry.zone(zone_id)  # raises KeyError for an unknown zone id - let callers translate to their own error type

    pv_params = default_params_from_capacity(zone.dc_capacity_kwp)
    dc_power = pd.Series(predict_power_kw(irradiance_w_m2, temp_c, pv_params), index=index)

    factors = default_loss_factors(zone_id)
    inverter_efficiency_pct = zone.inverter_detail.efficiency_pct if zone.inverter_detail else DEFAULT_INVERTER_EFFICIENCY_PCT

    ac_power = apply_losses(dc_power, factors, inverter_efficiency_pct)
    ac_power = clip_to_inverter_capacity(ac_power, zone.ac_capacity_kw)

    return ZoneBaseline(zone=zone, ac_power_kw=ac_power, loss_factors=factors, inverter_efficiency_pct=inverter_efficiency_pct)


def estimate_annual_ac_energy_kwh(baseline: ZoneBaseline) -> float:
    """Annual AC energy estimate: `baseline`'s own day summed to kWh, x
    `DAYS_PER_YEAR`. This is a flat extrapolation of one synthetic clear-sky
    day - NOT a real annual simulation with weather variability or seasonal
    irradiance variation, since Module 1/2 don't have enough accumulated
    history yet to average over (same caveat as every other module's dev-time
    behavior - see README "Known gaps"). Swapping in a real day-by-day annual
    sum is a follow-up once that history exists, not a redesign of this
    function's shape.
    """
    return float(baseline.ac_power_kw.sum()) * DAYS_PER_YEAR


def loss_breakdown_with_temperature(
    baseline: ZoneBaseline, irradiance_w_m2: np.ndarray | pd.Series, temp_c: np.ndarray | pd.Series,
) -> dict[str, float]:
    """`baseline.loss_breakdown` plus a `temperature_pct` entry - Module 7's
    Energy Report (Feature D) wants temperature alongside soiling/shading/
    mismatch/DC-wiring/inverter as one loss table, but `loss_model.py`
    deliberately excludes temperature (see that module's own docstring: it's
    already baked into DC power by `pv_conversion.predict_power_kw`'s
    temperature-coefficient term, not a separate multiplicative derate like
    the others). Estimated here by comparing DC energy at the actual
    temperature profile against DC energy at STC (25degC) for the same
    irradiance - the difference is what temperature alone cost, holding
    irradiance fixed.
    """
    pv_params = default_params_from_capacity(baseline.zone.dc_capacity_kwp)
    dc_actual = predict_power_kw(irradiance_w_m2, temp_c, pv_params)
    stc_temp = np.full_like(np.asarray(temp_c, dtype=float), STC_TEMP_C)
    dc_at_stc_temp = predict_power_kw(irradiance_w_m2, stc_temp, pv_params)

    actual_sum = float(np.sum(dc_actual))
    stc_sum = float(np.sum(dc_at_stc_temp))
    temperature_pct = max(0.0, (1 - actual_sum / stc_sum) * 100) if stc_sum > 0 else 0.0

    return {"temperature_pct": temperature_pct, **baseline.loss_breakdown}


@dataclass(frozen=True)
class MonthlyEstimate:
    month: int  # 1-12
    ac_energy_kwh: float
    is_rainy_season: bool


def _representative_day_irradiance_temp(
    month: int, day: int = 15, year: int | None = None
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """One local (Asia/Bangkok) day's hourly clear-sky GHI - real solar
    position/Ineichen clear-sky model (`nongfab_features.clearsky`) at Nong
    Fab's actual coordinates, so month-to-month variation in day length and
    sun angle is genuine astronomy, not a fabricated seasonal curve.
    Temperature reuses the existing synthetic diurnal shape (peak at local
    noon here, unlike the older UTC-indexed generators - see NONG_FAB_TZ's
    own docstring) since no real monthly temperature climatology exists in
    this system; irradiance/day-length is what actually drives most of the
    seasonal generation swing here, not temperature. `day=15` is a
    representative mid-month sample, not a true monthly average.
    """
    year = year or datetime.now(dt_timezone.utc).year
    start = pd.Timestamp(year=year, month=month, day=day, tz=NONG_FAB_TZ)
    idx = pd.date_range(start, periods=24, freq="h", tz=NONG_FAB_TZ)
    lat, lon = nong_fab_site_location()
    solpos = compute_clearsky_and_position(idx, lat, lon, tz=NONG_FAB_TZ)
    ssrd = solpos["ghi_clearsky"].to_numpy()
    local_hour = idx.hour.to_numpy()
    temp = 28 + 5 * np.sin(np.pi * (local_hour - 6) / 12)
    return idx, ssrd, temp


def monthly_ac_energy_estimates(zone_id: str, year: int | None = None) -> list[MonthlyEstimate]:
    """One representative-day-based AC energy estimate per calendar month,
    scaled to that month's real day count (`calendar.monthrange`) - a
    genuine astronomical (pvlib solar-position) seasonal irradiance swing,
    with an approximate rainy-season cloud derate applied June-October (see
    RAINY_SEASON_EXTRA_CLOUD_ATTENUATION_PCT's own docstring for why that
    part is a documented assumption, not measured data). Same "flat single-
    day extrapolation" caveat as `estimate_annual_ac_energy_kwh` applies
    within each month - this is one step more granular (a real day per
    month, not one real day for the whole year), not a full day-by-day
    annual simulation.
    """
    year = year or datetime.now(dt_timezone.utc).year
    estimates = []
    for month in range(1, 13):
        days_in_month = calendar.monthrange(year, month)[1]
        idx, ssrd, temp = _representative_day_irradiance_temp(month, year=year)
        baseline = simulate_zone_baseline(zone_id, ssrd, temp, idx)
        is_rainy = month in RAINY_SEASON_MONTHS
        power = baseline.ac_power_kw
        if is_rainy:
            power = apply_scenario(power, ScenarioParams(extra_cloud_attenuation_pct=RAINY_SEASON_EXTRA_CLOUD_ATTENUATION_PCT))
        ac_energy_kwh = float(power.sum()) * days_in_month
        estimates.append(MonthlyEstimate(month=month, ac_energy_kwh=ac_energy_kwh, is_rainy_season=is_rainy))
    return estimates


@dataclass(frozen=True)
class LifecycleEstimate:
    year_1_ac_energy_kwh: float
    year_25_ac_energy_kwh: float
    year_25_pct_of_year_1: float
    lifetime_ac_energy_kwh: float
    degradation_pct_per_year_assumed: float


def lifecycle_ac_energy_estimate(
    year_1_ac_energy_kwh: float,
    degradation_pct_per_year: float = DEFAULT_DEGRADATION_PCT_PER_YEAR,
    years: int = LIFETIME_YEARS,
) -> LifecycleEstimate:
    """`year_1_ac_energy_kwh` degraded linearly year over year, reusing
    `what_if.apply_scenario`'s own validated degradation model (one call per
    year rather than a single vectorized call, since `apply_scenario`
    applies one uniform `years_since_commissioning` per call, not a
    different one per series element) - see DEFAULT_DEGRADATION_PCT_PER_YEAR's
    own docstring for why the rate itself is a documented assumption, not a
    site-specific measurement. Year 1 = 0 years since commissioning (no
    degradation yet); year 25 = 24 years since commissioning.
    """
    if year_1_ac_energy_kwh < 0:
        raise ValueError(f"year_1_ac_energy_kwh cannot be negative, got {year_1_ac_energy_kwh}")
    params = ScenarioParams(degradation_pct_per_year=degradation_pct_per_year)
    per_year = [
        float(apply_scenario(pd.Series([year_1_ac_energy_kwh]), params, years_since_commissioning=y - 1).iloc[0])
        for y in range(1, years + 1)
    ]
    return LifecycleEstimate(
        year_1_ac_energy_kwh=per_year[0],
        year_25_ac_energy_kwh=per_year[-1],
        year_25_pct_of_year_1=(per_year[-1] / per_year[0] * 100) if per_year[0] > 0 else 0.0,
        lifetime_ac_energy_kwh=sum(per_year),
        degradation_pct_per_year_assumed=degradation_pct_per_year,
    )
