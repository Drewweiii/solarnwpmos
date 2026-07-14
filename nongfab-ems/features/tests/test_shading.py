import pytest
from nongfab_features.panel_geometry import Panel, ZoneLayout
from nongfab_features.shading import (
    average_solar_access_pct,
    row_shaded_fraction,
    zone_solar_access,
)

TILT = 10.0
AZIMUTH = 180.0
PITCH = 3.0
SLANT_HEIGHT = 1.303  # real module short side, meters


def test_night_is_fully_shaded():
    assert row_shaded_fraction(TILT, AZIMUTH, PITCH, SLANT_HEIGHT, solar_elevation_deg=-5, solar_azimuth_deg=AZIMUTH) == 1.0


def test_sun_directly_overhead_casts_negligible_shadow():
    fraction = row_shaded_fraction(TILT, AZIMUTH, PITCH, SLANT_HEIGHT, solar_elevation_deg=90, solar_azimuth_deg=AZIMUTH)
    assert fraction == pytest.approx(0.0, abs=1e-6)


def test_sun_directly_behind_the_array_casts_no_forward_shadow():
    # Sun's azimuth 180 degrees from the array's own azimuth = shining on
    # the array's back, not its front - this simplified model has no
    # backward-onto-next-row shadow in that case.
    fraction = row_shaded_fraction(TILT, AZIMUTH, PITCH, SLANT_HEIGHT, solar_elevation_deg=10, solar_azimuth_deg=AZIMUTH - 180)
    assert fraction == 0.0


def test_sun_side_on_casts_no_shadow_in_this_2d_model():
    fraction = row_shaded_fraction(TILT, AZIMUTH, PITCH, SLANT_HEIGHT, solar_elevation_deg=10, solar_azimuth_deg=AZIMUTH + 90)
    assert fraction == 0.0


def test_sun_dead_on_at_low_elevation_shades_meaningfully():
    fraction = row_shaded_fraction(TILT, AZIMUTH, PITCH, SLANT_HEIGHT, solar_elevation_deg=5, solar_azimuth_deg=AZIMUTH)
    assert 0.0 < fraction <= 1.0


def test_shading_increases_as_sun_gets_lower():
    fractions = [
        row_shaded_fraction(TILT, AZIMUTH, PITCH, SLANT_HEIGHT, solar_elevation_deg=e, solar_azimuth_deg=AZIMUTH)
        for e in (40, 20, 10, 5, 2)
    ]
    assert fractions == sorted(fractions)  # monotonically non-decreasing as elevation drops


def test_tighter_row_pitch_increases_shading():
    tight = row_shaded_fraction(TILT, AZIMUTH, 1.5, SLANT_HEIGHT, solar_elevation_deg=15, solar_azimuth_deg=AZIMUTH)
    loose = row_shaded_fraction(TILT, AZIMUTH, 6.0, SLANT_HEIGHT, solar_elevation_deg=15, solar_azimuth_deg=AZIMUTH)
    assert tight >= loose


def test_fraction_is_always_clamped_to_0_1():
    fraction = row_shaded_fraction(TILT, AZIMUTH, 0.01, SLANT_HEIGHT, solar_elevation_deg=0.5, solar_azimuth_deg=AZIMUTH)
    assert 0.0 <= fraction <= 1.0


def _two_row_layout() -> ZoneLayout:
    panels = [
        Panel(block_id="b", row=0, col=0, east_m=0, north_m=0, width_m=1.0, slant_height_m=SLANT_HEIGHT, tilt_deg=TILT, azimuth_deg=AZIMUTH),
        Panel(block_id="b", row=1, col=0, east_m=0, north_m=PITCH, width_m=1.0, slant_height_m=SLANT_HEIGHT, tilt_deg=TILT, azimuth_deg=AZIMUTH),
    ]
    return ZoneLayout(zone_id="test", tilt_deg=TILT, azimuth_deg=AZIMUTH, row_pitch_m=PITCH, panels=panels)


def test_front_row_is_never_shaded_even_at_low_sun():
    layout = _two_row_layout()
    access = zone_solar_access(layout, solar_elevation_deg=3, solar_azimuth_deg=AZIMUTH)
    front = next(p for p in access if p.row == 0)
    assert front.solar_access_pct == 100.0


def test_back_row_is_shaded_when_front_row_blocks_low_sun():
    layout = _two_row_layout()
    access = zone_solar_access(layout, solar_elevation_deg=3, solar_azimuth_deg=AZIMUTH)
    back = next(p for p in access if p.row == 1)
    assert back.solar_access_pct < 100.0


def test_zone_solar_access_at_night_shades_every_row_including_front():
    layout = _two_row_layout()
    access = zone_solar_access(layout, solar_elevation_deg=-1, solar_azimuth_deg=AZIMUTH)
    assert all(p.solar_access_pct == 0.0 for p in access)


def test_average_solar_access_pct_matches_manual_mean():
    layout = _two_row_layout()
    access = zone_solar_access(layout, solar_elevation_deg=3, solar_azimuth_deg=AZIMUTH)
    expected = sum(p.solar_access_pct for p in access) / len(access)
    assert average_solar_access_pct(access) == pytest.approx(expected)


def test_average_solar_access_pct_of_empty_layout_is_100():
    assert average_solar_access_pct([]) == 100.0
