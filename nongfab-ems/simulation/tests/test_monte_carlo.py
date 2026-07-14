import numpy as np
import pandas as pd
import pytest

from nongfab_simulation.monte_carlo import evaluate_monte_carlo_interval, monte_carlo_prediction_interval


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
