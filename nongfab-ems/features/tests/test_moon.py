from datetime import datetime, timedelta, timezone

import pytest

from nongfab_features.moon import moon_illumination, moon_position

NONG_FAB_LAT, NONG_FAB_LON = 12.68, 101.12


def test_moon_position_returns_valid_ranges():
    az, el = moon_position(datetime(2026, 7, 18, 12, tzinfo=timezone.utc), NONG_FAB_LAT, NONG_FAB_LON)
    assert 0.0 <= az < 360.0
    assert -90.0 <= el <= 90.0


def test_moon_position_accepts_naive_datetime_as_utc():
    naive_az, naive_el = moon_position(datetime(2026, 7, 18, 12), NONG_FAB_LAT, NONG_FAB_LON)
    aware_az, aware_el = moon_position(datetime(2026, 7, 18, 12, tzinfo=timezone.utc), NONG_FAB_LAT, NONG_FAB_LON)
    assert naive_az == pytest.approx(aware_az)
    assert naive_el == pytest.approx(aware_el)


def test_moon_position_changes_smoothly_over_small_time_steps():
    """No discontinuous jumps a real moon (moving ~0.5deg/hour across the
    sky) couldn't make - catches a sign-flip/wraparound bug in the
    topocentric rotation math, not just "does it run"."""
    now = datetime(2026, 7, 18, 6, tzinfo=timezone.utc)
    prev_az, prev_el = moon_position(now, NONG_FAB_LAT, NONG_FAB_LON)
    for minute in range(10, 24 * 60, 10):
        az, el = moon_position(now + timedelta(minutes=minute), NONG_FAB_LAT, NONG_FAB_LON)
        # Elevation is continuous - the moon crosses the sky in a smooth arc,
        # never more than a couple degrees in a 10-minute step.
        assert abs(el - prev_el) < 5.0
        # Azimuth is continuous too, once wraparound (359 -> 0) is accounted
        # for - a generous threshold since azimuth genuinely swings fast
        # near zenith (a coordinate singularity, not a bug - the same thing
        # happens to the sun's own azimuth near solar noon at low latitudes).
        az_delta = min(abs(az - prev_az), 360 - abs(az - prev_az))
        assert az_delta < 20.0
        prev_az, prev_el = az, el


def test_moon_rises_and_sets_within_roughly_one_lunar_day():
    """The Moon's own day (moonrise to moonrise) is ~24h50m, not exactly
    24h - over a 30-hour window from a below-horizon start, it must cross
    the horizon (rise) at least once, proving this isn't returning a static
    or always-negative/always-positive elevation."""
    now = datetime(2026, 7, 18, 0, tzinfo=timezone.utc)
    _, start_el = moon_position(now, NONG_FAB_LAT, NONG_FAB_LON)
    elevations = [moon_position(now + timedelta(minutes=m), NONG_FAB_LAT, NONG_FAB_LON)[1] for m in range(0, 30 * 60, 30)]
    crossed = any((e < 0) != (start_el < 0) for e in elevations)
    assert crossed


def test_moon_position_differs_from_a_fixed_reference_across_days():
    """The Moon visibly moves against the same time-of-day from one day to
    the next (~12-13deg/day in longitude) - this would stay constant if the
    function were accidentally ignoring `when` (e.g. a hardcoded epoch bug)."""
    az1, el1 = moon_position(datetime(2026, 7, 18, 12, tzinfo=timezone.utc), NONG_FAB_LAT, NONG_FAB_LON)
    az2, el2 = moon_position(datetime(2026, 7, 25, 12, tzinfo=timezone.utc), NONG_FAB_LAT, NONG_FAB_LON)
    assert (az1, el1) != (az2, el2)
    assert abs(az1 - az2) > 1.0 or abs(el1 - el2) > 1.0


def test_moon_illumination_full_cycle_bounds_and_waxing_flag():
    # Fraction is always a valid 0..1, and the waxing flag flips exactly once
    # per synodic month (new -> full growing, full -> new shrinking).
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fracs = []
    waxings = []
    for day in range(0, 30):
        f, wax = moon_illumination(base + timedelta(days=day))
        assert 0.0 <= f <= 1.0
        fracs.append(f)
        waxings.append(wax)
    # Over a full month it must reach both a near-new (<0.1) and near-full (>0.9).
    assert min(fracs) < 0.1
    assert max(fracs) > 0.9
    # Both waxing and waning phases occur within the month.
    assert True in waxings and False in waxings


def test_moon_illumination_matches_known_july_2026_crescent():
    # 2026-07-19 is a waxing crescent (~a quarter lit) - the date the 3D-view
    # phase marker was built against (see routes_solar3d /moon-path).
    f, wax = moon_illumination(datetime(2026, 7, 19, 12, tzinfo=timezone.utc))
    assert wax is True
    assert 0.1 < f < 0.45
