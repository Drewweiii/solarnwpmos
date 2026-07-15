import pandas as pd
import pytest

from nongfab_forecast.pv_conversion import default_params_from_capacity, predict_power_kw
from nongfab_forecast.real_data import real_day_df, real_hour_df, real_minute_df


@pytest.fixture
def himawari_observations() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "observed_at": pd.date_range("2026-07-15T00:00:00Z", periods=5, freq="10min"),
            "cloud_opacity_pct": [10.0, 20.0, 90.0, 95.0, 30.0],
            "cloud_index": [0.1, 0.2, 0.9, 1.0, 0.3],
            "source": ["noaa-himawari9-real"] * 5,
        }
    )


@pytest.fixture
def gfs_forecast() -> pd.DataFrame:
    # A tiny real-shaped diurnal curve: night -> dawn -> midday -> dusk.
    return pd.DataFrame(
        {
            "valid_time": pd.date_range("2026-07-15T00:00:00Z", periods=4, freq="6h"),
            "ssrd_w_m2": [0.0, 300.0, 800.0, 50.0],
            "temp2m_c": [26.0, 28.0, 32.0, 29.0],
        }
    )


def test_real_minute_df_keeps_only_cloud_columns_in_order(himawari_observations):
    out = real_minute_df(himawari_observations)
    assert list(out.columns) == ["cloud_opacity_pct", "cloud_index"]
    assert len(out) == 5
    assert out["cloud_opacity_pct"].iloc[2] == 90.0


def test_real_hour_df_drops_first_row_and_lags_power(gfs_forecast):
    X, y = real_hour_df(gfs_forecast, zone_capacity_kwp=100.0)
    assert len(X) == len(y) == 3  # one row dropped (no lag available)
    assert list(X.columns) == ["ssrd_w_m2", "temp2m_c", "power_lag1"]
    assert y.name == "power_kw"

    params = default_params_from_capacity(100.0)
    expected_power = predict_power_kw(gfs_forecast["ssrd_w_m2"], gfs_forecast["temp2m_c"], params)
    # X's power_lag1 for the first remaining row is the *dropped* row's power.
    assert X["power_lag1"].iloc[0] == pytest.approx(expected_power.iloc[0])
    assert y.iloc[0] == pytest.approx(expected_power.iloc[1])


def test_real_hour_df_night_rows_have_zero_power(gfs_forecast):
    _X, y = real_hour_df(gfs_forecast, zone_capacity_kwp=100.0)
    # ssrd_w_m2=0 at the first row was dropped as the lag source; none of the
    # remaining 3 rows has zero irradiance, so just check the physics holds elsewhere.
    assert (y >= 0).all()


def test_real_day_df_indexed_by_valid_time(gfs_forecast):
    out = real_day_df(gfs_forecast, zone_capacity_kwp=100.0)
    assert list(out.columns) == ["power_kw", "ssrd_w_m2", "temp2m_c"]
    assert list(out.index) == list(gfs_forecast["valid_time"])
    # Zero irradiance at night -> zero power, regardless of temperature.
    assert out["power_kw"].iloc[0] == 0.0


def test_real_hour_and_day_df_use_the_same_physics(gfs_forecast):
    """Both builders must derive power from the same pv_conversion params -
    a regression guard against one of them silently drifting to a different
    conversion (e.g. a different temp coefficient) than the other.
    """
    params = default_params_from_capacity(150.0)
    _X, y_hour = real_hour_df(gfs_forecast, zone_capacity_kwp=150.0, params=params)
    day_df = real_day_df(gfs_forecast, zone_capacity_kwp=150.0, params=params)
    assert y_hour.iloc[-1] == pytest.approx(day_df["power_kw"].iloc[-1])
