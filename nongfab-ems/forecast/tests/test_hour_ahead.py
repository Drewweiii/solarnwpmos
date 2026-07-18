import numpy as np
import pandas as pd
import pytest

from nongfab_forecast.hour_ahead import (
    HourAheadKStepModel,
    predict_hour_ahead,
    predict_hour_ahead_kstep,
    train_hour_ahead_model,
    train_rf_hour_ahead_model,
)


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


def test_predict_hour_ahead_kstep_attaches_the_winning_algorithm_and_its_rmse(trained_model):
    """The dashboard colors each lead-hour's forecast dot by which candidate
    won (LightGBM vs Random Forest) and shows that candidate's own held-out
    RMSE as an "error" line - both need to survive the k-step dispatch, not
    just live on the model object."""
    X, y = _synthetic_dataset(n=300, seed=5)
    rf_model = train_rf_hour_ahead_model(X.iloc[:200], y.iloc[:200], X.iloc[200:], y.iloc[200:])

    kstep_model = HourAheadKStepModel(
        models_by_lead_hour={1: trained_model, 2: rf_model},
        algorithm_by_lead_hour={1: "lightgbm", 2: "random_forest"},
        rmse_by_lead_hour={1: 12.5, 2: 9.75},
        lead_hours=(1, 2),
    )
    X_test, _ = _synthetic_dataset(n=1, seed=6)
    result = predict_hour_ahead_kstep(kstep_model, {1: X_test, 2: X_test})

    assert list(result.index) == [1, 2]
    assert result.loc[1, "algorithm"] == "lightgbm"
    assert result.loc[2, "algorithm"] == "random_forest"
    assert result.loc[1, "error_rmse"] == pytest.approx(12.5)
    assert result.loc[2, "error_rmse"] == pytest.approx(9.75)


def test_predict_hour_ahead_kstep_leaves_error_rmse_none_when_not_recorded():
    """Older/incomplete models (rmse_by_lead_hour not populated for a lead)
    shouldn't crash the dispatch - just report no error for that point."""
    X, y = _synthetic_dataset(n=300, seed=7)
    lgbm_model = train_hour_ahead_model(X.iloc[:200], y.iloc[:200], X.iloc[200:], y.iloc[200:], n_trials=2)
    kstep_model = HourAheadKStepModel(
        models_by_lead_hour={1: lgbm_model}, algorithm_by_lead_hour={1: "lightgbm"}, lead_hours=(1,),
    )
    X_test, _ = _synthetic_dataset(n=1, seed=8)
    result = predict_hour_ahead_kstep(kstep_model, {1: X_test})
    assert pd.isna(result.loc[1, "error_rmse"])


def test_predict_hour_ahead_kstep_attaches_every_candidates_own_rmse(trained_model):
    """The new Model Competition panel needs all three candidates' RMSE per
    lead hour, not just the winner's - HourAheadKStepModel.
    candidate_rmse_by_lead_hour carries that, and predict_hour_ahead_kstep
    must surface it as its own column so serving.py can pass it straight to
    ForecastPoint.candidate_errors."""
    X, y = _synthetic_dataset(n=300, seed=5)
    rf_model = train_rf_hour_ahead_model(X.iloc[:200], y.iloc[:200], X.iloc[200:], y.iloc[200:])

    kstep_model = HourAheadKStepModel(
        models_by_lead_hour={1: trained_model, 2: rf_model},
        algorithm_by_lead_hour={1: "lightgbm", 2: "random_forest"},
        rmse_by_lead_hour={1: 12.5, 2: 9.75},
        candidate_rmse_by_lead_hour={
            1: {"lightgbm": 12.5, "random_forest": 14.0, "sum_k_lstm": 13.2},
            2: {"lightgbm": 11.0, "random_forest": 9.75},
        },
        lead_hours=(1, 2),
    )
    X_test, _ = _synthetic_dataset(n=1, seed=6)
    result = predict_hour_ahead_kstep(kstep_model, {1: X_test, 2: X_test})

    assert result.loc[1, "candidate_errors"] == {"lightgbm": 12.5, "random_forest": 14.0, "sum_k_lstm": 13.2}
    assert result.loc[2, "candidate_errors"] == {"lightgbm": 11.0, "random_forest": 9.75}


def test_predict_hour_ahead_kstep_defaults_candidate_errors_for_pre_field_model(trained_model):
    """A model pickled before candidate_rmse_by_lead_hour existed unpickles
    without that attribute at all (plain-dataclass unpickling skips
    __init__/field defaults) - simulate that by deleting the attribute after
    construction, and confirm the dispatch degrades to {} instead of raising
    AttributeError."""
    kstep_model = HourAheadKStepModel(
        models_by_lead_hour={1: trained_model}, algorithm_by_lead_hour={1: "lightgbm"},
        rmse_by_lead_hour={1: 12.5}, lead_hours=(1,),
    )
    del kstep_model.__dict__["candidate_rmse_by_lead_hour"]

    X_test, _ = _synthetic_dataset(n=1, seed=6)
    result = predict_hour_ahead_kstep(kstep_model, {1: X_test})
    assert result.loc[1, "candidate_errors"] == {}
