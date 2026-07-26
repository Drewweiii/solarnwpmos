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

from . import sky_condition

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
    the skill score.

    `lower_kw`/`upper_kw` carry the interval that was published alongside the
    point forecast, so the band can be scored too (see `compute_interval_metrics`).
    Both None for the physics-baseline fallback, which publishes no interval.
    """

    target_time: datetime
    lead_hours: float
    predicted_kw: float
    actual_kw: float
    persistence_kw: float | None = None
    lower_kw: float | None = None
    upper_kw: float | None = None

    @property
    def has_interval(self) -> bool:
        return self.lower_kw is not None and self.upper_kw is not None


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


def metrics_by_sky(
    pairs: list[ForecastActualPair],
    kt_lookup: dict[datetime, float],
    capacity_kw: float | None = None,
    clear_kt: float = sky_condition.DEFAULT_CLEAR_KT,
    overcast_kt: float = sky_condition.DEFAULT_OVERCAST_KT,
) -> list[tuple[str, VerificationMetrics, int]]:
    """Metrics split by sky condition, plus the count of pairs that could not be
    classified at all.

    Returns `(label, metrics, unclassified_n)` where `unclassified_n` repeats on
    every row (it belongs to the whole split, not to any bucket). Hours with no
    NWP row, or with a clear-sky reference too small to divide by, land there
    rather than being forced into a bucket - a table that quietly absorbs the
    hours it could not classify is worse than one that admits to them.

    Every bucket is returned even when empty, for the same reason `metrics_by_lead`
    does it: an omitted bucket looks like a bucket with no errors.
    """
    buckets: dict[str, list[ForecastActualPair]] = {label: [] for label in sky_condition.SKY_ORDER}
    unclassified = 0
    for pair in pairs:
        label = sky_condition.sky_label_for(pair.target_time, kt_lookup, clear_kt, overcast_kt)
        if label is None:
            unclassified += 1
            continue
        buckets[label].append(pair)
    return [
        (label, compute_metrics(buckets[label], capacity_kw), unclassified)
        for label in sky_condition.SKY_ORDER
    ]


# --- Scoring the published interval (2026-07-25) ----------------------------
# Both the LightGBM and Random Forest hour-ahead candidates publish their band at
# quantiles 0.05/0.95 (see hour_ahead.LightGbmCandidate.interval_quantiles), i.e.
# a nominal 90% interval: 90 out of 100 outcomes are supposed to land inside it.
#
# Whether they actually do had never been checked. `metrics.picp` exists, but it
# is computed during TRAINING on a hold-out split - exactly the distinction this
# module was written for, applied to the point forecast and then left undone for
# the band. The interval the site draws on its chart has been unverified since
# the day it was drawn.
NOMINAL_QUANTILES: tuple[float, float] = (0.05, 0.95)


def nominal_coverage_pct(quantiles: tuple[float, float] = NOMINAL_QUANTILES) -> float:
    """The coverage the band advertises, as a percentage.

    Rounded because binary floating point makes 100 * (0.95 - 0.05) come out as
    89.99999999999999 - harmless in arithmetic, but this figure is a LABEL: it
    is printed next to the measured coverage as the number being compared
    against, and "นับได้ 89.99999999999999%" on screen would look like a bug in
    the very panel whose job is to look trustworthy.
    """
    return round(100.0 * (quantiles[1] - quantiles[0]), 6)


NOMINAL_COVERAGE_PCT = nominal_coverage_pct()


@dataclass(frozen=True)
class IntervalMetrics:
    """How the published prediction interval actually behaved."""

    n: int
    nominal_pct: float
    # PICP: the share of outcomes that fell inside the band. The single number
    # this whole section exists to produce.
    coverage_pct: float
    mean_width_kw: float
    # Mean width as a percentage of AC capacity (PINAW). None without capacity.
    # Coverage alone can be gamed by a band wide enough to contain anything, so
    # the two are only meaningful read together.
    pinaw_pct: float | None
    # Mean pinball (quantile) loss across both published quantiles, in kW.
    # A proper scoring rule, so unlike coverage it cannot be improved by simply
    # widening the band. NOT a CRPS: a full CRPS needs the whole predictive
    # distribution and only two quantiles are published.
    pinball_kw: float
    # Which side the misses fall on. An interval that misses evenly is merely
    # too narrow; one that misses mostly on a single side is also mis-centred,
    # which is a different defect with a different fix.
    miss_low_pct: float
    miss_high_pct: float

    @property
    def coverage_gap_pct(self) -> float:
        """Signed distance from nominal. Negative = overconfident (the band is
        too narrow and reality escapes it more often than advertised), which is
        the failure mode that matters, because a viewer reads the band as a
        promise."""
        return self.coverage_pct - self.nominal_pct


EMPTY_INTERVAL_METRICS = IntervalMetrics(
    n=0,
    nominal_pct=NOMINAL_COVERAGE_PCT,
    coverage_pct=0.0,
    mean_width_kw=0.0,
    pinaw_pct=None,
    pinball_kw=0.0,
    miss_low_pct=0.0,
    miss_high_pct=0.0,
)


def interval_pairs(pairs: list[ForecastActualPair]) -> list[ForecastActualPair]:
    """Only the pairs that actually carry a band. Kept separate from the point
    metrics' pair set on purpose: the physics-baseline fallback publishes no
    interval, and counting those rows as misses would invent a failure that the
    model never claimed anything about."""
    return [p for p in pairs if p.has_interval]


def _pinball(actual: float, quantile_value: float, q: float) -> float:
    """Pinball loss for one quantile forecast. Asymmetric by design: at q=0.05
    being above the outcome is penalised 19x harder than being below it, which
    is what makes it reward an honestly-placed quantile rather than a safe one."""
    delta = actual - quantile_value
    return q * delta if delta >= 0 else (q - 1) * delta


def compute_interval_metrics(
    pairs: list[ForecastActualPair],
    capacity_kw: float | None = None,
    quantiles: tuple[float, float] = NOMINAL_QUANTILES,
) -> IntervalMetrics:
    """Score the published band over pairs that have one.

    Empty input yields n=0 rather than a fabricated 0% coverage - "no band was
    ever published in this window" and "the band never contained anything" are
    opposite findings and must not render identically.
    """
    scored = interval_pairs(pairs)
    if not scored:
        return EMPTY_INTERVAL_METRICS

    lower = np.array([p.lower_kw for p in scored], dtype=float)
    upper = np.array([p.upper_kw for p in scored], dtype=float)
    actual = np.array([p.actual_kw for p in scored], dtype=float)

    inside = (actual >= lower) & (actual <= upper)
    below = actual < lower
    above = actual > upper
    n = len(scored)

    widths = upper - lower
    mean_width = float(np.mean(widths))
    pinaw = (mean_width / capacity_kw * 100) if capacity_kw and capacity_kw > 0 else None

    lo_q, hi_q = quantiles
    pinball = float(
        np.mean(
            [
                (_pinball(a, lo, lo_q) + _pinball(a, hi, hi_q)) / 2
                for a, lo, hi in zip(actual, lower, upper)
            ]
        )
    )

    return IntervalMetrics(
        n=n,
        nominal_pct=nominal_coverage_pct(quantiles),
        coverage_pct=100.0 * float(np.sum(inside)) / n,
        mean_width_kw=mean_width,
        pinaw_pct=pinaw,
        pinball_kw=pinball,
        miss_low_pct=100.0 * float(np.sum(below)) / n,
        miss_high_pct=100.0 * float(np.sum(above)) / n,
    )


def interval_metrics_by_lead(
    pairs: list[ForecastActualPair], capacity_kw: float | None = None, buckets=LEAD_BUCKETS
) -> list[tuple[str, IntervalMetrics]]:
    """Coverage per lead-time bucket - the reliability breakdown.

    A band should be narrow and still honest at short lead, and wider further
    out. Coverage that stays flat while width grows means the extra width is
    not buying anything; coverage that collapses at long lead means the model
    knows less than its band admits out there.
    """
    return [
        (label, compute_interval_metrics([p for p in pairs if low <= p.lead_hours < high], capacity_kw))
        for label, low, high in buckets
    ]


def build_pairs(
    issuances: list[tuple],
    actual_by_time: dict[datetime, float],
) -> list[ForecastActualPair]:
    """Join stored forecast issuances to recorded actuals.

    `issuances` is (target_time, issued_at, predicted_kw) with two optional
    trailing fields (lower_kw, upper_kw) - what
    `RealDataStore.forecast_history_issuances` returns, already parsed to
    datetimes. `actual_by_time` maps a target hour to the recorded actual output.

    A forecast with no actual for its hour is skipped entirely (nothing to score
    against). The persistence reference for a pair with lead L is the actual one
    lead-time earlier, i.e. "what it was doing when this forecast was issued" -
    left None when that hour isn't in the actuals.
    """
    pairs: list[ForecastActualPair] = []
    for row in issuances:
        target_time, issued_at, predicted_kw = row[0], row[1], row[2]
        # 3-tuples stay valid: the interval columns were added later (2026-07-25)
        # and a caller that doesn't have them still gets point metrics.
        lower = row[3] if len(row) > 3 else None
        upper = row[4] if len(row) > 4 else None
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
                lower_kw=None if lower is None else float(lower),
                upper_kw=None if upper is None else float(upper),
            )
        )
    return pairs


def _round_to_hour(when: datetime) -> datetime:
    """The hour `when` falls in - actuals are recorded on hour anchors (see
    serving.record_generated_power), so an issue time mid-hour has to be floored
    to line up with them."""
    return when.replace(minute=0, second=0, microsecond=0)
