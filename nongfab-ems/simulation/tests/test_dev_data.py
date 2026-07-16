from datetime import datetime, timezone

from nongfab_simulation.dev_data import live_efficiency_factor


def test_live_efficiency_factor_is_bounded():
    now = datetime(2026, 7, 16, 6, 30, 0, tzinfo=timezone.utc)
    for zone in ("GIS", "ISB", "Jetty"):
        value = live_efficiency_factor(zone, now)
        assert 0.85 <= value <= 1.0


def test_live_efficiency_factor_is_nearly_stable_across_a_quick_refresh():
    # Continuously interpolated across each 5-minute bucket (see the
    # function's own docstring), so a 10s gap isn't bit-for-bit identical -
    # but should be a tiny drift, not a jump, so two refreshes seconds apart
    # (e.g. the dashboard's 60s poll) read as "the same" to a human.
    base = datetime(2026, 7, 16, 6, 30, 0, tzinfo=timezone.utc)
    a = live_efficiency_factor("GIS", base)
    b = live_efficiency_factor("GIS", base.replace(second=10))
    assert abs(a - b) < 0.01


def test_live_efficiency_factor_varies_across_buckets():
    early = datetime(2026, 7, 16, 6, 0, 0, tzinfo=timezone.utc)
    later = datetime(2026, 7, 16, 6, 30, 0, tzinfo=timezone.utc)
    assert live_efficiency_factor("GIS", early) != live_efficiency_factor("GIS", later)


def test_live_efficiency_factor_differs_by_zone():
    now = datetime(2026, 7, 16, 6, 30, 0, tzinfo=timezone.utc)
    assert live_efficiency_factor("GIS", now) != live_efficiency_factor("ISB", now)


def test_live_efficiency_factor_interpolates_smoothly_across_a_bucket_boundary():
    # Just before and just after a 5-minute bucket boundary should be close
    # to each other, not a hard jump - that's the whole point of the linear
    # interpolation (see the function's own docstring).
    just_before = datetime(2026, 7, 16, 6, 4, 59, tzinfo=timezone.utc)
    just_after = datetime(2026, 7, 16, 6, 5, 1, tzinfo=timezone.utc)
    a = live_efficiency_factor("GIS", just_before)
    b = live_efficiency_factor("GIS", just_after)
    assert abs(a - b) < 0.02
