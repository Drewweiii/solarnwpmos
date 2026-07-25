"""Covers data-feed health + seasonal output anomalies (2026-07-25)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nongfab_forecast.health import (
    STATUS_MISSING,
    STATUS_OK,
    STATUS_STALE,
    DayEnergy,
    evaluate_coverage_feed,
    evaluate_observation_feed,
    find_output_anomalies,
    rank_cause,
    worst_status,
)

_NOW = datetime(2026, 7, 25, 6, 0, tzinfo=timezone.utc)


def test_an_observation_feed_is_ok_while_recent_and_stale_once_old():
    fresh = evaluate_observation_feed("cloud", _NOW - timedelta(minutes=15), 500, _NOW, max_age_minutes=60)
    assert fresh.status == STATUS_OK
    assert fresh.age_minutes == pytest.approx(15)
    assert fresh.lead_minutes is None

    old = evaluate_observation_feed("cloud", _NOW - timedelta(hours=5), 500, _NOW, max_age_minutes=60)
    assert old.status == STATUS_STALE
    assert "เก่ากว่าที่ควร" in old.detail


def test_an_empty_feed_is_missing_not_stale():
    empty = evaluate_observation_feed("uv", None, 0, _NOW, max_age_minutes=60)
    assert empty.status == STATUS_MISSING
    assert empty.age_minutes is None
    # Rows present but no timestamp is equally "missing", never silently ok.
    assert evaluate_coverage_feed("nwp", None, 0, _NOW, min_lead_minutes=120).status == STATUS_MISSING


def test_a_coverage_feed_is_healthy_when_it_reaches_FORWARD_of_now():
    """The aerosol bug's exact signature: a forecast feed whose newest row is
    merely 'recent' has already run out of forward coverage."""
    ahead = evaluate_coverage_feed("aerosol", _NOW + timedelta(hours=6), 2000, _NOW, min_lead_minutes=180)
    assert ahead.status == STATUS_OK
    assert ahead.lead_minutes == pytest.approx(360)
    assert ahead.age_minutes == pytest.approx(-360)  # negative age = in the future

    just_behind = evaluate_coverage_feed("aerosol", _NOW - timedelta(minutes=30), 2000, _NOW, min_lead_minutes=180)
    assert just_behind.status == STATUS_STALE
    assert just_behind.lead_minutes == pytest.approx(-30)
    assert "ล่วงหน้าไม่พอ" in just_behind.detail

    # Still ahead of now, but not far enough to cover the model's leads.
    shallow = evaluate_coverage_feed("aerosol", _NOW + timedelta(minutes=60), 2000, _NOW, min_lead_minutes=180)
    assert shallow.status == STATUS_STALE


def test_worst_status_reports_the_worst_feed_and_treats_no_feeds_as_missing():
    ok = evaluate_observation_feed("a", _NOW, 1, _NOW, 60)
    stale = evaluate_observation_feed("b", _NOW - timedelta(hours=9), 1, _NOW, 60)
    missing = evaluate_observation_feed("c", None, 0, _NOW, 60)
    assert worst_status([ok, ok]) == STATUS_OK
    assert worst_status([ok, stale]) == STATUS_STALE
    assert worst_status([ok, stale, missing]) == STATUS_MISSING
    assert worst_status([]) == STATUS_MISSING


def _day(day: str, kwh: float, **drivers) -> DayEnergy:
    return DayEnergy(day=day, energy_kwh=kwh, **drivers)


def test_only_days_below_the_threshold_are_flagged_newest_first():
    days = [
        _day("2026-07-20", 100.0),
        _day("2026-07-21", 50.0),  # 0.5 of norm -> flagged
        _day("2026-07-22", 95.0),
        _day("2026-07-23", 40.0),  # 0.4 -> flagged
    ]
    found = find_output_anomalies(days, norm_kwh=100.0)
    assert [a.day for a in found] == ["2026-07-23", "2026-07-21"]
    assert found[0].ratio == pytest.approx(0.4)
    assert found[0].shortfall_kwh == pytest.approx(60.0)


def test_a_nonpositive_norm_flags_nothing_rather_than_dividing_by_zero():
    assert find_output_anomalies([_day("2026-07-21", 10.0)], norm_kwh=0.0) == []
    assert find_output_anomalies([_day("2026-07-21", 10.0)], norm_kwh=-5.0) == []


def test_cause_ranking_picks_the_driver_that_deviated_most():
    days = [
        _day("2026-07-20", 100.0, cloud_pct=40.0, precip_mm=0.0, aod=0.2),
        _day("2026-07-21", 100.0, cloud_pct=40.0, precip_mm=0.0, aod=0.2),
        # A heavily overcast day: cloud is far above the median, rain barely.
        _day("2026-07-22", 30.0, cloud_pct=95.0, precip_mm=1.0, aod=0.21),
    ]
    cause, detail = rank_cause(days[-1], days)
    assert cause == "cloud"
    assert "เมฆมากกว่าปกติ" in detail

    found = find_output_anomalies(days, norm_kwh=100.0)
    assert len(found) == 1
    assert found[0].likely_cause == "cloud"


def test_cause_ranking_can_pick_soiling_or_aerosol_over_a_calm_sky():
    days = [
        _day("2026-07-20", 100.0, cloud_pct=30.0, soiling_pct=0.5, aod=0.2),
        _day("2026-07-21", 100.0, cloud_pct=30.0, soiling_pct=0.5, aod=0.2),
        # Same sky, but the glass is filthy.
        _day("2026-07-22", 40.0, cloud_pct=30.0, soiling_pct=9.0, aod=0.2),
    ]
    assert rank_cause(days[-1], days)[0] == "soiling"

    hazy = [
        _day("2026-07-20", 100.0, cloud_pct=30.0, aod=0.15),
        _day("2026-07-21", 100.0, cloud_pct=30.0, aod=0.15),
        _day("2026-07-22", 45.0, cloud_pct=30.0, aod=0.9),
    ]
    assert rank_cause(hazy[-1], hazy)[0] == "aerosol"


def test_cause_is_unknown_rather_than_guessed_when_nothing_was_measured():
    days = [_day("2026-07-20", 100.0), _day("2026-07-21", 20.0)]
    cause, detail = rank_cause(days[-1], days)
    assert cause == "unknown"
    assert "ยังไม่มีตัวแปรอากาศ" in detail


def test_a_driver_better_than_median_is_never_blamed():
    """A day with LESS cloud than usual must not be blamed on cloud."""
    days = [
        _day("2026-07-20", 100.0, cloud_pct=60.0),
        _day("2026-07-21", 100.0, cloud_pct=60.0),
        _day("2026-07-22", 30.0, cloud_pct=10.0),
    ]
    assert rank_cause(days[-1], days)[0] == "unknown"
