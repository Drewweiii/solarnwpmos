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

**Checked for a Thailand/marine-specific replacement (2026-07-18), kept the
generic defaults**: the user asked whether a better-cited, region-specific
figure exists to replace the generic NREL PVWatts numbers below. A
literature search turned up real Thailand soiling/degradation studies and
real coastal/marine soiling studies, but none of them is a clean, directly-
substitutable "annual soiling loss %" for *this* site's actual conditions
(a Thai monsoon-climate, land-and-pier-over-water installation, not
comparable to the specific sites those papers measured):
- Thai composite-climate rooftop PV studies report daily soiling reduction
  of ~4% (rainy season) up to ~20% (dry season) - a *daily instantaneous*
  figure, not an annual-average loss %, and not derived from a utility-
  scale ground-mount or pier-mounted array like GIS/ISB/Jetty.
- Coastal/marine soiling studies exist (e.g. Atacama Desert coastline,
  offshore floating-PV salt-spray lab experiments), but those sites are
  climatically nothing like tropical, rain-washed Thailand (the Atacama is
  one of the driest deserts on Earth - dust never gets rinsed off the way
  Thailand's monsoon season does it for free) - substituting a number from
  either would trade one placeholder for a *worse*, false-precision one
  (implying site-specific rigor a mismatched source can't actually provide).

Verdict: no literature source found clears the bar of "clearly better than
the current generic default for this specific site" - keeping
`DEFAULT_SOILING_PCT_MARINE`/`_LAND` as documented industry-generic
placeholders remains the more honest choice than swapping in a
context-mismatched "real" number. Revisit if the user has a specific paper
in mind, or once real O&M cleaning/inspection data exists for Nong Fab
itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from nongfab_features.shading import annual_shading_loss_pct

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
#
# DEFAULT_SHADING_PCT is only the fallback for a LossFactors built without a
# zone (direct construction / tests). The zone-aware path
# (default_loss_factors) instead computes the *inter-row self-shading* part
# from the array's real modelled geometry
# (nongfab_features.shading.annual_shading_loss_pct, 2026-07-22 roadmap item
# 3) and adds DEFAULT_EXTERNAL_SHADING_PCT on top of it - see
# default_loss_factors.
DEFAULT_SHADING_PCT = 3.0
# Allowance for external-obstacle shading (neighbouring structures, terrain,
# vegetation) that the geometric inter-row model does NOT capture - there is no
# site obstacle survey in config/assets.yaml, so this stays a documented
# literature allowance, not a measured figure. Added on top of the
# geometry-derived inter-row loss so a well-pitched array (whose real inter-row
# loss can be well under 1%) still carries a realistic total shading derate.
# Replace with a surveyed figure once a real obstacle survey exists.
DEFAULT_EXTERNAL_SHADING_PCT = 2.0
DEFAULT_MISMATCH_PCT = 2.0
DEFAULT_DC_WIRING_PCT = 2.0
DEFAULT_CONNECTIONS_PCT = 0.5
DEFAULT_AVAILABILITY_PCT = 3.0  # grid/inverter downtime allowance

MARINE_ZONE_IDS = {"Jetty"}


# Where a LossFactors' soiling figure came from, so every surface that reports
# it can say so instead of leaving the reader to guess.
SOILING_SOURCE_LITERATURE = "literature-default"
SOILING_SOURCE_MEASURED = "measured-airquality-rainfall"


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
    soiling_source: str = SOILING_SOURCE_LITERATURE


# --- Measured soiling override (2026-07-25) ---------------------------------
# The user asked for the data-driven soiling estimate to REPLACE the literature
# placeholders, not just sit beside them. The estimate needs the real
# air-quality + rainfall history, which lives in a store this package has no
# handle on (simulation/ is pure computation; the store is owned by the API
# process), so the API injects it here once ingestion has data - see
# api/soiling_service.refresh_measured_soiling. Until it does, or if the feed
# goes empty, `default_loss_factors` falls back to the documented literature
# constants and says so via `soiling_source`, so nothing ever silently reports a
# measured-looking number it doesn't have.
_measured_soiling_pct: dict[str, float] = {}


def set_measured_soiling_pct(zone_id: str, soiling_pct: float) -> None:
    """Publish a measured annual-average soiling loss (%) for one zone."""
    if not (0 <= soiling_pct <= 100):
        raise ValueError(f"soiling_pct must be in [0, 100], got {soiling_pct}")
    _measured_soiling_pct[zone_id] = float(soiling_pct)


def clear_measured_soiling_pct() -> None:
    """Drop every published measurement (used by tests, and by the API if the
    aerosol/precipitation feed stops being trustworthy)."""
    _measured_soiling_pct.clear()


def measured_soiling_pct(zone_id: str) -> float | None:
    """The published measured soiling for a zone, or None when there is none."""
    return _measured_soiling_pct.get(zone_id)


def default_loss_factors(zone_id: str) -> LossFactors:
    """Zone-aware defaults.

    Soiling prefers the MEASURED estimate published by the API from this site's
    own PM10/dust/salt-index and rainfall history (2026-07-25 - see
    features/soiling_dynamics.py for the Kimber/Coello-style model). When none
    has been published it falls back to the literature constants, where Jetty
    (marine trestle) gets the higher figure per the architecture doc's own
    callout ("Jetty soiling/corrosion higher - ละอองเกลือ") and GIS/ISB (land)
    get the PVWatts land default. `soiling_source` records which one it is.

    Shading is likewise not the flat DEFAULT_SHADING_PCT literature default: it
    is the array's real geometry-derived inter-row self-shading loss
    (annual_shading_loss_pct, energy-weighted over a full year's sun path) plus
    DEFAULT_EXTERNAL_SHADING_PCT as an allowance for unmodelled external-obstacle
    shading (no site obstacle survey exists). 2026-07-22 roadmap item 3.
    """
    measured = measured_soiling_pct(zone_id)
    if measured is None:
        soiling = DEFAULT_SOILING_PCT_MARINE if zone_id in MARINE_ZONE_IDS else DEFAULT_SOILING_PCT_LAND
        source = SOILING_SOURCE_LITERATURE
    else:
        soiling = measured
        source = SOILING_SOURCE_MEASURED
    shading = annual_shading_loss_pct(zone_id) + DEFAULT_EXTERNAL_SHADING_PCT
    return LossFactors(soiling_pct=soiling, shading_pct=shading, soiling_source=source)


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
