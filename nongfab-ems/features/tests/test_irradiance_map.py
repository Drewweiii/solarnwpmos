import pytest
from nongfab_common.assets import load_assets

from nongfab_features.irradiance_map import (
    MAX_DISPLAY_GHI_W_M2,
    grid_points,
    irradiance_grid,
)


def test_grid_points_returns_n_squared_points():
    points = grid_points(n=5)
    assert len(points) == 25


def test_grid_points_span_the_plant_target_bbox():
    registry = load_assets()
    from nongfab_common.assets import target_bbox

    lat_min, lat_max, lon_min, lon_max = target_bbox(registry)
    points = grid_points(registry, n=10)
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    assert min(lats) == pytest.approx(lat_min)
    assert max(lats) == pytest.approx(lat_max)
    assert min(lons) == pytest.approx(lon_min)
    assert max(lons) == pytest.approx(lon_max)


def test_irradiance_grid_is_zero_at_night_clearsky():
    grid = irradiance_grid(clearsky_ghi_w_m2=0.0, epoch_seconds=1_800_000_000, n=4)
    assert all(p.ghi_w_m2 == 0.0 for p in grid)


def test_irradiance_grid_varies_spatially_under_a_clear_midday_sky():
    grid = irradiance_grid(clearsky_ghi_w_m2=900.0, epoch_seconds=1_800_000_000, n=6)
    values = {p.ghi_w_m2 for p in grid}
    assert len(values) > 1  # cloud factor differs point to point, not a flat overlay


def test_irradiance_grid_clips_to_max_display_range():
    grid = irradiance_grid(clearsky_ghi_w_m2=1400.0, epoch_seconds=1_800_000_000, n=4)
    assert all(0.0 <= p.ghi_w_m2 <= MAX_DISPLAY_GHI_W_M2 for p in grid)


def test_irradiance_grid_cloud_factor_within_bounds():
    grid = irradiance_grid(clearsky_ghi_w_m2=900.0, epoch_seconds=1_800_000_000, n=6)
    assert all(0.0 <= p.cloud_factor <= 1.0 for p in grid)


def test_irradiance_grid_deterministic_for_same_time_and_position():
    grid_a = irradiance_grid(clearsky_ghi_w_m2=900.0, epoch_seconds=1_800_000_000, n=4)
    grid_b = irradiance_grid(clearsky_ghi_w_m2=900.0, epoch_seconds=1_800_000_000, n=4)
    assert [p.ghi_w_m2 for p in grid_a] == [p.ghi_w_m2 for p in grid_b]


def test_irradiance_grid_changes_over_time():
    grid_a = irradiance_grid(clearsky_ghi_w_m2=900.0, epoch_seconds=1_800_000_000, n=6)
    grid_b = irradiance_grid(clearsky_ghi_w_m2=900.0, epoch_seconds=1_800_003_600 * 3, n=6)
    assert [p.cloud_factor for p in grid_a] != [p.cloud_factor for p in grid_b]
