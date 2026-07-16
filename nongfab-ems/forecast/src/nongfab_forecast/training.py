"""Model training: the per-horizon train-then-register logic behind the dev
API's POST /train-now/{zone}/{horizon} (api.py). Extracted (mirroring how
serving.py already holds the shared per-horizon serving logic) so the STEP
10 Prefect retrain flow (orchestration/) can call the exact same code
instead of duplicating this horizon-branching block a second time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import real_data, registry
from .bias_correction import train_bias_correction
from .day_ahead import predict_day_ahead, train_day_ahead_model
from .hour_ahead import HourAheadKStepModel, predict_hour_ahead, train_hour_ahead_model, train_rf_hour_ahead_model
from .local_store import RealDataStore
from .metrics import evaluate_point_forecast, evaluate_prediction_interval
from .minute_ahead import train_minute_ahead_model
from .serving import (
    HOUR_LEAD_HOURS,
    MAX_DAY_AHEAD_HOURS,
    _synthetic_day_df,
    _synthetic_hour_df,
    _synthetic_minute_df,
    validate_horizon,
    validate_zone,
)
from .sum_k_lstm import align_common_rows, predict_sum_k_lstm, train_sum_k_lstm_model

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainResult:
    zone: str
    horizon: str
    run_id: str
    model_version: int
    metrics: dict[str, float]
    data_source: str = "synthetic"  # "real" once enough real history has accumulated - see real_data.py


def train_now(zone: str, horizon: str, store: RealDataStore | None = None) -> TrainResult:
    """Trains a fresh model for (zone, horizon) and registers it with MLflow.
    Prefers real ingested/backfilled data (`real_data.py`, via `store` -
    defaults to `RealDataStore()`, which is an empty in-memory store unless
    NONGFAB_REAL_DATA_DB is set, so this call is a no-behavior-change no-op
    for every existing caller/test) once enough has accumulated; falls back to
    the original synthetic generators below that bar - see real_data.py's own
    docstring for why every real "power_kw" here is still a physics-model
    conversion of real weather, never a real measured value (no plant
    telemetry exists anywhere in this system). Raises UnknownZoneError/
    UnknownHorizonError for bad input - the same exception types serving.
    get_latest_forecast() raises, so callers (the dev API route, the Prefect
    retrain flow) handle both the same way.
    """
    zone = validate_zone(zone)
    horizon = validate_horizon(horizon)
    store = store if store is not None else RealDataStore()
    data_source = "synthetic"

    if horizon == "minute":
        try:
            train_df = real_data.real_minute_frame(store)
            data_source = "real"
        except real_data.InsufficientHistoryError:
            train_df = _synthetic_minute_df(n=400, seed=0)
        model = train_minute_ahead_model(
            train_df, real_data.MINUTE_FEATURE_COLS, "cloud_opacity_pct", epochs=30, patience=6,
        )
        params = {"lookback": model.lookback, "horizon": model.horizon}
        metrics = {"best_val_loss": min(model.train_history)}

    elif horizon == "hour":
        model, params, metrics, data_source = _train_hour_ahead_kstep(zone, store)

    else:  # day
        try:
            train_df = real_data.real_day_frame(zone, store)
            data_source = "real"
        except real_data.InsufficientHistoryError:
            train_df = _synthetic_day_df(n_hours=24 * 20, seed=0)
        model = train_day_ahead_model(train_df, "power_kw", ["ssrd_w_m2", "temp2m_c"], epochs=15)

        if data_source == "real":
            try:
                future_df = real_data.real_future_regressors(store)[:MAX_DAY_AHEAD_HOURS]
            except real_data.InsufficientHistoryError:
                future_df = pd.DataFrame()
            if len(future_df) == 0:  # no real future NWP rows accumulated yet - fall back to the synthetic eval frame
                test_df = _synthetic_day_df(n_hours=MAX_DAY_AHEAD_HOURS, seed=1)
                test_df.index = train_df.index[-1] + pd.to_timedelta(np.arange(1, MAX_DAY_AHEAD_HOURS + 1), unit="h")
            else:
                test_df = future_df
        else:
            test_df = _synthetic_day_df(n_hours=MAX_DAY_AHEAD_HOURS, seed=1)
            test_df.index = train_df.index[-1] + pd.to_timedelta(np.arange(1, MAX_DAY_AHEAD_HOURS + 1), unit="h")
        pred = predict_day_ahead(model, train_df, test_df[["ssrd_w_m2", "temp2m_c"]], periods=len(test_df))
        params = {"quantiles": str(model.quantiles)}
        if "power_kw" in test_df.columns:
            metrics = {
                **evaluate_point_forecast(test_df["power_kw"], pred["pred"]),
                **evaluate_prediction_interval(test_df["power_kw"], pred["lower"], pred["upper"]),
            }
        else:
            # real future regressors have no target to score against (that's the
            # forecast, not a held-out truth) - metrics are training-set-only here.
            metrics = {}

        # Bias-correction cascade (see bias_correction.py's "near-zero residual"
        # caveat given no real generation telemetry exists anywhere in this
        # system). Trained on its own held-out 80/20 split of train_df's own
        # *history* (genuine past rows with a known physics-derived target),
        # never on test_df/future_df - for the real-data path that's a genuine
        # future forecast with no target to learn a residual against.
        bias_split = max(1, int(len(train_df) * 0.8))
        bias_val_df = train_df.iloc[bias_split:]
        if len(bias_val_df) >= 3:
            bias_val_pred = predict_day_ahead(
                model, train_df.iloc[:bias_split], bias_val_df[["ssrd_w_m2", "temp2m_c"]], periods=len(bias_val_df)
            )
            day_corrector = train_bias_correction(
                bias_val_df[["ssrd_w_m2", "temp2m_c"]], bias_val_pred["pred"].to_numpy(), bias_val_df["power_kw"]
            )
            metrics["residual_std"] = day_corrector.residual_std_train
            params["bias_correction"] = "trained"
        else:
            params["bias_correction"] = "skipped-insufficient-history"

    run_id, version = registry.log_run(horizon, zone, model, params={**params, "data_source": data_source}, metrics=metrics)
    return TrainResult(zone=zone, horizon=horizon, run_id=run_id, model_version=version, metrics=metrics, data_source=data_source)


def _train_hour_ahead_kstep(zone: str, store: RealDataStore) -> tuple[HourAheadKStepModel, dict, dict, str]:
    """Trains HourAheadKStepModel's 6 per-lead-hour sub-models (see that
    class's own docstring for why 6 independent models, not one multi-output
    model). For each lead hour: trains LightGBM, Random Forest, and (jointly,
    once, across all 6 leads - see below) Sum-k LSTM, registers whichever
    candidate wins that lead on held-out validation RMSE (see hour_ahead.py's
    own module docstring for the "this compares which algorithm fits a
    deterministic physics target more closely, not real forecast skill"
    caveat - genuinely real once real telemetry exists), then trains a
    bias-correction cascade on that winner's own validation residual
    (bias_correction.py - same "near-zero residual" caveat applies).

    Sum-k LSTM (sum_k_lstm.py, added 2026-07-16 from the user's own reference
    slides) is trained *once*, jointly across every lead's own training split
    (not per-lead like LightGBM/Random Forest - its shared backbone needs
    gradient signal from all 6 heads at once, see that module's own
    docstring), then scored per lead the same RMSE way as the other two so
    the three genuinely compete rather than Sum-k LSTM being treated
    specially. If Sum-k LSTM fails to train (e.g. too little aligned history
    across leads - see sum_k_lstm.train_sum_k_lstm_model's own ValueError),
    the other two candidates still compete normally; a training failure here
    is never fatal to the rest of hour-ahead.

    Returns (model, params, metrics, data_source) in the same shape train_now()
    logs for every other horizon - data_source is "real" if *any* lead hour
    found enough real history, "synthetic" only if every lead hour fell back.
    """
    models_by_lead: dict[int, object] = {}
    algo_by_lead: dict[int, str] = {}
    rmse_by_lead: dict[int, float] = {}
    source_by_lead: dict[int, str] = {}
    bias_correctors_by_lead: dict[int, object] = {}
    metrics: dict[str, float] = {}
    any_real = False

    X_train_by_lead: dict[int, pd.DataFrame] = {}
    y_train_by_lead: dict[int, pd.Series] = {}
    X_val_by_lead: dict[int, pd.DataFrame] = {}
    y_val_by_lead: dict[int, pd.Series] = {}
    lgbm_by_lead: dict[int, object] = {}
    rf_by_lead: dict[int, object] = {}
    lgbm_pred_by_lead: dict[int, pd.DataFrame] = {}
    rf_pred_by_lead: dict[int, pd.DataFrame] = {}
    lgbm_rmse_by_lead: dict[int, float] = {}
    rf_rmse_by_lead: dict[int, float] = {}

    for lead in HOUR_LEAD_HOURS:
        try:
            X_all, y_all = real_data.real_hour_frame_kstep(zone, store, lead)
            source_by_lead[lead] = "real"
            any_real = True
            split = int(len(X_all) * 0.7)
        except real_data.InsufficientHistoryError:
            # Fixed 200/100 split, unchanged from the original single-model hour-
            # ahead's synthetic path - kept exact per lead (seeded by lead hour
            # so the 6 synthetic frames aren't identical) to avoid perturbing
            # already-tested/live-verified synthetic behavior.
            X_all, y_all = _synthetic_hour_df(n=300, seed=lead)
            source_by_lead[lead] = "synthetic"
            split = 200
        X_train, y_train, X_val, y_val = X_all.iloc[:split], y_all.iloc[:split], X_all.iloc[split:], y_all.iloc[split:]
        X_train_by_lead[lead], y_train_by_lead[lead] = X_train, y_train
        X_val_by_lead[lead], y_val_by_lead[lead] = X_val, y_val

        lgbm_model = train_hour_ahead_model(X_train, y_train, X_val, y_val, n_trials=5)
        rf_model = train_rf_hour_ahead_model(X_train, y_train, X_val, y_val)
        lgbm_pred = predict_hour_ahead(lgbm_model, X_val)
        rf_pred = predict_hour_ahead(rf_model, X_val)
        lgbm_by_lead[lead], rf_by_lead[lead] = lgbm_model, rf_model
        lgbm_pred_by_lead[lead], rf_pred_by_lead[lead] = lgbm_pred, rf_pred
        lgbm_rmse_by_lead[lead] = float(np.sqrt(np.mean((lgbm_pred["pred"].to_numpy() - y_val.to_numpy()) ** 2)))
        rf_rmse_by_lead[lead] = float(np.sqrt(np.mean((rf_pred["pred"].to_numpy() - y_val.to_numpy()) ** 2)))

    sum_k_model = None
    sum_k_rmse_by_lead: dict[int, float] = {}
    sum_k_pred_by_lead: dict[int, pd.DataFrame] = {}
    aligned_X_val: dict[int, pd.DataFrame] = {}
    aligned_y_val: dict[int, pd.Series] = {}
    try:
        sum_k_model = train_sum_k_lstm_model(X_train_by_lead, y_train_by_lead)
        aligned_X_val, aligned_y_val, _ = align_common_rows(X_val_by_lead, y_val_by_lead, HOUR_LEAD_HOURS)
        for lead in sum_k_model.lead_hours:
            if lead not in aligned_X_val:
                continue
            pred = predict_sum_k_lstm(sum_k_model, lead, aligned_X_val)
            sum_k_pred_by_lead[lead] = pred
            sum_k_rmse_by_lead[lead] = float(np.sqrt(np.mean((pred["pred"].to_numpy() - aligned_y_val[lead].to_numpy()) ** 2)))
    except Exception:
        logger.warning("sum_k_lstm training/scoring failed for zone=%s - LightGBM/Random Forest still compete normally", zone, exc_info=True)

    for lead in HOUR_LEAD_HOURS:
        X_val, y_val = X_val_by_lead[lead], y_val_by_lead[lead]
        candidates = [
            (lgbm_rmse_by_lead[lead], "lightgbm", lgbm_by_lead[lead], lgbm_pred_by_lead[lead], X_val, y_val),
            (rf_rmse_by_lead[lead], "random_forest", rf_by_lead[lead], rf_pred_by_lead[lead], X_val, y_val),
        ]
        if lead in sum_k_rmse_by_lead:
            candidates.append(
                (sum_k_rmse_by_lead[lead], "sum_k_lstm", None, sum_k_pred_by_lead[lead], aligned_X_val[lead], aligned_y_val[lead])
            )
        winner_rmse, algo, winner_model, winner_pred, winner_X, winner_y = min(candidates, key=lambda c: c[0])

        models_by_lead[lead] = winner_model
        algo_by_lead[lead] = algo
        rmse_by_lead[lead] = winner_rmse

        day_corrector = train_bias_correction(winner_X, winner_pred["pred"], winner_y)
        bias_correctors_by_lead[lead] = day_corrector

        lead_metrics = {
            **evaluate_point_forecast(winner_y, winner_pred["pred"]),
            **evaluate_prediction_interval(winner_y, winner_pred["lower"], winner_pred["upper"]),
        }
        for key, value in lead_metrics.items():
            metrics[f"lead{lead}_{key}"] = value
        metrics[f"lead{lead}_lgbm_rmse"] = lgbm_rmse_by_lead[lead]
        metrics[f"lead{lead}_rf_rmse"] = rf_rmse_by_lead[lead]
        if lead in sum_k_rmse_by_lead:
            metrics[f"lead{lead}_sum_k_rmse"] = sum_k_rmse_by_lead[lead]
        metrics[f"lead{lead}_residual_std"] = day_corrector.residual_std_train

    model = HourAheadKStepModel(
        models_by_lead_hour=models_by_lead, algorithm_by_lead_hour=algo_by_lead,
        bias_correctors_by_lead_hour=bias_correctors_by_lead, rmse_by_lead_hour=rmse_by_lead,
        lead_hours=HOUR_LEAD_HOURS, sum_k_model=sum_k_model,
    )
    params = {f"lead{lead}_algorithm": algo for lead, algo in algo_by_lead.items()}
    params.update({f"lead{lead}_data_source": source for lead, source in source_by_lead.items()})
    data_source = "real" if any_real else "synthetic"
    return model, params, metrics, data_source
