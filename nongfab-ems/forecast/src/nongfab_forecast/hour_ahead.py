"""Hour-ahead forecaster: LightGBM and Random Forest candidates on NWP + lag +
clear-sky features (from Module 3's `nongfab_features`), tuned with Optuna
(Bayesian) + early stopping for LightGBM. Loss is L2 (squared error) by default
for LightGBM, per the architecture doc, with L1 (MAE) selectable for comparison
("ℓ2 พร้อมทดลอง ℓ1").

Both algorithms exist per the reference deck (Songsiri, "An Introduction to
Solar Energy Forecasting") comparing RF/SVR/MARS/ANN and finding RF the best
performer on real measured data - training.py's train_now() trains both per
k-step lead hour and registers whichever wins on held-out validation RMSE (see
that module's own k-step orchestration). IMPORTANT CAVEAT (see forecast/
README.md's "Real-data feature layer" for the full explanation): this repo has
no real generation telemetry anywhere, so every target here is a deterministic
physics-model conversion of the same NWP row used as input - "RF beats
LightGBM" in this system reflects which algorithm fits that deterministic
function more closely, not which one forecasts the real plant more accurately.
The comparison machinery is still real and will reflect true forecast skill
the moment real telemetry exists to train against.

Prediction intervals come from two extra LightGBM models trained with the
`quantile` objective (or, for Random Forest, from the empirical spread across
individual trees' predictions - a standard "quantile regression forest"
approximation) at the interval's lower/upper quantiles (e.g. 0.05/0.95 for a
90% interval) - a standard, well-supported way to get PICP/PINAW-style
intervals out of a tree model without a parametric noise assumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

optuna.logging.set_verbosity(optuna.logging.WARNING)  # Optuna is chatty by default; one line per cycle is enough


@dataclass
class HourAheadModel:
    """LightGBM candidate - point model + two quantile models for the PI."""

    point_model: lgb.LGBMRegressor
    lower_model: lgb.LGBMRegressor
    upper_model: lgb.LGBMRegressor
    feature_names: list[str]
    best_params: dict = field(default_factory=dict)
    interval_quantiles: tuple[float, float] = (0.05, 0.95)
    algorithm: str = "lightgbm"


@dataclass
class RFHourAheadModel:
    """Random Forest candidate - one forest gives both the point prediction
    (mean across trees) and the PI (empirical quantiles across individual
    trees' predictions, a standard quantile-regression-forest approximation -
    no separate quantile-objective models needed, unlike the LightGBM path).
    """

    forest: RandomForestRegressor
    feature_names: list[str]
    best_params: dict = field(default_factory=dict)
    interval_quantiles: tuple[float, float] = (0.05, 0.95)
    algorithm: str = "random_forest"


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


def _predict_lgbm_hour_ahead(model: HourAheadModel, X: pd.DataFrame) -> pd.DataFrame:
    """Returns a DataFrame aligned to X's index with columns: pred, lower, upper.
    `lower`/`upper` are clipped so the interval never inverts (quantile models
    are trained independently and can occasionally cross near the tails), and
    `pred` is then clipped into that interval - the point model is a third,
    separately-trained model (different objective than either quantile model),
    so nothing otherwise guarantees it lands inside its own interval (this was
    the pre-existing "PYTHONHASHSEED-flaky round trip test" cause on this
    module's single-lead predecessor - now that k-step trains 6x as many
    LightGBM trios, the same gap surfaced reliably instead of rarely).
    """
    X = X[model.feature_names]
    pred = model.point_model.predict(X)
    lower = model.lower_model.predict(X)
    upper = model.upper_model.predict(X)
    lower, upper = np.minimum(lower, upper), np.maximum(lower, upper)
    pred = np.clip(pred, lower, upper)
    return pd.DataFrame({"pred": pred, "lower": lower, "upper": upper}, index=X.index)


def train_rf_hour_ahead_model(
    X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame, y_val: pd.Series,
    interval_quantiles: tuple[float, float] = (0.05, 0.95), n_estimators: int = 300, seed: int = 0,
) -> RFHourAheadModel:
    """No Optuna search (unlike LightGBM) - Random Forest's own defaults are
    already close to its practical ceiling for a dataset this size (a few
    hundred to a few thousand rows), and the reference deck's own RF result
    didn't tune extensively either. `X_val`/`y_val` are accepted for interface
    symmetry with train_hour_ahead_model (training.py's k-step orchestration
    calls both the same way) but only used for the eventual metric comparison
    there, not for early stopping here (RandomForestRegressor has none).
    """
    del X_val, y_val  # symmetry with train_hour_ahead_model's signature, see docstring
    forest = RandomForestRegressor(n_estimators=n_estimators, random_state=seed, n_jobs=-1, min_samples_leaf=2)
    forest.fit(X_train, y_train)
    return RFHourAheadModel(
        forest=forest, feature_names=list(X_train.columns), best_params={"n_estimators": n_estimators}, interval_quantiles=interval_quantiles,
    )


def _predict_rf_hour_ahead(model: RFHourAheadModel, X: pd.DataFrame) -> pd.DataFrame:
    """Point = mean across trees; PI = empirical (lo_q, hi_q) percentile across
    each individual tree's own prediction - the "quantile regression forest"
    approximation this module's docstring describes.
    """
    X = X[model.feature_names]
    # Individual trees (forest.estimators_) are fit internally on plain arrays, not
    # the DataFrame the outer RandomForestRegressor.fit() sees - passing a DataFrame
    # to tree.predict() here works but triggers a "fitted without feature names"
    # UserWarning per tree; .to_numpy() avoids it without changing the result.
    X_arr = X.to_numpy()
    tree_preds = np.stack([tree.predict(X_arr) for tree in model.forest.estimators_], axis=0)  # (n_trees, n_samples)
    lo_q, hi_q = model.interval_quantiles
    pred = tree_preds.mean(axis=0)
    lower = np.percentile(tree_preds, lo_q * 100, axis=0)
    upper = np.percentile(tree_preds, hi_q * 100, axis=0)
    lower, upper = np.minimum(lower, upper), np.maximum(lower, upper)
    return pd.DataFrame({"pred": pred, "lower": lower, "upper": upper}, index=X.index)


def predict_hour_ahead(model: HourAheadModel | RFHourAheadModel, X: pd.DataFrame) -> pd.DataFrame:
    """Dispatches to the LightGBM or Random Forest predictor based on which
    candidate `model` actually is - callers (serving.py) don't need to know
    which algorithm won training.py's k-step auto-select comparison. Returns
    a DataFrame aligned to X's index with columns: pred, lower, upper.
    """
    if isinstance(model, RFHourAheadModel):
        return _predict_rf_hour_ahead(model, X)
    return _predict_lgbm_hour_ahead(model, X)


@dataclass
class HourAheadKStepModel:
    """Six independently-trained models, one per lead hour (default 1-6h) -
    not a single multi-output model, since each lead hour sees a different
    NWP-forecast-skill/feature relationship as lead time grows (matching the
    reference deck's own "Forecast results: k-step" evaluation, which scores
    each k separately too - see forecast/README.md's "Reference" section).
    Each sub-model independently won an RF-vs-LightGBM comparison at training
    time (training.py's k-step orchestration) - `algorithm_by_lead_hour`
    records which. Bundled into one object (not 6 separately MLflow-registered
    models) so the existing one-model-per-(horizon,zone) registry/versioning
    scheme (registry.py) needed no changes for this - see forecast/README.md.
    """

    models_by_lead_hour: dict[int, HourAheadModel | RFHourAheadModel]
    algorithm_by_lead_hour: dict[int, str]
    bias_correctors_by_lead_hour: dict[int, object] = field(default_factory=dict)  # bias_correction.BiasCorrectionModel, see that module
    lead_hours: tuple[int, ...] = (1, 2, 3, 4, 5, 6)


def predict_hour_ahead_kstep(model: HourAheadKStepModel, X_by_lead_hour: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """`X_by_lead_hour`: {lead_hour: single-row X frame for that lead hour's
    own sub-model}. Returns one row per lead hour present in *both* the model
    and `X_by_lead_hour` (a lead hour missing real/synthetic input data at
    serving time is silently skipped, not an error - see serving.py's caller),
    indexed by lead_hour ascending, columns pred/lower/upper. Applies each
    lead's bias corrector (if one was trained) after the base prediction - see
    bias_correction.py.
    """
    from .bias_correction import apply_bias_correction

    rows = []
    for lead_hour, sub_model in model.models_by_lead_hour.items():
        if lead_hour not in X_by_lead_hour:
            continue
        X = X_by_lead_hour[lead_hour]
        result = predict_hour_ahead(sub_model, X)
        pred, lower, upper = float(result["pred"].iloc[0]), float(result["lower"].iloc[0]), float(result["upper"].iloc[0])
        corrector = model.bias_correctors_by_lead_hour.get(lead_hour)
        if corrector is not None:
            pred, lower, upper = apply_bias_correction(corrector, X, pred, lower, upper)
        rows.append({"lead_hour": lead_hour, "pred": pred, "lower": lower, "upper": upper})
    return pd.DataFrame(rows).set_index("lead_hour").sort_index()
