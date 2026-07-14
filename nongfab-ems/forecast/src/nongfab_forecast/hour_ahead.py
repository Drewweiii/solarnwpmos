"""Hour-ahead forecaster: LightGBM on NWP + lag + clear-sky features (from
Module 3's `nongfab_features`), tuned with Optuna (Bayesian) + early stopping.
Loss is L2 (squared error) by default, per the architecture doc, with L1
(MAE) selectable for comparison ("ℓ2 พร้อมทดลอง ℓ1").

Prediction intervals come from two extra LightGBM models trained with the
`quantile` objective at the interval's lower/upper quantiles (e.g. 0.05/0.95
for a 90% interval) - a standard, well-supported way to get PICP/PINAW-style
intervals out of a tree model without a parametric noise assumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd

optuna.logging.set_verbosity(optuna.logging.WARNING)  # Optuna is chatty by default; one line per cycle is enough


@dataclass
class HourAheadModel:
    point_model: lgb.LGBMRegressor
    lower_model: lgb.LGBMRegressor
    upper_model: lgb.LGBMRegressor
    feature_names: list[str]
    best_params: dict = field(default_factory=dict)
    interval_quantiles: tuple[float, float] = (0.05, 0.95)


def _objective(trial: optuna.Trial, X_train, y_train, X_val, y_val, loss: str) -> float:
    params = {
        "objective": "regression_l2" if loss == "l2" else "regression_l1",
        "num_leaves": trial.suggest_int("num_leaves", 8, 64),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "min_child_samples": trial.suggest_int("min_child_samples", 3, 30),
        "n_estimators": 200,
        "verbosity": -1,
    }
    model = lgb.LGBMRegressor(**params)
    model.fit(
        X_train, y_train, eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(stopping_rounds=10, verbose=False)],
    )
    pred = model.predict(X_val, num_iteration=model.best_iteration_)
    return float(np.sqrt(np.mean((pred - y_val) ** 2)))


def train_hour_ahead_model(
    X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame, y_val: pd.Series,
    n_trials: int = 20, loss: str = "l2", interval_quantiles: tuple[float, float] = (0.05, 0.95), seed: int = 0,
) -> HourAheadModel:
    """Bayesian-tunes a point-forecast LightGBM model against (X_val, y_val),
    then trains two quantile models at `interval_quantiles` (reusing the
    tuned tree-shape hyperparameters, since quantile loss shape is close
    enough to squared/absolute error that a separate search rarely earns its cost).
    """
    if loss not in ("l1", "l2"):
        raise ValueError(f"loss must be 'l1' or 'l2', got {loss!r}")

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(lambda trial: _objective(trial, X_train, y_train, X_val, y_val, loss), n_trials=n_trials)

    best_params = dict(study.best_params)
    point_model = lgb.LGBMRegressor(objective="regression_l2" if loss == "l2" else "regression_l1", n_estimators=200, verbosity=-1, **best_params)
    point_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], callbacks=[lgb.early_stopping(stopping_rounds=10, verbose=False)])

    lo_q, hi_q = interval_quantiles
    lower_model = lgb.LGBMRegressor(objective="quantile", alpha=lo_q, n_estimators=200, verbosity=-1, **best_params)
    lower_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], callbacks=[lgb.early_stopping(stopping_rounds=10, verbose=False)])

    upper_model = lgb.LGBMRegressor(objective="quantile", alpha=hi_q, n_estimators=200, verbosity=-1, **best_params)
    upper_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], callbacks=[lgb.early_stopping(stopping_rounds=10, verbose=False)])

    return HourAheadModel(
        point_model=point_model, lower_model=lower_model, upper_model=upper_model,
        feature_names=list(X_train.columns), best_params=best_params, interval_quantiles=interval_quantiles,
    )


def predict_hour_ahead(model: HourAheadModel, X: pd.DataFrame) -> pd.DataFrame:
    """Returns a DataFrame aligned to X's index with columns: pred, lower, upper.
    `lower`/`upper` are clipped so the interval never inverts (quantile models
    are trained independently and can occasionally cross near the tails).
    """
    X = X[model.feature_names]
    pred = model.point_model.predict(X)
    lower = model.lower_model.predict(X)
    upper = model.upper_model.predict(X)
    lower, upper = np.minimum(lower, upper), np.maximum(lower, upper)
    return pd.DataFrame({"pred": pred, "lower": lower, "upper": upper}, index=X.index)
