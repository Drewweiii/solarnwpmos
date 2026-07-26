"""Forecast convergence: how one hour's prediction moved as it approached
(project D, 2026-07-25)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nongfab_forecast.evolution import (
    MIN_ISSUANCES_FOR_A_TREND,
    build_evolution,
    most_revised_target,
)

TARGET = datetime(2026, 7, 22, 5, 0, tzinfo=timezone.utc)  # 12:00 ICT


def _row(target: datetime, lead_hours: float, pred: float, lower=None, upper=None):
    return (target, target - timedelta(hours=lead_hours), pred, lower, upper)


def test_issuances_are_ordered_oldest_first_whatever_order_they_arrive_in():
    rows = [_row(TARGET, 12, 175.0), _row(TARGET, 60, 180.0), _row(TARGET, 3, 172.0)]
    evolution = build_evolution(rows, TARGET)
    assert [i.pred_kw for i in evolution.issuances] == [180.0, 175.0, 172.0]
    assert evolution.first.pred_kw == 180.0
    assert evolution.latest.pred_kw == 172.0


def test_rows_for_other_target_hours_are_ignored():
    other = TARGET + timedelta(hours=1)
    rows = [_row(TARGET, 12, 100.0), _row(other, 12, 500.0)]
    assert build_evolution(rows, TARGET).n == 1


def test_an_issuance_at_or_after_the_event_is_not_a_forecast_of_it():
    # A row issued after the hour it names would make the line "converge" onto
    # an answer given after the fact.
    rows = [_row(TARGET, 12, 100.0), _row(TARGET, 0, 120.0), _row(TARGET, -3, 118.0)]
    assert build_evolution(rows, TARGET).n == 1


def test_total_revision_is_signed_because_direction_is_the_story():
    rows = [_row(TARGET, 48, 180.0), _row(TARGET, 3, 140.0)]
    assert build_evolution(rows, TARGET).total_revision_kw == -40.0


def test_swing_catches_a_model_that_changed_its_mind_and_came_back():
    # 180 -> 90 -> 175: total revision is a placid -5 kW, and that reading is
    # wrong about what happened. The swing is 90.
    rows = [_row(TARGET, 60, 180.0), _row(TARGET, 30, 90.0), _row(TARGET, 3, 175.0)]
    evolution = build_evolution(rows, TARGET)
    assert evolution.total_revision_kw == -5.0
    assert evolution.max_swing_kw == 90.0


def test_a_single_issuance_has_no_revision_to_report():
    evolution = build_evolution([_row(TARGET, 12, 100.0)], TARGET)
    assert evolution.total_revision_kw is None
    assert evolution.max_swing_kw is None


def test_convergence_is_undecidable_from_one_revision():
    # Two answers give one revision, and there is nothing to compare it to.
    rows = [_row(TARGET, 48, 180.0), _row(TARGET, 3, 140.0)]
    assert build_evolution(rows, TARGET).is_converging() is None


def test_a_settling_forecast_reads_as_converging():
    rows = [
        _row(TARGET, 72, 200.0),
        _row(TARGET, 48, 170.0),
        _row(TARGET, 24, 165.0),
        _row(TARGET, 3, 164.0),
    ]
    assert build_evolution(rows, TARGET).is_converging() is True


def test_a_forecast_that_lurches_late_does_not_read_as_converging():
    rows = [
        _row(TARGET, 72, 170.0),
        _row(TARGET, 48, 168.0),
        _row(TARGET, 24, 166.0),
        _row(TARGET, 3, 80.0),
    ]
    assert build_evolution(rows, TARGET).is_converging() is False


def test_most_revised_target_picks_by_swing_not_by_net_change():
    quiet = TARGET
    dramatic = TARGET + timedelta(hours=1)
    rows = [
        # Net -40, no drama.
        _row(quiet, 60, 180.0),
        _row(quiet, 30, 160.0),
        _row(quiet, 3, 140.0),
        # Net -5, but it swung 90 kW on the way.
        _row(dramatic, 60, 180.0),
        _row(dramatic, 30, 90.0),
        _row(dramatic, 3, 175.0),
    ]
    chosen = most_revised_target(rows)
    assert chosen is not None
    assert chosen.target_time == dramatic


def test_most_revised_target_skips_hours_without_enough_issuances():
    thin = TARGET + timedelta(hours=2)
    rows = [
        _row(TARGET, 60, 100.0),
        _row(TARGET, 30, 105.0),
        _row(TARGET, 3, 104.0),
        # A single enormous outlier with only two issuances must not win.
        _row(thin, 60, 0.0),
        _row(thin, 3, 400.0),
    ]
    chosen = most_revised_target(rows)
    assert chosen is not None
    assert chosen.target_time == TARGET


def test_most_revised_target_returns_none_before_anything_has_a_trend():
    rows = [_row(TARGET, 60, 100.0), _row(TARGET, 3, 120.0)]
    assert MIN_ISSUANCES_FOR_A_TREND == 3
    assert most_revised_target(rows) is None


def test_the_published_band_travels_with_each_issuance():
    rows = [_row(TARGET, 48, 180.0, 150.0, 210.0), _row(TARGET, 3, 172.0, 165.0, 179.0)]
    evolution = build_evolution(rows, TARGET)
    assert evolution.first.lower_kw == 150.0
    assert evolution.latest.upper_kw == 179.0


def test_lead_hours_are_recovered_from_the_issue_time():
    evolution = build_evolution([_row(TARGET, 36, 100.0)], TARGET)
    assert evolution.issuances[0].lead_hours == 36.0
