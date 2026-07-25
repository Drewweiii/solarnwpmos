"""TOU peak/off-peak split of generation (project G).

`green_savings.py` prices every kWh at the Peak rate and admits in its own
docstring that this ignores weekends and off-peak hours. These tests pin the
correction, and in particular the two effects that are easy to miss.
"""

from __future__ import annotations

import pytest
from nongfab_simulation.tou import blended_rate_thb_per_kwh, is_peak_hour, weekday_count, zone_tou_split

YEAR = 2026


class TestWindows:
    def test_peak_is_nine_to_ten_at_night_inclusive_of_neither_end_wrongly(self):
        """An off-by-one here moves three hours of morning production between
        windows and would look perfectly reasonable in a total."""
        assert is_peak_hour(8) is False
        assert is_peak_hour(9) is True
        assert is_peak_hour(21) is True
        assert is_peak_hour(22) is False

    def test_morning_generation_is_off_peak_even_on_a_working_day(self):
        """The non-obvious half of the finding: the array starts around 06:00
        but the tariff's peak window does not open until 09:00."""
        assert all(not is_peak_hour(h) for h in (6, 7, 8))

    def test_weekdays_are_counted_from_the_real_calendar(self):
        """Not approximated as 5/7 - month lengths and start days move the real
        ratio by more than a day, and this feeds a money figure."""
        weekdays, weekend = weekday_count(2026, 2)
        assert weekdays + weekend == 28
        # February 2026 starts on a Sunday, so it has exactly four full weekends.
        assert weekend == 8


class TestSplit:
    def test_a_third_of_the_year_lands_outside_the_peak_window(self):
        """The headline. Weekends alone are ~28% of days, and the 06:00-09:00
        morning adds more - so a flat peak-rate valuation overstates."""
        split = zone_tou_split("GIS", YEAR)
        assert 25.0 < split.offpeak_share_pct < 40.0
        assert split.peak_share_pct + split.offpeak_share_pct == pytest.approx(100.0)

    def test_counting_holidays_moves_energy_from_peak_to_off_peak(self):
        """Holidays default to zero so the reported peak share is a ceiling.
        Supplying them can only push energy the other way - if this ever
        reversed, the "conservative floor" claim on the panel would be false."""
        none = zone_tou_split("GIS", YEAR, offpeak_holiday_days=0)
        many = zone_tou_split("GIS", YEAR, offpeak_holiday_days=16)

        assert many.offpeak_share_pct > none.offpeak_share_pct
        assert many.total_kwh == pytest.approx(none.total_kwh, rel=1e-9)

    def test_the_split_conserves_energy(self):
        """Peak + off-peak must equal the total the rest of the system reports;
        a split that quietly loses or duplicates kWh would misprice everything
        downstream."""
        split = zone_tou_split("ISB", YEAR)
        assert split.total_kwh == pytest.approx(split.peak_kwh + split.offpeak_kwh)
        assert split.peak_kwh > 0 and split.offpeak_kwh > 0


class TestBlendedRate:
    def test_equal_rates_reproduce_the_flat_rate_exactly(self):
        """The guardrail that lets this ship without moving a published number:
        the off-peak rate defaults to the peak rate, so the blended answer must
        be identical to today's until somebody enters the real figure."""
        split = zone_tou_split("GIS", YEAR)
        assert blended_rate_thb_per_kwh(split, 4.1025, 4.1025) == pytest.approx(4.1025)

    def test_a_cheaper_off_peak_rate_lowers_the_blended_value(self):
        split = zone_tou_split("GIS", YEAR)
        blended = blended_rate_thb_per_kwh(split, 4.1025, 2.6)
        assert 2.6 < blended < 4.1025
