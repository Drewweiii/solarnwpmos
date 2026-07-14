"""Linear PV conversion model (P = β·I + γ·T + intercept) per the architecture
doc's "MOSKF" reference - irradiance/temperature -> AC power, per zone/sub-array.

Two ways to get parameters:
- `fit_pv_conversion_model()`: ordinary least squares against real (I, T, P)
  history - the intended path once Module 1/2 have accumulated enough of it.
- `default_params_from_capacity()`: a physically-motivated fallback derived
  from the zone's own installed capacity (config/assets.yaml) and a typical
  module temperature coefficient, for when no regression history exists yet
  (today - see README "Known gaps").
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Trina Vertex N TSM-NEG21C.20 (the Jetty module, per config/assets.yaml) is an
# N-type i-TOPCon panel; -0.30%/degC is a typical power temperature coefficient
# for that cell technology. NOT sourced from the actual datasheet (config/assets.yaml
# doesn't carry one) - a documented approximation, not a measured constant.
DEFAULT_TEMP_COEFF_PCT_PER_C = -0.30
STC_IRRADIANCE_W_M2 = 1000.0
STC_TEMP_C = 25.0


@dataclass(frozen=True)
class PVConversionParams:
    """P_kw = beta_kw_per_wm2 * irradiance_w_m2 + gamma_kw_per_c * temp_c + intercept_kw"""

    beta_kw_per_wm2: float
    gamma_kw_per_c: float
    intercept_kw: float


def default_params_from_capacity(capacity_kwp: float, temp_coeff_pct_per_c: float = DEFAULT_TEMP_COEFF_PCT_PER_C) -> PVConversionParams:
    """A reasonable starting point with no regression history: at STC
    (1000 W/m^2, 25degC) output equals the rated capacity; power scales
    linearly with irradiance and derates linearly with temperature above
    STC_TEMP_C at the module's temperature coefficient.
    """
    if capacity_kwp <= 0:
        raise ValueError("capacity_kwp must be positive")

    beta = capacity_kwp / STC_IRRADIANCE_W_M2
    gamma = capacity_kwp * (temp_coeff_pct_per_c / 100.0)
    # intercept absorbs the "-gamma*STC_TEMP_C" term so P(1000, 25) == capacity_kwp exactly
    intercept = -gamma * STC_TEMP_C
    return PVConversionParams(beta_kw_per_wm2=beta, gamma_kw_per_c=gamma, intercept_kw=intercept)


def fit_pv_conversion_model(irradiance_w_m2: pd.Series, temp_c: pd.Series, power_kw: pd.Series) -> PVConversionParams:
    """Ordinary least squares fit of P = beta*I + gamma*T + intercept against
    real (irradiance, temperature, power) history. Raises if fewer than 3
    valid (non-NaN) rows remain - underdetermined otherwise.
    """
    df = pd.DataFrame({"I": irradiance_w_m2, "T": temp_c, "P": power_kw}).dropna()
    if len(df) < 3:
        raise ValueError(f"need at least 3 valid (I, T, P) rows to fit, got {len(df)}")

    design = np.column_stack([df["I"].to_numpy(), df["T"].to_numpy(), np.ones(len(df))])
    (beta, gamma, intercept), *_ = np.linalg.lstsq(design, df["P"].to_numpy(), rcond=None)
    return PVConversionParams(beta_kw_per_wm2=float(beta), gamma_kw_per_c=float(gamma), intercept_kw=float(intercept))


def predict_power_kw(irradiance_w_m2: pd.Series | np.ndarray | float, temp_c: pd.Series | np.ndarray | float, params: PVConversionParams):
    """Vectorized: accepts scalars, numpy arrays, or pandas Series. Clipped at
    0 (a fitted model can predict small negative power at night-time zero
    irradiance due to the intercept term, which is not physical).
    """
    power = params.beta_kw_per_wm2 * irradiance_w_m2 + params.gamma_kw_per_c * temp_c + params.intercept_kw
    if isinstance(power, pd.Series):
        return power.clip(lower=0)
    return np.clip(power, 0, None)


def nong_fab_zone_capacities_kwp() -> dict[str, float]:
    """{zone_id: dc_capacity_kwp} for every zone in config/assets.yaml - the
    single source of truth other modules should use too, not hardcoded duplicates.
    """
    from nongfab_common.assets import load_assets

    registry = load_assets()
    return {zone.id: zone.dc_capacity_kwp for zone in registry.zones}
