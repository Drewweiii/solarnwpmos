import numpy as np
import pandas as pd
import pytest

from nongfab_forecast.day_ahead import predict_day_ahead, train_day_ahead_model


def _synthetic_daily_dataset(n_hours=24 * 20, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-06-01", periods=n_hours, freq="h", tz="UTC")
    hour = idx.hour.to_numpy()
    ssrd = np.clip(800 * np.sin(np.pi * (hour - 6) / 12), 0, None)
    temp = 28 + 5 * np.sin(np.pi * (hour - 6) / 12) + rng.normal(0, 0.5, size=n_hours)
    power = 0.15 * ssrd - 0.3 * temp + rng.normal(0, 5, size=n_hours) + 15

    return pd.DataFrame({"power_kw": power, "ssrd_w_m2": ssrd, "temp2m_c": temp}, index=idx)


@pytest.fixture(scope="module")
def trained_model():
    df = _synthetic_daily_dataset(n_hours=24 * 20, seed=0)
    return train_day_ahead_model(
        df, target_col="power_kw", regressor_cols=["ssrd_w_m2", "temp2m_c"],
        quantiles=(0.1, 0.9), epochs=10, daily_seasonality=True, weekly_seasonality=False, yearly_seasonality=False,
    )


def test_train_day_ahead_model_returns_expected_structure(trained_model):
    assert trained_model.target_col == "power_kw"
    assert trained_model.regressor_cols == ["ssrd_w_m2", "temp2m_c"]
    assert trained_model.quantiles == (0.1, 0.9)


def test_train_day_ahead_model_rejects_non_datetime_index():
    df = _synthetic_daily_dataset(n_hours=48).reset_index(drop=True)
    with pytest.raises(ValueError):
        train_day_ahead_model(df, "power_kw", ["ssrd_w_m2", "temp2m_c"], epochs=1)


def test_predict_day_ahead_returns_24h_forecast_with_interval(trained_model):
    history = _synthetic_daily_dataset(n_hours=24 * 20, seed=0)
    future = _synthetic_daily_dataset(n_hours=24, seed=1)
    future.index = pd.date_range(history.index[-1] + pd.Timedelta(hours=1), periods=24, freq="h", tz="UTC")

    result = predict_day_ahead(trained_model, history, future[["ssrd_w_m2", "temp2m_c"]], periods=24)

    assert list(result.columns) == ["pred", "lower", "upper"]
    assert len(result) == 24
    assert (result["upper"] >= result["lower"]).all()


def test_predict_day_ahead_preserves_tz_awareness(trained_model):
    """NeuralProphet normalizes tz-aware timestamps to UTC internally then
    returns them tz-naive (verified live, not documented) - predict_day_ahead
    must restore tz-awareness so callers get back what they put in.
    """
    history = _synthetic_daily_dataset(n_hours=24 * 20, seed=0)
    future = _synthetic_daily_dataset(n_hours=24, seed=1)
    future.index = pd.date_range(history.index[-1] + pd.Timedelta(hours=1), periods=24, freq="h", tz="UTC")

    result = predict_day_ahead(trained_model, history, future[["ssrd_w_m2", "temp2m_c"]], periods=24)

    assert result.index.tz is not None
    assert str(result.index.tz) == "UTC"


def test_predict_day_ahead_tracks_daytime_shape(trained_model):
    """Predicted power should be near-zero overnight and positive at midday -
    the model should have picked up daily seasonality + the SSRD regressor,
    not just predicted a flat line.
    """
    history = _synthetic_daily_dataset(n_hours=24 * 20, seed=0)
    future = _synthetic_daily_dataset(n_hours=24, seed=1)
    future.index = pd.date_range(history.index[-1] + pd.Timedelta(hours=1), periods=24, freq="h", tz="UTC")

    result = predict_day_ahead(trained_model, history, future[["ssrd_w_m2", "temp2m_c"]], periods=24)
    result["hour"] = result.index.hour

    midday_pred = result.loc[result["hour"].between(10, 14), "pred"].mean()
    night_pred = result.loc[(result["hour"] >= 22) | (result["hour"] <= 3), "pred"].mean()
    assert midday_pred > night_pred
