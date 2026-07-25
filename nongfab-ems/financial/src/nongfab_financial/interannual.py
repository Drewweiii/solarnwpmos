"""How much the sun at Nong Fab actually varies from year to year (2026-07-25).

`uncertainty.py` needs one number to build the P50/P90 band: the coefficient of
variation of ANNUAL yield. It shipped with 4.0%, taken from the published range
for tropical-monsoon sites (3-5%) because no on-site record exists.

That guess was wrong for this site, and measurably so. NASA POWER publishes
daily surface irradiance for any coordinate back to 1981, free and key-less -
the same source this project already uses for UV. Summing its daily
`ALLSKY_SFC_SW_DWN` into annual totals at Nong Fab's own coordinates over the
26 complete years 2000-2025 gives:

    mean 1,852.6 kWh/m2/yr · std 39.0 · CV = 2.11%
    worst year 2011 = 1,792.1 · best year 2004 = 1,939.1

So the sun here is roughly TWICE as steady as the literature range assumed, and
the P90 band built on 4% was about twice as wide as this site deserves. That
matters in the conservative direction: it was overstating the downside a lender
would underwrite on.

This module keeps the derivation reproducible rather than leaving 2.11 as a
magic constant. `annual_cv_pct` is pure and tested; `scripts/derive_annual_cv.py`
re-runs it against the live API so the figure can be refreshed (and audited)
without anyone having to trust a comment.

Why irradiance and not modelled AC energy: annual PV output is very nearly
proportional to annual irradiance once temperature and soiling are averaged over
a whole year, so the irradiance CV is the right order for the yield CV, and it
avoids compounding this site's own model error into an uncertainty estimate.
That approximation is stated rather than hidden - it is why this is `derived`
rather than `confirmed`.
"""

from __future__ import annotations

import calendar
import statistics
from dataclasses import dataclass

# NASA POWER's fill value for "no data". Anything at or below this is missing,
# never a real reading - dropping it matters because a single -999 would swamp
# an annual sum.
POWER_FILL_VALUE = -900.0

NASA_POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
GHI_PARAMETER = "ALLSKY_SFC_SW_DWN"


@dataclass(frozen=True)
class InterannualStats:
    """Year-to-year spread of annual totals."""

    years_used: int
    first_year: int
    last_year: int
    mean_annual: float
    std_annual: float
    cv_pct: float
    min_year: int
    min_annual: float
    max_year: int
    max_annual: float


def annual_totals(daily: dict[str, float]) -> dict[int, float]:
    """Sum a `{"YYYYMMDD": value}` daily record into annual totals, keeping ONLY
    calendar-complete years.

    Incomplete years are dropped rather than scaled up: a year missing its
    cloudy months would scale to a falsely high total and shrink the very
    variability this exists to measure. Fill values are dropped first, which is
    what can make a year incomplete.
    """
    by_year: dict[int, list[float]] = {}
    for key, value in daily.items():
        if value is None or value <= POWER_FILL_VALUE:
            continue
        try:
            year = int(str(key)[:4])
        except (TypeError, ValueError):
            continue
        by_year.setdefault(year, []).append(float(value))

    complete: dict[int, float] = {}
    for year, values in by_year.items():
        expected = 366 if calendar.isleap(year) else 365
        if len(values) == expected:
            complete[year] = sum(values)
    return complete


def annual_cv_pct(daily: dict[str, float]) -> InterannualStats | None:
    """Interannual coefficient of variation, as a percentage of the mean.

    None when fewer than two complete years survive - one year has no spread,
    and reporting 0% would read as "this site never varies", which is the
    opposite of "we don't know yet".
    """
    totals = annual_totals(daily)
    if len(totals) < 2:
        return None

    values = list(totals.values())
    mean = statistics.mean(values)
    if mean <= 0:
        return None
    std = statistics.stdev(values)
    min_year = min(totals, key=lambda y: totals[y])
    max_year = max(totals, key=lambda y: totals[y])
    return InterannualStats(
        years_used=len(totals),
        first_year=min(totals),
        last_year=max(totals),
        mean_annual=mean,
        std_annual=std,
        cv_pct=std / mean * 100,
        min_year=min_year,
        min_annual=totals[min_year],
        max_year=max_year,
        max_annual=totals[max_year],
    )
