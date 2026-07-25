"""Soiling & cleaning advisor: turns the stored air-quality + weather history
into "how dirty is the array right now, what is it costing, and when should it
be washed" (2026-07-25).

This is the data side of `nongfab_features.soiling_dynamics` (which holds the
pure model). Here we:
1. roll the hourly stores up to DAILY aggregates - mean PM10/dust, mean
   salt-spray index (from wind + humidity), and TOTAL rainfall per day, which is
   the resolution the Kimber-style accumulate/wash model works at;
2. run the model per zone, scaling the salt term by how exposed that zone is to
   sea spray;
3. publish the window's AVERAGE loss into `loss_model.set_measured_soiling_pct`,
   which is what replaces the old literature soiling placeholder everywhere
   (Energy Report losses breakdown, /financial, /simulate) - the user approved
   this replacement on 2026-07-25.

Honest-empty throughout: with no aerosol or no NWP history there is nothing to
assess, so `assess_zone` returns `available=False` and the loss model keeps its
documented literature default rather than being handed a fabricated number.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
from nongfab_features.soiling import salt_soiling_index
from nongfab_features.soiling_dynamics import (
    SoilingParams,
    daily_soiling_rate_pct,
    days_until_threshold,
    energy_lost_kwh,
    simulate_soiling,
)
from nongfab_forecast.local_store import RealDataStore
from nongfab_simulation.loss_model import MARINE_ZONE_IDS, set_measured_soiling_pct

from .settings_store import effective

logger = logging.getLogger(__name__)

ZONES = ("GIS", "ISB", "Jetty")

# How much of the open-sea salt load each zone actually sees. The Jetty array
# sits on the trestle out over the water, so it takes the full salt-spray load
# the wind/humidity index describes; GIS and ISB are set back inland behind the
# terminal structures. Documented exposure allowance (same footing as
# DEFAULT_EXTERNAL_SHADING_PCT), not a measured deposition ratio - there is no
# on-site salt-deposition survey.
MARINE_SALT_EXPOSURE = 1.0
INLAND_SALT_EXPOSURE = 0.45

# Soiling level at which a wash starts paying for itself on a plant this size.
# A planning trigger for the advisory readout, not a contractual threshold.
CLEANING_TRIGGER_PCT = 3.0

# How much history the assessment walks. 90 days covers a full seasonal swing
# either side of the monsoon onset while staying inside the 92-day cap the
# Open-Meteo air-quality backfill can reach.
ASSESSMENT_WINDOW_DAYS = 90


def salt_exposure(zone_id: str) -> float:
    """How much of the open-sea salt load this zone sees. Reads the user-settable
    values (see settings_registry), which default to the constants above."""
    if zone_id in MARINE_ZONE_IDS:
        return effective("soiling.salt_exposure_marine")
    return effective("soiling.salt_exposure_inland")


def cleaning_trigger_pct() -> float:
    return effective("soiling.cleaning_trigger_pct")


def assessment_window_days() -> int:
    return int(effective("windows.soiling_days"))


def soiling_params() -> SoilingParams:
    """The soiling model's coefficients as the user has them set. Passed
    explicitly into the pure model rather than mutating its module constants, so
    features/ stays free of global state."""
    return SoilingParams(
        pm10_reference_ug_m3=effective("soiling.pm10_reference_ug_m3"),
        pm10_rate_pct_per_day=effective("soiling.pm10_rate_pct_per_day"),
        salt_rate_pct_per_day=effective("soiling.salt_rate_pct_per_day"),
        dust_reference_ug_m3=effective("soiling.dust_reference_ug_m3"),
        dust_rate_pct_per_day=effective("soiling.dust_rate_pct_per_day"),
        max_loss_pct=effective("soiling.max_loss_pct"),
        rain_clean_threshold_mm=effective("soiling.rain_clean_threshold_mm"),
        rain_full_clean_mm=effective("soiling.rain_full_clean_mm"),
        residual_after_rain_pct=effective("soiling.residual_after_rain_pct"),
    )


@dataclass(frozen=True)
class DailyConditions:
    """One day of the aggregates the soiling model consumes."""

    day: pd.Timestamp
    pm10_ug_m3: float
    dust_ug_m3: float
    salt_index: float
    precip_mm: float


def daily_conditions(store: RealDataStore, window_days: int | None = None) -> list[DailyConditions]:
    """Daily PM10/dust/salt-index/rainfall for the last `window_days`.

    PM10 and dust come from aerosol_history (CAMS); the salt index is derived
    per hour from nwp_history's wind + humidity exactly as the forecast features
    do (so the two never disagree), then averaged; rainfall is SUMMED because a
    day's cleaning power is its total, not its mean. Days present in one store
    but not the other are kept with the missing side left at 0 rather than
    dropped - a gap in one feed shouldn't erase the day.
    """
    window_days = assessment_window_days() if window_days is None else window_days
    aero = store.aerosol_history_df()
    nwp = store.nwp_history_df()
    if len(aero) == 0 or len(nwp) == 0:
        return []

    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    aero = aero[aero["valid_time"] >= since].copy()
    nwp = nwp[nwp["valid_time"] >= since].copy()
    if len(aero) == 0 or len(nwp) == 0:
        return []

    aero["day"] = aero["valid_time"].dt.floor("D")
    aero_daily = aero.groupby("day")[[c for c in ("pm10", "dust") if c in aero.columns]].mean()

    nwp["salt_index"] = salt_soiling_index(
        nwp["wind10m_u_ms"].fillna(0.0).to_numpy(),
        nwp["wind10m_v_ms"].fillna(0.0).to_numpy(),
        nwp["relative_humidity_pct"].fillna(0.0).to_numpy(),
    )
    nwp["day"] = nwp["valid_time"].dt.floor("D")
    # An hour can appear more than once (several issue times for the same
    # valid_time); collapse to one row per hour first so a heavily-reforecast
    # hour doesn't get counted repeatedly in the day's rainfall total.
    hourly = nwp.groupby(["day", "valid_time"]).agg(salt_index=("salt_index", "mean"), precip_mm=("precip_mm", "mean"))
    nwp_daily = hourly.groupby("day").agg(salt_index=("salt_index", "mean"), precip_mm=("precip_mm", "sum"))

    joined = aero_daily.join(nwp_daily, how="outer").sort_index().fillna(0.0)
    return [
        DailyConditions(
            day=day,
            pm10_ug_m3=float(row.get("pm10", 0.0)),
            dust_ug_m3=float(row.get("dust", 0.0)),
            salt_index=float(row.get("salt_index", 0.0)),
            precip_mm=float(row.get("precip_mm", 0.0)),
        )
        for day, row in joined.iterrows()
    ]


@dataclass(frozen=True)
class SoilingAssessment:
    """Everything the /soiling route and the advisor panel need."""

    available: bool
    zone: str
    days_assessed: int
    current_loss_pct: float
    average_loss_pct: float
    current_daily_rate_pct: float
    days_since_cleaning_rain: int | None
    cleaning_events: int
    days_until_trigger: int | None
    cleaning_trigger_pct: float
    max_loss_pct: float
    # Cost of the CURRENT soiling level, projected over a year at today's
    # dirtiness - "what leaving it like this costs", not a measured loss.
    annual_energy_lost_kwh: float | None
    annual_cost_lost_thb: float | None
    series_days: tuple[str, ...]
    series_loss_pct: tuple[float, ...]


def assess_zone(
    store: RealDataStore,
    zone_id: str,
    annual_clean_energy_kwh: float | None = None,
    tariff_thb_per_kwh: float | None = None,
    window_days: int | None = None,
) -> SoilingAssessment:
    """Run the soiling model for one zone over the stored history.

    `annual_clean_energy_kwh` / `tariff_thb_per_kwh` are optional: given them,
    the assessment also reports what the current soiling level costs per year.
    Without them those two fields stay None (no guessed tariff).
    """
    window_days = assessment_window_days() if window_days is None else window_days
    params = soiling_params()
    trigger = cleaning_trigger_pct()
    days = daily_conditions(store, window_days)
    if not days:
        return SoilingAssessment(
            available=False,
            zone=zone_id,
            days_assessed=0,
            current_loss_pct=0.0,
            average_loss_pct=0.0,
            current_daily_rate_pct=0.0,
            days_since_cleaning_rain=None,
            cleaning_events=0,
            days_until_trigger=None,
            cleaning_trigger_pct=trigger,
            max_loss_pct=params.max_loss_pct,
            annual_energy_lost_kwh=None,
            annual_cost_lost_thb=None,
            series_days=(),
            series_loss_pct=(),
        )

    exposure = salt_exposure(zone_id)
    pm10 = [d.pm10_ug_m3 for d in days]
    dust = [d.dust_ug_m3 for d in days]
    salt = [d.salt_index * exposure for d in days]
    rain = [d.precip_mm for d in days]

    timeline = simulate_soiling(pm10, salt, rain, dust_ug_m3=dust, params=params)
    # Today's accumulation rate, from the most recent day's own conditions - what
    # the "days until a wash pays" projection extrapolates on.
    rate_today = float(daily_soiling_rate_pct(pm10[-1], salt[-1], dust[-1], params=params))

    energy_lost = None
    cost_lost = None
    if annual_clean_energy_kwh is not None and annual_clean_energy_kwh > 0:
        energy_lost = energy_lost_kwh(annual_clean_energy_kwh, timeline.current_loss_pct)
        if tariff_thb_per_kwh is not None and tariff_thb_per_kwh > 0:
            cost_lost = energy_lost * tariff_thb_per_kwh

    return SoilingAssessment(
        available=True,
        zone=zone_id,
        days_assessed=len(days),
        current_loss_pct=timeline.current_loss_pct,
        average_loss_pct=timeline.average_loss_pct,
        current_daily_rate_pct=rate_today,
        days_since_cleaning_rain=timeline.days_since_cleaning_rain,
        cleaning_events=timeline.cleaning_events,
        days_until_trigger=days_until_threshold(timeline.current_loss_pct, rate_today, trigger),
        cleaning_trigger_pct=trigger,
        max_loss_pct=params.max_loss_pct,
        annual_energy_lost_kwh=energy_lost,
        annual_cost_lost_thb=cost_lost,
        series_days=tuple(d.day.date().isoformat() for d in days),
        series_loss_pct=timeline.loss_pct_series,
    )


def refresh_measured_soiling(store: RealDataStore) -> dict[str, float]:
    """Recompute each zone's measured annual-average soiling and publish it to
    the loss model, replacing the literature placeholder. Returns what was
    published ({} when the history can't support an assessment yet, in which
    case the literature defaults deliberately stay in force).

    Called after ingestion refreshes rather than per request: it walks up to 90
    days of history per zone, which is far too much work to redo on every
    /energy-report call.
    """
    published: dict[str, float] = {}
    for zone in ZONES:
        assessment = assess_zone(store, zone)
        if not assessment.available:
            continue
        set_measured_soiling_pct(zone, assessment.average_loss_pct)
        published[zone] = assessment.average_loss_pct
    if published:
        logger.info("measured soiling published: %s", {z: round(p, 2) for z, p in published.items()})
    return published
