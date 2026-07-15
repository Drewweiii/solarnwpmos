"""High-level orchestration tying Modules 3/4/5 together: irradiance/temp ->
PV conversion (Module 4) -> loss model + DC/AC clipping (Module 5) -> one
zone's baseline AC power series. Extracted from api.py so any other caller
(a future Module 6 endpoint, a batch precompute job) gets the same pipeline
for free instead of re-deriving the fetch/convert/derate/clip chain by hand.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from nongfab_common.assets import Zone, load_assets
from nongfab_forecast.pv_conversion import STC_TEMP_C, default_params_from_capacity, predict_power_kw

from .loss_model import LossFactors, apply_losses, clip_to_inverter_capacity, default_loss_factors, loss_breakdown_summary

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


def loss_breakdown_with_temperature(baseline: ZoneBaseline, irradiance_w_m2: np.ndarray | pd.Series, temp_c: np.ndarray | pd.Series) -> dict[str, float]:
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
