"""Monte Carlo prediction intervals: perturb a point forecast with sampled
noise many times and take empirical percentiles - a model-agnostic way to
get a PI around *any* point forecast (Module 4's per-horizon models already
have their own native PI method; this is the general-purpose fallback the
architecture doc asks for under Module 5, e.g. for a what-if-adjusted series
that doesn't have its own PI).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from nongfab_forecast.metrics import evaluate_prediction_interval


def monte_carlo_prediction_interval(
    point_forecast: pd.Series, error_std: float | pd.Series, n_samples: int = 1000,
    quantiles: tuple[float, float] = (0.05, 0.95), seed: int = 0,
) -> pd.DataFrame:
    """Samples `n_samples` Gaussian-perturbed realizations of `point_forecast`
    (per-timestep std from `error_std` - a scalar applies uniformly, a Series
    must align with `point_forecast`'s index for heteroscedastic uncertainty,
    e.g. wider near sunrise/sunset than at midday) and returns empirical
    quantile bounds. Samples are clipped at 0 (power can't go negative)
    before taking quantiles, so a large std near zero-power hours doesn't
    produce a physically-impossible negative lower bound.

    Returns a DataFrame aligned to `point_forecast`'s index with columns:
    pred, lower, upper.
    """
    if n_samples < 2:
        raise ValueError(f"n_samples must be at least 2, got {n_samples}")
    lo_q, hi_q = quantiles
    if not (0 <= lo_q < hi_q <= 1):
        raise ValueError(f"quantiles must satisfy 0 <= lower < upper <= 1, got {quantiles}")

    if isinstance(error_std, pd.Series):
        std = error_std.reindex(point_forecast.index)
        if std.isna().any():
            raise ValueError("error_std Series does not cover every timestep in point_forecast's index")
        std = std.to_numpy()
    else:
        if error_std < 0:
            raise ValueError(f"error_std must be non-negative, got {error_std}")
        std = np.full(len(point_forecast), error_std)

    rng = np.random.default_rng(seed)
    noise = rng.normal(loc=0.0, scale=std, size=(n_samples, len(point_forecast)))
    samples = np.clip(point_forecast.to_numpy()[None, :] + noise, 0, None)

    lower = np.quantile(samples, lo_q, axis=0)
    upper = np.quantile(samples, hi_q, axis=0)

    return pd.DataFrame({"pred": point_forecast.to_numpy(), "lower": lower, "upper": upper}, index=point_forecast.index)


def evaluate_monte_carlo_interval(y_true: pd.Series, mc_result: pd.DataFrame, normalize: str = "range") -> dict[str, float]:
    """Thin wrapper around `nongfab_forecast.metrics.evaluate_prediction_interval` -
    checks a Monte Carlo interval's PICP/PINAW against realized values the
    same way Module 4 checks its own models' native intervals, so the two
    approaches are directly comparable.
    """
    return evaluate_prediction_interval(y_true, mc_result["lower"], mc_result["upper"], normalize)
