import numpy as np
import pandas as pd
import pytest

from nongfab_simulation.pipeline import simulate_zone_baseline


def _synthetic_day():
    idx = pd.date_range("2026-07-14", periods=24, freq="h", tz="UTC")
    hour = idx.hour.to_numpy()
    ssrd = np.clip(1000 * np.sin(np.pi * (hour - 6) / 12), 0, None)
    temp = np.full(24, 28.0)
    return idx, ssrd, temp


def test_simulate_zone_baseline_returns_expected_structure():
    idx, ssrd, temp = _synthetic_day()
    result = simulate_zone_baseline("GIS", ssrd, temp, idx)

    assert result.zone.id == "GIS"
    assert isinstance(result.ac_power_kw, pd.Series)
    assert len(result.ac_power_kw) == 24
    assert list(result.ac_power_kw.index) == list(idx)


def test_simulate_zone_baseline_is_zero_at_night():
    idx, ssrd, temp = _synthetic_day()
    result = simulate_zone_baseline("ISB", ssrd, temp, idx)
    night_hours = (idx.hour <= 5) | (idx.hour >= 19)
    assert (result.ac_power_kw[night_hours] == 0).all()


def test_simulate_zone_baseline_clips_to_inverter_ac_capacity():
    idx, ssrd, temp = _synthetic_day()
    result = simulate_zone_baseline("GIS", ssrd, temp, idx)
    assert (result.ac_power_kw <= result.zone.ac_capacity_kw + 1e-6).all()


def test_simulate_zone_baseline_uses_zone_specific_soiling():
    idx, ssrd, temp = _synthetic_day()
    jetty = simulate_zone_baseline("Jetty", ssrd, temp, idx)
    gis = simulate_zone_baseline("GIS", ssrd, temp, idx)
    assert jetty.loss_factors.soiling_pct > gis.loss_factors.soiling_pct


def test_simulate_zone_baseline_uses_real_inverter_efficiency_from_config():
    idx, ssrd, temp = _synthetic_day()
    result = simulate_zone_baseline("ISB", ssrd, temp, idx)
    assert result.inverter_efficiency_pct == pytest.approx(99.0)


def test_zone_baseline_loss_breakdown_property_matches_loss_model():
    idx, ssrd, temp = _synthetic_day()
    result = simulate_zone_baseline("GIS", ssrd, temp, idx)
    breakdown = result.loss_breakdown
    assert breakdown["soiling_pct"] == result.loss_factors.soiling_pct
    assert 0 < breakdown["total_system_loss_pct"] < 100


def test_simulate_zone_baseline_rejects_unknown_zone():
    idx, ssrd, temp = _synthetic_day()
    with pytest.raises(KeyError):
        simulate_zone_baseline("Nowhere", ssrd, temp, idx)
