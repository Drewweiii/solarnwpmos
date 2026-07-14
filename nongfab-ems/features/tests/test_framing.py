import pandas as pd
import pytest

from nongfab_features.framing import build_training_frame, chronological_split, make_multistep_targets


def test_make_multistep_targets_shifts_forward():
    df = pd.DataFrame({"P": [1.0, 2.0, 3.0, 4.0, 5.0]})
    result = make_multistep_targets(df, "P", horizon=2)

    assert result["P_t+1"].iloc[0] == 2.0
    assert result["P_t+2"].iloc[0] == 3.0
    assert result["P_t+2"].iloc[-1] != result["P_t+2"].iloc[-1]  # NaN at the tail


def test_make_multistep_targets_rejects_invalid_horizon():
    df = pd.DataFrame({"P": [1.0, 2.0]})
    with pytest.raises(ValueError):
        make_multistep_targets(df, "P", horizon=0)


def test_build_training_frame_drops_nan_rows():
    df = pd.DataFrame({"P": [1.0, 2.0, 3.0, 4.0, 5.0], "I_lag1": [None, 1.0, 2.0, 3.0, 4.0]})
    result = build_training_frame(df, "P", horizon=1)

    # row 0 (I_lag1 NaN) and row 4 (P_t+1 NaN) both dropped, leaving rows 1-3
    assert len(result) == 3
    assert result.isna().sum().sum() == 0


def test_build_training_frame_keep_na_if_requested():
    df = pd.DataFrame({"P": [1.0, 2.0, 3.0]})
    result = build_training_frame(df, "P", horizon=1, drop_na=False)
    assert len(result) == 3
    assert result["P_t+1"].isna().sum() == 1


def test_chronological_split_preserves_order_and_sizes():
    df = pd.DataFrame({"t": range(100)})
    train, val, test = chronological_split(df, train_frac=0.7, val_frac=0.15)

    assert len(train) == 70
    assert len(val) == 15
    assert len(test) == 15
    # no shuffling: train's last row precedes val's first, val's last precedes test's first
    assert train["t"].max() < val["t"].min()
    assert val["t"].max() < test["t"].min()


def test_chronological_split_rejects_bad_fractions():
    df = pd.DataFrame({"t": range(10)})
    with pytest.raises(ValueError):
        chronological_split(df, train_frac=0.7, val_frac=0.4)  # sums to > 1
