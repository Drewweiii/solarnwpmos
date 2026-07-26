"""Sky-condition classification for the per-regime accuracy split (project C,
2026-07-25)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from nongfab_forecast.sky_condition import (
    SKY_CLEAR,
    SKY_ORDER,
    SKY_OVERCAST,
    SKY_PARTLY,
    classify_kt,
    kt_by_hour,
    sky_label_for,
)
from nongfab_forecast.verification import ForecastActualPair, metrics_by_sky

_T0 = datetime(2026, 7, 20, 6, 0, tzinfo=timezone.utc)


def test_classify_kt_splits_the_three_regimes_at_the_documented_thresholds():
    assert classify_kt(0.95) == SKY_CLEAR
    assert classify_kt(0.70) == SKY_CLEAR  # the boundary is inclusive at the top
    assert classify_kt(0.55) == SKY_PARTLY
    assert classify_kt(0.30) == SKY_PARTLY  # and exclusive at the bottom
    assert classify_kt(0.10) == SKY_OVERCAST


def test_an_unusable_kt_is_unclassified_not_overcast():
    # "We could not tell" and "it was overcast" are different findings; folding
    # the first into the second would invent bad weather out of missing data.
    assert classify_kt(None) is None
    assert classify_kt(float("nan")) is None


def test_thresholds_are_movable_because_they_are_definitions():
    assert classify_kt(0.65, clear_kt=0.6) == SKY_CLEAR
    assert classify_kt(0.65) == SKY_PARTLY


def test_kt_by_hour_takes_the_freshest_issue_for_each_hour():
    # Two issues for the same valid hour: an early one saying it will be dark,
    # a later one saying it is bright. The later issue is the closest thing to
    # what actually happened, so it must win.
    df = pd.DataFrame(
        {
            "valid_time": pd.to_datetime([_T0, _T0], utc=True),
            "issue_time": pd.to_datetime([_T0 - timedelta(hours=12), _T0 - timedelta(hours=1)], utc=True),
            "ssrd_w_m2": [10.0, 800.0],
        }
    )
    lookup = kt_by_hour(df, 12.68, 101.12)
    assert len(lookup) == 1
    # 13:00 ICT under 800 W/m2 is a bright sky, not the 10 W/m2 the stale issue said.
    assert next(iter(lookup.values())) > 0.5


def test_kt_by_hour_drops_night_hours_rather_than_dividing_by_a_tiny_reference():
    # 18:00Z is 01:00 ICT - the clear-sky reference is zero and kt is undefined.
    night = _T0.replace(hour=18)
    df = pd.DataFrame(
        {
            "valid_time": pd.to_datetime([night], utc=True),
            "issue_time": pd.to_datetime([night - timedelta(hours=1)], utc=True),
            "ssrd_w_m2": [0.0],
        }
    )
    assert kt_by_hour(df, 12.68, 101.12) == {}


def test_kt_by_hour_tolerates_an_empty_history():
    assert kt_by_hour(pd.DataFrame(), 12.68, 101.12) == {}


def _pair(hour: int, predicted: float, actual: float):
    return ForecastActualPair(
        target_time=_T0 + timedelta(hours=hour), lead_hours=1.0, predicted_kw=predicted, actual_kw=actual
    )


def test_metrics_by_sky_shows_the_model_failing_under_cloud():
    # Perfect on the clear hours, badly wrong on the overcast ones - exactly the
    # pattern one site-wide RMSE would average away.
    pairs = [_pair(0, 40, 40), _pair(1, 40, 40), _pair(2, 40, 10), _pair(3, 40, 10)]
    kt = {
        _T0: 0.9,
        _T0 + timedelta(hours=1): 0.85,
        _T0 + timedelta(hours=2): 0.15,
        _T0 + timedelta(hours=3): 0.1,
    }
    by_label = {label: metrics for label, metrics, _ in metrics_by_sky(pairs, kt)}
    assert by_label[SKY_CLEAR].n == 2
    assert by_label[SKY_CLEAR].rmse_kw == pytest.approx(0.0)
    assert by_label[SKY_OVERCAST].n == 2
    assert by_label[SKY_OVERCAST].rmse_kw == pytest.approx(30.0)


def test_metrics_by_sky_returns_every_bucket_even_when_empty():
    rows = metrics_by_sky([_pair(0, 40, 40)], {_T0: 0.9})
    assert [label for label, _, _ in rows] == list(SKY_ORDER)
    assert {label: m for label, m, _ in rows}[SKY_PARTLY].n == 0


def test_metrics_by_sky_counts_unclassifiable_hours_instead_of_hiding_them():
    pairs = [_pair(0, 40, 40), _pair(1, 40, 20), _pair(2, 40, 20)]
    rows = metrics_by_sky(pairs, {_T0: 0.9})  # only the first hour has a kt
    assert rows[0][2] == 2
    assert sum(m.n for _, m, _ in rows) == 1


def test_sky_label_for_returns_none_for_an_hour_with_no_reading():
    assert sky_label_for(_T0, {}) is None
