"""Covers the forecast verification / skill-score math (2026-07-25)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nongfab_forecast.verification import (
    EMPTY_METRICS,
    LEAD_BUCKETS,
    ForecastActualPair,
    build_pairs,
    compute_metrics,
    daylight_pairs,
    metrics_by_lead,
)

_T0 = datetime(2026, 7, 20, 6, 0, tzinfo=timezone.utc)


def _pair(hour: int, predicted: float, actual: float, lead: float = 1.0, persistence: float | None = None):
    return ForecastActualPair(
        target_time=_T0 + timedelta(hours=hour),
        lead_hours=lead,
        predicted_kw=predicted,
        actual_kw=actual,
        persistence_kw=persistence,
    )


def test_empty_input_scores_nothing_rather_than_dividing_by_zero():
    assert compute_metrics([]) == EMPTY_METRICS
    assert compute_metrics([]).n == 0
    assert compute_metrics([]).skill_score is None


def test_a_perfect_forecast_scores_zero_error():
    m = compute_metrics([_pair(0, 10.0, 10.0), _pair(1, 20.0, 20.0)])
    assert m.n == 2
    assert m.mae_kw == 0.0
    assert m.rmse_kw == 0.0
    assert m.mbe_kw == 0.0


def test_mae_rmse_and_the_sign_of_the_bias():
    # Errors of +2 and -4 -> MAE 3, RMSE sqrt(10), MBE -1 (runs LOW overall).
    m = compute_metrics([_pair(0, 12.0, 10.0), _pair(1, 16.0, 20.0)])
    assert m.mae_kw == pytest.approx(3.0)
    assert m.rmse_kw == pytest.approx(((4 + 16) / 2) ** 0.5)
    assert m.mbe_kw == pytest.approx(-1.0)


def test_a_systematically_optimistic_forecast_has_a_positive_bias():
    m = compute_metrics([_pair(0, 12.0, 10.0), _pair(1, 24.0, 20.0)])
    assert m.mbe_kw > 0


def test_nrmse_needs_a_capacity_and_is_a_percentage_of_it():
    pairs = [_pair(0, 15.0, 10.0)]  # error 5 kW
    assert compute_metrics(pairs).nrmse_pct is None
    assert compute_metrics(pairs, capacity_kw=50.0).nrmse_pct == pytest.approx(10.0)
    # A zero/absent capacity must not divide by zero.
    assert compute_metrics(pairs, capacity_kw=0.0).nrmse_pct is None


def test_skill_score_is_positive_when_the_model_beats_persistence():
    # Model off by 1, persistence off by 5.
    pairs = [_pair(0, 11.0, 10.0, persistence=15.0), _pair(1, 21.0, 20.0, persistence=25.0)]
    m = compute_metrics(pairs)
    assert m.persistence_rmse_kw == pytest.approx(5.0)
    assert m.skill_score == pytest.approx(1 - 1 / 5)


def test_skill_score_is_zero_when_the_model_only_matches_persistence():
    pairs = [_pair(0, 15.0, 10.0, persistence=15.0), _pair(1, 25.0, 20.0, persistence=25.0)]
    assert compute_metrics(pairs).skill_score == pytest.approx(0.0)


def test_skill_score_goes_negative_when_the_model_is_worse_than_doing_nothing():
    pairs = [_pair(0, 30.0, 10.0, persistence=11.0)]
    assert compute_metrics(pairs).skill_score < 0


def test_skill_score_is_none_without_any_persistence_reference():
    m = compute_metrics([_pair(0, 11.0, 10.0)])
    assert m.persistence_rmse_kw is None
    assert m.skill_score is None


def test_skill_score_compares_the_model_over_the_same_subset():
    """A pair with no persistence reference must not skew the ratio: the model's
    RMSE in the skill score is measured over exactly the pairs persistence could
    also be scored on."""
    pairs = [
        _pair(0, 11.0, 10.0, persistence=15.0),  # both scorable
        _pair(1, 90.0, 20.0),  # model does terribly, but no persistence reference
    ]
    m = compute_metrics(pairs)
    # The overall RMSE is dominated by the second pair...
    assert m.rmse_kw > 40
    # ...while the skill score reflects only the first.
    assert m.skill_score == pytest.approx(1 - 1 / 5)


def test_daylight_filter_drops_night_but_keeps_a_real_miss():
    pairs = [
        _pair(0, 0.0, 0.0),  # night, trivially right - must be dropped
        _pair(1, 40.0, 0.0),  # predicted output, got nothing - a real miss, KEEP
        _pair(2, 0.0, 35.0),  # predicted nothing, got output - also a real miss
        _pair(3, 30.0, 28.0),
    ]
    kept = daylight_pairs(pairs)
    assert len(kept) == 3
    assert all(max(p.predicted_kw, p.actual_kw) > 0 for p in kept)


def test_metrics_by_lead_returns_every_bucket_including_empty_ones():
    pairs = [_pair(0, 11.0, 10.0, lead=0.5), _pair(1, 15.0, 10.0, lead=4.0)]
    by_lead = dict(metrics_by_lead(pairs))
    assert [label for label, _, _ in LEAD_BUCKETS] == list(by_lead)
    assert by_lead["0-1h"].n == 1
    assert by_lead["3-6h"].n == 1
    assert by_lead["24h+"].n == 0  # present but empty, not omitted
    # The nearer lead is the more accurate one here, as it should be.
    assert by_lead["0-1h"].rmse_kw < by_lead["3-6h"].rmse_kw


def test_build_pairs_joins_on_the_target_hour_and_recovers_the_lead_time():
    issuances = [
        (_T0 + timedelta(hours=3), _T0, 30.0),  # 3h lead
        (_T0 + timedelta(hours=1), _T0, 12.0),  # 1h lead
    ]
    actuals = {_T0: 5.0, _T0 + timedelta(hours=1): 10.0, _T0 + timedelta(hours=3): 28.0}
    pairs = sorted(build_pairs(issuances, actuals), key=lambda p: p.lead_hours)
    assert [p.lead_hours for p in pairs] == [1.0, 3.0]
    assert pairs[0].actual_kw == 10.0
    # Persistence = what it was doing when the forecast was issued (T0 -> 5 kW).
    assert pairs[0].persistence_kw == 5.0


def test_build_pairs_skips_hours_with_no_actual_instead_of_inventing_one():
    issuances = [(_T0 + timedelta(hours=1), _T0, 12.0), (_T0 + timedelta(hours=2), _T0, 18.0)]
    pairs = build_pairs(issuances, {_T0 + timedelta(hours=1): 10.0})
    assert len(pairs) == 1
    assert pairs[0].target_time == _T0 + timedelta(hours=1)


def test_build_pairs_leaves_persistence_none_when_the_reference_hour_is_missing():
    issuances = [(_T0 + timedelta(hours=1), _T0, 12.0)]
    pairs = build_pairs(issuances, {_T0 + timedelta(hours=1): 10.0})  # no actual at T0
    assert pairs[0].persistence_kw is None


def test_build_pairs_ignores_a_row_issued_after_its_target():
    issuances = [(_T0, _T0 + timedelta(hours=2), 12.0)]
    assert build_pairs(issuances, {_T0: 10.0}) == []


def test_build_pairs_floors_a_mid_hour_issue_time_onto_the_actuals_grid():
    """Actuals are recorded on hour anchors, so an issue time at :37 has to floor
    to :00 to find its persistence reference."""
    issued = _T0 + timedelta(minutes=37)
    issuances = [(_T0 + timedelta(hours=2), issued, 20.0)]
    actuals = {_T0: 7.0, _T0 + timedelta(hours=2): 22.0}
    pairs = build_pairs(issuances, actuals)
    assert pairs[0].persistence_kw == 7.0
