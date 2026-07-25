"""Forecast verification: scoring past forecasts against what actually happened
(2026-07-25).

Every accuracy number the dashboard showed until now came from TRAINING
(`rmse_by_lead_hour`, `candidate_errors` - hold-out error measured while fitting
the model). That answers "how well did this model fit its training data", which
is not the same question as "how good have the forecasts this system actually
issued turned out to be". This module answers the second one, which is the
standard way solar-forecasting work reports itself:

- MAE / RMSE / MBE (mean bias error - the sign matters: a model that is
  systematically optimistic is a different problem from one that is merely
  noisy), plus RMSE normalized by the array's AC capacity so zones of different
  sizes are comparable.
- A SKILL SCORE against the persistence baseline. Persistence ("output in k
  hours will equal output now") is the reference every solar forecasting paper
  is expected to beat, because a model can post a small RMSE simply by living
  somewhere with steady weather. skill = 1 - RMSE_model / RMSE_persistence: > 0
  means the model genuinely adds information, 0 means it is no better than
  assuming nothing changes, < 0 means it is worse than doing nothing.

Two honesty constraints baked in:
1. Daylight filtering. Night hours are trivially correct (everyone predicts
   zero) and would dilute every metric toward zero error, so the headline
   figures are computed over daylight pairs only, with the count reported.
2. Pairs are only formed where a real actual exists. Nothing is interpolated,
   and a window with no overlap yields `n=0` metrics rather than invented ones.

Pure (numpy only, no store/HTTP) so it is fully unit-testable; the API's
verification_service does the store reads and hands pairs in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

# Hours below this output count as "night" for the daylight filter. A small
# positive floor rather than exactly 0 so a hair of pre-dawn/post-dusk noise
# doesn't drag a zone's metrics around.
DAYLIGHT_FLOOR_KW = 0.5


@dataclass(frozen=True)
class ForecastActualPair:
    """One scored forecast: what was predicted for `target_time`, what actually
    happened, and what persistence would have said. `persistence_kw` is None
    where the actual it needed (the observation one lead-time earlier) is
    missing - those pairs still score the model, they just can't contribute to
    the skill score."""

    target_time: datetime
    lead_hours: float
    predicted_kw: float
    actual_kw: float
    persistence_kw: float | None = None


@dataclass(frozen=True)
class VerificationMetrics:
    n: int
    mae_kw: float
    rmse_kw: float
    # Mean bias: positive = the forecast runs HIGH (optimistic) on average.
    mbe_kw: float
    # RMSE as a percentage of AC capacity - None when no capacity was supplied.
    nrmse_pct: float | None
    # Persistence RMSE over the same pairs, and the skill score against it.
    # Both None when too few pairs carried a persistence reference.
    persistence_rmse_kw: float | None
    skill_score: float | None


EMPTY_METRICS = VerificationMetrics(
    n=0, mae_kw=0.0, rmse_kw=0.0, mbe_kw=0.0, nrmse_pct=None, persistence_rmse_kw=None, skill_score=None
)


def daylight_pairs(pairs: list[ForecastActualPair], floor_kw: float = DAYLIGHT_FLOOR_KW) -> list[ForecastActualPair]:
    """Pairs where SOMETHING was generating - either the forecast or the actual
    is above the floor. Keeping a pair where only one side is non-zero matters:
    "predicted 40 kW, got 0" is exactly the kind of miss verification exists to
    catch, and dropping it because the actual was zero would flatter the model."""
    return [p for p in pairs if max(p.predicted_kw, p.actual_kw) > floor_kw]


def compute_metrics(pairs: list[ForecastActualPair], capacity_kw: float | None = None) -> VerificationMetrics:
    """Score a set of pairs. Empty input -> EMPTY_METRICS (n=0), never a
    divide-by-zero or a fabricated score."""
    if not pairs:
        return EMPTY_METRICS
    predicted = np.array([p.predicted_kw for p in pairs], dtype=float)
    actual = np.array([p.actual_kw for p in pairs], dtype=float)
    error = predicted - actual
    mae = float(np.mean(np.abs(error)))
    rmse = float(np.sqrt(np.mean(error**2)))
    mbe = float(np.mean(error))
    nrmse = (rmse / capacity_kw * 100) if capacity_kw and capacity_kw > 0 else None

    with_persistence = [p for p in pairs if p.persistence_kw is not None]
    persistence_rmse: float | None = None
    skill: float | None = None
    if with_persistence:
        p_pred = np.array([p.persistence_kw for p in with_persistence], dtype=float)
        p_act = np.array([p.actual_kw for p in with_persistence], dtype=float)
        persistence_rmse = float(np.sqrt(np.mean((p_pred - p_act) ** 2)))
        # Score the MODEL over the same subset, so the ratio compares like with
        # like - a skill score built from RMSEs measured over different pair sets
        # would be meaningless.
        m_pred = np.array([p.predicted_kw for p in with_persistence], dtype=float)
        model_rmse_same_subset = float(np.sqrt(np.mean((m_pred - p_act) ** 2)))
        if persistence_rmse > 0:
            skill = 1 - model_rmse_same_subset / persistence_rmse
    return VerificationMetrics(
        n=len(pairs),
        mae_kw=mae,
        rmse_kw=rmse,
        mbe_kw=mbe,
        nrmse_pct=nrmse,
        persistence_rmse_kw=persistence_rmse,
        skill_score=skill,
    )


# Lead-time buckets, in hours. Coarse on purpose: only the freshest issuance per
# target hour survives in the store (see
# RealDataStore.forecast_history_issuances' own docstring), so finer buckets
# would mostly be empty and imply a lead-time matrix this store doesn't keep.
LEAD_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0-1h", 0.0, 1.0),
    ("1-3h", 1.0, 3.0),
    ("3-6h", 3.0, 6.0),
    ("6-24h", 6.0, 24.0),
    ("24h+", 24.0, float("inf")),
)


def metrics_by_lead(
    pairs: list[ForecastActualPair], capacity_kw: float | None = None, buckets=LEAD_BUCKETS
) -> list[tuple[str, VerificationMetrics]]:
    """Metrics per lead-time bucket, in bucket order. Buckets with no pairs are
    returned with n=0 rather than omitted, so the frontend can show the gap
    honestly instead of silently rescaling its axis."""
    out = []
    for label, low, high in buckets:
        in_bucket = [p for p in pairs if low <= p.lead_hours < high]
        out.append((label, compute_metrics(in_bucket, capacity_kw)))
    return out


def build_pairs(
    issuances: list[tuple[datetime, datetime, float]],
    actual_by_time: dict[datetime, float],
) -> list[ForecastActualPair]:
    """Join stored forecast issuances to recorded actuals.

    `issuances` is (target_time, issued_at, predicted_kw) - what
    `RealDataStore.forecast_history_issuances` returns, already parsed to
    datetimes. `actual_by_time` maps a target hour to the recorded actual output.

    A forecast with no actual for its hour is skipped entirely (nothing to score
    against). The persistence reference for a pair with lead L is the actual one
    lead-time earlier, i.e. "what it was doing when this forecast was issued" -
    left None when that hour isn't in the actuals.
    """
    pairs: list[ForecastActualPair] = []
    for target_time, issued_at, predicted_kw in issuances:
        actual = actual_by_time.get(target_time)
        if actual is None:
            continue
        lead_hours = (target_time - issued_at).total_seconds() / 3600
        if lead_hours < 0:
            # A row whose issue time is after its target: nothing was actually
            # being predicted, so it is not a forecast to verify.
            continue
        reference_hour = _round_to_hour(issued_at)
        pairs.append(
            ForecastActualPair(
                target_time=target_time,
                lead_hours=lead_hours,
                predicted_kw=float(predicted_kw),
                actual_kw=float(actual),
                persistence_kw=actual_by_time.get(reference_hour),
            )
        )
    return pairs


def _round_to_hour(when: datetime) -> datetime:
    """The hour `when` falls in - actuals are recorded on hour anchors (see
    serving.record_generated_power), so an issue time mid-hour has to be floored
    to line up with them."""
    return when.replace(minute=0, second=0, microsecond=0)
