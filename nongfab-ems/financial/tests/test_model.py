import pytest

from nongfab_financial.model import (
    DEFAULT_CAPEX_PER_KWP_THB,
    FinancialAssumptions,
    _find_payback_year,
    _irr,
    compute_financial_analysis,
)


def test_compute_financial_analysis_rejects_negative_energy():
    with pytest.raises(ValueError):
        compute_financial_analysis(-1.0, 100.0)


def test_compute_financial_analysis_rejects_non_positive_capacity():
    with pytest.raises(ValueError):
        compute_financial_analysis(100_000.0, 0.0)


def test_compute_financial_analysis_derives_capex_from_capacity_when_not_given():
    result = compute_financial_analysis(100_000.0, 200.0)
    assert result.capex_thb == pytest.approx(DEFAULT_CAPEX_PER_KWP_THB * 200.0)


def test_compute_financial_analysis_uses_explicit_capex_when_given():
    assumptions = FinancialAssumptions(capex_thb=5_000_000.0)
    result = compute_financial_analysis(100_000.0, 200.0, assumptions)
    assert result.capex_thb == 5_000_000.0


def test_compute_financial_analysis_returns_one_cash_flow_row_per_lifetime_year():
    assumptions = FinancialAssumptions(lifetime_years=10)
    result = compute_financial_analysis(100_000.0, 200.0, assumptions)
    assert len(result.cash_flows) == 10
    assert [cf.year for cf in result.cash_flows] == list(range(1, 11))


def test_compute_financial_analysis_energy_degrades_year_over_year():
    assumptions = FinancialAssumptions(degradation_pct_per_year=1.0, lifetime_years=5)
    result = compute_financial_analysis(100_000.0, 200.0, assumptions)
    energies = [cf.ac_energy_kwh for cf in result.cash_flows]
    assert energies == sorted(energies, reverse=True)
    assert energies[0] > energies[-1]


def test_compute_financial_analysis_zero_boi_holiday_means_tax_from_year_1():
    assumptions = FinancialAssumptions(boi_tax_holiday_years=0, tariff_thb_per_kwh=10.0, opex_pct_of_capex_per_year=0.0)
    result = compute_financial_analysis(100_000.0, 200.0, assumptions)
    assert result.cash_flows[0].tax_thb > 0


def test_compute_financial_analysis_boi_holiday_zeroes_tax_during_holiday_years():
    assumptions = FinancialAssumptions(boi_tax_holiday_years=3, tariff_thb_per_kwh=10.0, opex_pct_of_capex_per_year=0.0)
    result = compute_financial_analysis(100_000.0, 200.0, assumptions)
    for cf in result.cash_flows[:3]:
        assert cf.tax_thb == 0.0
    assert result.cash_flows[3].tax_thb > 0


def test_compute_financial_analysis_higher_tariff_improves_npv():
    low = compute_financial_analysis(100_000.0, 200.0, FinancialAssumptions(tariff_thb_per_kwh=2.0))
    high = compute_financial_analysis(100_000.0, 200.0, FinancialAssumptions(tariff_thb_per_kwh=8.0))
    assert high.npv_thb > low.npv_thb


def test_compute_financial_analysis_a_very_cheap_capex_pays_back_and_has_positive_irr():
    # A deliberately generous scenario (cheap CAPEX, rich tariff, no
    # OPEX/tax) should unambiguously pay back quickly with a large positive
    # IRR - a sanity check that the whole pipeline (energy -> revenue ->
    # cash flow -> NPV/IRR/payback) is wired consistently, not testing
    # exact values. CAPEX is generous but not so tiny that the true IRR
    # exceeds _irr()'s search range (see that function's own docstring for
    # why the range is bounded, not unlimited).
    assumptions = FinancialAssumptions(
        capex_thb=500_000.0, tariff_thb_per_kwh=10.0, opex_pct_of_capex_per_year=0.0, tax_rate_pct=0.0
    )
    result = compute_financial_analysis(100_000.0, 200.0, assumptions)
    assert result.npv_thb > 0
    assert result.irr_pct is not None
    assert result.irr_pct > 0
    assert result.simple_payback_years is not None
    assert result.simple_payback_years < 1
    assert result.discounted_payback_years is not None
    assert result.discounted_payback_years >= result.simple_payback_years


def test_compute_financial_analysis_never_paying_back_gives_none():
    # A deliberately hopeless scenario (huge CAPEX, worthless tariff) should
    # never cross zero within the lifetime.
    assumptions = FinancialAssumptions(capex_thb=1_000_000_000.0, tariff_thb_per_kwh=0.01, opex_pct_of_capex_per_year=0.0)
    result = compute_financial_analysis(100_000.0, 200.0, assumptions)
    assert result.simple_payback_years is None
    assert result.discounted_payback_years is None
    assert result.npv_thb < 0


def test_compute_financial_analysis_lcoe_is_positive_and_finite_for_a_normal_scenario():
    result = compute_financial_analysis(100_000.0, 200.0)
    assert 0 < result.lcoe_thb_per_kwh < float("inf")


def test_irr_finds_zero_for_a_simple_doubling_case():
    # -100 now, +200 in one year -> IRR should be exactly 100%.
    irr = _irr([-100.0, 200.0])
    assert irr == pytest.approx(100.0, abs=0.01)


def test_irr_returns_none_when_project_never_breaks_even():
    irr = _irr([-100.0, 1.0, 1.0, 1.0])
    assert irr is None


def test_find_payback_year_interpolates_within_the_crossing_year():
    # -100 capex, +40/year -> crosses zero at exactly year 2.5
    cumulative = [-60.0, -20.0, 20.0, 60.0]
    payback = _find_payback_year(cumulative, capex=100.0)
    assert payback == pytest.approx(2.5)


def test_find_payback_year_returns_none_if_it_never_crosses_zero():
    cumulative = [-80.0, -60.0, -40.0]
    assert _find_payback_year(cumulative, capex=100.0) is None


def test_financial_assumptions_rejects_invalid_tax_rate():
    with pytest.raises(ValueError):
        FinancialAssumptions(tax_rate_pct=150.0)


def test_financial_assumptions_rejects_negative_boi_years():
    with pytest.raises(ValueError):
        FinancialAssumptions(boi_tax_holiday_years=-1)


def test_financial_assumptions_rejects_non_positive_explicit_capex():
    with pytest.raises(ValueError):
        FinancialAssumptions(capex_thb=0.0)
