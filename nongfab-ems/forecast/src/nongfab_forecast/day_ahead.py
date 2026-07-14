"""Day-ahead forecaster: NeuralProphet with trend + seasonality + future
regressors (SSRD, temperature from Module 2's NWP), MAE loss per the
architecture doc. `n_lags=0` deliberately - the model is driven by trend/
seasonality/regressors that are all known ahead of time for the full
day-ahead horizon, not by autoregressing on the target's own recent lags
(which aren't available that far into the future).

Prediction intervals come from NeuralProphet's native `quantiles` support
(quantile regression heads), not a separate model - simpler than the
hour-ahead LightGBM approach since NeuralProphet already provides it.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

import pandas as pd
from neuralprophet import NeuralProphet

logging.getLogger("NP").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="neuralprophet")


@dataclass
class DayAheadModel:
    model: NeuralProphet
    target_col: str
    regressor_cols: list[str]
    quantiles: tuple[float, float]


def _to_neuralprophet_frame(df: pd.DataFrame, target_col: str, regressor_cols: list[str]) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("df must be indexed by a DatetimeIndex (becomes NeuralProphet's 'ds' column)")
    out = df[[target_col, *regressor_cols]].rename(columns={target_col: "y"})
    out.insert(0, "ds", df.index)
    return out.reset_index(drop=True)


def train_day_ahead_model(
    df: pd.DataFrame, target_col: str, regressor_cols: list[str], quantiles: tuple[float, float] = (0.05, 0.95),
    epochs: int = 50, learning_rate: float = 0.1, freq: str = "h",
    daily_seasonality: bool = True, weekly_seasonality: bool = True, yearly_seasonality: bool = False,
) -> DayAheadModel:
    """`df` must be indexed by a tz-aware (or naive - both work) DatetimeIndex,
    with `target_col` and every column in `regressor_cols` present.
    """
    train_df = _to_neuralprophet_frame(df, target_col, regressor_cols)

    model = NeuralProphet(
        n_lags=0, n_forecasts=1, loss_func="MAE", quantiles=list(quantiles), epochs=epochs, learning_rate=learning_rate,
        daily_seasonality=daily_seasonality, weekly_seasonality=weekly_seasonality, yearly_seasonality=yearly_seasonality,
    )
    for col in regressor_cols:
        model.add_future_regressor(col)

    model.fit(train_df, freq=freq, progress=None)
    return DayAheadModel(model=model, target_col=target_col, regressor_cols=regressor_cols, quantiles=quantiles)


def predict_day_ahead(model: DayAheadModel, history_df: pd.DataFrame, future_regressors_df: pd.DataFrame, periods: int) -> pd.DataFrame:
    """`history_df` is the same-shaped frame training used (index + target_col +
    regressor_cols) - NeuralProphet needs some history context even though
    n_lags=0 means it isn't autoregressing on it. `future_regressors_df` must be
    indexed by the `periods` future timestamps to forecast, with `regressor_cols`
    columns (e.g. Module 2's NWP future regressors for tomorrow).

    Returns a DataFrame indexed by a tz-aware (UTC) ds with columns: pred, lower, upper.
    """
    input_had_tz = history_df.index.tz is not None
    history = _to_neuralprophet_frame(history_df, model.target_col, model.regressor_cols)
    # regressors_df passed to make_future_dataframe needs a 'ds' column, not a DatetimeIndex
    future_regressors = future_regressors_df[model.regressor_cols].copy()
    future_regressors.insert(0, "ds", future_regressors_df.index)

    future = model.model.make_future_dataframe(history, regressors_df=future_regressors, periods=periods)
    fcst = model.model.predict(future)

    lo_q, hi_q = model.quantiles
    lower_col = f"yhat1 {lo_q * 100:.1f}%"
    upper_col = f"yhat1 {hi_q * 100:.1f}%"

    result = fcst[["ds", "yhat1", lower_col, upper_col]].tail(periods).rename(
        columns={"yhat1": "pred", lower_col: "lower", upper_col: "upper"}
    ).set_index("ds")

    # NeuralProphet normalizes tz-aware timestamps to UTC internally then returns
    # them tz-naive (verified live - not documented behavior) - restore tz-awareness
    # so callers get back what they put in, not a silently-degraded index.
    if input_had_tz and result.index.tz is None:
        result.index = result.index.tz_localize("UTC")
    return result
