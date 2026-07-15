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

from . import registry
from .day_ahead import predict_day_ahead, train_day_ahead_model
from .hour_ahead import predict_hour_ahead, train_hour_ahead_model
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


def train_now(zone: str, horizon: str) -> TrainResult:
    """Trains a fresh model for (zone, horizon) against synthetic data (no
    real accumulated history yet - see README "Known gaps") and registers it
    with MLflow. Raises UnknownZoneError/UnknownHorizonError for bad input -
    the same exception types serving.get_latest_forecast() raises, so
    callers (the dev API route, the Prefect retrain flow) handle both the
    same way.
    """
    zone = validate_zone(zone)
    horizon = validate_horizon(horizon)

    if horizon == "minute":
        train_df = _synthetic_minute_df(n=400, seed=0)
        model = train_minute_ahead_model(
            train_df, ["cloud_opacity_pct", "cloud_index"], "cloud_opacity_pct", epochs=30, patience=6,
        )
        params = {"lookback": model.lookback, "horizon": model.horizon}
        metrics = {"best_val_loss": min(model.train_history)}

    elif horizon == "hour":
        X, y = _synthetic_hour_df(n=300, seed=0)
        X_train, y_train, X_val, y_val = X.iloc[:200], y.iloc[:200], X.iloc[200:], y.iloc[200:]
        model = train_hour_ahead_model(X_train, y_train, X_val, y_val, n_trials=5)

        X_test, y_test = _synthetic_hour_df(n=100, seed=1)
        pred = predict_hour_ahead(model, X_test)
        params = dict(model.best_params)
        metrics = {**evaluate_point_forecast(y_test, pred["pred"]), **evaluate_prediction_interval(y_test, pred["lower"], pred["upper"])}

    else:  # day
        train_df = _synthetic_day_df(n_hours=24 * 20, seed=0)
        model = train_day_ahead_model(train_df, "power_kw", ["ssrd_w_m2", "temp2m_c"], epochs=15)

        test_df = _synthetic_day_df(n_hours=24, seed=1)
        test_df.index = train_df.index[-1] + pd.to_timedelta(np.arange(1, 25), unit="h")
        pred = predict_day_ahead(model, train_df, test_df[["ssrd_w_m2", "temp2m_c"]], periods=24)
        params = {"quantiles": str(model.quantiles)}
        metrics = {
            **evaluate_point_forecast(test_df["power_kw"], pred["pred"]),
            **evaluate_prediction_interval(test_df["power_kw"], pred["lower"], pred["upper"]),
        }

    run_id, version = registry.log_run(horizon, zone, model, params=params, metrics=metrics)
    return TrainResult(zone=zone, horizon=horizon, run_id=run_id, model_version=version, metrics=metrics)
