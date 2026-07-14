import numpy as np
import pandas as pd
import pytest

from nongfab_forecast.hour_ahead import predict_hour_ahead, train_hour_ahead_model


def _synthetic_dataset(n=300, seed=0):
    rng = np.random.default_rng(seed)
    irradiance = rng.uniform(0, 1000, size=n)
    temp = rng.uniform(20, 40, size=n)
    lag_power = rng.uniform(0, 200, size=n)
    noise = rng.normal(0, 5, size=n)
    power = 0.2 * irradiance - 0.5 * temp + 0.1 * lag_power + 10 + noise

    X = pd.DataFrame({"ssrd_w_m2": irradiance, "temp2m_c": temp, "power_lag1": lag_power})
    y = pd.Series(power, name="power_kw")
    return X, y


@pytest.fixture(scope="module")
def trained_model():
    X, y = _synthetic_dataset(n=300)
    X_train, y_train = X.iloc[:200], y.iloc[:200]
    X_val, y_val = X.iloc[200:], y.iloc[200:]
    return train_hour_ahead_model(X_train, y_train, X_val, y_val, n_trials=3)


def test_train_hour_ahead_model_returns_expected_structure(trained_model):
    assert trained_model.feature_names == ["ssrd_w_m2", "temp2m_c", "power_lag1"]
    assert trained_model.interval_quantiles == (0.05, 0.95)
    assert "num_leaves" in trained_model.best_params


def test_predict_hour_ahead_tracks_the_true_linear_relationship(trained_model):
    X_test, y_test = _synthetic_dataset(n=100, seed=1)
    result = predict_hour_ahead(trained_model, X_test)

    assert list(result.columns) == ["pred", "lower", "upper"]
    assert len(result) == len(X_test)

    from nongfab_forecast.metrics import nrmse

    error = nrmse(y_test, result["pred"], normalize="mean")
    assert error < 0.3  # a reasonably close fit to a near-linear synthetic relationship


def test_predict_hour_ahead_interval_never_inverts(trained_model):
    X_test, _ = _synthetic_dataset(n=100, seed=2)
    result = predict_hour_ahead(trained_model, X_test)
    assert (result["upper"] >= result["lower"]).all()


def test_predict_hour_ahead_interval_has_reasonable_coverage(trained_model):
    X_test, y_test = _synthetic_dataset(n=200, seed=3)
    result = predict_hour_ahead(trained_model, X_test)

    from nongfab_forecast.metrics import picp

    coverage = picp(y_test, result["lower"], result["upper"])
    assert coverage > 0.6  # loose bound - this is a 90% nominal interval on tiny/synthetic data, not a calibration test


def test_train_hour_ahead_model_rejects_unknown_loss():
    X, y = _synthetic_dataset(n=50)
    with pytest.raises(ValueError):
        train_hour_ahead_model(X.iloc[:30], y.iloc[:30], X.iloc[30:], y.iloc[30:], n_trials=1, loss="bogus")
