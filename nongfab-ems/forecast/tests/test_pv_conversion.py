import numpy as np
import pandas as pd
import pytest

from nongfab_forecast.pv_conversion import (
    STC_IRRADIANCE_W_M2,
    STC_TEMP_C,
    default_params_from_capacity,
    fit_pv_conversion_model,
    nong_fab_simulated_zone_ids,
    nong_fab_zone_capacities_kwp,
    predict_power_kw,
)


def test_default_params_reproduce_capacity_at_stc():
    params = default_params_from_capacity(capacity_kwp=200.0)
    power_at_stc = predict_power_kw(STC_IRRADIANCE_W_M2, STC_TEMP_C, params)
    assert power_at_stc == pytest.approx(200.0, abs=1e-6)


def test_default_params_derate_with_higher_temperature():
    params = default_params_from_capacity(capacity_kwp=200.0)
    power_hot = predict_power_kw(STC_IRRADIANCE_W_M2, 45.0, params)
    power_stc = predict_power_kw(STC_IRRADIANCE_W_M2, STC_TEMP_C, params)
    assert power_hot < power_stc  # negative temp coefficient -> hotter is worse


def test_default_params_rejects_nonpositive_capacity():
    with pytest.raises(ValueError):
        default_params_from_capacity(capacity_kwp=0.0)


def test_predict_power_clips_at_zero():
    params = default_params_from_capacity(capacity_kwp=100.0)
    power = predict_power_kw(0.0, 25.0, params)  # night: irradiance=0
    assert power >= 0


def test_predict_power_vectorized_over_series():
    params = default_params_from_capacity(capacity_kwp=100.0)
    irradiance = pd.Series([0.0, 500.0, 1000.0])
    temp = pd.Series([25.0, 25.0, 25.0])
    power = predict_power_kw(irradiance, temp, params)
    assert isinstance(power, pd.Series)
    assert list(power) == pytest.approx([0.0, 50.0, 100.0], abs=1e-6)


def test_fit_pv_conversion_model_recovers_known_linear_relationship():
    rng = np.random.default_rng(0)
    irradiance = rng.uniform(0, 1000, size=200)
    temp = rng.uniform(20, 40, size=200)
    true_beta, true_gamma, true_intercept = 0.2, -0.5, 5.0
    power = true_beta * irradiance + true_gamma * temp + true_intercept

    params = fit_pv_conversion_model(pd.Series(irradiance), pd.Series(temp), pd.Series(power))

    assert params.beta_kw_per_wm2 == pytest.approx(true_beta, abs=1e-6)
    assert params.gamma_kw_per_c == pytest.approx(true_gamma, abs=1e-6)
    assert params.intercept_kw == pytest.approx(true_intercept, abs=1e-6)


def test_fit_pv_conversion_model_drops_nan_rows():
    irradiance = pd.Series([100.0, 200.0, np.nan, 400.0])
    temp = pd.Series([25.0, 26.0, 27.0, 28.0])
    power = pd.Series([20.0, 40.0, 60.0, 80.0])

    params = fit_pv_conversion_model(irradiance, temp, power)
    assert params.beta_kw_per_wm2 is not None  # succeeds despite the NaN row


def test_fit_pv_conversion_model_rejects_too_few_rows():
    with pytest.raises(ValueError):
        fit_pv_conversion_model(pd.Series([100.0, 200.0]), pd.Series([25.0, 26.0]), pd.Series([20.0, 40.0]))


def test_nong_fab_zone_capacities_matches_config_assets_yaml():
    capacities = nong_fab_zone_capacities_kwp()
    assert set(capacities) == {"GIS", "ISB", "Jetty"}
    assert capacities["Jetty"] == pytest.approx(228.8)
    assert all(v > 0 for v in capacities.values())


def test_nong_fab_simulated_zone_ids_flags_jetty_only():
    # Jetty has no panels installed yet (confirmed by satellite imagery); GIS/ISB do.
    assert nong_fab_simulated_zone_ids() == {"Jetty"}
