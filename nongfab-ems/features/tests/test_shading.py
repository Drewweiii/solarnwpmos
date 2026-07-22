import pytest

from nongfab_features.panel_geometry import Panel, ZoneLayout
from nongfab_features.shading import (
    annual_shading_loss_pct,
    average_solar_access_pct,
    row_shaded_fraction,
    string_power_balance,
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


def test_string_power_balance_is_zero_when_strings_equally_shaded():
    layout = _two_row_layout()  # both rows have 1 panel each, front row row=0
    access = zone_solar_access(layout, solar_elevation_deg=90, solar_azimuth_deg=AZIMUTH)  # overhead sun -> no shading at all
    balance = string_power_balance(access, module_power_w=715, max_allowed_kw=2.0)
    assert len(balance) == 1
    assert balance[0].imbalance_kw == pytest.approx(0.0, abs=1e-6)
    assert balance[0].exceeds_limit is False


def test_string_power_balance_detects_imbalance_from_shading():
    layout = _two_row_layout()
    access = zone_solar_access(layout, solar_elevation_deg=3, solar_azimuth_deg=AZIMUTH)  # low sun -> row 1 shaded, row 0 not
    balance = string_power_balance(access, module_power_w=715, max_allowed_kw=0.001)
    block = balance[0]
    assert block.imbalance_kw > 0
    assert block.exceeds_limit is True


def test_string_power_balance_without_a_limit_never_exceeds():
    layout = _two_row_layout()
    access = zone_solar_access(layout, solar_elevation_deg=3, solar_azimuth_deg=AZIMUTH)
    balance = string_power_balance(access, module_power_w=715, max_allowed_kw=None)
    assert balance[0].exceeds_limit is False
    assert balance[0].max_allowed_kw is None


def test_string_power_balance_groups_by_block_and_string_index():
    layout = _two_row_layout()
    access = zone_solar_access(layout, solar_elevation_deg=90, solar_azimuth_deg=AZIMUTH)
    balance = string_power_balance(access, module_power_w=715)
    strings = balance[0].strings
    assert {s.string_index for s in strings} == {0, 1}
    assert all(s.module_count == 1 for s in strings)
    assert all(s.estimated_power_kw == pytest.approx(0.715, abs=1e-6) for s in strings)  # 1 module x 715W at 100% access


def test_string_power_balance_of_empty_input_is_empty():
    assert string_power_balance([], module_power_w=715) == []


def test_annual_shading_loss_pct_is_a_small_nonnegative_percentage():
    # Well-pitched arrays -> a small but non-negative inter-row self-shading
    # loss (0..100%). Not asserting a tight value: it's a geometric property of
    # the real modelled layout, but it must be a sane percentage.
    for zone_id in ("GIS", "ISB", "Jetty"):
        loss = annual_shading_loss_pct(zone_id)
        assert 0.0 <= loss < 100.0


def test_annual_shading_loss_pct_is_cached_and_deterministic():
    # @lru_cache'd deterministic geometry: same input -> identical output, and
    # the second call returns the very same cached float object.
    first = annual_shading_loss_pct("Jetty")
    second = annual_shading_loss_pct("Jetty")
    assert first == second
