"""Minute-ahead forecaster: a CNN-LSTM over the cloud opacity/index sequence
(Module 1's `cloud_obs`) - Conv1d layers extract local temporal patterns,
an LSTM models longer dependencies, a linear head predicts the next
`horizon` steps. Trained with Adam + early stopping on Huber or L1 loss
(both reused from `neuralforecast.losses.pytorch`, per the architecture
doc's "ℓ1 หรือ Huber (robust)").

neuralforecast does not ship a literal "CNN-LSTM" architecture (its `LSTM`,
`TCN`, `RNN` classes are single-family, not this specific hybrid) - so the
network itself is a small hand-written torch module here rather than a
`neuralforecast.models.X` class, while still genuinely using the
`neuralforecast` package for its loss functions (the actual per-sample loss
math, not just imported and unused). See README "Design notes" for this
interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import torch
from neuralforecast.losses.pytorch import MAE, HuberLoss
from torch import nn


class CNNLSTM(nn.Module):
    def __init__(self, n_features: int, conv_channels: int, lstm_hidden: int, horizon: int):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(n_features, conv_channels, kernel_size=3, padding=1), nn.ReLU(),
            nn.Conv1d(conv_channels, conv_channels, kernel_size=3, padding=1), nn.ReLU(),
        )
        self.lstm = nn.LSTM(input_size=conv_channels, hidden_size=lstm_hidden, batch_first=True)
        self.head = nn.Linear(lstm_hidden, horizon)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, lookback, n_features)
        x = self.conv(x.transpose(1, 2)).transpose(1, 2)  # -> (batch, lookback, conv_channels)
        _, (h_n, _) = self.lstm(x)
        return self.head(h_n[-1])  # (batch, horizon)


@dataclass
class MinuteAheadModel:
    net: CNNLSTM
    lookback: int
    horizon: int
    feature_names: list[str]
    feat_mean: np.ndarray
    feat_std: np.ndarray
    target_mean: float
    target_std: float
    train_history: list[float] = field(default_factory=list)


def make_sequences(df: pd.DataFrame, feature_cols: list[str], target_col: str, lookback: int, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    """Sliding-window (X, y) pairs from a chronologically-sorted DataFrame.
    X[i] = feature_cols over rows [i, i+lookback); y[i] = target_col over the
    following `horizon` rows.
    """
    values = df[feature_cols].to_numpy(dtype=float)
    target = df[target_col].to_numpy(dtype=float)
    n_samples = len(df) - lookback - horizon + 1
    if n_samples <= 0:
        raise ValueError(f"not enough rows ({len(df)}) for lookback={lookback} + horizon={horizon}")

    X = np.stack([values[i : i + lookback] for i in range(n_samples)])
    y = np.stack([target[i + lookback : i + lookback + horizon] for i in range(n_samples)])
    return X, y


def train_minute_ahead_model(
    df: pd.DataFrame, feature_cols: list[str], target_col: str, lookback: int = 12, horizon: int = 6,
    loss: str = "huber", conv_channels: int = 16, lstm_hidden: int = 32, epochs: int = 200, patience: int = 15,
    lr: float = 1e-3, val_frac: float = 0.2, batch_size: int = 32, seed: int = 0,
) -> MinuteAheadModel:
    if loss not in ("l1", "huber"):
        raise ValueError(f"loss must be 'l1' or 'huber', got {loss!r}")

    torch.manual_seed(seed)
    X, y = make_sequences(df, feature_cols, target_col, lookback, horizon)

    n_val = max(1, int(len(X) * val_frac))
    n_train = len(X) - n_val
    if n_train < 1:
        raise ValueError("not enough sequences for a chronological train/val split - use more history or a shorter lookback/horizon")

    X_train, y_train = X[:n_train], y[:n_train]
    X_val, y_val = X[n_train:], y[n_train:]

    feat_mean = X_train.reshape(-1, X_train.shape[-1]).mean(axis=0)
    feat_std = X_train.reshape(-1, X_train.shape[-1]).std(axis=0)
    feat_std[feat_std == 0] = 1.0
    target_mean = float(y_train.mean())
    target_std = float(y_train.std()) or 1.0

    X_train_t = torch.tensor((X_train - feat_mean) / feat_std, dtype=torch.float32)
    y_train_t = torch.tensor((y_train - target_mean) / target_std, dtype=torch.float32)
    X_val_t = torch.tensor((X_val - feat_mean) / feat_std, dtype=torch.float32)
    y_val_t = torch.tensor((y_val - target_mean) / target_std, dtype=torch.float32)

    net = CNNLSTM(n_features=len(feature_cols), conv_channels=conv_channels, lstm_hidden=lstm_hidden, horizon=horizon)
    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    loss_fn = HuberLoss() if loss == "huber" else MAE()

    best_val_loss = float("inf")
    best_state = None
    patience_counter = 0
    history: list[float] = []

    for _epoch in range(epochs):
        net.train()
        permutation = torch.randperm(len(X_train_t))
        for start in range(0, len(X_train_t), batch_size):
            idx = permutation[start : start + batch_size]
            xb, yb = X_train_t[idx], y_train_t[idx]
            optimizer.zero_grad()
            pred = net(xb)
            batch_loss = loss_fn(y=yb, y_hat=pred, mask=torch.ones_like(yb))
            batch_loss.backward()
            optimizer.step()

        net.eval()
        with torch.no_grad():
            val_pred = net(X_val_t)
            val_loss = loss_fn(y=y_val_t, y_hat=val_pred, mask=torch.ones_like(y_val_t)).item()
        history.append(val_loss)

        if val_loss < best_val_loss - 1e-6:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                break

    if best_state is not None:
        net.load_state_dict(best_state)

    return MinuteAheadModel(
        net=net, lookback=lookback, horizon=horizon, feature_names=list(feature_cols),
        feat_mean=feat_mean, feat_std=feat_std, target_mean=target_mean, target_std=target_std, train_history=history,
    )


def predict_minute_ahead(model: MinuteAheadModel, recent_window: pd.DataFrame) -> np.ndarray:
    """`recent_window` must have exactly `model.lookback` rows (the most recent
    observations, chronologically ordered) with `model.feature_names` columns.
    Returns a length-`model.horizon` array of predicted values.
    """
    if len(recent_window) != model.lookback:
        raise ValueError(f"expected exactly {model.lookback} rows (the model's lookback window), got {len(recent_window)}")

    X = recent_window[model.feature_names].to_numpy(dtype=float)
    X_norm = (X - model.feat_mean) / model.feat_std
    X_t = torch.tensor(X_norm[None, :, :], dtype=torch.float32)

    model.net.eval()
    with torch.no_grad():
        pred_norm = model.net(X_t).numpy()[0]
    return pred_norm * model.target_std + model.target_mean
