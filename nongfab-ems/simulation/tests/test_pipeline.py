import numpy as np
import pandas as pd
import pytest

from nongfab_simulation.pipeline import (
    DAYS_PER_YEAR,
    RAINY_SEASON_MONTHS,
    estimate_annual_ac_energy_kwh,
    lifecycle_ac_energy_estimate,
    loss_breakdown_with_temperature,
    monthly_ac_energy_estimates,
    simulate_zone_baseline,
)


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


def test_estimate_annual_ac_energy_kwh_is_daily_energy_times_days_per_year():
    idx, ssrd, temp = _synthetic_day()
    baseline = simulate_zone_baseline("GIS", ssrd, temp, idx)
    annual = estimate_annual_ac_energy_kwh(baseline)
    assert annual == pytest.approx(float(baseline.ac_power_kw.sum()) * DAYS_PER_YEAR)


def test_estimate_annual_ac_energy_kwh_is_positive_for_a_sunny_day():
    idx, ssrd, temp = _synthetic_day()
    baseline = simulate_zone_baseline("ISB", ssrd, temp, idx)
    assert estimate_annual_ac_energy_kwh(baseline) > 0


def test_loss_breakdown_with_temperature_adds_temperature_pct_alongside_existing_keys():
    idx, ssrd, temp = _synthetic_day()
    baseline = simulate_zone_baseline("GIS", ssrd, temp, idx)
    breakdown = loss_breakdown_with_temperature(baseline, ssrd, temp)
    assert "temperature_pct" in breakdown
    for key in baseline.loss_breakdown:
        assert breakdown[key] == baseline.loss_breakdown[key]


def test_loss_breakdown_with_temperature_is_zero_at_stc_temperature():
    idx, ssrd, _temp = _synthetic_day()
    stc_temp = np.full(24, 25.0)
    baseline = simulate_zone_baseline("GIS", ssrd, stc_temp, idx)
    breakdown = loss_breakdown_with_temperature(baseline, ssrd, stc_temp)
    assert breakdown["temperature_pct"] == pytest.approx(0.0, abs=1e-6)


def test_loss_breakdown_with_temperature_is_positive_above_stc_temperature():
    idx, ssrd, _temp = _synthetic_day()
    hot_temp = np.full(24, 40.0)
    baseline = simulate_zone_baseline("GIS", ssrd, hot_temp, idx)
    breakdown = loss_breakdown_with_temperature(baseline, ssrd, hot_temp)
    assert breakdown["temperature_pct"] > 0


def test_monthly_ac_energy_estimates_returns_one_entry_per_calendar_month():
    estimates = monthly_ac_energy_estimates("GIS", year=2026)
    assert [e.month for e in estimates] == list(range(1, 13))


def test_monthly_ac_energy_estimates_flags_rainy_season_months_correctly():
    estimates = monthly_ac_energy_estimates("ISB", year=2026)
    for e in estimates:
        assert e.is_rainy_season == (e.month in RAINY_SEASON_MONTHS)


def test_monthly_ac_energy_estimates_are_all_positive():
    estimates = monthly_ac_energy_estimates("GIS", year=2026)
    assert all(e.ac_energy_kwh > 0 for e in estimates)


def test_monthly_ac_energy_estimates_rainy_season_is_lower_than_dry_season():
    # Same zone, same latitude - the only thing distinguishing a rainy-season
    # month from a similarly-sunny dry-season month here is the cloud derate
    # (see RAINY_SEASON_EXTRA_CLOUD_ATTENUATION_PCT), so July (rainy) should
    # come in lower than January (dry) even though both are reasonably sunny
    # months at this latitude.
    estimates = {e.month: e.ac_energy_kwh for e in monthly_ac_energy_estimates("GIS", year=2026)}
    assert estimates[7] < estimates[1]


def test_lifecycle_ac_energy_estimate_year_1_matches_input():
    result = lifecycle_ac_energy_estimate(1000.0, degradation_pct_per_year=0.5)
    assert result.year_1_ac_energy_kwh == pytest.approx(1000.0)


def test_lifecycle_ac_energy_estimate_degrades_over_25_years():
    result = lifecycle_ac_energy_estimate(1000.0, degradation_pct_per_year=0.5)
    assert result.year_25_ac_energy_kwh < result.year_1_ac_energy_kwh
    assert result.year_25_pct_of_year_1 == pytest.approx(100 - 0.5 * 24, abs=1e-6)


def test_lifecycle_ac_energy_estimate_lifetime_is_sum_of_all_25_years():
    result = lifecycle_ac_energy_estimate(1000.0, degradation_pct_per_year=0.5)
    # Linear degradation -> arithmetic series: sum = years * average(first, last)
    expected = 25 * (result.year_1_ac_energy_kwh + result.year_25_ac_energy_kwh) / 2
    assert result.lifetime_ac_energy_kwh == pytest.approx(expected, rel=1e-6)


def test_lifecycle_ac_energy_estimate_zero_degradation_is_flat():
    result = lifecycle_ac_energy_estimate(1000.0, degradation_pct_per_year=0.0)
    assert result.year_25_ac_energy_kwh == pytest.approx(1000.0)
    assert result.lifetime_ac_energy_kwh == pytest.approx(25000.0)


def test_lifecycle_ac_energy_estimate_rejects_negative_year_1():
    with pytest.raises(ValueError):
        lifecycle_ac_energy_estimate(-1.0)
