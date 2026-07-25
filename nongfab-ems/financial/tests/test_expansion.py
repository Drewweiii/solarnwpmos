"""Covers the expansion-scenario math (2026-07-25)."""

from __future__ import annotations

import pytest

from nongfab_financial.expansion import (
    HOURS_PER_YEAR,
    ExpansionPhase,
    build_scenarios,
    capacity_for_target_offset,
    facility_annual_load_kwh,
)

# Today's plant, roughly the real figures: 400 kW AC / 429 kWp DC.
CURRENT_AC = 400.0
CURRENT_DC = 429.0
CURRENT_ENERGY = 600_000.0
# The real user-stated facility load.
LOAD_KW = 13_500.0
TARIFF = 2.54  # ~300 MTHB / (13.5 MW x 8760 h)

PHASES = [ExpansionPhase(phase="1.5", additional_ac_capacity_kw=100.0), ExpansionPhase(phase="2", additional_ac_capacity_kw=300.0)]


def test_baseline_scenario_reports_today_with_no_marginal_columns():
    scenarios = build_scenarios(CURRENT_AC, CURRENT_DC, CURRENT_ENERGY, [])
    assert len(scenarios) == 1
    now = scenarios[0]
    assert now.ac_capacity_kw == CURRENT_AC
    assert now.annual_energy_kwh == CURRENT_ENERGY
    # Nothing to compare against, so no marginal figures and no CAPEX.
    assert now.marginal_ac_capacity_kw is None
    assert now.capex_estimate_thb is None
    assert now.simple_payback_years is None


def test_phases_accumulate_capacity_and_energy_proportionally():
    scenarios = build_scenarios(CURRENT_AC, CURRENT_DC, CURRENT_ENERGY, PHASES)
    assert [s.phase for s in scenarios] == [None, "1.5", "2"]
    assert scenarios[1].ac_capacity_kw == pytest.approx(500.0)
    assert scenarios[2].ac_capacity_kw == pytest.approx(800.0)
    # Energy scales with capacity, so 2x the plant is 2x the energy.
    assert scenarios[2].annual_energy_kwh == pytest.approx(CURRENT_ENERGY * 800 / 400)
    # And the DC/AC ratio is preserved from today's array.
    assert scenarios[2].dc_capacity_kwp / scenarios[2].ac_capacity_kw == pytest.approx(CURRENT_DC / CURRENT_AC)


def test_marginal_columns_describe_the_phase_not_the_running_total():
    scenarios = build_scenarios(CURRENT_AC, CURRENT_DC, CURRENT_ENERGY, PHASES)
    phase2 = scenarios[2]
    assert phase2.marginal_ac_capacity_kw == 300.0
    assert phase2.marginal_annual_energy_kwh == pytest.approx(phase2.annual_energy_kwh - scenarios[1].annual_energy_kwh)
    # Under proportional scaling every phase yields the same energy per kWp -
    # reported so that assumption is visible rather than implied.
    assert phase2.marginal_energy_per_kwp == pytest.approx(scenarios[1].marginal_energy_per_kwp)


def test_offset_and_saving_stay_none_without_the_inputs():
    bare = build_scenarios(CURRENT_AC, CURRENT_DC, CURRENT_ENERGY, PHASES)
    assert all(s.solar_offset_pct is None for s in bare)
    assert all(s.annual_bill_saving_thb is None for s in bare)
    # A load but no tariff -> offset only, never a guessed baht figure.
    load_only = build_scenarios(CURRENT_AC, CURRENT_DC, CURRENT_ENERGY, PHASES, facility_load_kw=LOAD_KW)
    assert load_only[0].solar_offset_pct is not None
    assert load_only[0].annual_bill_saving_thb is None


def test_offset_is_a_percentage_of_the_facilitys_own_annual_demand():
    scenarios = build_scenarios(CURRENT_AC, CURRENT_DC, CURRENT_ENERGY, PHASES, facility_load_kw=LOAD_KW, tariff_thb_per_kwh=TARIFF)
    expected = CURRENT_ENERGY / (LOAD_KW * HOURS_PER_YEAR) * 100
    assert scenarios[0].solar_offset_pct == pytest.approx(expected)
    # Even at the 800 kW end state the offset is only ~1% of the terminal's own
    # demand - which is exactly why this panel reports it.
    assert scenarios[2].solar_offset_pct < 2.0
    # Saving tracks the tariff exactly.
    assert scenarios[0].annual_bill_saving_thb == pytest.approx(CURRENT_ENERGY * TARIFF)


def test_payback_uses_the_phases_own_capex_and_saving():
    scenarios = build_scenarios(
        CURRENT_AC, CURRENT_DC, CURRENT_ENERGY, PHASES, facility_load_kw=LOAD_KW, tariff_thb_per_kwh=TARIFF, capex_per_kwp_thb=30_000.0
    )
    phase15 = scenarios[1]
    added_dc = phase15.dc_capacity_kwp - scenarios[0].dc_capacity_kwp
    assert phase15.capex_estimate_thb == pytest.approx(added_dc * 30_000.0)
    assert phase15.simple_payback_years == pytest.approx(phase15.capex_estimate_thb / phase15.marginal_bill_saving_thb)


def test_payback_is_none_when_there_is_no_tariff_to_pay_it_back_with():
    scenarios = build_scenarios(CURRENT_AC, CURRENT_DC, CURRENT_ENERGY, PHASES, facility_load_kw=LOAD_KW)
    assert scenarios[1].capex_estimate_thb is not None  # CAPEX doesn't need a tariff
    assert scenarios[1].simple_payback_years is None


def test_a_zero_capacity_plant_yields_nothing_rather_than_dividing_by_zero():
    assert build_scenarios(0.0, 0.0, 0.0, PHASES) == []
    assert build_scenarios(400.0, 0.0, 600_000.0, PHASES) == []


def test_a_nonpositive_phase_is_skipped():
    scenarios = build_scenarios(CURRENT_AC, CURRENT_DC, CURRENT_ENERGY, [ExpansionPhase(phase="x", additional_ac_capacity_kw=0.0)])
    assert len(scenarios) == 1


def test_facility_annual_load_is_flat_load_times_hours():
    assert facility_annual_load_kwh(LOAD_KW) == LOAD_KW * HOURS_PER_YEAR


def test_capacity_for_a_target_offset_scales_from_todays_yield():
    # 10% of the facility's demand needs 10% of its annual load in energy.
    needed = capacity_for_target_offset(10.0, CURRENT_ENERGY, CURRENT_DC, LOAD_KW)
    energy_per_kwp = CURRENT_ENERGY / CURRENT_DC
    assert needed == pytest.approx(LOAD_KW * HOURS_PER_YEAR * 0.10 / energy_per_kwp)
    # ~8.5 MWp: an order of magnitude beyond the 800 kW end state of the planned
    # phases, which is exactly the point of reporting it.
    assert needed > 5_000


def test_capacity_for_target_offset_refuses_impossible_inputs():
    assert capacity_for_target_offset(0.0, CURRENT_ENERGY, CURRENT_DC, LOAD_KW) is None
    assert capacity_for_target_offset(10.0, 0.0, CURRENT_DC, LOAD_KW) is None
    assert capacity_for_target_offset(10.0, CURRENT_ENERGY, 0.0, LOAD_KW) is None
    assert capacity_for_target_offset(10.0, CURRENT_ENERGY, CURRENT_DC, 0.0) is None
