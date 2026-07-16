import numpy as np
import pandas as pd
import pytest
import torch

from nongfab_forecast.sum_k_lstm import (
    AUTO_LAGGED_COLS,
    FUTURE_REGRESSOR_COLS,
    LEAD_HOURS,
    SumKLSTMModel,
    predict_sum_k_lstm,
    qd_loss,
    train_sum_k_lstm_model,
)


def _synthetic_lead_frame(n: int, lead: int, seed: int) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed + lead)
    ssrd = rng.uniform(0, 1000, size=n)
    temp = rng.uniform(20, 40, size=n)
    power_lag1 = rng.uniform(0, 200, size=n)
    cloud_index = rng.uniform(0, 1, size=n)
    clear_sky = ssrd * rng.uniform(1.0, 1.3, size=n)
    power = 0.2 * ssrd - 0.5 * temp + 0.1 * power_lag1 + 10 + rng.normal(0, 5, size=n)
    X = pd.DataFrame(
        {"ssrd_w_m2": ssrd, "temp2m_c": temp, "power_lag1": power_lag1, "clear_sky_ssrd_w_m2": clear_sky, "cloud_index": cloud_index}
    )
    return X, pd.Series(power, name="power_kw")


def _all_lead_frames(n: int = 120, seed: int = 0) -> tuple[dict, dict]:
    X_by_lead, y_by_lead = {}, {}
    for lead in LEAD_HOURS:
        X_by_lead[lead], y_by_lead[lead] = _synthetic_lead_frame(n, lead, seed)
    return X_by_lead, y_by_lead


def test_qd_loss_penalizes_a_narrow_miss_more_than_a_modestly_wider_covering_interval():
    y = torch.tensor([0.0, 0.0, 0.0])
    narrow_missing = qd_loss(y, torch.tensor([1.0, 1.0, 1.0]), torch.tensor([1.5, 1.5, 1.5]))
    covering = qd_loss(y, torch.tensor([-0.5, -0.5, -0.5]), torch.tensor([0.5, 0.5, 0.5]))
    assert float(narrow_missing) > float(covering)


def test_qd_loss_still_penalizes_an_unnecessarily_wide_covering_interval():
    """Width matters too, not just coverage - a much wider interval than needed
    should score worse than a tighter one that still covers."""
    y = torch.tensor([0.0, 0.0, 0.0])
    tight_covering = qd_loss(y, torch.tensor([-0.5, -0.5, -0.5]), torch.tensor([0.5, 0.5, 0.5]))
    unnecessarily_wide = qd_loss(y, torch.tensor([-5.0, -5.0, -5.0]), torch.tensor([5.0, 5.0, 5.0]))
    assert float(unnecessarily_wide) > float(tight_covering)


def test_train_sum_k_lstm_model_trains_a_head_per_lead():
    X_by_lead, y_by_lead = _all_lead_frames(n=100, seed=1)
    model = train_sum_k_lstm_model(X_by_lead, y_by_lead, hidden_size=4, head_hidden=4, epochs=5, patience=3)

    assert isinstance(model, SumKLSTMModel)
    assert model.lead_hours == LEAD_HOURS
    assert set(model.heads.keys()) == {str(lead) for lead in LEAD_HOURS}
    assert len(model.train_history) > 0


def test_predict_sum_k_lstm_returns_pred_lower_upper_aligned_to_input():
    X_by_lead, y_by_lead = _all_lead_frames(n=100, seed=2)
    model = train_sum_k_lstm_model(X_by_lead, y_by_lead, hidden_size=4, head_hidden=4, epochs=5, patience=3)

    X_test, _ = _synthetic_lead_frame(10, lead=3, seed=99)
    X_test_by_lead = {lead: X_by_lead[lead].iloc[-10:].reset_index(drop=True) for lead in LEAD_HOURS}
    X_test_by_lead[3] = X_test  # the lead actually being predicted uses fresh test rows

    result = predict_sum_k_lstm(model, lead_hour=3, X_by_lead=X_test_by_lead)
    assert list(result.columns) == ["pred", "lower", "upper"]
    assert len(result) == 10
    assert (result["lower"] <= result["upper"]).all()
    assert (result["lower"] <= result["pred"]).all()
    assert (result["pred"] <= result["upper"]).all()


def test_predict_sum_k_lstm_rejects_an_untrained_lead():
    X_by_lead, y_by_lead = _all_lead_frames(n=100, seed=3)
    model = train_sum_k_lstm_model(
        {k: v for k, v in X_by_lead.items() if k != 6}, {k: v for k, v in y_by_lead.items() if k != 6},
        hidden_size=4, head_hidden=4, epochs=3, patience=2,
    )
    with pytest.raises(ValueError):
        predict_sum_k_lstm(model, lead_hour=6, X_by_lead=X_by_lead)


def test_train_sum_k_lstm_model_raises_when_too_few_aligned_rows():
    X_by_lead, y_by_lead = _all_lead_frames(n=3, seed=4)
    with pytest.raises(ValueError):
        train_sum_k_lstm_model(X_by_lead, y_by_lead, epochs=2)


def test_train_sum_k_lstm_model_aligns_leads_of_different_lengths():
    """Real per-lead data can accumulate at different rates - training must not
    crash, and should use the shortest lead's own row count as the common
    alignment (see _align_common_rows)."""
    X_by_lead, y_by_lead = _all_lead_frames(n=50, seed=5)
    X_by_lead[1], y_by_lead[1] = _synthetic_lead_frame(120, lead=1, seed=5)  # one lead has much more real history

    model = train_sum_k_lstm_model(X_by_lead, y_by_lead, hidden_size=4, head_hidden=4, epochs=3, patience=2)
    assert model.lead_hours == LEAD_HOURS


def test_auto_lagged_and_future_regressor_column_names_match_real_data_schema():
    """Regression guard: these must exactly match real_data.real_hour_frame_kstep's
    own column names (power_lag1/cloud_index/ssrd_w_m2/temp2m_c/
    clear_sky_ssrd_w_m2), or training.py's wiring silently trains on the wrong
    columns."""
    assert AUTO_LAGGED_COLS == ("power_lag1", "cloud_index")
    assert FUTURE_REGRESSOR_COLS == ("ssrd_w_m2", "temp2m_c", "clear_sky_ssrd_w_m2")
