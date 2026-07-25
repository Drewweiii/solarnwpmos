"""Tests for deriving Nong Fab's real year-to-year sun variability.

The behaviour that matters most here is what gets THROWN AWAY: NASA POWER fill
values and calendar-incomplete years. A year missing its monsoon months would
otherwise sum low, then be read as a genuinely bad year - inflating exactly the
variability this module exists to measure.
"""

from __future__ import annotations

import calendar

import pytest

from nongfab_financial.interannual import POWER_FILL_VALUE, annual_cv_pct, annual_totals


def full_year(year: int, daily_value: float) -> dict[str, float]:
    """A complete calendar year of identical daily readings."""
    out: dict[str, float] = {}
    for month in range(1, 13):
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            out[f"{year}{month:02d}{day:02d}"] = daily_value
    return out


class TestAnnualTotals:
    def test_sums_a_complete_year(self):
        totals = annual_totals(full_year(2021, 5.0))
        assert totals == {2021: pytest.approx(365 * 5.0)}

    def test_counts_the_extra_day_in_a_leap_year(self):
        totals = annual_totals(full_year(2024, 5.0))
        assert totals == {2024: pytest.approx(366 * 5.0)}

    def test_drops_an_incomplete_year_rather_than_scaling_it_up(self):
        # A year missing its cloudy months would scale to a falsely HIGH total
        # and then read as an unusually good year - manufacturing variability.
        partial = full_year(2021, 5.0)
        for key in list(partial)[:40]:
            del partial[key]
        assert annual_totals(partial) == {}

    def test_a_fill_value_makes_its_year_incomplete_rather_than_poisoning_the_sum(self):
        # -999 in an annual sum would be catastrophic; dropping it leaves the
        # year one day short, which the completeness check then rejects.
        year = full_year(2021, 5.0)
        year["20210615"] = -999.0
        assert annual_totals(year) == {}

    def test_keeps_only_the_complete_years_out_of_a_mixed_record(self):
        record = {**full_year(2020, 4.0), **full_year(2021, 5.0)}
        for key in list(full_year(2022, 6.0))[:10]:
            record[key] = 6.0
        totals = annual_totals(record)
        assert sorted(totals) == [2020, 2021]

    def test_ignores_malformed_keys_instead_of_crashing(self):
        record = {**full_year(2021, 5.0), "not-a-date": 5.0, "": 1.0}
        assert sorted(annual_totals(record)) == [2021]

    def test_the_fill_threshold_is_below_any_plausible_reading(self):
        # Irradiance is never negative, so anything at/below the sentinel is
        # missing data by definition.
        assert POWER_FILL_VALUE < 0


class TestAnnualCv:
    def test_identical_non_leap_years_have_zero_variability(self):
        record = {**full_year(2021, 5.0), **full_year(2022, 5.0), **full_year(2023, 5.0)}
        stats = annual_cv_pct(record)
        assert stats is not None
        assert stats.cv_pct == pytest.approx(0.0)
        assert stats.years_used == 3

    def test_a_leap_year_really_does_collect_more_sun_than_a_common_one(self):
        # Not a bug to normalise away: 366 days of sunshine IS more energy than
        # 365, and a plant genuinely earns more in a leap year. It shows up as a
        # small, real contribution to interannual spread.
        record = {**full_year(2020, 5.0), **full_year(2021, 5.0)}
        totals = annual_totals(record)
        assert totals[2020] > totals[2021]
        stats = annual_cv_pct(record)
        assert stats is not None
        assert 0 < stats.cv_pct < 0.5  # ~0.27% from the extra day alone

    def test_reports_the_best_and_worst_year_by_name(self):
        record = {**full_year(2020, 4.0), **full_year(2021, 6.0), **full_year(2022, 5.0)}
        stats = annual_cv_pct(record)
        assert stats is not None
        assert (stats.min_year, stats.max_year) == (2020, 2021)
        assert stats.first_year == 2020 and stats.last_year == 2022

    def test_a_wider_spread_of_years_gives_a_bigger_CV(self):
        tight = annual_cv_pct({**full_year(2020, 4.9), **full_year(2021, 5.1)})
        loose = annual_cv_pct({**full_year(2020, 3.0), **full_year(2021, 7.0)})
        assert tight is not None and loose is not None
        assert loose.cv_pct > tight.cv_pct

    def test_one_year_yields_None_not_zero_percent(self):
        # "we have one year" and "this site never varies" are opposite claims.
        assert annual_cv_pct(full_year(2021, 5.0)) is None

    def test_no_usable_data_yields_None(self):
        assert annual_cv_pct({}) is None
        assert annual_cv_pct({"20210101": -999.0}) is None

    def test_matches_the_figure_shipped_as_the_default(self):
        # Guards the published constant against a silent regression in the
        # aggregation: these are the real NASA POWER annual totals for Nong Fab
        # (12.71 N, 101.15 E), 2000-2025, printed by scripts/derive_annual_cv.py.
        real_totals = [
            1861.2, 1842.2, 1844.0, 1899.0, 1939.1, 1818.7, 1850.6, 1835.1, 1826.6,
            1862.8, 1842.7, 1792.1, 1815.1, 1812.5, 1906.8, 1920.6, 1866.3, 1810.8,
            1827.9, 1908.0, 1841.2, 1863.2, 1808.9, 1903.1, 1851.4, 1817.2,
        ]
        record: dict[str, float] = {}
        for offset, total in enumerate(real_totals):
            year = 2000 + offset
            days = 366 if calendar.isleap(year) else 365
            record.update(full_year(year, total / days))

        stats = annual_cv_pct(record)
        assert stats is not None
        assert stats.years_used == 26
        assert stats.mean_annual == pytest.approx(1852.6, abs=0.5)
        # The shipped default: 2.11%, not the 4% literature guess it replaced.
        assert stats.cv_pct == pytest.approx(2.11, abs=0.02)
