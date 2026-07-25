"""Parsing + derived-context tests for the EGAT SysGen national-grid source.

The payload shapes below are trimmed captures of the real endpoints taken on
2026-07-25 (`/api/hist/actual`, `/api/control/plan`, `/api/control/peak`), so
these assert against what EGAT actually serves rather than an invented schema.
The network path itself can't run in CI (egress-blocked), which is exactly why
the parsing and the arithmetic are pure and tested here.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nongfab_api.egat_grid import (
    ICT,
    GridPoint,
    parse_peaks,
    parse_series,
    peak_is_after_sunset,
    plan_deviation_mw,
    series_peak,
    share_of_system_pct,
    value_at,
)

ACTUAL_PAYLOAD = {
    "id": "1800142",
    "day": "25-07-2026",
    "list": [[0, 28539.4, 28.83], [60, 28485.7, 28.83], [120, 28455.7, 28.89], [46920, 25058.6, 34.8]],
}

PLAN_PAYLOAD = {
    "day": "25-07-2026",
    # The plan endpoint carries no ambient temperature - only two columns.
    "list": [[0, 28412.2], [60, 28349.235], [120, 28286.34], [46920, 24800.0]],
}

PEAK_PAYLOAD = {
    "success": True,
    "thisYear": {"value": 35991.6, "temperature": 31.7, "date": "22-04-2026", "time": "20:50"},
    "lastYear": {"value": 34568.3, "temperature": 31.3, "date": "25-04-2025", "time": "22:18"},
    "allTime": {"value": 36477.8, "temperature": 31.8, "date": "29-04-2024", "time": "20:56"},
    "fromCache": True,
}


class TestParseSeries:
    def test_reads_the_day_and_every_sample(self):
        day, points = parse_series(ACTUAL_PAYLOAD)
        assert day == "2026-07-25"
        assert len(points) == 4
        assert points[0].mw == 28539.4
        assert points[0].ambient_c == 28.83

    def test_offsets_are_ICT_seconds_from_local_midnight_not_UTC(self):
        # 46,920 s is 13:02 - and it must be 13:02 *Thai* time, which is the
        # whole reason this module never converts from UTC.
        _, points = parse_series(ACTUAL_PAYLOAD)
        last = points[-1]
        assert (last.at.hour, last.at.minute) == (13, 2)
        assert last.at.utcoffset() == timedelta(hours=7)

    def test_plan_rows_without_a_temperature_column_parse_with_ambient_none(self):
        _, points = parse_series(PLAN_PAYLOAD)
        assert len(points) == 4
        assert all(p.ambient_c is None for p in points)

    def test_a_malformed_row_is_skipped_not_defaulted_to_zero_MW(self):
        # A zero on a national demand curve would read as a nationwide blackout,
        # so a broken row must vanish rather than become 0.
        payload = {"day": "25-07-2026", "list": [[0, 28539.4], ["x", "y"], [60], [120, None], [180, 28000.0]]}
        _, points = parse_series(payload)
        assert [p.mw for p in points] == [28539.4, 28000.0]

    def test_an_unparseable_day_yields_nothing_rather_than_the_wrong_day(self):
        assert parse_series({"day": "2026/07/25", "list": [[0, 1.0]]}) == (None, [])
        assert parse_series({"list": [[0, 1.0]]}) == (None, [])
        assert parse_series("not a dict") == (None, [])

    def test_points_come_back_in_time_order_even_if_the_feed_is_shuffled(self):
        payload = {"day": "25-07-2026", "list": [[120, 3.0], [0, 1.0], [60, 2.0]]}
        _, points = parse_series(payload)
        assert [p.mw for p in points] == [1.0, 2.0, 3.0]


class TestParsePeaks:
    def test_reads_all_three_records_with_their_ICT_timestamps(self):
        peaks = parse_peaks(PEAK_PAYLOAD)
        assert len(peaks) == 3
        this_year = peaks[0]
        assert this_year.label == "สูงสุดปีนี้"
        assert this_year.mw == 35991.6
        assert this_year.at is not None
        assert (this_year.at.year, this_year.at.month, this_year.at.day) == (2026, 4, 22)
        # The finding this feature exists for: the national peak is at night.
        assert (this_year.at.hour, this_year.at.minute) == (20, 50)

    def test_a_record_with_an_unreadable_clock_keeps_its_MW_figure(self):
        peaks = parse_peaks({"thisYear": {"value": 100.0, "date": "22-04-2026", "time": "99:99"}})
        assert peaks[0].mw == 100.0
        # Falls back to the day rather than dropping the record entirely.
        assert peaks[0].at is not None and peaks[0].at.hour == 0

    def test_a_record_without_a_numeric_value_is_dropped(self):
        assert parse_peaks({"thisYear": {"date": "22-04-2026", "time": "20:50"}}) == []
        assert parse_peaks("not a dict") == []


class TestDerivedContext:
    def test_series_peak_is_the_largest_sample(self):
        _, points = parse_series(ACTUAL_PAYLOAD)
        assert series_peak(points).mw == 28539.4
        assert series_peak([]) is None

    def test_value_at_picks_the_nearest_sample_not_an_interpolation(self):
        _, points = parse_series(ACTUAL_PAYLOAD)
        target = datetime(2026, 7, 25, 0, 1, 40, tzinfo=ICT)  # 100 s, between 60 and 120
        assert value_at(points, target).mw == 28455.7  # the 120 s sample, 20 s away
        assert value_at([], target) is None

    def test_plan_deviation_is_positive_when_the_country_draws_more_than_planned(self):
        _, actual = parse_series(ACTUAL_PAYLOAD)
        _, plan = parse_series(PLAN_PAYLOAD)
        # Newest actual 25,058.6 MW vs planned 24,800.0 MW at the same minute.
        assert plan_deviation_mw(actual, plan) == pytest.approx(258.6)

    def test_plan_deviation_is_none_when_either_side_is_missing(self):
        _, actual = parse_series(ACTUAL_PAYLOAD)
        assert plan_deviation_mw(actual, []) is None
        assert plan_deviation_mw([], actual) is None

    def test_site_share_of_the_national_system_is_tiny_but_real(self):
        # 429 kWp against ~25 GW: a real number, not a rounding artefact.
        share = share_of_system_pct(429.0, 25058.6)
        assert share is not None
        assert 0.0017 < share < 0.0018

    def test_site_share_guards_a_non_positive_system_figure(self):
        assert share_of_system_pct(429.0, 0.0) is None
        assert share_of_system_pct(429.0, -5.0) is None

    def test_the_annual_peak_falls_after_the_sun_is_down(self):
        # This is the claim the panel makes, asserted against EGAT's own record:
        # peak 20:50 vs a Nong Fab sunset around 18:40.
        peak_at = datetime(2026, 4, 22, 20, 50, tzinfo=ICT)
        sunset = datetime(2026, 7, 25, 18, 40, tzinfo=ICT)
        assert peak_is_after_sunset(peak_at, sunset) is True

    def test_a_midday_peak_would_correctly_report_false(self):
        peak_at = datetime(2026, 4, 22, 13, 0, tzinfo=ICT)
        sunset = datetime(2026, 7, 25, 18, 40, tzinfo=ICT)
        assert peak_is_after_sunset(peak_at, sunset) is False

    def test_an_unknown_time_gives_none_not_a_confident_no(self):
        sunset = datetime(2026, 7, 25, 18, 40, tzinfo=ICT)
        assert peak_is_after_sunset(None, sunset) is None
        assert peak_is_after_sunset(datetime(2026, 4, 22, 20, 50, tzinfo=ICT), None) is None

    def test_grid_point_is_immutable(self):
        point = GridPoint(at=datetime(2026, 7, 25, tzinfo=ICT), mw=1.0)
        try:
            point.mw = 2.0  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("GridPoint should be frozen")
