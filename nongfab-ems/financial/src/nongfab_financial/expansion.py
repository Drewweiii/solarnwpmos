"""Expansion scenarios: what each planned phase actually buys (2026-07-25).

Nong Fab's array is 400 kW AC against a terminal that draws 13.5 MW, so today's
solar covers ~0.4% of the site's own electricity. config/assets.yaml already
records the real planned phases (Jetty phase 1.5 = +100 kW AC, phase 2 = +300 kW,
"target total 600kW AC"), and the question they raise - how much of the bill does
each phase actually move, and what does the LAST kilowatt buy compared with the
first - had no answer anywhere on the site.

This module answers it as cumulative scenarios with a marginal column, because
that is the number an investment decision turns on: a phase's total looks
impressive next to nothing, while its yield PER ADDED kWp is what says whether it
is as good a deal as what came before.

Method and its limits, stated rather than buried:
- Added energy is scaled from the CURRENT array's own seasonal annual estimate by
  the capacity ratio. Valid because a phase extends the same site at the same
  latitude with the same tilt/module/inverter family - not a fresh simulation of
  the new sub-array's own geometry, which would need a layout that doesn't exist
  yet for phase 2. Documented as a proportional estimate.
- Bill saving uses the tariff the caller passes in. The API passes the facility's
  own implied rate (its real annual cost / real annual load), NOT the financial
  module's placeholder PEA tariff.
- CAPEX is `DEFAULT_CAPEX_PER_KWP_THB`, still a documented PLACEHOLDER (see
  model.py's own table). So `simple_payback_years` inherits that and every
  surface must label it. Everything else here is derived from real figures.

Pure: no store, no HTTP, no assets loading. The caller supplies today's numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import DEFAULT_CAPEX_PER_KWP_THB

HOURS_PER_YEAR = 8760


@dataclass(frozen=True)
class ExpansionPhase:
    """One planned phase, straight from config/assets.yaml's future_phases."""

    phase: str
    additional_ac_capacity_kw: float
    note: str | None = None


@dataclass(frozen=True)
class ExpansionScenario:
    """The cumulative state of the plant after a phase completes.

    `marginal_*` fields compare this scenario with the previous one - what the
    phase itself added, as opposed to the running total. They are None for the
    baseline (there is no previous scenario to compare against).
    """

    label: str
    phase: str | None
    ac_capacity_kw: float
    dc_capacity_kwp: float
    annual_energy_kwh: float
    # Share of the facility's own annual electricity demand this covers.
    solar_offset_pct: float | None
    annual_bill_saving_thb: float | None
    # This phase's own contribution.
    marginal_ac_capacity_kw: float | None
    marginal_annual_energy_kwh: float | None
    marginal_bill_saving_thb: float | None
    # Energy per added kWp - the "is this phase still worth it" number. Constant
    # under proportional scaling by design; it is reported so the assumption is
    # visible rather than implied.
    marginal_energy_per_kwp: float | None
    # Placeholder-driven (CAPEX). Labelled as such everywhere it surfaces.
    capex_estimate_thb: float | None
    simple_payback_years: float | None


def facility_annual_load_kwh(facility_load_kw: float) -> float:
    """Flat load x hours. The load figure is the user's real 13.5 MW; only its
    flat shape is an approximation (no hourly load profile exists)."""
    return facility_load_kw * HOURS_PER_YEAR


def build_scenarios(
    current_ac_capacity_kw: float,
    current_dc_capacity_kwp: float,
    current_annual_energy_kwh: float,
    phases: list[ExpansionPhase],
    facility_load_kw: float | None = None,
    tariff_thb_per_kwh: float | None = None,
    capex_per_kwp_thb: float = DEFAULT_CAPEX_PER_KWP_THB,
) -> list[ExpansionScenario]:
    """Today's plant plus one cumulative scenario per phase, in order.

    Returns an empty list for a non-positive current capacity (nothing to scale
    from), rather than dividing by zero. `solar_offset_pct` /
    `annual_bill_saving_thb` are None where the facility load / tariff aren't
    known - never guessed.
    """
    if current_ac_capacity_kw <= 0 or current_dc_capacity_kwp <= 0:
        return []

    dc_per_ac = current_dc_capacity_kwp / current_ac_capacity_kw
    energy_per_kwp = current_annual_energy_kwh / current_dc_capacity_kwp
    annual_load_kwh = facility_annual_load_kwh(facility_load_kw) if facility_load_kw and facility_load_kw > 0 else None

    def offset(energy_kwh: float) -> float | None:
        return None if annual_load_kwh is None else energy_kwh / annual_load_kwh * 100

    def saving(energy_kwh: float) -> float | None:
        return None if not tariff_thb_per_kwh or tariff_thb_per_kwh <= 0 else energy_kwh * tariff_thb_per_kwh

    scenarios = [
        ExpansionScenario(
            label="ปัจจุบัน",
            phase=None,
            ac_capacity_kw=current_ac_capacity_kw,
            dc_capacity_kwp=current_dc_capacity_kwp,
            annual_energy_kwh=current_annual_energy_kwh,
            solar_offset_pct=offset(current_annual_energy_kwh),
            annual_bill_saving_thb=saving(current_annual_energy_kwh),
            marginal_ac_capacity_kw=None,
            marginal_annual_energy_kwh=None,
            marginal_bill_saving_thb=None,
            marginal_energy_per_kwp=None,
            capex_estimate_thb=None,
            simple_payback_years=None,
        )
    ]

    ac = current_ac_capacity_kw
    for phase in phases:
        if phase.additional_ac_capacity_kw <= 0:
            continue
        previous = scenarios[-1]
        ac += phase.additional_ac_capacity_kw
        dc = ac * dc_per_ac
        energy = dc * energy_per_kwp
        added_dc = dc - previous.dc_capacity_kwp
        added_energy = energy - previous.annual_energy_kwh
        added_saving = saving(added_energy)
        capex = added_dc * capex_per_kwp_thb
        payback = capex / added_saving if added_saving and added_saving > 0 else None
        scenarios.append(
            ExpansionScenario(
                label=f"เฟส {phase.phase}",
                phase=phase.phase,
                ac_capacity_kw=ac,
                dc_capacity_kwp=dc,
                annual_energy_kwh=energy,
                solar_offset_pct=offset(energy),
                annual_bill_saving_thb=saving(energy),
                marginal_ac_capacity_kw=phase.additional_ac_capacity_kw,
                marginal_annual_energy_kwh=added_energy,
                marginal_bill_saving_thb=added_saving,
                marginal_energy_per_kwp=added_energy / added_dc if added_dc > 0 else None,
                capex_estimate_thb=capex,
                simple_payback_years=payback,
            )
        )
    return scenarios


def capacity_for_target_offset(
    target_offset_pct: float,
    current_annual_energy_kwh: float,
    current_dc_capacity_kwp: float,
    facility_load_kw: float,
) -> float | None:
    """DC capacity (kWp) that would cover `target_offset_pct` of the facility's
    annual demand - the "what would it actually take" figure, which for a 13.5 MW
    site is worth seeing next to a 600 kW plan. None when the inputs can't support
    the arithmetic."""
    if current_dc_capacity_kwp <= 0 or current_annual_energy_kwh <= 0 or facility_load_kw <= 0 or target_offset_pct <= 0:
        return None
    energy_per_kwp = current_annual_energy_kwh / current_dc_capacity_kwp
    target_energy = facility_annual_load_kwh(facility_load_kw) * target_offset_pct / 100
    return target_energy / energy_per_kwp
