"""Sum-k LSTM: a shared-backbone, multi-head prediction-interval forecaster for
hour-ahead, built from the user's own reference slides (2026-07-16, a course
project on probabilistic hour-ahead irradiance forecasting - see forecast/
README.md's matching dated entry for the full request/decision trail). Competes
as a third candidate alongside LightGBM/Random Forest in training.py's existing
per-lead-hour auto-select (training.py's own docstring explains the 3-way tie
-break), not a replacement for either.

Reference architecture (as described in the slides):
  - One shared "common model" M_c (an LSTM in the slides' headlined/winning
    variant - an ANN alternative is also shown but not carried over here, see
    "Adaptations" below) processes *lagged* regressors only - it never sees a
    future value.
  - K independent small head networks M_1..M_k, one per forecast step. Each
    head takes the shared backbone's output *plus that step's own future
    regressors* (in the slides: clear-sky irradiance and NWP forecasts for that
    specific future time) and predicts a prediction interval (not a bare point
    value) for that step.
  - Trained *jointly*: one loss L_total = sum_i L_i(theta_c, theta_i) across
    every head at once, so the shared backbone's weights get gradient signal
    from all K heads simultaneously - not K independently-trained models the
    way this module's LightGBM/Random Forest siblings work.
  - Each head's own loss balances *coverage* (PICP - the fraction of true
    values actually inside the predicted interval) against *interval width*,
    not plain point-accuracy error - see qd_loss()'s own docstring for the
    specific (QD/Pearce-et-al.-style) formulation used here.

Adaptations from the literal slides (all discussed with the user before
building, not silent deviations):
  - K=6 steps at *1-hour* resolution (matching this project's own
    HOUR_LEAD_HOURS = (1..6), i.e. hour_ahead.py's existing Intra-day
    structure), not the slides' K=4 steps at 15-minute resolution. Same
    architecture, this project's own established horizon.
  - LSTM backbone only (the slides' headlined "proposed method" and best
    result) - the ANN backbone variant shown alongside it in the slides isn't
    built here.
  - "Auto-lagged regressors" and "future regressors" are built from this
    project's own available real signals, not the slides' literal I(t-15)/
    I(t-30)/I(t-45) sequence: the auto-lagged branch is a length-K sequence
    of [power_lag1, cloud_index] taken from the *same underlying forecast
    cycle's* view at each of the 6 lead-hour buckets (see
    _build_common_inputs's own docstring for exactly why "sequence" means
    "across lead-hour views" here, not literal wall-clock lag steps) - this
    project's k-step data is bucketed by lead hour (real_data.
    real_hour_frame_kstep), not a single continuous per-minute series the way
    the slides' own dataset apparently was. The future-regressor branch per
    head is [ssrd_w_m2, temp2m_c, clear_sky_ssrd_w_m2] (NWP forecast + real
    I_clr - see real_data.py's own _clear_sky_ssrd_w_m2), matching the
    slides' I_nwp/T_nwp/I_clr roles (RH_nwp is available in nwp_history but
    not yet wired into hour-ahead's feature set for *any* of the 3
    candidates - a possible follow-up, not unique to Sum-k LSTM).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import torch
from torch import nn

# Matches hour_ahead.HOUR_LEAD_HOURS exactly - not imported from there to avoid
# a circular import (hour_ahead.py imports *this* module, see training.py's wiring).
LEAD_HOURS = (1, 2, 3, 4, 5, 6)
AUTO_LAGGED_COLS = ("power_lag1", "cloud_index")
FUTURE_REGRESSOR_COLS = ("ssrd_w_m2", "temp2m_c", "clear_sky_ssrd_w_m2")


class CommonLSTM(nn.Module):
    """The shared backbone M_c - an LSTM over the length-K auto-lagged sequence,
    returning its final hidden state as the shared representation every head
    reads from."""

    def __init__(self, n_auto_features: int, hidden_size: int):
        super().__init__()
        self.lstm = nn.LSTM(input_size=n_auto_features, hidden_size=hidden_size, batch_first=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, K, n_auto_features)
        _, (h_n, _) = self.lstm(x)
        return h_n[-1]  # (batch, hidden_size) - the LSTM's final-step hidden state


class HeadNet(nn.Module):
    """One per lead hour (M_k) - shared representation + this lead's own future
    regressors -> [lower, upper] prediction-interval bounds in normalized target
    space. No separate point-estimate output: Sum-k LSTM's own architecture is a
    PI estimator (see module docstring); predict_sum_k_lstm() below reports the
    interval's midpoint as `pred` for compatibility with the other two
    candidates' point-forecast interface, not because this model computes one
    independently.
    """

    def __init__(self, hidden_size: int, n_future_features: int, head_hidden: int = 16):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(hidden_size + n_future_features, head_hidden),
            nn.ReLU(),
            nn.Linear(head_hidden, 2),
        )

    def forward(self, shared: torch.Tensor, future_features: torch.Tensor) -> torch.Tensor:
        return self.net(torch.cat([shared, future_features], dim=-1))


def qd_loss(
    y_true: torch.Tensor, lower: torch.Tensor, upper: torch.Tensor,
    confidence: float = 0.9, lambda_width: float = 10.0, softening: float = 50.0,
) -> torch.Tensor:
    """Quality-Driven-style prediction-interval loss (Pearce et al., 2018,
    "High-Quality Prediction Intervals for Deep Learning") - a genuine
    coverage-plus-width objective, not plain MSE, matching the slides'
    "loss = PICP + sum of large width". `k_soft` is a differentiable
    (sigmoid-based) approximation of "is y_true actually inside [lower,
    upper]" (a hard 0/1 indicator has no gradient); `softening` controls how
    close that approximation is to the true step function. `mpiw_capt` is the
    mean width of only the *captured* intervals (an interval that misses the
    true value shouldn't get credit for being narrow), and the coverage
    penalty pushes soft-PICP toward `confidence` whenever it falls short (only
    penalized one-directionally - an interval that's *already* wide enough
    isn't punished further for being even wider, which is what width alone
    already discourages).
    """
    k_soft = torch.sigmoid(softening * (upper - y_true)) * torch.sigmoid(softening * (y_true - lower))
    picp_soft = k_soft.mean()
    width = (upper - lower).clamp(min=0)
    mpiw_capt = (k_soft * width).sum() / (k_soft.sum() + 1e-6)
    coverage_penalty = torch.clamp(confidence - picp_soft, min=0) ** 2
    return mpiw_capt + lambda_width * coverage_penalty


@dataclass
class SumKLSTMModel:
    common: CommonLSTM
    heads: nn.ModuleDict  # keys: str(lead_hour), e.g. "1".."6"
    lead_hours: tuple[int, ...]
    auto_feat_mean: np.ndarray
    auto_feat_std: np.ndarray
    future_feat_mean: dict[int, np.ndarray] = field(default_factory=dict)
    future_feat_std: dict[int, np.ndarray] = field(default_factory=dict)
    target_mean: dict[int, float] = field(default_factory=dict)
    target_std: dict[int, float] = field(default_factory=dict)
    confidence: float = 0.9
    train_history: list[float] = field(default_factory=list)


def align_common_rows(
    X_by_lead: dict[int, pd.DataFrame], y_by_lead: dict[int, pd.Series], lead_hours: tuple[int, ...],
) -> tuple[dict[int, pd.DataFrame], dict[int, pd.Series], int]:
    """Truncates every present lead's (X, y) to the same row count (the most
    recent `common_n` rows of each) - the shared backbone needs row i to mean
    "the same underlying forecast cycle" across every lead's own view (see
    module docstring's "Adaptations" on why "sequence" means "across lead-hour
    views" here). Real per-lead series can differ in length (different leads
    may have accumulated different amounts of real history); this alignment
    is Sum-k LSTM's own concern - LightGBM/Random Forest keep using each
    lead's *full* series independently (see training.py's own docstring),
    since forcing that same truncation on them would shrink their training
    data for no benefit of their own.
    """
    present = [lead for lead in lead_hours if lead in X_by_lead]
    common_n = min(len(X_by_lead[lead]) for lead in present)
    aligned_X = {lead: X_by_lead[lead].iloc[-common_n:].reset_index(drop=True) for lead in present}
    aligned_y = {lead: y_by_lead[lead].iloc[-common_n:].reset_index(drop=True) for lead in present}
    return aligned_X, aligned_y, common_n


def _build_auto_sequence(X_by_lead: dict[int, pd.DataFrame], lead_hours: tuple[int, ...], n_rows: int) -> np.ndarray:
    """(n_rows, K, 2) - row i, step k = lead_hours[k]'s own [power_lag1,
    cloud_index] at aligned row i. K = number of leads present in X_by_lead
    (every lead when real/synthetic data covers all 6; fewer only if some
    lead's own InsufficientHistoryError propagated - see training.py)."""
    present = [lead for lead in lead_hours if lead in X_by_lead]
    return np.stack([X_by_lead[lead][list(AUTO_LAGGED_COLS)].to_numpy(dtype=float)[:n_rows] for lead in present], axis=1)


def train_sum_k_lstm_model(
    X_by_lead: dict[int, pd.DataFrame], y_by_lead: dict[int, pd.Series], lead_hours: tuple[int, ...] = LEAD_HOURS,
    hidden_size: int = 16, head_hidden: int = 16, confidence: float = 0.9, epochs: int = 150, patience: int = 15,
    lr: float = 1e-3, val_frac: float = 0.2, seed: int = 0,
) -> SumKLSTMModel:
    """Trains the shared backbone and all K heads jointly against one combined
    loss (L_total = sum of each head's own qd_loss - see module docstring).
    `X_by_lead`/`y_by_lead`: one (X, y) pair per lead hour, same shape
    real_data.real_hour_frame_kstep()/serving._synthetic_hour_df() already
    produce for LightGBM/Random Forest (columns power_lag1/cloud_index/
    ssrd_w_m2/temp2m_c/clear_sky_ssrd_w_m2) - this function does not fetch its
    own data, training.py passes the same frames every candidate sees.
    """
    torch.manual_seed(seed)
    X_by_lead, y_by_lead, common_n = align_common_rows(X_by_lead, y_by_lead, lead_hours)
    present_leads = [lead for lead in lead_hours if lead in X_by_lead]
    if common_n < 4:
        raise ValueError(f"not enough aligned rows ({common_n}) across leads to train Sum-k LSTM - need >= 4")

    n_val = max(1, int(common_n * val_frac))
    n_train = common_n - n_val
    if n_train < 2:
        n_train, n_val = common_n - 1, 1

    auto_seq = _build_auto_sequence(X_by_lead, lead_hours, common_n)  # (common_n, K, 2)
    auto_mean = auto_seq[:n_train].reshape(-1, auto_seq.shape[-1]).mean(axis=0)
    auto_std = auto_seq[:n_train].reshape(-1, auto_seq.shape[-1]).std(axis=0)
    auto_std[auto_std == 0] = 1.0
    auto_seq_norm = (auto_seq - auto_mean) / auto_std
    auto_train_t = torch.tensor(auto_seq_norm[:n_train], dtype=torch.float32)
    auto_val_t = torch.tensor(auto_seq_norm[n_train:], dtype=torch.float32)

    common = CommonLSTM(n_auto_features=len(AUTO_LAGGED_COLS), hidden_size=hidden_size)
    heads = nn.ModuleDict()
    future_train_t: dict[int, torch.Tensor] = {}
    future_val_t: dict[int, torch.Tensor] = {}
    target_train_t: dict[int, torch.Tensor] = {}
    target_val_t: dict[int, torch.Tensor] = {}
    future_mean: dict[int, np.ndarray] = {}
    future_std: dict[int, np.ndarray] = {}
    target_mean: dict[int, float] = {}
    target_std: dict[int, float] = {}

    for lead in present_leads:
        X_lead = X_by_lead[lead][list(FUTURE_REGRESSOR_COLS)].to_numpy(dtype=float)
        y_lead = y_by_lead[lead].to_numpy(dtype=float)

        f_mean, f_std = X_lead[:n_train].mean(axis=0), X_lead[:n_train].std(axis=0)
        f_std[f_std == 0] = 1.0
        t_mean, t_std = float(y_lead[:n_train].mean()), float(y_lead[:n_train].std()) or 1.0
        future_mean[lead], future_std[lead] = f_mean, f_std
        target_mean[lead], target_std[lead] = t_mean, t_std

        X_norm = (X_lead - f_mean) / f_std
        y_norm = (y_lead - t_mean) / t_std
        future_train_t[lead] = torch.tensor(X_norm[:n_train], dtype=torch.float32)
        future_val_t[lead] = torch.tensor(X_norm[n_train:], dtype=torch.float32)
        target_train_t[lead] = torch.tensor(y_norm[:n_train], dtype=torch.float32)
        target_val_t[lead] = torch.tensor(y_norm[n_train:], dtype=torch.float32)

        heads[str(lead)] = HeadNet(hidden_size=hidden_size, n_future_features=len(FUTURE_REGRESSOR_COLS), head_hidden=head_hidden)

    params = list(common.parameters())
    for head in heads.values():
        params += list(head.parameters())
    optimizer = torch.optim.Adam(params, lr=lr)

    best_val_loss = float("inf")
    best_state = None
    patience_counter = 0
    history: list[float] = []

    for _epoch in range(epochs):
        common.train()
        for head in heads.values():
            head.train()
        optimizer.zero_grad()
        shared_train = common(auto_train_t)
        total_loss = torch.tensor(0.0)
        for lead in present_leads:
            out = heads[str(lead)](shared_train, future_train_t[lead])
            lower, upper = out[:, 0], out[:, 1]
            lower, upper = torch.minimum(lower, upper), torch.maximum(lower, upper)
            total_loss = total_loss + qd_loss(target_train_t[lead], lower, upper, confidence=confidence)
        total_loss.backward()
        optimizer.step()

        common.eval()
        for head in heads.values():
            head.eval()
        with torch.no_grad():
            shared_val = common(auto_val_t)
            val_loss = torch.tensor(0.0)
            for lead in present_leads:
                out = heads[str(lead)](shared_val, future_val_t[lead])
                lower, upper = out[:, 0], out[:, 1]
                lower, upper = torch.minimum(lower, upper), torch.maximum(lower, upper)
                val_loss = val_loss + qd_loss(target_val_t[lead], lower, upper, confidence=confidence)
        val_loss_value = float(val_loss.item())
        history.append(val_loss_value)

        if val_loss_value < best_val_loss - 1e-6:
            best_val_loss = val_loss_value
            best_state = {
                "common": {k: v.clone() for k, v in common.state_dict().items()},
                "heads": {k: v.clone() for k, v in heads.state_dict().items()},
            }
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                break

    if best_state is not None:
        common.load_state_dict(best_state["common"])
        heads.load_state_dict(best_state["heads"])

    return SumKLSTMModel(
        common=common, heads=heads, lead_hours=tuple(present_leads),
        auto_feat_mean=auto_mean, auto_feat_std=auto_std,
        future_feat_mean=future_mean, future_feat_std=future_std,
        target_mean=target_mean, target_std=target_std, confidence=confidence, train_history=history,
    )


def predict_sum_k_lstm(model: SumKLSTMModel, lead_hour: int, X_by_lead: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Batch prediction for one lead hour - `X_by_lead` must include every lead
    the model was trained on (same auto-lagged-sequence requirement training
    has, see module docstring), each with at least as many rows as the lead
    being predicted (only the *last* len(X_by_lead[lead_hour]) rows of every
    other lead are used, aligned positionally - see align_common_rows).
    Returns a DataFrame aligned to X_by_lead[lead_hour]'s index with columns
    pred/lower/upper (pred = interval midpoint, see HeadNet's own docstring).
    """
    if lead_hour not in model.lead_hours:
        raise ValueError(f"model was not trained for lead_hour={lead_hour} (trained leads: {model.lead_hours})")

    n_rows = len(X_by_lead[lead_hour])
    auto_seq = _build_auto_sequence(X_by_lead, model.lead_hours, n_rows)
    auto_seq_norm = (auto_seq - model.auto_feat_mean) / model.auto_feat_std
    auto_t = torch.tensor(auto_seq_norm, dtype=torch.float32)

    X_lead = X_by_lead[lead_hour][list(FUTURE_REGRESSOR_COLS)].to_numpy(dtype=float)
    X_norm = (X_lead - model.future_feat_mean[lead_hour]) / model.future_feat_std[lead_hour]
    future_t = torch.tensor(X_norm, dtype=torch.float32)

    model.common.eval()
    head = model.heads[str(lead_hour)]
    head.eval()
    with torch.no_grad():
        shared = model.common(auto_t)
        out = head(shared, future_t).numpy()
    lower_norm, upper_norm = np.minimum(out[:, 0], out[:, 1]), np.maximum(out[:, 0], out[:, 1])

    t_mean, t_std = model.target_mean[lead_hour], model.target_std[lead_hour]
    lower = lower_norm * t_std + t_mean
    upper = upper_norm * t_std + t_mean
    pred = (lower + upper) / 2
    return pd.DataFrame({"pred": pred, "lower": lower, "upper": upper}, index=X_by_lead[lead_hour].index)
