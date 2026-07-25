"""Re-derive the interannual yield variability at Nong Fab from NASA POWER.

Run this to refresh (or audit) `financial.annual_yield_cv_pct`. It prints the
per-year totals as well as the headline CV, so the number can be checked rather
than trusted:

    python scripts/derive_annual_cv.py
    python scripts/derive_annual_cv.py --start 1990 --end 2025

Kept as a script rather than wired into the app on purpose: this is a figure
that changes on the scale of a decade, and an app that silently re-derived it
per request would make the published P90 band move for no visible reason.
"""

from __future__ import annotations

import argparse
import json
import urllib.request

from nongfab_financial.interannual import GHI_PARAMETER, NASA_POWER_DAILY_URL, annual_cv_pct, annual_totals

# Nong Fab's nominal centre, matching config/assets.yaml's site.nominal_center.
NONG_FAB_LAT = 12.71
NONG_FAB_LON = 101.15


def fetch_daily(lat: float, lon: float, start_year: int, end_year: int) -> dict[str, float]:
    url = (
        f"{NASA_POWER_DAILY_URL}?parameters={GHI_PARAMETER}&community=RE"
        f"&longitude={lon}&latitude={lat}&start={start_year}0101&end={end_year}1231&format=JSON"
    )
    with urllib.request.urlopen(url, timeout=180) as response:  # noqa: S310 - fixed NASA host
        payload = json.load(response)
    return payload["properties"]["parameter"][GHI_PARAMETER]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=NONG_FAB_LAT)
    parser.add_argument("--lon", type=float, default=NONG_FAB_LON)
    parser.add_argument("--start", type=int, default=2000)
    parser.add_argument("--end", type=int, default=2025)
    args = parser.parse_args()

    daily = fetch_daily(args.lat, args.lon, args.start, args.end)
    totals = annual_totals(daily)
    for year in sorted(totals):
        print(f"  {year}: {totals[year]:8.1f} kWh/m2/yr")

    stats = annual_cv_pct(daily)
    if stats is None:
        print("\nNot enough complete years to derive a CV.")
        return
    print(
        f"\nlat/lon         : {args.lat}, {args.lon}"
        f"\ncomplete years  : {stats.years_used} ({stats.first_year}-{stats.last_year})"
        f"\nmean annual GHI : {stats.mean_annual:,.1f} kWh/m2/yr"
        f"\nstd dev         : {stats.std_annual:,.1f}"
        f"\ninterannual CV  : {stats.cv_pct:.2f} %   <- financial.annual_yield_cv_pct"
        f"\nworst year      : {stats.min_year} = {stats.min_annual:,.1f}"
        f"\nbest year       : {stats.max_year} = {stats.max_annual:,.1f}"
    )


if __name__ == "__main__":
    main()
