import numpy as np
import pandas as pd
import pytest

from nongfab_forecast.metrics import (
    evaluate_by_group,
    evaluate_point_forecast,
    evaluate_prediction_interval,
    mae,
    mbe,
    nrmse,
    picp,
    pinaw,
    rmse,
)


def test_rmse_zero_for_perfect_forecast():
    y = [1.0, 2.0, 3.0]
    assert rmse(y, y) == 0.0


def test_rmse_known_value():
    y_true = [0.0, 0.0]
    y_pred = [3.0, 4.0]
    assert rmse(y_true, y_pred) == pytest.approx(np.sqrt((9 + 16) / 2))


def test_mae_known_value():
    assert mae([0.0, 0.0], [3.0, -4.0]) == pytest.approx(3.5)


def test_mbe_captures_systematic_overforecast():
    # consistently predicting 2 higher than truth -> MBE = +2, not 0 like RMSE/MAE would obscure
    assert mbe([10.0, 20.0, 30.0], [12.0, 22.0, 32.0]) == pytest.approx(2.0)


def test_mbe_is_signed_unlike_mae():
    y_true = [10.0, 20.0]
    y_pred = [8.0, 22.0]  # errors cancel: -2, +2
    assert mbe(y_true, y_pred) == pytest.approx(0.0)
    assert mae(y_true, y_pred) == pytest.approx(2.0)


def test_nrmse_normalize_by_mean():
    y_true = [100.0, 100.0]
    y_pred = [110.0, 90.0]
    result = nrmse(y_true, y_pred, normalize="mean")
    assert result == pytest.approx(rmse(y_true, y_pred) / 100.0)


def test_nrmse_normalize_by_range():
    y_true = [0.0, 100.0]
    y_pred = [10.0, 90.0]
    result = nrmse(y_true, y_pred, normalize="range")
    assert result == pytest.approx(rmse(y_true, y_pred) / 100.0)


def test_nrmse_rejects_unknown_normalize_mode():
    with pytest.raises(ValueError):
        nrmse([1.0], [1.0], normalize="bogus")


def test_nrmse_nan_when_denominator_zero():
    assert np.isnan(nrmse([0.0, 0.0], [1.0, 1.0], normalize="mean"))


def test_picp_full_coverage():
    y_true = [5.0, 6.0, 7.0]
    lower = [0.0, 0.0, 0.0]
    upper = [10.0, 10.0, 10.0]
    assert picp(y_true, lower, upper) == pytest.approx(1.0)


def test_picp_partial_coverage():
    y_true = [5.0, 15.0]  # second point outside [0,10]
    lower = [0.0, 0.0]
    upper = [10.0, 10.0]
    assert picp(y_true, lower, upper) == pytest.approx(0.5)


def test_pinaw_narrower_interval_is_smaller():
    y_true = [0.0, 100.0]
    wide = pinaw(y_true, [0.0, 0.0], [50.0, 50.0], normalize="range")
    narrow = pinaw(y_true, [0.0, 0.0], [10.0, 10.0], normalize="range")
    assert narrow < wide


def test_pinaw_accepts_explicit_numeric_normalizer():
    y_true = [50.0, 60.0]
    result = pinaw(y_true, [40.0, 40.0], [60.0, 60.0], normalize=200.0)
    assert result == pytest.approx(20.0 / 200.0)


def test_evaluate_point_forecast_returns_all_four_metrics():
    result = evaluate_point_forecast([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert set(result) == {"rmse", "mae", "mbe", "nrmse"}
    assert result["rmse"] == 0.0


def test_evaluate_prediction_interval_returns_picp_and_pinaw():
    result = evaluate_prediction_interval([5.0], [0.0], [10.0])
    assert set(result) == {"picp", "pinaw"}


def test_evaluate_by_group_hourly_breakdown():
    df = pd.DataFrame(
        {
            "y_true": [10.0, 10.0, 20.0, 20.0],
            "y_pred": [12.0, 8.0, 25.0, 15.0],
            "hour": [9, 9, 15, 15],
        }
    )
    result = evaluate_by_group(df, "y_true", "y_pred", "hour")

    assert list(result.index) == [9, 15]
    assert result.loc[9, "n"] == 2
    assert result.loc[9, "mbe"] == pytest.approx(0.0)  # +2 and -2 cancel
    assert result.loc[15, "mbe"] == pytest.approx(0.0)  # +5 and -5 cancel


def test_evaluate_by_group_kstep_breakdown_shows_growing_error():
    # error should grow with k-step horizon - a realistic pattern worth being able to see
    df = pd.DataFrame(
        {
            "y_true": [100.0, 100.0, 100.0],
            "y_pred": [101.0, 105.0, 112.0],
            "k_step": [1, 2, 3],
        }
    )
    result = evaluate_by_group(df, "y_true", "y_pred", "k_step")
    assert result.loc[1, "mae"] < result.loc[2, "mae"] < result.loc[3, "mae"]
