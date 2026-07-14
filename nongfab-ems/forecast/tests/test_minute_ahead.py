import numpy as np
import pandas as pd
import pytest

from nongfab_forecast.minute_ahead import make_sequences, predict_minute_ahead, train_minute_ahead_model


def _synthetic_cloud_series(n=400, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    # smooth periodic "cloud passing over" pattern + slow drift + small noise -
    # learnable from recent history, unlike pure white noise.
    opacity = 50 + 30 * np.sin(2 * np.pi * t / 40) + 0.01 * t + rng.normal(0, 1.5, size=n)
    opacity = np.clip(opacity, 0, 100)
    cloud_index = opacity / 100.0 + rng.normal(0, 0.02, size=n)
    return pd.DataFrame({"cloud_opacity_pct": opacity, "cloud_index": cloud_index})


def test_make_sequences_shapes():
    df = _synthetic_cloud_series(n=50)
    X, y = make_sequences(df, ["cloud_opacity_pct", "cloud_index"], "cloud_opacity_pct", lookback=12, horizon=6)
    assert X.shape == (50 - 12 - 6 + 1, 12, 2)
    assert y.shape == (50 - 12 - 6 + 1, 6)


def test_make_sequences_rejects_insufficient_rows():
    df = _synthetic_cloud_series(n=10)
    with pytest.raises(ValueError):
        make_sequences(df, ["cloud_opacity_pct"], "cloud_opacity_pct", lookback=12, horizon=6)


@pytest.fixture(scope="module")
def trained_model():
    df = _synthetic_cloud_series(n=400, seed=0)
    return train_minute_ahead_model(
        df, feature_cols=["cloud_opacity_pct", "cloud_index"], target_col="cloud_opacity_pct",
        lookback=12, horizon=6, epochs=40, patience=8, seed=0,
    )


def test_train_minute_ahead_model_returns_expected_structure(trained_model):
    assert trained_model.lookback == 12
    assert trained_model.horizon == 6
    assert trained_model.feature_names == ["cloud_opacity_pct", "cloud_index"]
    assert len(trained_model.train_history) > 0


def test_train_minute_ahead_model_rejects_unknown_loss():
    df = _synthetic_cloud_series(n=100)
    with pytest.raises(ValueError):
        train_minute_ahead_model(df, ["cloud_opacity_pct"], "cloud_opacity_pct", loss="bogus")


def test_predict_minute_ahead_rejects_wrong_window_length(trained_model):
    df = _synthetic_cloud_series(n=20)
    with pytest.raises(ValueError):
        predict_minute_ahead(trained_model, df.iloc[:5])  # too short


def test_predict_minute_ahead_returns_horizon_length_array(trained_model):
    df = _synthetic_cloud_series(n=50, seed=1)
    window = df.iloc[-12:]
    pred = predict_minute_ahead(trained_model, window)
    assert pred.shape == (6,)


def test_predict_minute_ahead_beats_naive_persistence_baseline(trained_model):
    """On a smooth periodic signal, a trained sequence model should track the
    upcoming trend better than "repeat the last observed value" - not a tight
    bound (small synthetic dataset, short training), just meaningfully better.
    """
    df = _synthetic_cloud_series(n=500, seed=2)  # different seed than training data
    lookback, horizon = trained_model.lookback, trained_model.horizon

    errors_model, errors_naive = [], []
    for start in range(300, 400, 10):
        window = df.iloc[start : start + lookback]
        actual = df["cloud_opacity_pct"].iloc[start + lookback : start + lookback + horizon].to_numpy()
        pred = predict_minute_ahead(trained_model, window)
        naive = np.full(horizon, df["cloud_opacity_pct"].iloc[start + lookback - 1])

        errors_model.append(np.mean(np.abs(pred - actual)))
        errors_naive.append(np.mean(np.abs(naive - actual)))

    assert np.mean(errors_model) < np.mean(errors_naive)
