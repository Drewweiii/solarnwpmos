"""Point-forecast accuracy metrics (RMSE/MAE/MBE/NRMSE) and prediction-interval
metrics (PICP/PINAW), plus grouped evaluation helpers for the "รายชั่วโมง"
(per hour-of-day) and "ราย k-step" (per forecast-horizon step) breakdowns the
architecture doc asks for.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _as_array(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def rmse(y_true, y_pred) -> float:
    y_true, y_pred = _as_array(y_true), _as_array(y_pred)
    return float(np.sqrt(np.mean((y_pred - y_true) ** 2)))


def mae(y_true, y_pred) -> float:
    y_true, y_pred = _as_array(y_true), _as_array(y_pred)
    return float(np.mean(np.abs(y_pred - y_true)))


def mbe(y_true, y_pred) -> float:
    """Mean Bias Error - signed, so systematic over/under-forecasting shows up
    (unlike RMSE/MAE which are always non-negative).
    """
    y_true, y_pred = _as_array(y_true), _as_array(y_pred)
    return float(np.mean(y_pred - y_true))


def nrmse(y_true, y_pred, normalize: str = "mean") -> float:
    """RMSE normalized so different zones/capacities/horizons are comparable.
    normalize: "mean" (RMSE / mean(y_true)) or "range" (RMSE / (max-min of y_true)).
    """
    y_true, y_pred = _as_array(y_true), _as_array(y_pred)
    value = rmse(y_true, y_pred)
    if normalize == "mean":
        denom = np.mean(y_true)
    elif normalize == "range":
        denom = np.max(y_true) - np.min(y_true)
    else:
        raise ValueError(f"unknown normalize mode {normalize!r}, expected 'mean' or 'range'")
    if denom == 0:
        return float("nan")
    return float(value / denom)


def picp(y_true, lower, upper) -> float:
    """Prediction Interval Coverage Probability - fraction of true values that
    actually fall within [lower, upper]. Should be close to the interval's
    nominal confidence level (e.g. ~0.9 for a 90% interval) - too low means the
    interval is overconfident (too narrow), too high means it's wasteful (too wide).
    """
    y_true, lower, upper = _as_array(y_true), _as_array(lower), _as_array(upper)
    inside = (y_true >= lower) & (y_true <= upper)
    return float(np.mean(inside))


def pinaw(y_true, lower, upper, normalize: str = "range") -> float:
    """Prediction Interval Normalized Average Width - mean interval width,
    normalized by the true value's range (or "capacity" via an explicit float)
    so intervals are comparable across zones/horizons. Narrower is better,
    *given* PICP already meets its target - a tiny interval with low PICP is
    not actually good, just overconfident.
    """
    y_true, lower, upper = _as_array(y_true), _as_array(lower), _as_array(upper)
    width = np.mean(upper - lower)
    if normalize == "range":
        denom = np.max(y_true) - np.min(y_true)
    elif isinstance(normalize, (int, float)):
        denom = float(normalize)
    else:
        raise ValueError(f"unknown normalize mode {normalize!r}, expected 'range' or a numeric capacity")
    if denom == 0:
        return float("nan")
    return float(width / denom)


def evaluate_point_forecast(y_true, y_pred, normalize: str = "mean") -> dict[str, float]:
    return {"rmse": rmse(y_true, y_pred), "mae": mae(y_true, y_pred), "mbe": mbe(y_true, y_pred), "nrmse": nrmse(y_true, y_pred, normalize)}


def evaluate_prediction_interval(y_true, lower, upper, normalize: str = "range") -> dict[str, float]:
    return {"picp": picp(y_true, lower, upper), "pinaw": pinaw(y_true, lower, upper, normalize)}


def evaluate_by_group(df: pd.DataFrame, y_true_col: str, y_pred_col: str, group_col: str, normalize: str = "mean") -> pd.DataFrame:
    """Per-group (hour-of-day, or forecast-horizon k-step) RMSE/MAE/MBE/NRMSE -
    the "รายชั่วโมง...และราย k-step" breakdown the architecture doc asks for.
    `group_col` is typically an hour-of-day int column or a k-step int column
    the caller derives before calling this (this function is grouping-key
    agnostic - it doesn't care what the column represents).
    """
    rows = []
    for group_value, sub in df.groupby(group_col):
        row = evaluate_point_forecast(sub[y_true_col], sub[y_pred_col], normalize)
        row[group_col] = group_value
        row["n"] = len(sub)
        rows.append(row)
    return pd.DataFrame(rows).set_index(group_col).sort_index()
