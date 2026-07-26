"""GET /poster (2026-07-26, project S) - a year of real solar geometry, and the
resolution boundary the poster is not allowed to cross."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nongfab_api.routes_poster import build_poster


def test_poster_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/poster/GIS").status_code == 401


def test_unknown_zone_names_the_real_ones(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/poster/Atlantis", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    assert "GIS" in resp.json()["detail"]


def test_absurd_year_is_rejected_rather_than_computed(app, token_factory):
    # pvlib will cheerfully return solar positions for year 3; a poster of them
    # would be a plausible-looking picture of nothing.
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/poster/GIS?year=3", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400


def test_the_geometry_is_real_astronomy_for_this_site():
    """Not a smoke test. These are checkable facts about 12.71°N, and if the
    coordinates or the timezone conversion were wrong they would all move."""
    poster = build_poster("GIS", 2026)

    assert len(poster.days) == 365
    assert round(poster.lat, 2) == 12.71

    # Day length at this latitude swings roughly 11.4h to 12.9h. A site read at
    # the equator would be flat at 12h; one read in Europe would swing far more.
    daylight = [d.daylight_hours for d in poster.days if d.daylight_hours is not None]
    assert 11.2 < min(daylight) < 11.6
    assert 12.7 < max(daylight) < 13.1

    # Longest day near the June solstice, shortest near December's - and both
    # are read off the computed series, not assumed.
    assert 165 <= poster.longest_day <= 178
    assert 348 <= poster.shortest_day <= 360

    # Solar noon is high all year here and passes almost overhead in spring.
    noon = [d.noon_elevation_deg for d in poster.days if d.noon_elevation_deg is not None]
    assert min(noon) > 50
    assert max(noon) > 85


def test_sunrise_is_morning_and_sunset_is_evening_in_thai_local_time():
    """The one bug this route could plausibly ship: leaving the times in UTC.
    Seven hours off would put 'sunrise' before midnight and look merely odd
    rather than wrong."""
    poster = build_poster("GIS", 2026)
    for day in poster.days:
        assert day.sunrise_hour is not None and day.sunset_hour is not None
        assert 5.0 < day.sunrise_hour < 7.0, day
        assert 17.5 < day.sunset_hour < 19.5, day
        assert day.sunset_hour > day.sunrise_hour


def test_energy_stays_at_monthly_resolution():
    """The honesty constraint that shaped the feature. The annual model is
    twelve representative days; the payload must not pretend otherwise by
    carrying a per-day energy figure the poster could colour with."""
    poster = build_poster("GIS", 2026)
    assert len(poster.months) == 12
    assert all(m.ac_energy_kwh > 0 for m in poster.months)
    # No per-day energy field exists to be misused.
    assert not hasattr(poster.days[0], "ac_energy_kwh")
    assert "รายเดือน" in poster.energy_note


def test_month_day_counts_sum_to_the_year_that_was_drawn():
    # The frontend slices 365 rays into months using these counts; if they did
    # not add up, every month label after the error would point at the wrong arc.
    for year, expected in ((2026, 365), (2028, 366)):
        poster = build_poster("GIS", year)
        assert sum(m.days_in_month for m in poster.months) == expected
        assert len(poster.days) == expected


def test_the_rainy_season_is_marked():
    poster = build_poster("GIS", 2026)
    rainy = {m.month for m in poster.months if m.is_rainy_season}
    assert rainy == {6, 7, 8, 9, 10}
