import pandas as pd
import pytest

from nongfab_simulation.what_if import ScenarioParams, apply_scenario


def test_baseline_scenario_is_a_no_op():
    baseline = pd.Series([10.0, 20.0, 30.0])
    result = apply_scenario(baseline, ScenarioParams())
    assert list(result) == pytest.approx([10.0, 20.0, 30.0])


def test_extra_cloud_attenuation_reduces_power():
    baseline = pd.Series([100.0])
    result = apply_scenario(baseline, ScenarioParams(extra_cloud_attenuation_pct=20.0))
    assert result.iloc[0] == pytest.approx(80.0)


def test_negative_cloud_attenuation_means_clearer_than_baseline():
    baseline = pd.Series([100.0])
    result = apply_scenario(baseline, ScenarioParams(extra_cloud_attenuation_pct=-10.0))
    assert result.iloc[0] == pytest.approx(110.0)


def test_curtailment_reduces_power():
    baseline = pd.Series([100.0])
    result = apply_scenario(baseline, ScenarioParams(curtailment_pct=25.0))
    assert result.iloc[0] == pytest.approx(75.0)


def test_degradation_compounds_with_years_since_commissioning():
    baseline = pd.Series([100.0])
    result_5y = apply_scenario(baseline, ScenarioParams(degradation_pct_per_year=0.5), years_since_commissioning=5.0)
    result_10y = apply_scenario(baseline, ScenarioParams(degradation_pct_per_year=0.5), years_since_commissioning=10.0)
    assert result_5y.iloc[0] == pytest.approx(97.5)  # 100 * (1 - 0.005*5)
    assert result_10y.iloc[0] == pytest.approx(95.0)
    assert result_10y.iloc[0] < result_5y.iloc[0]


def test_all_three_adjustments_combine_multiplicatively():
    baseline = pd.Series([100.0])
    params = ScenarioParams(extra_cloud_attenuation_pct=10.0, curtailment_pct=10.0, degradation_pct_per_year=1.0)
    result = apply_scenario(baseline, params, years_since_commissioning=2.0)
    # 100 * 0.9 * 0.9 * (1 - 0.02) = 79.38
    assert result.iloc[0] == pytest.approx(79.38)


def test_result_never_goes_negative_even_with_extreme_inputs():
    baseline = pd.Series([100.0])
    result = apply_scenario(baseline, ScenarioParams(extra_cloud_attenuation_pct=90.0, curtailment_pct=90.0))
    assert result.iloc[0] >= 0


def test_rejects_impossible_reduction_below_negative_100_percent():
    with pytest.raises(ValueError):
        apply_scenario(pd.Series([100.0]), ScenarioParams(curtailment_pct=-150.0))


def test_rejects_negative_years_since_commissioning():
    with pytest.raises(ValueError):
        apply_scenario(pd.Series([100.0]), ScenarioParams(), years_since_commissioning=-1.0)


def test_degradation_floor_does_not_go_negative_for_extreme_age():
    baseline = pd.Series([100.0])
    result = apply_scenario(baseline, ScenarioParams(degradation_pct_per_year=50.0), years_since_commissioning=10.0)
    assert result.iloc[0] >= 0
