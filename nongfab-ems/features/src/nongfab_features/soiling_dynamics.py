"""Time-dependent soiling: accumulation between rain events, and the cleaning
those rain events do (2026-07-25).

`soiling.py` next door gives an INSTANTANEOUS salt-spray index - useful as a
model feature, but it says nothing about how dirty the glass actually *is*
right now, which is a memory of days of deposition minus whatever the last
rain washed off. This module adds that memory, and it is what replaced the
`loss_model.DEFAULT_SOILING_PCT_*` literature placeholders with a figure
derived from this site's own measured air quality and rainfall (the user
approved the replacement on 2026-07-25).

Method - a Kimber-style soiling model with a data-driven deposition rate:
- Kimber et al. (2007) is the standard engineering treatment: soiling loss
  grows roughly LINEARLY through a dry spell and a rain event above a
  threshold restores the array to (near) clean. That shape is what makes
  soiling a time series rather than a constant derate.
- Coello & Boyle (2019), "Simple Model for Predicting Time Series Soiling of
  Photovoltaic Panels" (IEEE J. Photovoltaics), is the reason the rate here
  is not a constant: they show the daily soiling rate scales with the ambient
  PM10 mass concentration, which is exactly the variable the CAMS ingestion
  already stores per hour (see api/openmeteo_aq.py).
- The marine salt term on top is this site's own known-worse driver (the
  architecture doc's "Jetty soiling/corrosion higher - ละอองเกลือ" callout),
  scaled by the salt_soiling_index from soiling.py.

Honesty about what is and isn't measured: the RATE COEFFICIENTS below are
literature-calibrated, not fitted to Nong Fab (no on-site soiling
measurement or cleaning log exists - that stays a known gap). What is real
and site-specific is everything they are multiplied by: measured PM10/dust,
measured wind/humidity, and measured rainfall. So this is "a literature model
driven by our own data", which is a strictly better footing than the previous
"a literature constant", and it is labelled that way everywhere it surfaces.

Pure and dependency-light (numpy only), like the rest of features/.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Reference PM10 (ug/m3) at which the PM-driven part of the deposition rate
# equals PM10_SOILING_RATE_PCT_PER_DAY. 50 ug/m3 is a moderately hazy day and
# roughly Thailand's own 24h PM10 standard region - a mid-scale anchor, not a
# threshold with any regulatory meaning here.
PM10_REFERENCE_UG_M3 = 50.0
# Daily soiling loss added at the reference PM10, dry, with no salt. Sits inside
# the 0.1-0.3 %/day band Kimber/Coello report for non-desert sites.
PM10_SOILING_RATE_PCT_PER_DAY = 0.20
# Extra daily soiling at a fully saturated salt index (index = 1.0). Marine
# salt-spray deposition is the site's documented aggravating factor, so it is
# allowed to roughly double the dirty-day rate at full scale.
SALT_SOILING_RATE_PCT_PER_DAY = 0.18
# Mineral dust is already largely inside PM10, so it only gets a small
# additional term for the coarse fraction PM10 under-reports.
DUST_REFERENCE_UG_M3 = 20.0
DUST_SOILING_RATE_PCT_PER_DAY = 0.05

# Soiling saturates: once the glass is coated, more deposition adds little
# further loss (Kimber's own model caps it, and coastal/tropical arrays are
# rain-washed long before an unbounded ramp would be physical).
MAX_SOILING_LOSS_PCT = 12.0

# Rain that actually cleans. Kimber uses 0.254 mm (0.01 in) as the threshold for
# a "cleaning" event; a heavier event cleans more completely, so the effect is
# graded between the two thresholds below rather than being all-or-nothing.
RAIN_CLEAN_THRESHOLD_MM = 0.25
RAIN_FULL_CLEAN_MM = 5.0
# Even a downpour leaves a residue (and rain itself can deposit dust), so a
# cleaning event never returns the array to a perfect 0%.
RESIDUAL_AFTER_RAIN_PCT = 0.3


@dataclass(frozen=True)
class SoilingParams:
    """The model's coefficients, overridable per call (2026-07-25).

    The module constants above stay the defaults, but the user asked to be able
    to change these from the web UI, so every function that reads a coefficient
    takes them as a parameter instead. Passed EXPLICITLY rather than mutated
    globally: this package is pure computation shared by training and serving, and
    a mutable module-level config would make two callers able to silently change
    each other's results.
    """

    pm10_reference_ug_m3: float = PM10_REFERENCE_UG_M3
    pm10_rate_pct_per_day: float = PM10_SOILING_RATE_PCT_PER_DAY
    salt_rate_pct_per_day: float = SALT_SOILING_RATE_PCT_PER_DAY
    dust_reference_ug_m3: float = DUST_REFERENCE_UG_M3
    dust_rate_pct_per_day: float = DUST_SOILING_RATE_PCT_PER_DAY
    max_loss_pct: float = MAX_SOILING_LOSS_PCT
    rain_clean_threshold_mm: float = RAIN_CLEAN_THRESHOLD_MM
    rain_full_clean_mm: float = RAIN_FULL_CLEAN_MM
    residual_after_rain_pct: float = RESIDUAL_AFTER_RAIN_PCT


DEFAULT_PARAMS = SoilingParams()


def daily_soiling_rate_pct(pm10_ug_m3, salt_index, dust_ug_m3=0.0, params: SoilingParams = DEFAULT_PARAMS):
    """Percent of output lost per DRY day at these conditions. Vectorized.

    Missing/negative inputs are treated as zero contribution rather than
    raising: a gap in the aerosol feed must not silently inflate the estimate.
    """
    pm10 = np.clip(np.nan_to_num(np.asarray(pm10_ug_m3, dtype=float)), 0.0, None)
    salt = np.clip(np.nan_to_num(np.asarray(salt_index, dtype=float)), 0.0, 1.0)
    dust = np.clip(np.nan_to_num(np.asarray(dust_ug_m3, dtype=float)), 0.0, None)
    return (
        params.pm10_rate_pct_per_day * (pm10 / params.pm10_reference_ug_m3)
        + params.salt_rate_pct_per_day * salt
        + params.dust_rate_pct_per_day * (dust / params.dust_reference_ug_m3)
    )


def rain_cleaning_fraction(precip_mm, params: SoilingParams = DEFAULT_PARAMS):
    """How much of the accumulated soiling a day's rainfall removes, 0..1.

    Below RAIN_CLEAN_THRESHOLD_MM nothing is washed off (drizzle can even make
    it worse by cementing dust, which this model does not attempt to represent);
    at RAIN_FULL_CLEAN_MM and above the wash is complete. Graded linearly in
    between - a documented simplification of Kimber's binary event, so a day of
    light-but-real rain doesn't read as a full clean.
    """
    mm = np.clip(np.nan_to_num(np.asarray(precip_mm, dtype=float)), 0.0, None)
    span = max(params.rain_full_clean_mm - params.rain_clean_threshold_mm, 1e-6)
    return np.clip((mm - params.rain_clean_threshold_mm) / span, 0.0, 1.0)


@dataclass(frozen=True)
class SoilingTimeline:
    """The simulated day-by-day soiling state.

    loss_pct_series: soiling loss (%) at the END of each input day.
    current_loss_pct: the last day's value - "how dirty the array is now".
    average_loss_pct: mean over the whole window - the figure that replaces the
        annual-average soiling placeholder in the loss model.
    days_since_cleaning_rain: dry days since the last rain that actually
        cleaned (None when no cleaning rain occurred anywhere in the window, so
        callers can say "not seen in this window" instead of implying zero).
    cleaning_events: how many cleaning rains the window contained.
    """

    loss_pct_series: tuple[float, ...]
    current_loss_pct: float
    average_loss_pct: float
    days_since_cleaning_rain: int | None
    cleaning_events: int


def simulate_soiling(
    pm10_ug_m3,
    salt_index,
    precip_mm,
    dust_ug_m3=None,
    initial_loss_pct: float = 0.0,
    params: SoilingParams = DEFAULT_PARAMS,
) -> SoilingTimeline:
    """Walk a series of DAILY aggregates forward through accumulate-then-wash.

    All four inputs are per-day sequences of the same length (daily mean PM10 /
    salt index / dust, daily TOTAL rainfall). Returns the timeline plus the
    summary figures the API surfaces. Empty input -> an all-zero timeline with
    `days_since_cleaning_rain=None`, never a fabricated value.
    """
    pm10 = np.atleast_1d(np.asarray(pm10_ug_m3, dtype=float))
    salt = np.atleast_1d(np.asarray(salt_index, dtype=float))
    rain = np.atleast_1d(np.asarray(precip_mm, dtype=float))
    dust = np.zeros_like(pm10) if dust_ug_m3 is None else np.atleast_1d(np.asarray(dust_ug_m3, dtype=float))
    n = min(len(pm10), len(salt), len(rain), len(dust))
    if n == 0:
        return SoilingTimeline((), 0.0, 0.0, None, 0)

    rates = daily_soiling_rate_pct(pm10[:n], salt[:n], dust[:n], params=params)
    wash = rain_cleaning_fraction(rain[:n], params=params)

    loss = float(initial_loss_pct)
    series: list[float] = []
    days_since: int | None = None
    events = 0
    for i in range(n):
        # Accumulate the day's deposition first, then apply that day's rain -
        # a day that both soils and rains ends up clean, which is the physical
        # ordering (the rain falls on the dust that arrived with it).
        loss = min(loss + float(rates[i]), params.max_loss_pct)
        w = float(wash[i])
        if w > 0:
            cleaned = loss * (1 - w) + params.residual_after_rain_pct * w
            loss = min(loss, cleaned)
            events += 1
            days_since = 0
        elif days_since is not None:
            days_since += 1
        series.append(loss)

    return SoilingTimeline(
        loss_pct_series=tuple(series),
        current_loss_pct=series[-1],
        average_loss_pct=float(np.mean(series)),
        days_since_cleaning_rain=days_since,
        cleaning_events=events,
    )


def days_until_threshold(
    current_loss_pct: float,
    daily_rate_pct: float,
    threshold_pct: float,
) -> int | None:
    """Dry days until soiling would reach `threshold_pct` - the "you should
    plan a wash around then" number. None when it is already past the threshold
    or the rate is non-positive (nothing to project)."""
    if daily_rate_pct <= 0:
        return None
    remaining = threshold_pct - current_loss_pct
    if remaining <= 0:
        return None
    return int(np.ceil(remaining / daily_rate_pct))


def energy_lost_kwh(clean_energy_kwh: float, soiling_loss_pct: float) -> float:
    """Energy (kWh) given up to soiling over a period whose clean-glass output
    would have been `clean_energy_kwh`. Straight proportional loss, matching how
    `loss_model.combined_derate` treats the soiling derate."""
    pct = max(0.0, min(100.0, soiling_loss_pct))
    return clean_energy_kwh * pct / 100
