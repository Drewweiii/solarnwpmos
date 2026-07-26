"""Ramp detection: how fast the output changes, not just how much (project B,
2026-07-25)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nongfab_forecast.ramp import (
    DIRECTION_DOWN,
    DIRECTION_FLAT,
    DIRECTION_UP,
    EMPTY_STATISTICS,
    SEVERITY_CALM,
    SEVERITY_MODERATE,
    SEVERITY_STEEP,
    ramp_statistics,
    ramps_from_series,
    steepest_down_ramp,
)

_T0 = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)  # 10:00 ICT
CAPACITY = 50.0


def _series(*values: float, step_hours: float = 1.0):
    return [(_T0 + timedelta(hours=i * step_hours), v) for i, v in enumerate(values)]


def test_ramps_are_the_steps_between_consecutive_points():
    ramps = ramps_from_series(_series(10, 30, 25))
    assert [r.delta_kw for r in ramps] == [20, -5]


def test_rate_divides_by_duration_so_a_slow_change_is_not_a_ramp():
    # Same 30 kW delta over one hour and over three. The delta cannot tell them
    # apart and the rate must.
    fast = ramps_from_series(_series(10, 40))[0]
    slow = ramps_from_series(_series(10, 40, step_hours=3))[0]
    assert fast.delta_kw == slow.delta_kw == 30
    assert fast.rate_kw_per_h == 30.0
    assert slow.rate_kw_per_h == 10.0


def test_severity_is_relative_to_capacity_so_zones_compare():
    # 15 kW/h is 30% of GIS's 50 kW but only 7.5% of Jetty's 200 kW.
    ramp = ramps_from_series(_series(30, 15))[0]
    assert ramp.severity(50.0) == SEVERITY_MODERATE
    assert ramp.severity(200.0) == SEVERITY_CALM


def test_severity_ignores_direction_but_direction_is_reported_separately():
    up = ramps_from_series(_series(0, 25))[0]
    down = ramps_from_series(_series(25, 0))[0]
    assert up.severity(CAPACITY) == down.severity(CAPACITY) == SEVERITY_STEEP
    assert up.direction(CAPACITY) == DIRECTION_UP
    assert down.direction(CAPACITY) == DIRECTION_DOWN


def test_a_small_wobble_is_flat_not_a_tiny_ramp():
    # 0.5 kW/h on a 50 kW array is 1% - the model breathing, not an event.
    ramp = ramps_from_series(_series(20.0, 20.5))[0]
    assert ramp.direction(CAPACITY) == DIRECTION_FLAT


def test_duplicate_timestamps_do_not_manufacture_a_zero_length_ramp():
    # The store can hold more than one row for an hour across issuances; the
    # later value wins rather than producing an infinite rate.
    series = [(_T0, 10.0), (_T0, 40.0), (_T0 + timedelta(hours=1), 45.0)]
    ramps = ramps_from_series(series)
    assert len(ramps) == 1
    assert ramps[0].from_kw == 40.0


def test_an_out_of_order_series_is_sorted_before_differencing():
    scrambled = [(_T0 + timedelta(hours=2), 5.0), (_T0, 45.0), (_T0 + timedelta(hours=1), 25.0)]
    assert [r.delta_kw for r in ramps_from_series(scrambled)] == [-20, -20]


def test_a_single_point_yields_no_ramps():
    assert ramps_from_series([(_T0, 10.0)]) == []


def test_steepest_down_ramp_ignores_ordinary_afternoon_drift():
    # A gentle decline all afternoon: real, but not worth a warning. A warning
    # that fires every day is one nobody reads.
    gentle = ramps_from_series(_series(40, 38, 36, 34))
    assert steepest_down_ramp(gentle, CAPACITY) is None


def test_steepest_down_ramp_picks_the_sharpest_qualifying_fall():
    ramps = ramps_from_series(_series(40, 38, 10, 8))
    worst = steepest_down_ramp(ramps, CAPACITY)
    assert worst is not None
    assert worst.delta_kw == -28


def test_steepest_down_ramp_never_returns_a_climb():
    assert steepest_down_ramp(ramps_from_series(_series(0, 45)), CAPACITY) is None


def test_statistics_count_events_and_find_when_falls_cluster():
    # Two steep falls, both starting at 08:00Z = 15:00 ICT on different days.
    ramps: list = []
    for day in range(2):
        base = _T0 + timedelta(days=day)
        ramps += ramps_from_series([(base.replace(hour=8), 45.0), (base.replace(hour=9), 5.0)])
    stats = ramp_statistics(ramps, CAPACITY)
    assert stats.n_steep_down == 2
    assert stats.busiest_down_hour_ict == 15
    assert stats.busiest_down_hour_count == 2
    assert stats.worst_down_pct_per_h == pytest.approx(-80.0)


def test_statistics_report_the_worst_climb_too():
    stats = ramp_statistics(ramps_from_series(_series(5, 45)), CAPACITY)
    assert stats.worst_up_pct_per_h == pytest.approx(80.0)
    assert stats.worst_down_pct_per_h is None


def test_statistics_on_an_empty_history_report_nothing_rather_than_zeros_that_look_measured():
    stats = ramp_statistics([], CAPACITY)
    assert stats == EMPTY_STATISTICS
    assert stats.busiest_down_hour_ict is None
    assert stats.worst_down_pct_per_h is None


def test_without_a_capacity_severity_degrades_to_calm_rather_than_guessing():
    # No capacity means no way to say whether 15 kW/h is a lot. Reporting
    # "steep" off an unnormalised number would be a fabricated judgement.
    ramp = ramps_from_series(_series(30, 15))[0]
    assert ramp.pct_of_capacity_per_h(None) is None
    assert ramp.severity(None) == SEVERITY_CALM
    # The direction is still knowable from the raw sign, and is still reported.
    assert ramp.direction(None) == DIRECTION_DOWN
