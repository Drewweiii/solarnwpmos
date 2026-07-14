import numpy as np
import pandas as pd

from nongfab_features.lag_features import add_auto_lags, add_ema, add_future_regressors


def test_add_auto_lags_shifts_correctly():
    df = pd.DataFrame({"I": [1.0, 2.0, 3.0, 4.0]})
    result = add_auto_lags(df, columns=["I"], lags=[1, 2])

    assert result["I_lag1"].iloc[1] == 1.0
    assert result["I_lag2"].iloc[2] == 1.0
    assert result["I_lag1"].isna().sum() == 1
    assert result["I_lag2"].isna().sum() == 2


def test_add_auto_lags_handles_multiple_columns():
    df = pd.DataFrame({"I": [1.0, 2.0, 3.0], "P": [10.0, 20.0, 30.0]})
    result = add_auto_lags(df, columns=["I", "P"], lags=[1])

    assert "I_lag1" in result.columns
    assert "P_lag1" in result.columns
    assert result["P_lag1"].iloc[1] == 10.0


def test_add_ema_smooths_and_preserves_length():
    df = pd.DataFrame({"I": [100.0, 100.0, 0.0, 100.0, 100.0]})
    result = add_ema(df, columns=["I"], spans=[3])

    assert len(result) == len(df)
    assert "I_ema3" in result.columns
    # the dip to 0 should be smoothed, not fully reflected
    assert result["I_ema3"].iloc[2] > 0


def test_add_future_regressors_shifts_backward():
    df = pd.DataFrame({"ssrd_nwp": [1.0, 2.0, 3.0, 4.0]})
    result = add_future_regressors(df, columns=["ssrd_nwp"], horizons=[1])

    assert result["ssrd_nwp_future1"].iloc[0] == 2.0
    assert np.isnan(result["ssrd_nwp_future1"].iloc[-1])
