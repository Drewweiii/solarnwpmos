import numpy as np
import pandas as pd
import pytest

from nongfab_simulation.monte_carlo import (
    ScenarioDistribution,
    evaluate_monte_carlo_interval,
    monte_carlo_prediction_interval,
    monte_carlo_scenario_simulation,
)


def _point_forecast(n=50, level=100.0):
    idx = pd.date_range("2026-07-14", periods=n, freq="h", tz="UTC")
    return pd.Series(level, index=idx)


def test_monte_carlo_interval_has_expected_shape_and_columns():
    forecast = _point_forecast(n=20)
    result = monte_carlo_prediction_interval(forecast, error_std=5.0, n_samples=500, seed=0)

    assert list(result.columns) == ["pred", "lower", "upper"]
    assert len(result) == 20
    assert (result["pred"] == 100.0).all()


def test_monte_carlo_interval_widens_with_larger_error_std():
    forecast = _point_forecast(n=10)
    narrow = monte_carlo_prediction_interval(forecast, error_std=2.0, n_samples=2000, seed=0)
    wide = monte_carlo_prediction_interval(forecast, error_std=20.0, n_samples=2000, seed=0)

    narrow_width = (narrow["upper"] - narrow["lower"]).mean()
    wide_width = (wide["upper"] - wide["lower"]).mean()
    assert wide_width > narrow_width


def test_monte_carlo_interval_lower_bound_never_negative():
    forecast = _point_forecast(n=10, level=5.0)  # near-zero power, large relative noise
    result = monte_carlo_prediction_interval(forecast, error_std=50.0, n_samples=2000, seed=0)
    assert (result["lower"] >= 0).all()


def test_monte_carlo_interval_accepts_heteroscedastic_error_std_series():
    forecast = _point_forecast(n=5, level=100.0)
    std_series = pd.Series([1.0, 1.0, 50.0, 1.0, 1.0], index=forecast.index)  # spike of uncertainty mid-series
    result = monte_carlo_prediction_interval(forecast, error_std=std_series, n_samples=2000, seed=0)

    width = result["upper"] - result["lower"]
    assert width.iloc[2] > width.iloc[0]
    assert width.iloc[2] > width.iloc[4]


def test_monte_carlo_interval_rejects_misaligned_error_std_series():
    forecast = _point_forecast(n=5)
    misaligned_std = pd.Series([1.0, 2.0, 3.0])  # different index entirely
    with pytest.raises(ValueError):
        monte_carlo_prediction_interval(forecast, error_std=misaligned_std, n_samples=100)


def test_monte_carlo_interval_rejects_too_few_samples():
    with pytest.raises(ValueError):
        monte_carlo_prediction_interval(_point_forecast(n=5), error_std=1.0, n_samples=1)


def test_monte_carlo_interval_rejects_invalid_quantiles():
    with pytest.raises(ValueError):
        monte_carlo_prediction_interval(_point_forecast(n=5), error_std=1.0, quantiles=(0.9, 0.1))


def test_monte_carlo_interval_rejects_negative_error_std():
    with pytest.raises(ValueError):
        monte_carlo_prediction_interval(_point_forecast(n=5), error_std=-1.0)


def test_evaluate_monte_carlo_interval_reuses_module4_metrics():
    rng = np.random.default_rng(0)
    forecast = _point_forecast(n=200, level=100.0)
    mc_result = monte_carlo_prediction_interval(forecast, error_std=10.0, n_samples=1000, quantiles=(0.05, 0.95), seed=1)

    # ground truth drawn from the same noise model the interval assumes -> should calibrate close to 90%
    y_true = pd.Series(rng.normal(100.0, 10.0, size=200).clip(0), index=forecast.index)

    metrics = evaluate_monte_carlo_interval(y_true, mc_result)
    assert set(metrics) == {"picp", "pinaw"}
    assert 0.7 < metrics["picp"] <= 1.0  # loose bound - genuinely random draw, not a tight calibration test


def _flat_baseline(n=24, level=50.0):
    idx = pd.date_range("2026-07-14", periods=n, freq="h", tz="UTC")
    return pd.Series(level, index=idx)


def test_scenario_simulation_with_no_uncertainty_collapses_to_a_point():
    baseline = _flat_baseline()
    result = monte_carlo_scenario_simulation(baseline, ScenarioDistribution(), n_samples=200, seed=0)
    # every std is 0 (the default) -> every trial is identical -> zero-width interval
    assert (result["lower"] == result["upper"]).all()
    assert result["median"].iloc[0] == pytest.approx(50.0)


def test_scenario_simulation_cloud_uncertainty_widens_interval():
    baseline = _flat_baseline()
    dist = ScenarioDistribution(extra_cloud_attenuation=(20.0, 15.0))
    result = monte_carlo_scenario_simulation(baseline, dist, n_samples=2000, seed=0)

    width = (result["upper"] - result["lower"]).iloc[0]
    assert width > 0
    # median should reflect the mean 20% attenuation, roughly
    assert result["median"].iloc[0] == pytest.approx(40.0, abs=3.0)


def test_scenario_simulation_curtailment_samples_never_go_negative_in_effect():
    baseline = _flat_baseline()
    # large std relative to mean would draw negative curtailment_pct samples if unclipped
    dist = ScenarioDistribution(curtailment=(5.0, 20.0))
    result = monte_carlo_scenario_simulation(baseline, dist, n_samples=2000, seed=0)
    # a negative curtailment sample clips to 0 (no curtailment), never boosts power above baseline
    assert (result["upper"] <= 50.0 + 1e-6).all()


def test_scenario_simulation_only_varies_requested_parameters():
    baseline = _flat_baseline()
    # only curtailment has uncertainty; cloud/degradation are fixed at their means (0)
    dist = ScenarioDistribution(curtailment=(10.0, 5.0))
    result = monte_carlo_scenario_simulation(baseline, dist, n_samples=500, seed=0)
    assert result["median"].iloc[0] == pytest.approx(45.0, abs=2.0)  # ~10% curtailed on average


def test_scenario_simulation_rejects_too_few_samples():
    with pytest.raises(ValueError):
        monte_carlo_scenario_simulation(_flat_baseline(), ScenarioDistribution(), n_samples=1)


def test_scenario_simulation_rejects_invalid_quantiles():
    with pytest.raises(ValueError):
        monte_carlo_scenario_simulation(_flat_baseline(), ScenarioDistribution(), quantiles=(0.9, 0.1))


def test_scenario_simulation_rejects_negative_years_since_commissioning():
    with pytest.raises(ValueError):
        monte_carlo_scenario_simulation(_flat_baseline(), ScenarioDistribution(), years_since_commissioning=-1.0)


def test_scenario_simulation_is_deterministic_given_a_seed():
    baseline = _flat_baseline()
    dist = ScenarioDistribution(extra_cloud_attenuation=(10.0, 10.0))
    result1 = monte_carlo_scenario_simulation(baseline, dist, n_samples=300, seed=42)
    result2 = monte_carlo_scenario_simulation(baseline, dist, n_samples=300, seed=42)
    pd.testing.assert_frame_equal(result1, result2)
