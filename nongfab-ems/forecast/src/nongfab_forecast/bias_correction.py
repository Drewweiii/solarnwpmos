"""Bias-correction cascade: a lightweight second-stage model that learns the
residual error of a primary forecaster (hour_ahead's per-lead-hour models,
day_ahead's NeuralProphet), per the reference deck's "bias-correction cascade"
suggestion and the MOS+KF thesis this whole project cites (Suksamosorn &
Songsiri) - a second model regresses on the *first* model's residual instead
of predicting the target directly.

IMPORTANT CAVEAT (read before trusting any metric this module logs): the
MOS+KF thesis's bias-correction learns real NWP-vs-*measured* bias, using real
telemetry this system doesn't have (see forecast/README.md's "Real-data
feature layer"). Every target here is a deterministic physics-model conversion
of the same NWP row the primary model already sees as input - there is no
real, unexplained bias for a second model to discover; the primary model
already fits that deterministic relationship near-exactly, so the residual
this module trains against is close to pure numerical noise from the primary
model's own imperfect fit, not a real forecast-skill gap. This module is real,
tested scaffolding - not a demonstrated accuracy improvement - ready to start
doing real work the moment real generation telemetry exists. Every training
call returns `residual_std_train` (training.py logs it to MLflow) specifically
so this can be watched empirically rather than just asserted: a residual_std
that stays a tiny fraction of the target's own std is exactly what "there's no
real bias to learn yet" looks like in the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge


@dataclass
class BiasCorrectionModel:
    corrector: Ridge
    feature_names: list[str]
    residual_std_train: float


def train_bias_correction(X: pd.DataFrame, primary_pred: pd.Series | np.ndarray, y_true: pd.Series) -> BiasCorrectionModel:
    """`X`: the same features the primary model saw (this cascade reuses them
    rather than a separate feature set - see module docstring on why there's
    no independent "past error" signal to draw on yet). `primary_pred`: the
    primary model's own prediction for these rows. `y_true`: matching targets
    (still physics-derived, not measured - see module docstring).

    Trains a small Ridge regression (deliberately not another gradient-boosted
    tree - a residual this close to noise doesn't need tree capacity, and
    Ridge keeps "how much is this actually correcting" legible from the
    coefficients rather than hidden inside an opaque ensemble) to predict
    `residual = y_true - primary_pred` from X.
    """
    primary_pred_arr = np.asarray(primary_pred, dtype=float)
    residual = y_true.to_numpy() - primary_pred_arr
    corrector = Ridge(alpha=1.0)
    corrector.fit(X, residual)
    return BiasCorrectionModel(corrector=corrector, feature_names=list(X.columns), residual_std_train=float(np.std(residual)))


def predict_bias_correction(model: BiasCorrectionModel, X: pd.DataFrame) -> np.ndarray:
    return model.corrector.predict(X[model.feature_names])


def apply_bias_correction(model: BiasCorrectionModel, X: pd.DataFrame, pred: float, lower: float, upper: float) -> tuple[float, float, float]:
    """Applies the cascade to a single-row serving-time prediction - shifts
    pred/lower/upper by the same correction amount (the PI width itself isn't
    re-estimated by the corrector, only the center - a second uncertainty-
    quantification stage is a candidate follow-up, not built this round, see
    module docstring on why the correction signal is thin to begin with).
    """
    correction = float(predict_bias_correction(model, X)[0])
    return pred + correction, lower + correction, upper + correction
