"""Final assembly: multi-step targets y(t+1..t+H), drop NaN (from lags/EMA/future
regressors/targets all needing rows this dataframe doesn't have at the edges),
and a chronological (not shuffled - avoids leaking future data into training)
train/val/test split.
"""

from __future__ import annotations

import pandas as pd


def make_multistep_targets(df: pd.DataFrame, target_col: str, horizon: int) -> pd.DataFrame:
    """Adds {target_col}_t+1 .. {target_col}_t+{horizon}: the multi-step forecast
    targets y(t+1..t+H) each row is meant to predict.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    out = df.copy()
    for h in range(1, horizon + 1):
        out[f"{target_col}_t+{h}"] = out[target_col].shift(-h)
    return out


def build_training_frame(df: pd.DataFrame, target_col: str, horizon: int, drop_na: bool = True) -> pd.DataFrame:
    """make_multistep_targets() + drop rows with any NaN (from lag/EMA/future-regressor
    warm-up at the start, or target shift-ahead at the end) - the final frame a model
    can actually train on.
    """
    out = make_multistep_targets(df, target_col, horizon)
    if drop_na:
        out = out.dropna()
    return out


def chronological_split(
    df: pd.DataFrame, train_frac: float = 0.7, val_frac: float = 0.15
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Splits a time-ordered dataframe into train/val/test WITHOUT shuffling.
    Critical for time series: a random split would let the model train on rows
    chronologically after ones it's validated/tested on, leaking information a
    real deployment would never have at prediction time.
    """
    if not (0 < train_frac < 1) or not (0 < val_frac < 1) or train_frac + val_frac >= 1:
        raise ValueError(f"train_frac ({train_frac}) and val_frac ({val_frac}) must each be in (0,1) and sum to < 1")

    n = len(df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return df.iloc[:train_end].copy(), df.iloc[train_end:val_end].copy(), df.iloc[val_end:].copy()
