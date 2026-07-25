"""Covers the time-dependent soiling model (2026-07-25) - accumulation between
rain events, the graded rain wash, and the summary figures the API surfaces."""

from __future__ import annotations

import numpy as np

from nongfab_features.soiling_dynamics import (
    MAX_SOILING_LOSS_PCT,
    PM10_REFERENCE_UG_M3,
    PM10_SOILING_RATE_PCT_PER_DAY,
    RAIN_CLEAN_THRESHOLD_MM,
    RAIN_FULL_CLEAN_MM,
    daily_soiling_rate_pct,
    days_until_threshold,
    energy_lost_kwh,
    rain_cleaning_fraction,
    simulate_soiling,
)


def test_rate_scales_with_pm10_and_hits_the_literature_anchor():
    # At the reference PM10 with no salt/dust the rate is exactly the anchor.
    assert daily_soiling_rate_pct(PM10_REFERENCE_UG_M3, 0.0) == PM10_SOILING_RATE_PCT_PER_DAY
    # Twice the PM10 -> twice that part of the rate (Coello & Boyle scaling).
    assert daily_soiling_rate_pct(2 * PM10_REFERENCE_UG_M3, 0.0) == 2 * PM10_SOILING_RATE_PCT_PER_DAY
    # Clean air, no salt -> nothing accumulates.
    assert daily_soiling_rate_pct(0.0, 0.0) == 0.0


def test_salt_index_adds_on_top_and_is_capped_at_one():
    base = daily_soiling_rate_pct(PM10_REFERENCE_UG_M3, 0.0)
    salty = daily_soiling_rate_pct(PM10_REFERENCE_UG_M3, 1.0)
    assert salty > base
    # An out-of-range index must not run away - it clamps at the full-scale term.
    assert daily_soiling_rate_pct(PM10_REFERENCE_UG_M3, 5.0) == salty


def test_rate_treats_missing_inputs_as_no_contribution():
    assert daily_soiling_rate_pct(np.nan, np.nan) == 0.0
    assert daily_soiling_rate_pct(-10.0, -1.0) == 0.0


def test_rain_cleaning_is_graded_between_the_two_thresholds():
    assert rain_cleaning_fraction(0.0) == 0.0
    assert rain_cleaning_fraction(RAIN_CLEAN_THRESHOLD_MM) == 0.0  # drizzle doesn't clean
    assert rain_cleaning_fraction(RAIN_FULL_CLEAN_MM) == 1.0
    assert rain_cleaning_fraction(100.0) == 1.0
    mid = rain_cleaning_fraction((RAIN_CLEAN_THRESHOLD_MM + RAIN_FULL_CLEAN_MM) / 2)
    assert 0.4 < mid < 0.6


def test_soiling_accumulates_through_a_dry_spell():
    days = 10
    t = simulate_soiling([PM10_REFERENCE_UG_M3] * days, [0.0] * days, [0.0] * days)
    assert len(t.loss_pct_series) == days
    # Strictly increasing, and after 10 dry days at the anchor rate ~= 2%.
    assert all(b > a for a, b in zip(t.loss_pct_series, t.loss_pct_series[1:]))
    assert np.isclose(t.current_loss_pct, days * PM10_SOILING_RATE_PCT_PER_DAY)
    assert t.cleaning_events == 0
    # No cleaning rain anywhere in the window -> unknown, NOT reported as 0 days.
    assert t.days_since_cleaning_rain is None


def test_heavy_rain_cleans_and_resets_the_day_counter():
    pm10 = [PM10_REFERENCE_UG_M3] * 12
    salt = [0.0] * 12
    rain = [0.0] * 9 + [20.0] + [0.0, 0.0]
    t = simulate_soiling(pm10, salt, rain)
    dirty_before = t.loss_pct_series[8]
    assert t.loss_pct_series[9] < dirty_before  # the downpour washed it
    assert t.cleaning_events == 1
    # Two dry days after the wash.
    assert t.days_since_cleaning_rain == 2


def test_soiling_saturates_at_the_cap():
    days = 400
    t = simulate_soiling([300.0] * days, [1.0] * days, [0.0] * days)
    assert t.current_loss_pct == MAX_SOILING_LOSS_PCT
    assert max(t.loss_pct_series) == MAX_SOILING_LOSS_PCT


def test_empty_input_returns_zeros_and_unknown_not_a_made_up_value():
    t = simulate_soiling([], [], [])
    assert t.loss_pct_series == ()
    assert t.current_loss_pct == 0.0
    assert t.average_loss_pct == 0.0
    assert t.days_since_cleaning_rain is None
    assert t.cleaning_events == 0


def test_a_wet_season_stays_cleaner_than_a_dry_one():
    """The whole point of driving soiling off real rainfall: Thailand's monsoon
    washes the array for free, so the same air quality must yield a lower
    average loss in a rainy window than a dry one."""
    days = 60
    dry = simulate_soiling([PM10_REFERENCE_UG_M3] * days, [0.3] * days, [0.0] * days)
    # Rain every third day.
    rainy_pattern = [10.0 if i % 3 == 0 else 0.0 for i in range(days)]
    rainy = simulate_soiling([PM10_REFERENCE_UG_M3] * days, [0.3] * days, rainy_pattern)
    assert rainy.average_loss_pct < dry.average_loss_pct
    assert rainy.cleaning_events == 20


def test_days_until_threshold_projects_and_refuses_to_project_nonsense():
    assert days_until_threshold(1.0, 0.2, 3.0) == 10
    assert days_until_threshold(4.0, 0.2, 3.0) is None  # already past it
    assert days_until_threshold(1.0, 0.0, 3.0) is None  # nothing accumulating


def test_energy_lost_is_proportional_and_clamped():
    assert energy_lost_kwh(1000.0, 2.5) == 25.0
    assert energy_lost_kwh(1000.0, 0.0) == 0.0
    assert energy_lost_kwh(1000.0, -5.0) == 0.0
