"""Module 11: Financial/Investment Analysis - NPV, IRR, LCOE, and simple vs.
discounted payback for the Nong Fab solar installation over its 25-year
design life.

Added 2026-07-16 after the user pointed out that this site's sub-daily/
hour-ahead/day-ahead forecasting (Module 4) has little *operational* value
here: the plant is fully grid-tied with no battery, solar is not the
primary generation source, and capacity is capped by available land - so no
dispatch decision changes based on a forecast. What actually matters for
this asset is the same thing that matters for any capital project: does it
pay back, and how does it compare against the cost of capital. This module
answers that.

It reuses `nongfab_simulation.what_if.apply_scenario`'s own validated
degradation model (the same one `pipeline.lifecycle_ac_energy_estimate()`
uses) to degrade a starting annual-energy estimate year over year - no real
production telemetry required, unlike forecast-accuracy work, because
financial modeling works off a yield *estimate*, not minute-by-minute
ground truth.

**Every rate/cost assumption in `FinancialAssumptions` below is a
documented placeholder, not a confirmed figure for this project**, except
`tax_rate_pct` (Thailand's actual standard corporate income tax rate,
20% - a public fact, not a guess). The user still needs to supply: real
CAPEX, the actual PEA industrial tariff/contract structure, BOI promotion
status (if any) and its tax-holiday length, and the company's real WACC.
Tax/BOI treatment here is a simplified flat-rate model for a rough
estimate, not tax advice - confirm with the user's finance/tax team before
using this for a real investment decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nongfab_simulation.pipeline import DEFAULT_DEGRADATION_PCT_PER_YEAR, LIFETIME_YEARS

# Trina's warranty for the installed TSM-NEG21C.20 is a 1% step in year 1 and
# 0.40%/year after it - the larger first-year drop is light-induced degradation,
# a real one-off, not a rounding of the annual rate. Modelled separately so the
# published cash flow reproduces the warranty exactly:
#   factor(y) = 1 - first/100 - (annual/100) x (y - 1)
# which at y=30 gives 1 - 0.01 - 0.004 x 29 = 0.874, the warranted 87.4%.
DEFAULT_DEGRADATION_FIRST_YEAR_PCT = 1.0

# Thai utility-scale/C&I solar EPC cost ballpark (documented approximation,
# not a quote for this project) - used only when the caller doesn't supply a
# real CAPEX figure.
DEFAULT_CAPEX_PER_KWP_THB = 30_000.0
# Typical O&M cost as a percent of CAPEX per year (documented industry
# rule of thumb, not a site-specific contract figure).
DEFAULT_OPEX_PCT_OF_CAPEX_PER_YEAR = 1.2
# The real published rate this site pays: Type-4 (large industrial) TOU, Peak
# energy, HV (>= 69 kV) - the voltage level and tariff structure the user
# confirmed on 2026-07-19. Kept identical to green_savings.NORMAL_RATE_THB_PER_KWH
# by a test: the Savings page and the Financial page must not value the same kWh
# differently. Replaced a round 4.0 that had no source behind it.
#
# Documented approximation: solar output is valued at the Peak rate all year,
# without netting out weekend/holiday off-peak hours. Refining that needs a real
# half-hourly consumption profile, which does not exist yet.
DEFAULT_TARIFF_THB_PER_KWH = 4.1025
DEFAULT_TARIFF_ESCALATION_PCT_PER_YEAR = 3.0
DEFAULT_OPEX_ESCALATION_PCT_PER_YEAR = 3.0
# WACC placeholder - confirm against the company's real cost of capital.
DEFAULT_DISCOUNT_RATE_PCT = 8.0
# Thailand's actual standard corporate income tax rate - not a placeholder.
THAILAND_STANDARD_CORPORATE_TAX_RATE_PCT = 20.0
# CONFIRMED by the user 2026-07-25: this project holds BOI promotion - 8 years
# of corporate income tax exemption in the general areas (GIS, ISB) and 12 years
# for the Jetty. 8 is the default because the two zones actually built today are
# both general-area; a Jetty analysis must pass 12 explicitly (the API exposes
# `financial.boi_tax_holiday_years_jetty` for that, and /financial's own slider
# reaches 12). Was 0 until then - see git history for the pre-confirmation
# eligibility/holiday length - overstating a tax holiday would overstate
# returns.
DEFAULT_BOI_TAX_HOLIDAY_YEARS = 8


@dataclass(frozen=True)
class FinancialAssumptions:
    capex_thb: float | None = None  # None -> DEFAULT_CAPEX_PER_KWP_THB x installed DC kWp
    opex_pct_of_capex_per_year: float = DEFAULT_OPEX_PCT_OF_CAPEX_PER_YEAR
    tariff_thb_per_kwh: float = DEFAULT_TARIFF_THB_PER_KWH
    tariff_escalation_pct_per_year: float = DEFAULT_TARIFF_ESCALATION_PCT_PER_YEAR
    opex_escalation_pct_per_year: float = DEFAULT_OPEX_ESCALATION_PCT_PER_YEAR
    discount_rate_pct: float = DEFAULT_DISCOUNT_RATE_PCT  # WACC
    tax_rate_pct: float = THAILAND_STANDARD_CORPORATE_TAX_RATE_PCT
    boi_tax_holiday_years: int = DEFAULT_BOI_TAX_HOLIDAY_YEARS
    degradation_pct_per_year: float = DEFAULT_DEGRADATION_PCT_PER_YEAR
    degradation_first_year_pct: float = DEFAULT_DEGRADATION_FIRST_YEAR_PCT
    lifetime_years: int = LIFETIME_YEARS

    def __post_init__(self) -> None:
        if self.capex_thb is not None and self.capex_thb <= 0:
            raise ValueError(f"capex_thb must be positive if given, got {self.capex_thb}")
        if self.opex_pct_of_capex_per_year < 0:
            raise ValueError(f"opex_pct_of_capex_per_year cannot be negative, got {self.opex_pct_of_capex_per_year}")
        if self.tariff_thb_per_kwh < 0:
            raise ValueError(f"tariff_thb_per_kwh cannot be negative, got {self.tariff_thb_per_kwh}")
        if self.discount_rate_pct <= -100:
            raise ValueError(f"discount_rate_pct must be > -100, got {self.discount_rate_pct}")
        if not (0 <= self.tax_rate_pct <= 100):
            raise ValueError(f"tax_rate_pct must be within [0, 100], got {self.tax_rate_pct}")
        if self.boi_tax_holiday_years < 0:
            raise ValueError(f"boi_tax_holiday_years cannot be negative, got {self.boi_tax_holiday_years}")
        if self.lifetime_years < 1:
            raise ValueError(f"lifetime_years must be at least 1, got {self.lifetime_years}")


@dataclass(frozen=True)
class CashFlowYear:
    year: int  # 1-indexed
    ac_energy_kwh: float
    avoided_cost_thb: float
    opex_thb: float
    taxable_income_thb: float
    tax_thb: float
    net_cash_flow_thb: float
    discount_factor: float
    discounted_cash_flow_thb: float
    cumulative_undiscounted_cash_flow_thb: float
    cumulative_discounted_cash_flow_thb: float


@dataclass(frozen=True)
class FinancialResult:
    capex_thb: float
    npv_thb: float
    irr_pct: float | None  # None if no real root exists (project never breaks even, or always profitable at every rate tried)
    lcoe_thb_per_kwh: float
    simple_payback_years: float | None  # None if it never pays back within lifetime_years
    discounted_payback_years: float | None
    cash_flows: list[CashFlowYear] = field(default_factory=list)
    assumptions: FinancialAssumptions = field(default_factory=FinancialAssumptions)


def _npv_at_rate(cash_flows: list[float], rate: float) -> float:
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))


def _irr(cash_flows: list[float], low: float = -0.5, high: float = 10.0, tol: float = 1e-6, max_iter: int = 200) -> float | None:
    """Bisection solve for the rate where NPV(cash_flows, rate) == 0.
    `cash_flows[0]` is the (negative) initial CAPEX outflow at t=0. Returns
    None if no sign change is found across [low, high] - e.g. the project
    never turns a profit (cumulative cash flow stays negative at every
    rate in this range), so no economically meaningful IRR exists.
    `low` deliberately stops well short of -100%: as rate -> -100%, the
    discount factor 1/(1+rate)^t blows up toward infinity, which can make
    NPV cross zero at some absurd rate like -95% purely from that
    singularity - a real answer mathematically, but not one any dashboard
    should show as "the IRR". -50% is already far enough to flag "clearly
    unprofitable" for a solar project's return range. Dependency-free on
    purpose (no numpy_financial) - this project's other numeric code
    doesn't pull in extra packages for a single formula either.
    """
    f_low = _npv_at_rate(cash_flows, low)
    f_high = _npv_at_rate(cash_flows, high)
    if f_low == 0:
        return low * 100
    if f_high == 0:
        return high * 100
    if (f_low > 0) == (f_high > 0):
        return None
    mid = low
    for _ in range(max_iter):
        mid = (low + high) / 2
        f_mid = _npv_at_rate(cash_flows, mid)
        if abs(f_mid) < tol:
            return mid * 100
        if (f_mid > 0) == (f_low > 0):
            low, f_low = mid, f_mid
        else:
            high = mid
    return mid * 100


def _find_payback_year(cumulative_after_capex: list[float], capex: float) -> float | None:
    """`cumulative_after_capex[i]` is the cumulative net cash flow through
    year i+1, already netted against the initial -capex outflow. Linearly
    interpolates within the crossing year for a fractional-year result
    (e.g. 6.3 years) rather than just the first whole year it turns
    non-negative. Returns None if it never crosses zero within the series.
    """
    prev = -capex
    for i, cum in enumerate(cumulative_after_capex):
        if cum >= 0:
            year_end = i + 1
            if cum == prev:
                return float(year_end)
            frac = -prev / (cum - prev)
            return (year_end - 1) + frac
        prev = cum
    return None


def degradation_factor(degradation_pct_per_year: float, years_since_commissioning: float) -> float:
    """The surviving fraction of year-1 output after `years_since_commissioning`.

    Exactly `nongfab_simulation.what_if.apply_scenario`'s degradation term -
    LINEAR, not compounding, and floored at zero - reproduced as scalar
    arithmetic so a Monte Carlo does not pay for a pandas Series per year.

    Validation is repeated here rather than delegated: `ScenarioParams` is a
    plain dataclass that accepts anything, and it is `apply_scenario` that
    rejects a negative rate. Skipping this call therefore also skips the
    guard, so the same two checks are made explicitly, with the same wording.
    """
    if degradation_pct_per_year < 0:
        raise ValueError(
            f"degradation_pct_per_year cannot be negative (degradation only ever reduces performance), "
            f"got {degradation_pct_per_year}"
        )
    if years_since_commissioning < 0:
        raise ValueError("years_since_commissioning cannot be negative")
    return max(0.0, 1 - (degradation_pct_per_year / 100) * years_since_commissioning)


def compute_financial_analysis(
    year_1_ac_energy_kwh: float,
    installed_dc_capacity_kwp: float,
    assumptions: FinancialAssumptions | None = None,
) -> FinancialResult:
    """Builds the full year-by-year cash flow table and derives NPV/IRR/
    LCOE/payback from it. `year_1_ac_energy_kwh` should be a first-year
    physics-based annual yield estimate (e.g. summing
    `nongfab_simulation.pipeline.estimate_annual_ac_energy_kwh()` across the
    real installed zones) - the caller owns that composition, this function
    only degrades it year over year and turns it into money.
    """
    if year_1_ac_energy_kwh < 0:
        raise ValueError(f"year_1_ac_energy_kwh cannot be negative, got {year_1_ac_energy_kwh}")
    if installed_dc_capacity_kwp <= 0:
        raise ValueError(f"installed_dc_capacity_kwp must be positive, got {installed_dc_capacity_kwp}")

    assumptions = assumptions or FinancialAssumptions()
    capex = assumptions.capex_thb if assumptions.capex_thb is not None else DEFAULT_CAPEX_PER_KWP_THB * installed_dc_capacity_kwp
    discount_rate = assumptions.discount_rate_pct / 100
    # Validate the degradation rate through what_if's own rules, then apply it
    # arithmetically below. Degradation there is LINEAR (1 - rate*years, floored
    # at 0), so the scalar form is exact - and building a one-element Series per
    # year cost ~25 s per 2,000-trial Monte Carlo, which is the whole reason
    # `uncertainty.monte_carlo_financial_analysis` can run inside a request at
    # all. `test_model.py` pins the two against each other.

    cash_flows: list[CashFlowYear] = []
    cumulative_undiscounted = -capex
    cumulative_discounted = -capex
    undiscounted_series_for_irr = [-capex]

    for y in range(1, assumptions.lifetime_years + 1):
        # First-year LID applies from year 1 onward, the annual rate on top of
        # it - together they reproduce Trina's warranty curve for this module.
        surviving = degradation_factor(assumptions.degradation_pct_per_year, y - 1) - (
            assumptions.degradation_first_year_pct / 100
        )
        energy_kwh = year_1_ac_energy_kwh * max(0.0, surviving)
        tariff = assumptions.tariff_thb_per_kwh * (1 + assumptions.tariff_escalation_pct_per_year / 100) ** (y - 1)
        avoided_cost = energy_kwh * tariff
        opex = capex * (assumptions.opex_pct_of_capex_per_year / 100) * (1 + assumptions.opex_escalation_pct_per_year / 100) ** (
            y - 1
        )
        taxable_income = max(0.0, avoided_cost - opex)
        tax = 0.0 if y <= assumptions.boi_tax_holiday_years else taxable_income * (assumptions.tax_rate_pct / 100)
        net_cash_flow = avoided_cost - opex - tax
        discount_factor = 1 / (1 + discount_rate) ** y
        discounted_cf = net_cash_flow * discount_factor

        cumulative_undiscounted += net_cash_flow
        cumulative_discounted += discounted_cf
        undiscounted_series_for_irr.append(net_cash_flow)

        cash_flows.append(
            CashFlowYear(
                year=y,
                ac_energy_kwh=energy_kwh,
                avoided_cost_thb=avoided_cost,
                opex_thb=opex,
                taxable_income_thb=taxable_income,
                tax_thb=tax,
                net_cash_flow_thb=net_cash_flow,
                discount_factor=discount_factor,
                discounted_cash_flow_thb=discounted_cf,
                cumulative_undiscounted_cash_flow_thb=cumulative_undiscounted,
                cumulative_discounted_cash_flow_thb=cumulative_discounted,
            )
        )

    npv = cumulative_discounted
    irr = _irr(undiscounted_series_for_irr)

    total_discounted_energy = sum(cf.ac_energy_kwh * cf.discount_factor for cf in cash_flows)
    # LCOE's cost side is CAPEX + discounted OPEX only (the standard
    # definition) - tax is a financing/accounting flow, not a cost of
    # producing the energy, so it's excluded here even though it's part of
    # net_cash_flow above.
    total_discounted_cost = capex + sum(cf.opex_thb * cf.discount_factor for cf in cash_flows)
    lcoe = total_discounted_cost / total_discounted_energy if total_discounted_energy > 0 else float("inf")

    simple_payback = _find_payback_year([cf.cumulative_undiscounted_cash_flow_thb for cf in cash_flows], capex)
    discounted_payback = _find_payback_year([cf.cumulative_discounted_cash_flow_thb for cf in cash_flows], capex)

    return FinancialResult(
        capex_thb=capex,
        npv_thb=npv,
        irr_pct=irr,
        lcoe_thb_per_kwh=lcoe,
        simple_payback_years=simple_payback,
        discounted_payback_years=discounted_payback,
        cash_flows=cash_flows,
        assumptions=assumptions,
    )
