"""Feature engineering per the paper: auto-lags of I/P, lagged exogenous
regressors (cloud index, temperature, RH), EMA-smoothed irradiance, and
future regressors (values known ahead of time, like NWP forecasts, that a
model can condition on for future steps).
"""

from __future__ import annotations

import pandas as pd


def add_auto_lags(df: pd.DataFrame, columns: list[str], lags: list[int]) -> pd.DataFrame:
    """Adds {col}_lag{n} = col.shift(n) for every column/lag combination."""
    out = df.copy()
    for col in columns:
        for lag in lags:
            out[f"{col}_lag{lag}"] = out[col].shift(lag)
    return out


def add_ema(df: pd.DataFrame, columns: list[str], spans: list[int]) -> pd.DataFrame:
    """Adds {col}_ema{span}: exponential moving average, smoothing short-term
    irradiance noise (cloud edge flicker) the way the paper's EMA(I) feature does.
    """
    out = df.copy()
    for col in columns:
        for span in spans:
            out[f"{col}_ema{span}"] = out[col].ewm(span=span, adjust=False).mean()
    return out


def add_future_regressors(df: pd.DataFrame, columns: list[str], horizons: list[int]) -> pd.DataFrame:
    """Adds {col}_future{h} = col.shift(-h): values already known at forecast time
    (e.g. NWP-forecast SSRD/temperature for future steps), for models that
    condition on future exogenous inputs (NeuralProphet, LightGBM with NWP features).
    """
    out = df.copy()
    for col in columns:
        for h in horizons:
            out[f"{col}_future{h}"] = out[col].shift(-h)
    return out
