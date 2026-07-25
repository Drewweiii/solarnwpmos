"""Tests for P50/P90 yield and the financial Monte Carlo.

The load-bearing assertions here are the two that would be invisible if wrong:
that P90 sits BELOW P50 (the convention is a probability of exceedance, not a
percentile, and getting it backwards would make the conservative case look
optimistic), and that a zero-spread Monte Carlo reproduces the deterministic
result exactly (otherwise the page would show a distribution that quietly
disagrees with the headline number printed next to it).
"""

from __future__ import annotations

import pytest

from nongfab_financial.model import FinancialAssumptions, compute_financial_analysis
from nongfab_financial.uncertainty import (
    DEFAULT_ANNUAL_YIELD_CV_PCT,
    ExceedanceYield,
    FinancialDistribution,
    YieldUncertainty,
    exceedance_levels,
    monte_carlo_financial_analysis,
)

# Roughly the real plant: 429 kWp, ~792 MWh in year 1.
CAPACITY_KWP = 429.0
YEAR_1_KWH = 792_000.0


def base_assumptions(**kwargs) -> FinancialAssumptions:
    defaults = dict(capex_thb=30_000.0 * CAPACITY_KWP, tariff_thb_per_kwh=4.0, discount_rate_pct=8.0)
    defaults.update(kwargs)
    return FinancialAssumptions(**defaults)


class TestExceedanceLevels:
    def test_P90_is_BELOW_P50_because_it_is_a_probability_of_exceedance(self):
        # The single most invertible thing in this module. P90 = "exceeded in
        # 90% of years" = the pessimistic case, NOT the 90th percentile.
        levels = {level.label: level.annual_energy_kwh for level in exceedance_levels(YEAR_1_KWH)}
        assert levels["P90"] < levels["P50"]

    def test_P50_is_the_input_estimate_itself(self):
        levels = {level.label: level.annual_energy_kwh for level in exceedance_levels(YEAR_1_KWH)}
        assert levels["P50"] == pytest.approx(YEAR_1_KWH)

    def test_the_P90_gap_matches_the_normal_quantile_for_the_configured_CV(self):
        # z(0.10) = -1.2816, so P90 = mean - 1.2816 * sigma.
        levels = {level.label: level.annual_energy_kwh for level in exceedance_levels(YEAR_1_KWH)}
        sigma = YEAR_1_KWH * DEFAULT_ANNUAL_YIELD_CV_PCT / 100
        assert levels["P90"] == pytest.approx(YEAR_1_KWH - 1.2816 * sigma, rel=1e-3)

    def test_a_wider_CV_pushes_P90_further_down(self):
        narrow = exceedance_levels(YEAR_1_KWH, YieldUncertainty(annual_cv_pct=2.0))
        wide = exceedance_levels(YEAR_1_KWH, YieldUncertainty(annual_cv_pct=8.0))
        assert wide[1].annual_energy_kwh < narrow[1].annual_energy_kwh

    def test_zero_variability_collapses_every_level_onto_P50(self):
        # With no knowledge of year-to-year spread there is no spread to show -
        # the honest answer is "same number", not an invented band.
        levels = exceedance_levels(YEAR_1_KWH, YieldUncertainty(annual_cv_pct=0.0))
        assert all(level.annual_energy_kwh == pytest.approx(YEAR_1_KWH) for level in levels)

    def test_extra_exceedance_levels_come_back_ordered_as_asked(self):
        levels = exceedance_levels(YEAR_1_KWH, exceedances=(0.5, 0.75, 0.9, 0.99))
        assert [level.label for level in levels] == ["P50", "P75", "P90", "P99"]
        energies = [level.annual_energy_kwh for level in levels]
        assert energies == sorted(energies, reverse=True)  # higher exceedance = lower yield

    def test_yield_never_goes_negative_even_at_an_absurd_CV(self):
        levels = exceedance_levels(1000.0, YieldUncertainty(annual_cv_pct=500.0), exceedances=(0.99,))
        assert levels[0].annual_energy_kwh >= 0

    def test_rejects_nonsense_inputs(self):
        with pytest.raises(ValueError):
            exceedance_levels(-1.0)
        with pytest.raises(ValueError):
            exceedance_levels(YEAR_1_KWH, exceedances=(0.0,))
        with pytest.raises(ValueError):
            exceedance_levels(YEAR_1_KWH, exceedances=(1.0,))
        with pytest.raises(ValueError):
            YieldUncertainty(annual_cv_pct=-1.0)

    def test_exceedance_yield_is_immutable(self):
        level = ExceedanceYield(exceedance=0.9, label="P90", annual_energy_kwh=1.0)
        with pytest.raises(Exception):
            level.annual_energy_kwh = 2.0  # type: ignore[misc]


