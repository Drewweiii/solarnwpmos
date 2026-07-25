"""Does this array produce during the expensive hours? (2026-07-25, project G)

`green_savings.py` values every kWh this site makes at the TOU **Peak** rate,
and its own docstring already called that "a documented approximation - it does
not net out weekend/holiday off-peak hours; refine if a real half-hourly
consumption profile appears". This is that refinement, and it needs no
consumption profile after all - only the tariff calendar and the array's own
generation shape.

THE TARIFF WINDOWS (PEA/MEA Type 4, large general service):
  * On Peak  - 09:00 to 22:00, Monday to Friday
  * Off Peak - everything else: 22:00 to 09:00 on weekdays, and the WHOLE of
               Saturday, Sunday and the qualifying public holidays

Two consequences fall straight out and neither is obvious:

  1. WEEKENDS. Two days in seven produce entirely at the off-peak rate. Nothing
     about the array changes; the calendar simply pays less for it.
  2. MORNINGS. Peak does not begin until 09:00, but the array starts producing
     around 06:00. Every kWh made in those three hours is off-peak even on a
     working day - and at this latitude that is a real slice of the morning.

WHAT IS REAL HERE AND WHAT IS NOT.
  REAL   The calendar. Weekdays and weekends are counted from the actual year,
         not approximated as 5/7.
  REAL   The generation shape, from the same representative-day and POA
         machinery the published annual figure uses.
  NOT MODELLED  Public holidays. PEA/MEA count only a defined list of them as
         off-peak - not every public holiday qualifies - and that list is
         published annually. Rather than guess it, holidays are exposed as a
         settable count that defaults to ZERO, so the split shown is a
         conservative floor: the true off-peak share can only be HIGHER than
         what this reports, never lower.

The money side is deliberately left to the caller. This module answers "how much
energy lands in each window", which is a fact; converting that to baht needs the
Off-Peak rate from the tariff announcement, which this project does not yet have.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

import numpy as np

from .pipeline import _representative_day_irradiance_temp, simulate_zone_baseline

# PEA/MEA Type 4 TOU. Peak runs 09:00 up to but not including 22:00, on
# Monday-Friday only.
PEAK_START_HOUR = 9
PEAK_END_HOUR = 22


def is_peak_hour(hour: int) -> bool:
    """Whether a clock hour falls in the peak window, ignoring the day of week.
    Split out because the hour test and the weekday test fail differently: an
    off-by-one here silently moves three hours of morning production between
    windows, and it is the sort of thing that looks right in a total."""
    return PEAK_START_HOUR <= hour < PEAK_END_HOUR


def weekday_count(year: int, month: int) -> tuple[int, int]:
    """(weekdays, weekend days) in a real calendar month.

    Counted rather than approximated as 5/7: month lengths and where they start
    make the real ratio wander by more than a day either way, and this feeds a
    money figure.
    """
    days_in_month = calendar.monthrange(year, month)[1]
    weekend = sum(1 for day in range(1, days_in_month + 1) if date(year, month, day).weekday() >= 5)
    return days_in_month - weekend, weekend


@dataclass(frozen=True)
class TouSplit:
    """A year's generation divided by tariff window."""

    peak_kwh: float
    offpeak_kwh: float
    offpeak_holiday_days: int

    @property
    def total_kwh(self) -> float:
        return self.peak_kwh + self.offpeak_kwh

    @property
    def peak_share_pct(self) -> float:
        if self.total_kwh <= 0.0:
            return 0.0
        return 100.0 * self.peak_kwh / self.total_kwh

    @property
    def offpeak_share_pct(self) -> float:
        return 100.0 - self.peak_share_pct


def zone_tou_split(zone_id: str, year: int, offpeak_holiday_days: int = 0) -> TouSplit:
    """Annual generation split into peak and off-peak kWh for one zone.

    `offpeak_holiday_days` are working days that the tariff treats as off-peak.
    They are subtracted from the weekday count and added to the weekend count,
    which is exactly what a holiday does to the bill. Defaults to zero so the
    reported peak share is an upper bound - see the module docstring.
    """
    holidays_left = max(0, offpeak_holiday_days)
    peak_total = 0.0
    offpeak_total = 0.0

    for month in range(1, 13):
        index, ghi, temp = _representative_day_irradiance_temp(month, year=year)
        baseline = simulate_zone_baseline(zone_id, ghi, temp, index)
        power = baseline.ac_power_kw.to_numpy()
        hours = np.asarray([ts.hour for ts in index])

        # Hourly samples, so kW over one hour is kWh.
        peak_day_kwh = float(power[[is_peak_hour(h) for h in hours]].sum())
        whole_day_kwh = float(power.sum())

        weekdays, weekend_days = weekday_count(year, month)
        # Spread the holiday allowance across the year in month order; each one
        # converts a working day into a fully off-peak one.
        holidays_here = min(holidays_left, weekdays)
        holidays_left -= holidays_here
        working_days = weekdays - holidays_here
        offpeak_days = weekend_days + holidays_here

        peak_total += peak_day_kwh * working_days
        offpeak_total += (whole_day_kwh - peak_day_kwh) * working_days
        offpeak_total += whole_day_kwh * offpeak_days

    return TouSplit(peak_kwh=peak_total, offpeak_kwh=offpeak_total, offpeak_holiday_days=offpeak_holiday_days)


def blended_rate_thb_per_kwh(split: TouSplit, peak_rate: float, offpeak_rate: float) -> float:
    """The single rate that would price this generation the same way the two
    real rates do. Directly comparable with the flat rate `green_savings` uses,
    which is the point - the gap between them is the size of the approximation.
    """
    if split.total_kwh <= 0.0:
        return peak_rate
    return (split.peak_kwh * peak_rate + split.offpeak_kwh * offpeak_rate) / split.total_kwh
