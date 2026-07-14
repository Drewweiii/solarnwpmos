"""Monte Carlo prediction intervals - two complementary approaches:

- `monte_carlo_prediction_interval`: perturb a point forecast with generic
  Gaussian noise many times and take empirical percentiles - a model-
  agnostic fallback that works on *any* point forecast, but the caller has
  to supply an external `error_std` (from where? Module 4's own backtest
  error, typically) since it knows nothing about what physically drives
  the uncertainty.
- `monte_carlo_scenario_simulation`: sample cloud/curtailment/degradation
  from what-if uncertainty *distributions* and run `what_if.apply_scenario`
  per trial - a genuine Monte Carlo simulation over scenario assumptions
  ("how wide should the output distribution be, given how confident we are
  in the cloud/curtailment/degradation inputs"), which is what "Monte
  Carlo" means in the architecture doc's Module 5 spec when read alongside
  its what-if scenarios, not just noise bolted onto an unrelated point value.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from nongfab_forecast.metrics import evaluate_prediction_interval

from .what_if import ScenarioParams, apply_scenario


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


@dataclass(frozen=True)
class ScenarioDistribution:
    """Gaussian (mean, std) uncertainty around each what-if parameter, in the
    same units as `what_if.ScenarioParams`. A std of 0.0 (the default for
    every field) means that parameter is treated as fixed at its mean, not
    sampled - so a caller only needs to specify uncertainty for the
    parameters they actually want to vary.
    """

    extra_cloud_attenuation: tuple[float, float] = (0.0, 0.0)  # (mean_pct, std_pct)
    curtailment: tuple[float, float] = (0.0, 0.0)  # (mean_pct, std_pct)
    degradation_per_year: tuple[float, float] = (0.0, 0.0)  # (mean_pct, std_pct)


def _sample_or_fix(rng: np.random.Generator, mean: float, std: float, n_samples: int, lo: float, hi: float | None) -> np.ndarray:
    if std <= 0:
        return np.full(n_samples, mean)
    return np.clip(rng.normal(mean, std, size=n_samples), lo, hi)


def monte_carlo_scenario_simulation(
    baseline_power_kw: pd.Series, distribution: ScenarioDistribution, years_since_commissioning: float = 0.0,
    n_samples: int = 1000, quantiles: tuple[float, float] = (0.05, 0.95), seed: int = 0,
) -> pd.DataFrame:
    """Runs `n_samples` what-if trials, each drawing cloud/curtailment/
    degradation parameters from `distribution` and applying them via
    `what_if.apply_scenario`, then takes empirical quantiles of the
    resulting output ensemble - genuine Monte Carlo simulation over
    scenario uncertainty, not generic noise layered on a fixed point value
    (see `monte_carlo_prediction_interval` for that simpler alternative).

    Sampled curtailment/degradation draws are clipped to their physically
    valid range (>= 0 - see `what_if.apply_scenario`'s own validation) before
    being applied; a negative *sample* just means "this trial has no
    curtailment/degradation", not an invalid input to reject.

    Returns a DataFrame aligned to `baseline_power_kw`'s index with columns:
    median, lower, upper.
    """
    if n_samples < 2:
        raise ValueError(f"n_samples must be at least 2, got {n_samples}")
    lo_q, hi_q = quantiles
    if not (0 <= lo_q < hi_q <= 1):
        raise ValueError(f"quantiles must satisfy 0 <= lower < upper <= 1, got {quantiles}")
    if years_since_commissioning < 0:
        raise ValueError("years_since_commissioning cannot be negative")

    rng = np.random.default_rng(seed)
    cloud_samples = _sample_or_fix(rng, *distribution.extra_cloud_attenuation, n_samples, -100, 100)
    curtailment_samples = _sample_or_fix(rng, *distribution.curtailment, n_samples, 0, 100)
    degradation_samples = _sample_or_fix(rng, *distribution.degradation_per_year, n_samples, 0, None)

    samples = np.empty((n_samples, len(baseline_power_kw)))
    for i in range(n_samples):
        params = ScenarioParams(
            extra_cloud_attenuation_pct=float(cloud_samples[i]),
            curtailment_pct=float(curtailment_samples[i]),
            degradation_pct_per_year=float(degradation_samples[i]),
        )
        samples[i] = apply_scenario(baseline_power_kw, params, years_since_commissioning).to_numpy()

    median = np.quantile(samples, 0.5, axis=0)
    lower = np.quantile(samples, lo_q, axis=0)
    upper = np.quantile(samples, hi_q, axis=0)
    return pd.DataFrame({"median": median, "lower": lower, "upper": upper}, index=baseline_power_kw.index)