class TestFinancialDistribution:
    def test_a_fully_exact_distribution_reports_no_uncertainty(self):
        assert FinancialDistribution().any_uncertainty() is False

    def test_any_single_spread_counts_as_uncertainty(self):
        assert FinancialDistribution(discount_rate_std_pct=1.0).any_uncertainty() is True
        assert FinancialDistribution(annual_yield_cv_pct=4.0).any_uncertainty() is True

    def test_negative_spread_is_rejected(self):
        with pytest.raises(ValueError):
            FinancialDistribution(capex_per_kwp_std_thb=-1.0)


class TestMonteCarlo:
    def test_zero_spread_reproduces_the_deterministic_result_exactly(self):
        # If this drifts, the page shows a distribution that disagrees with the
        # single NPV printed beside it.
        base = base_assumptions()
        deterministic = compute_financial_analysis(YEAR_1_KWH, CAPACITY_KWP, base)
        mc = monte_carlo_financial_analysis(YEAR_1_KWH, CAPACITY_KWP, base, FinancialDistribution(), n_samples=10)
        npv = mc.metrics["npv_thb"]
        assert npv.p50 == pytest.approx(deterministic.npv_thb)
        assert npv.p10 == pytest.approx(deterministic.npv_thb)
        assert npv.p90 == pytest.approx(deterministic.npv_thb)

    def test_the_centre_comes_from_base_not_from_the_distribution(self):
        # The design point of the std-only distribution: changing only the base
        # CAPEX must move the whole NPV distribution.
        dist = FinancialDistribution(capex_per_kwp_std_thb=2_000.0)
        cheap = monte_carlo_financial_analysis(
            YEAR_1_KWH, CAPACITY_KWP, base_assumptions(capex_thb=20_000.0 * CAPACITY_KWP), dist, n_samples=200
        )
        dear = monte_carlo_financial_analysis(
            YEAR_1_KWH, CAPACITY_KWP, base_assumptions(capex_thb=45_000.0 * CAPACITY_KWP), dist, n_samples=200
        )
        assert cheap.metrics["npv_thb"].p50 > dear.metrics["npv_thb"].p50

    def test_widening_capex_uncertainty_widens_the_NPV_band(self):
        base = base_assumptions()
        narrow = monte_carlo_financial_analysis(
            YEAR_1_KWH, CAPACITY_KWP, base, FinancialDistribution(capex_per_kwp_std_thb=500.0), n_samples=400
        )
        wide = monte_carlo_financial_analysis(
            YEAR_1_KWH, CAPACITY_KWP, base, FinancialDistribution(capex_per_kwp_std_thb=8_000.0), n_samples=400
        )
        narrow_band = narrow.metrics["npv_thb"].p90 - narrow.metrics["npv_thb"].p10
        wide_band = wide.metrics["npv_thb"].p90 - wide.metrics["npv_thb"].p10
        assert wide_band > narrow_band

    def test_the_same_seed_reproduces_the_same_answer(self):
        base, dist = base_assumptions(), FinancialDistribution(capex_per_kwp_std_thb=5_000.0)
        a = monte_carlo_financial_analysis(YEAR_1_KWH, CAPACITY_KWP, base, dist, n_samples=100, seed=7)
        b = monte_carlo_financial_analysis(YEAR_1_KWH, CAPACITY_KWP, base, dist, n_samples=100, seed=7)
        assert a.metrics["npv_thb"].p50 == b.metrics["npv_thb"].p50

    def test_a_different_seed_gives_a_different_draw(self):
        base, dist = base_assumptions(), FinancialDistribution(capex_per_kwp_std_thb=5_000.0)
        a = monte_carlo_financial_analysis(YEAR_1_KWH, CAPACITY_KWP, base, dist, n_samples=100, seed=1)
        b = monte_carlo_financial_analysis(YEAR_1_KWH, CAPACITY_KWP, base, dist, n_samples=100, seed=2)
        assert a.metrics["npv_thb"].p50 != b.metrics["npv_thb"].p50

    def test_reports_the_share_of_trials_that_lose_money(self):
        # A CAPEX so high that most trials cannot pay back is the case this
        # number exists for.
        result = monte_carlo_financial_analysis(
            YEAR_1_KWH,
            CAPACITY_KWP,
            base_assumptions(capex_thb=300_000.0 * CAPACITY_KWP),
            FinancialDistribution(capex_per_kwp_std_thb=10_000.0),
            n_samples=200,
        )
        assert result.probability_npv_negative_pct > 50.0

    def test_a_healthy_project_reports_a_low_loss_probability(self):
        result = monte_carlo_financial_analysis(
            YEAR_1_KWH,
            CAPACITY_KWP,
            base_assumptions(capex_thb=10_000.0 * CAPACITY_KWP),
            FinancialDistribution(capex_per_kwp_std_thb=1_000.0),
            n_samples=200,
        )
        assert result.probability_npv_negative_pct == 0.0

    def test_undefined_payback_trials_are_counted_not_silently_dropped(self):
        # "12% of trials never pay back" is the most decision-relevant output
        # this module has; averaging over only the trials that DID pay back
        # would hide it entirely.
        result = monte_carlo_financial_analysis(
            YEAR_1_KWH,
            CAPACITY_KWP,
            base_assumptions(capex_thb=500_000.0 * CAPACITY_KWP),
            FinancialDistribution(capex_per_kwp_std_thb=1_000.0),
            n_samples=100,
        )
        assert result.probability_no_payback_pct > 0
        assert result.metrics["simple_payback_years"].undefined_trials > 0

    def test_an_all_undefined_metric_reports_none_rather_than_zero(self):
        # "never paid back in any trial" and "paid back immediately" must not
        # look the same.
        result = monte_carlo_financial_analysis(
            YEAR_1_KWH,
            CAPACITY_KWP,
            base_assumptions(capex_thb=1e12),
            FinancialDistribution(capex_per_kwp_std_thb=1.0),
            n_samples=20,
        )
        payback = result.metrics["simple_payback_years"]
        assert payback.p50 is None and payback.mean is None
        assert result.probability_no_payback_pct == 100.0

    def test_yield_uncertainty_alone_still_moves_the_NPV(self):
        # Yield is drawn inside the same trial as the money draws, so it must
        # produce a spread on its own.
        base = base_assumptions()
        result = monte_carlo_financial_analysis(
            YEAR_1_KWH, CAPACITY_KWP, base, FinancialDistribution(annual_yield_cv_pct=6.0), n_samples=300
        )
        assert result.metrics["npv_thb"].p90 > result.metrics["npv_thb"].p10

    def test_every_headline_metric_is_reported(self):
        result = monte_carlo_financial_analysis(
            YEAR_1_KWH, CAPACITY_KWP, base_assumptions(), FinancialDistribution(discount_rate_std_pct=1.0), n_samples=50
        )
        assert set(result.metrics) == {"npv_thb", "irr_pct", "lcoe_thb_per_kwh", "simple_payback_years"}
        assert result.samples == 50

    def test_rejects_nonsense_inputs(self):
        base, dist = base_assumptions(), FinancialDistribution()
        with pytest.raises(ValueError):
            monte_carlo_financial_analysis(YEAR_1_KWH, CAPACITY_KWP, base, dist, n_samples=1)
        with pytest.raises(ValueError):
            monte_carlo_financial_analysis(YEAR_1_KWH, 0.0, base, dist)
        with pytest.raises(ValueError):
            monte_carlo_financial_analysis(-1.0, CAPACITY_KWP, base, dist)
