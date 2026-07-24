import numpy as np
import pytest

from nongfab_features import soiling


def test_wind_speed_from_components():
    assert soiling.wind_speed_ms(3.0, 4.0) == pytest.approx(5.0)
    # NaN components are treated as calm.
    assert soiling.wind_speed_ms(np.nan, np.nan) == pytest.approx(0.0)


def test_wind_from_bearing_meteorological_convention():
    # Wind blowing TOWARD the north (v>0) comes FROM the south -> 180 deg.
    assert soiling.wind_from_bearing_deg(0.0, 5.0) == pytest.approx(180.0)
    # Blowing toward the east (u>0) comes FROM the west -> 270 deg.
    assert soiling.wind_from_bearing_deg(5.0, 0.0) == pytest.approx(270.0)


def test_onshore_factor_peaks_for_wind_off_the_sea():
    # Sea is to the south (bearing 180): a southerly wind (from the sea, v>0)
    # is fully onshore; a northerly (from land, v<0) is fully offshore -> 0.
    onshore = soiling.onshore_factor(0.0, 5.0)  # from south
    offshore = soiling.onshore_factor(0.0, -5.0)  # from north
    assert onshore == pytest.approx(1.0)
    assert offshore == pytest.approx(0.0)
    # Calm -> 0.
    assert soiling.onshore_factor(0.0, 0.0) == pytest.approx(0.0)


def test_salt_soiling_index_bounds_and_direction_sensitivity():
    # Strong humid sea breeze -> high index; equal-strength dry offshore -> ~0.
    humid_onshore = soiling.salt_soiling_index(0.0, 10.0, 90.0)
    dry_offshore = soiling.salt_soiling_index(0.0, -10.0, 20.0)
    assert 0.0 <= float(dry_offshore) <= float(humid_onshore) <= 1.0
    assert float(humid_onshore) > 0.5
    assert float(dry_offshore) == pytest.approx(0.0)


def test_salt_soiling_index_scales_with_humidity():
    dry = soiling.salt_soiling_index(0.0, 8.0, 30.0)
    wet = soiling.salt_soiling_index(0.0, 8.0, 95.0)
    assert float(wet) > float(dry)


def test_functions_are_vectorized_over_arrays():
    u = np.array([0.0, 0.0, 3.0])
    v = np.array([5.0, -5.0, 4.0])
    rh = np.array([80.0, 80.0, 50.0])
    idx = soiling.salt_soiling_index(u, v, rh)
    assert idx.shape == (3,)
    assert np.all((idx >= 0) & (idx <= 1))
    # element 1 is fully offshore -> exactly 0
    assert idx[1] == pytest.approx(0.0)
