"""PVWatts-style multiplicative loss model: soiling, shading, mismatch, DC
wiring, connections, availability, plus inverter efficiency and DC/AC
clipping - combined into a performance ratio (PR) per zone.

Temperature derate is deliberately NOT part of this module - it's already
handled by Module 4's `pv_conversion.predict_power_kw` (temperature
coefficient applied there, against real POA irradiance + ambient temp), so
this module's inputs are DC power *after* temperature derate, and this
module's job is everything else in the PVWatts loss chain.

Soiling defaults are zone-aware (Jetty/marine higher than GIS/ISB/land) per
literature typical values, NOT real O&M measurement (none exists yet - see
README "Known gaps"). Confirmed with the user (2026-07-14): use literature/
standard values, not fabricated site-specific numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# NREL PVWatts default is 2% annual soiling for a "moderate" (non-desert,
# non-coastal) climate; literature on coastal/marine PV commonly cites
# 5-8% due to salt-spray deposition requiring more frequent cleaning than a
# land installation gets. GIS/ISB use the PVWatts default; Jetty uses the
# midpoint of the marine range. All three are placeholders pending real O&M
# cleaning/inspection data, not measurements.
DEFAULT_SOILING_PCT_LAND = 2.5
DEFAULT_SOILING_PCT_MARINE = 6.0

# Typical PVWatts-style default derates for the remaining loss categories -
# generic industry defaults (NREL PVWatts documentation), not site-specific.
DEFAULT_SHADING_PCT = 3.0
DEFAULT_MISMATCH_PCT = 2.0
DEFAULT_DC_WIRING_PCT = 2.0
DEFAULT_CONNECTIONS_PCT = 0.5
DEFAULT_AVAILABILITY_PCT = 3.0  # grid/inverter downtime allowance

MARINE_ZONE_IDS = {"Jetty"}


@dataclass(frozen=True)
class LossFactors:
    """Each field is a fractional loss in percent (2.0 means 2% lost, i.e. a
    0.98 multiplier) - not yet combined into a single derate; see combined_derate().
    """

    soiling_pct: float
    shading_pct: float = DEFAULT_SHADING_PCT
    mismatch_pct: float = DEFAULT_MISMATCH_PCT
    dc_wiring_pct: float = DEFAULT_DC_WIRING_PCT
    connections_pct: float = DEFAULT_CONNECTIONS_PCT
    availability_pct: float = DEFAULT_AVAILABILITY_PCT


def default_loss_factors(zone_id: str) -> LossFactors:
    """Zone-aware defaults - Jetty (marine trestle) gets the higher soiling
    figure per the architecture doc's own callout ("Jetty soiling/corrosion
    higher - ละอองเกลือ"); GIS/ISB (land) get the PVWatts land default.
    """
    soiling = DEFAULT_SOILING_PCT_MARINE if zone_id in MARINE_ZONE_IDS else DEFAULT_SOILING_PCT_LAND
    return LossFactors(soiling_pct=soiling)


def combined_derate(factors: LossFactors) -> float:
    """Multiplicative (not additive) combination, the standard PVWatts
    convention - losses compound rather than simply summing, since each
    stage's loss applies to what's already survived the previous stages.
    Returns a fraction in (0, 1]: multiply DC power by this to get derated DC power.
    """
    pct_fields = (
        factors.soiling_pct, factors.shading_pct, factors.mismatch_pct,
        factors.dc_wiring_pct, factors.connections_pct, factors.availability_pct,
    )
    derate = 1.0
    for pct in pct_fields:
        if not (0 <= pct <= 100):
            raise ValueError(f"loss percentage must be in [0, 100], got {pct}")
        derate *= 1 - pct / 100
    return derate


def apply_losses(dc_power_kw: pd.Series, factors: LossFactors, inverter_efficiency_pct: float) -> pd.Series:
    """DC power (already temperature-derated, e.g. from
    `nongfab_forecast.pv_conversion.predict_power_kw`) -> AC power, applying
    the combined PVWatts-style derate then inverter conversion efficiency.
    Does NOT clip to inverter AC capacity - see `clip_to_inverter_capacity()`.
    """
    if not (0 < inverter_efficiency_pct <= 100):
        raise ValueError(f"inverter_efficiency_pct must be in (0, 100], got {inverter_efficiency_pct}")
    return dc_power_kw * combined_derate(factors) * (inverter_efficiency_pct / 100)


def clip_to_inverter_capacity(ac_power_kw: pd.Series, inverter_ac_capacity_kw: float) -> pd.Series:
    """Models inverter clipping for an oversized DC/AC ratio (e.g. GIS's 1.20 -
    "expect midday clipping" per config/assets.yaml's own note): AC output can
    never exceed the inverter's rated AC capacity, however much DC power is
    theoretically available.
    """
    if inverter_ac_capacity_kw <= 0:
        raise ValueError("inverter_ac_capacity_kw must be positive")
    return ac_power_kw.clip(upper=inverter_ac_capacity_kw)


def performance_ratio(actual_ac_energy_kwh: float, poa_irradiance_kwh_per_m2: float, capacity_kwp: float) -> float:
    """Standard PR = actual energy / (reference yield x installed capacity),
    where reference yield = plane-of-array irradiation / 1000 W/m^2 (STC).
    A PR of 1.0 is the theoretical ceiling (no losses at all); real systems
    typically land in the 0.75-0.85 range.
    """
    if poa_irradiance_kwh_per_m2 <= 0 or capacity_kwp <= 0:
        raise ValueError("poa_irradiance_kwh_per_m2 and capacity_kwp must both be positive")
    reference_yield_kwh_per_kwp = poa_irradiance_kwh_per_m2  # 1000 W/m^2 STC cancels with kWp's own W/1000 definition
    reference_energy_kwh = reference_yield_kwh_per_kwp * capacity_kwp
    return actual_ac_energy_kwh / reference_energy_kwh


def annual_specific_yield(annual_ac_energy_kwh: float, capacity_kwp: float) -> float:
    """kWh/kWp/year - lets zones of different sizes be compared on equal footing."""
    if capacity_kwp <= 0:
        raise ValueError("capacity_kwp must be positive")
    return annual_ac_energy_kwh / capacity_kwp


def loss_breakdown_summary(factors: LossFactors, inverter_efficiency_pct: float) -> dict[str, float]:
    """Individual loss percentages plus the combined system loss (1 - overall
    derate, as a percentage) - the "losses breakdown" table Feature D's Energy
    Report calls for.
    """
    overall_derate = combined_derate(factors) * (inverter_efficiency_pct / 100)
    return {
        "soiling_pct": factors.soiling_pct,
        "shading_pct": factors.shading_pct,
        "mismatch_pct": factors.mismatch_pct,
        "dc_wiring_pct": factors.dc_wiring_pct,
        "connections_pct": factors.connections_pct,
        "availability_pct": factors.availability_pct,
        "inverter_loss_pct": 100 - inverter_efficiency_pct,
        "total_system_loss_pct": (1 - overall_derate) * 100,
    }
