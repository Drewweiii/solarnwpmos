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
from nongfab_forecast.pv_conversion import default_params_from_capacity, predict_power_kw

from .loss_model import LossFactors, apply_losses, clip_to_inverter_capacity, default_loss_factors, loss_breakdown_summary

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
