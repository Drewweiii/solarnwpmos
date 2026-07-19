"""Unit tests for the pure green-savings calculation module (no I/O)."""

import pytest

from nongfab_api import green_savings as g


def test_bill_saving_uses_normal_tou_hv_peak_rate():
    m = g.compute_metrics(energy_kwh=1000.0, dc_capacity_kwp=100.0, capacity_years=1.0)
    assert m.bill_saving_thb == pytest.approx(1000.0 * 4.1025)


def test_ugt1_is_normal_plus_premium_and_units_equal_energy():
    m = g.compute_metrics(energy_kwh=1000.0, dc_capacity_kwp=100.0, capacity_years=1.0)
    assert m.ugt1_units_kwh == 1000.0
    assert m.ugt1_saving_thb == pytest.approx(1000.0 * (4.1025 + 0.0375))


def test_ugt2_portfolio_a_hv_rate():
    m = g.compute_metrics(energy_kwh=1000.0, dc_capacity_kwp=100.0, capacity_years=1.0)
    assert m.ugt2_units_kwh == 1000.0
    assert m.ugt2_saving_thb == pytest.approx(1000.0 * 4.0423)


def test_scope2_uses_tgo_emission_factor():
    m = g.compute_metrics(energy_kwh=2000.0, dc_capacity_kwp=100.0, capacity_years=1.0)
    assert m.scope2_co2_avoided_kg == pytest.approx(2000.0 * 0.4999)


def test_carbon_credit_and_trees_are_capacity_based_not_energy_based():
    # Same capacity+years but wildly different energy -> identical credit/trees.
    a = g.compute_metrics(energy_kwh=1.0, dc_capacity_kwp=100.0, capacity_years=1.0)
    b = g.compute_metrics(energy_kwh=999999.0, dc_capacity_kwp=100.0, capacity_years=1.0)
    assert a.carbon_credit_units == b.carbon_credit_units == pytest.approx(0.901 * 100.0)
    assert a.trees_equivalent == b.trees_equivalent == pytest.approx(101.0 * 100.0)
    assert a.carbon_credit_value_thb == pytest.approx(0.901 * 100.0 * 100.0)


def test_lifetime_scales_credit_by_years():
    one = g.compute_metrics(energy_kwh=1000.0, dc_capacity_kwp=100.0, capacity_years=1.0)
    life = g.compute_metrics(energy_kwh=1000.0, dc_capacity_kwp=100.0, capacity_years=25.0)
    assert life.carbon_credit_units == pytest.approx(one.carbon_credit_units * 25.0)


def test_negative_energy_rejected():
    with pytest.raises(ValueError):
        g.compute_metrics(energy_kwh=-1.0, dc_capacity_kwp=100.0, capacity_years=1.0)


def test_assumptions_echoes_the_locked_constants():
    a = g.assumptions()
    assert a["normal_rate_thb_per_kwh"] == 4.1025
    assert a["ugt1_rate_thb_per_kwh"] == pytest.approx(4.14)
    assert a["ugt2_rate_thb_per_kwh"] == 4.0423
    assert a["ef_scope2_kg_per_kwh"] == 0.4999
