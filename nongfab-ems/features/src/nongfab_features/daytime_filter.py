"""Drops night-time rows so evaluation metrics aren't inflated by trivially-easy
zero-output predictions (per the paper's warning) - zenith >= 85 deg is the cutoff.
"""

from __future__ import annotations

import pandas as pd

DEFAULT_MAX_ZENITH_DEG = 85.0


def filter_daytime(df: pd.DataFrame, zenith_col: str = "zenith_deg", max_zenith_deg: float = DEFAULT_MAX_ZENITH_DEG) -> pd.DataFrame:
    if zenith_col not in df.columns:
        raise KeyError(f"{zenith_col!r} not in dataframe - run compute_clearsky_and_position() first")
    return df.loc[df[zenith_col] < max_zenith_deg].copy()
