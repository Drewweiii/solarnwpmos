"""Model training: the per-horizon train-then-register logic behind the dev
API's POST /train-now/{zone}/{horizon} (api.py). Extracted (mirroring how
serving.py already holds the shared per-horizon serving logic) so the STEP
10 Prefect retrain flow (orchestration/) can call the exact same code
instead of duplicating this horizon-branching block a second time.
"""

from __future__ import annotations

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
    model). For each lead hour: trains both LightGBM and Random Forest
    candidates, registers whichever wins on held-out validation RMSE (see
    hour_ahead.py's own module docstring for the "this compares which
    algorithm fits a deterministic physics target more closely, not real
    forecast skill" caveat - genuinely real once real telemetry exists), then
    trains a bias-correction cascade on that winner's own validation residual
    (bias_correction.py - same "near-zero residual" caveat applies).

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

    for lead in HOUR_LEAD_HOURS:
        try:
            X_all, y_all = real_data.real_hour_frame_kstep(zone, store, lead)
            lead_source = "real"
            any_real = True
            split = int(len(X_all) * 0.7)
        except real_data.InsufficientHistoryError:
            # Fixed 200/100 split, unchanged from the original single-model hour-
            # ahead's synthetic path - kept exact per lead (seeded by lead hour
            # so the 6 synthetic frames aren't identical) to avoid perturbing
            # already-tested/live-verified synthetic behavior.
            X_all, y_all = _synthetic_hour_df(n=300, seed=lead)
            lead_source = "synthetic"
            split = 200
        X_train, y_train, X_val, y_val = X_all.iloc[:split], y_all.iloc[:split], X_all.iloc[split:], y_all.iloc[split:]

        lgbm_model = train_hour_ahead_model(X_train, y_train, X_val, y_val, n_trials=5)
        rf_model = train_rf_hour_ahead_model(X_train, y_train, X_val, y_val)
        lgbm_pred = predict_hour_ahead(lgbm_model, X_val)
        rf_pred = predict_hour_ahead(rf_model, X_val)
        lgbm_rmse = float(np.sqrt(np.mean((lgbm_pred["pred"].to_numpy() - y_val.to_numpy()) ** 2)))
        rf_rmse = float(np.sqrt(np.mean((rf_pred["pred"].to_numpy() - y_val.to_numpy()) ** 2)))

        if rf_rmse < lgbm_rmse:
            winner_model, winner_pred, algo, winner_rmse = rf_model, rf_pred, "random_forest", rf_rmse
        else:
            winner_model, winner_pred, algo, winner_rmse = lgbm_model, lgbm_pred, "lightgbm", lgbm_rmse
        models_by_lead[lead] = winner_model
        algo_by_lead[lead] = algo
        rmse_by_lead[lead] = winner_rmse

        day_corrector = train_bias_correction(X_val, winner_pred["pred"], y_val)
        bias_correctors_by_lead[lead] = day_corrector

        lead_metrics = {
            **evaluate_point_forecast(y_val, winner_pred["pred"]),
            **evaluate_prediction_interval(y_val, winner_pred["lower"], winner_pred["upper"]),
        }
        for key, value in lead_metrics.items():
            metrics[f"lead{lead}_{key}"] = value
        metrics[f"lead{lead}_lgbm_rmse"] = lgbm_rmse
        metrics[f"lead{lead}_rf_rmse"] = rf_rmse
        metrics[f"lead{lead}_residual_std"] = day_corrector.residual_std_train
        source_by_lead[lead] = lead_source

    model = HourAheadKStepModel(
        models_by_lead_hour=models_by_lead, algorithm_by_lead_hour=algo_by_lead,
        bias_correctors_by_lead_hour=bias_correctors_by_lead, rmse_by_lead_hour=rmse_by_lead,
        lead_hours=HOUR_LEAD_HOURS,
    )
    params = {f"lead{lead}_algorithm": algo for lead, algo in algo_by_lead.items()}
    params.update({f"lead{lead}_data_source": source for lead, source in source_by_lead.items()})
    data_source = "real" if any_real else "synthetic"
    return model, params, metrics, data_source
