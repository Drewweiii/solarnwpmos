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
from .day_ahead import predict_day_ahead, train_day_ahead_model
from .hour_ahead import predict_hour_ahead, train_hour_ahead_model
from .local_store import RealDataStore
from .metrics import evaluate_point_forecast, evaluate_prediction_interval
from .minute_ahead import train_minute_ahead_model
from .serving import _synthetic_day_df, _synthetic_hour_df, _synthetic_minute_df, validate_horizon, validate_zone


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
            train_df, ["cloud_opacity_pct", "cloud_index"], "cloud_opacity_pct", epochs=30, patience=6,
        )
        params = {"lookback": model.lookback, "horizon": model.horizon}
        metrics = {"best_val_loss": min(model.train_history)}

    elif horizon == "hour":
        try:
            X_all, y_all = real_data.real_hour_frame(zone, store)
            data_source = "real"
            # MIN_HOUR_ROWS=24 (real_data.py) guarantees this 70/30 split always
            # leaves a non-empty (>= 8 rows) validation set.
            split = int(len(X_all) * 0.7)
            X_train, y_train, X_val, y_val = X_all.iloc[:split], y_all.iloc[:split], X_all.iloc[split:], y_all.iloc[split:]
            X_test, y_test = X_val, y_val
        except real_data.InsufficientHistoryError:
            # Original fixed 200/100 split, unchanged - kept exact to avoid
            # perturbing the synthetic path's already-tested/live-verified behavior.
            X_all, y_all = _synthetic_hour_df(n=300, seed=0)
            X_train, y_train, X_val, y_val = X_all.iloc[:200], y_all.iloc[:200], X_all.iloc[200:], y_all.iloc[200:]
            X_test, y_test = _synthetic_hour_df(n=100, seed=1)
        model = train_hour_ahead_model(X_train, y_train, X_val, y_val, n_trials=5)
        pred = predict_hour_ahead(model, X_test)
        params = dict(model.best_params)
        metrics = {**evaluate_point_forecast(y_test, pred["pred"]), **evaluate_prediction_interval(y_test, pred["lower"], pred["upper"])}

    else:  # day
        try:
            train_df = real_data.real_day_frame(zone, store)
            data_source = "real"
        except real_data.InsufficientHistoryError:
            train_df = _synthetic_day_df(n_hours=24 * 20, seed=0)
        model = train_day_ahead_model(train_df, "power_kw", ["ssrd_w_m2", "temp2m_c"], epochs=15)

        if data_source == "real":
            try:
                future_df = real_data.real_future_regressors(store)[:24]
            except real_data.InsufficientHistoryError:
                future_df = pd.DataFrame()
            if len(future_df) == 0:  # no real future NWP rows accumulated yet - fall back to the synthetic eval frame
                test_df = _synthetic_day_df(n_hours=24, seed=1)
                test_df.index = train_df.index[-1] + pd.to_timedelta(np.arange(1, 25), unit="h")
            else:
                test_df = future_df
        else:
            test_df = _synthetic_day_df(n_hours=24, seed=1)
            test_df.index = train_df.index[-1] + pd.to_timedelta(np.arange(1, 25), unit="h")
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

    run_id, version = registry.log_run(horizon, zone, model, params={**params, "data_source": data_source}, metrics=metrics)
    return TrainResult(zone=zone, horizon=horizon, run_id=run_id, model_version=version, metrics=metrics, data_source=data_source)
