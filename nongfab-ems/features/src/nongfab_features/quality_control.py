"""Curtailment/degradation QC: flags periods where measured power stops
tracking irradiance the way a healthy, uncurtailed plant should - the paper's
warning that P can decouple from I (grid curtailment, inverter fault, panel
degradation/soiling event). Two complementary signals, since a hard curtailment
cap produces a degenerate case the first signal alone misses:

1. Rolling Pearson correlation between P and I: a healthy plant tracks I
   closely (corr close to 1 during daytime); a sustained drop below
   `corr_threshold` flags the window.
2. Flatlined power despite varying irradiance: correlation is undefined
   (NaN, zero variance) when power is perfectly capped/flat - which is
   itself the classic curtailment signature, not "no evidence of a
   problem". Caught separately via rolling std.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_WINDOW = 144  # 144 x 10-min samples = 1 day, if data is on a 10-min cadence
DEFAULT_CORR_THRESHOLD = 0.5
DEFAULT_MIN_PERIODS = 30
FLATLINE_STD_EPSILON = 1e-6


def rolling_power_irradiance_correlation(
    df: pd.DataFrame, irradiance_col: str, power_col: str, window: int = DEFAULT_WINDOW, min_periods: int = DEFAULT_MIN_PERIODS
) -> pd.Series:
    return df[power_col].rolling(window=window, min_periods=min_periods).corr(df[irradiance_col])


def flag_curtailment_or_degradation(
    df: pd.DataFrame, irradiance_col: str, power_col: str,
    window: int = DEFAULT_WINDOW, corr_threshold: float = DEFAULT_CORR_THRESHOLD, min_periods: int = DEFAULT_MIN_PERIODS,
) -> pd.Series:
    """Boolean Series, same index as `df`: True where P has decoupled from I -
    a QC flag for curtailment/degradation/fault, not a hard classification of
    which one (that needs plant-ops context this module doesn't have).

    NaN correlation caused by insufficient history (start of series, before
    `min_periods` samples exist) is "not flagged" - no evidence of a problem.
    NaN correlation caused by a flatlined power signal (zero variance) with
    irradiance still varying is a *positive* flag - see module docstring.
    """
    corr = rolling_power_irradiance_correlation(df, irradiance_col, power_col, window=window, min_periods=min_periods)
    low_corr = (corr < corr_threshold).fillna(False)  # NaN (incl. insufficient history) -> not flagged here

    power_std = df[power_col].rolling(window=window, min_periods=min_periods).std()
    irradiance_std = df[irradiance_col].rolling(window=window, min_periods=min_periods).std()
    flatlined_power = (power_std.fillna(np.inf) < FLATLINE_STD_EPSILON) & (irradiance_std.fillna(0) > FLATLINE_STD_EPSILON)

    return low_corr | flatlined_power
