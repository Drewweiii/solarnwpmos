import pandas as pd
import pytest

from nongfab_simulation.loss_model import (
    DEFAULT_SOILING_PCT_LAND,
    DEFAULT_SOILING_PCT_MARINE,
    LossFactors,
    annual_specific_yield,
    apply_losses,
    clip_to_inverter_capacity,
    combined_derate,
    default_loss_factors,
    loss_breakdown_summary,
    performance_ratio,
)


def test_default_loss_factors_gives_jetty_higher_soiling_than_land_zones():
    jetty = default_loss_factors("Jetty")
    gis = default_loss_factors("GIS")
    isb = default_loss_factors("ISB")

    assert jetty.soiling_pct == DEFAULT_SOILING_PCT_MARINE
    assert gis.soiling_pct == DEFAULT_SOILING_PCT_LAND
    assert isb.soiling_pct == DEFAULT_SOILING_PCT_LAND
    assert jetty.soiling_pct > gis.soiling_pct


def test_combined_derate_multiplies_not_adds():
    factors = LossFactors(soiling_pct=10.0, shading_pct=10.0, mismatch_pct=0.0, dc_wiring_pct=0.0, connections_pct=0.0, availability_pct=0.0)
    # 0.9 * 0.9 = 0.81, not 1 - 0.20 = 0.80
    assert combined_derate(factors) == pytest.approx(0.81)


def test_combined_derate_rejects_out_of_range_percentage():
    with pytest.raises(ValueError):
        combined_derate(LossFactors(soiling_pct=150.0))


def test_apply_losses_reduces_power_and_respects_inverter_efficiency():
    dc_power = pd.Series([100.0, 200.0])
    factors = LossFactors(soiling_pct=0.0, shading_pct=0.0, mismatch_pct=0.0, dc_wiring_pct=0.0, connections_pct=0.0, availability_pct=0.0)
    ac_power = apply_losses(dc_power, factors, inverter_efficiency_pct=99.0)
    assert list(ac_power) == pytest.approx([99.0, 198.0])


def test_apply_losses_rejects_invalid_inverter_efficiency():
    with pytest.raises(ValueError):
        apply_losses(pd.Series([100.0]), default_loss_factors("GIS"), inverter_efficiency_pct=0.0)


def test_clip_to_inverter_capacity_caps_but_never_raises_power():
    ac_power = pd.Series([10.0, 40.0, 60.0])  # inverter rated 50kW
    clipped = clip_to_inverter_capacity(ac_power, inverter_ac_capacity_kw=50.0)
    assert list(clipped) == [10.0, 40.0, 50.0]


def test_clip_to_inverter_capacity_rejects_nonpositive_capacity():
    with pytest.raises(ValueError):
        clip_to_inverter_capacity(pd.Series([10.0]), inverter_ac_capacity_kw=0.0)


def test_performance_ratio_is_one_at_theoretical_ceiling():
    # 100 kWp system, 5 kWh/m^2 POA irradiation, exactly 500 kWh actual output
    pr = performance_ratio(actual_ac_energy_kwh=500.0, poa_irradiance_kwh_per_m2=5.0, capacity_kwp=100.0)
    assert pr == pytest.approx(1.0)


def test_performance_ratio_reflects_real_world_losses():
    pr = performance_ratio(actual_ac_energy_kwh=400.0, poa_irradiance_kwh_per_m2=5.0, capacity_kwp=100.0)
    assert pr == pytest.approx(0.8)


def test_performance_ratio_rejects_nonpositive_inputs():
    with pytest.raises(ValueError):
        performance_ratio(actual_ac_energy_kwh=100.0, poa_irradiance_kwh_per_m2=0.0, capacity_kwp=100.0)


def test_annual_specific_yield():
    assert annual_specific_yield(annual_ac_energy_kwh=90090.0, capacity_kwp=60.06) == pytest.approx(1500.0)


def test_loss_breakdown_summary_includes_inverter_and_total():
    factors = default_loss_factors("Jetty")
    summary = loss_breakdown_summary(factors, inverter_efficiency_pct=99.0)
    assert summary["soiling_pct"] == DEFAULT_SOILING_PCT_MARINE
    assert summary["inverter_loss_pct"] == pytest.approx(1.0)
    assert 0 < summary["total_system_loss_pct"] < 100
