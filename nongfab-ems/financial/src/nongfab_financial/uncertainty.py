"""P50/P90 yield and Monte Carlo over the financial assumptions (2026-07-25).

`model.compute_financial_analysis` answers "what is the NPV" with one number,
which is the least honest thing a financial model can do on this project: its
CAPEX and WACC are documented placeholders, its tariff escalates at an assumed
rate, and the site has no meter, so the yield feeding it is itself an estimate.
A single NPV hides all of that behind two decimal places. This module puts the
spread back.

Two DIFFERENT things live here, deliberately not merged:

1. **P50/P90 on the energy yield** - the solar industry's own convention, and
   what a lender asks for. It describes how much the ANNUAL YIELD varies from
   year to year for a plant that is working perfectly: cloudier years, hazier
   years, wetter monsoons. It says nothing about whether the money assumptions
   are right.

2. **Monte Carlo over the financial assumptions** - CAPEX, tariff, escalation,
   WACC, degradation and opex sampled together, giving a distribution of NPV /
   IRR / LCOE / payback. This describes how little we know about the INPUTS,
   which on this project is the larger source of doubt by far.

Reporting them separately matters: a narrow P90 band next to a huge NPV spread
is exactly the correct message here - the sun is the predictable part, the
price of the project is not.

P50/P90 CONVENTION, because it is the classic thing to get backwards:
  * P50 = the median. Half of years beat it.
  * P90 = the level that is EXCEEDED in 90% of years - i.e. the 10th
    percentile of the distribution, so P90 < P50. Not the 90th percentile.
`test_uncertainty.py` asserts this ordering so it cannot silently invert.

Uncertainty inputs are `literature`-origin, not measured: no on-site
interannual record exists (the plant is new and unmetered). They are settable,
so a real figure replaces them without touching this code.

Sampling style follows `nongfab_simulation.monte_carlo` (frozen dataclass of
uncertainties, zero spread means "fixed, not sampled", explicit seed) so the
two Monte Carlos in this repo read the same way. It differs in one respect on
purpose - see `FinancialDistribution` for why the means are NOT duplicated
here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .model import DEFAULT_CAPEX_PER_KWP_THB, FinancialAssumptions, compute_financial_analysis

# Year-to-year variability of annual solar yield, as a coefficient of variation
# (std as a % of the mean). Published interannual variability for tropical
# monsoon sites generally falls around 3-5%; 4% is the mid-point taken here.
# LITERATURE DEFAULT, not measured at Nong Fab - there is no multi-year on-site
# record to derive it from, and inventing one would be exactly the kind of
# fabricated precision this repo forbids.
DEFAULT_ANNUAL_YIELD_CV_PCT = 4.0

# Percentile (as a probability of exceedance) that lenders underwrite on.
P50_EXCEEDANCE = 0.50
P90_EXCEEDANCE = 0.90

DEFAULT_SAMPLES = 2000


@dataclass(frozen=True)
class YieldUncertainty:
    """How much the annual yield swings between years, for a healthy plant."""

    annual_cv_pct: float = DEFAULT_ANNUAL_YIELD_CV_PCT

    def __post_init__(self) -> None:
        if self.annual_cv_pct < 0:
            raise ValueError(f"annual_cv_pct cannot be negative, got {self.annual_cv_pct}")


@dataclass(frozen=True)
class ExceedanceYield:
    """One P-level of the annual yield distribution."""

    exceedance: float  # 0.90 for P90
    label: str  # "P90"
    annual_energy_kwh: float


def exceedance_levels(
    p50_annual_energy_kwh: float,
    uncertainty: YieldUncertainty | None = None,
    exceedances: tuple[float, ...] = (P50_EXCEEDANCE, P90_EXCEEDANCE),
) -> list[ExceedanceYield]:
    """Annual yield at each probability of exceedance, assuming yields are
    normally distributed around the P50 estimate.

    A yield with 90% probability of exceedance sits BELOW the median, so this
    maps exceedance p to the (1 - p) quantile. Zero variability collapses every
    level onto the P50 figure, which is the honest degenerate case: with no
    knowledge of variability there is no spread to report.
    """
    if p50_annual_energy_kwh < 0:
        raise ValueError(f"p50_annual_energy_kwh cannot be negative, got {p50_annual_energy_kwh}")
    uncertainty = uncertainty or YieldUncertainty()
    sigma = p50_annual_energy_kwh * (uncertainty.annual_cv_pct / 100)

    levels: list[ExceedanceYield] = []
    for p in exceedances:
        if not (0 < p < 1):
            raise ValueError(f"exceedance must be strictly between 0 and 1, got {p}")
        # NormalDist inverse CDF without pulling in scipy: the (1-p) quantile.
        z = _inverse_standard_normal_cdf(1 - p)
        levels.append(
            ExceedanceYield(
                exceedance=p,
                label=f"P{int(round(p * 100))}",
                annual_energy_kwh=max(0.0, p50_annual_energy_kwh + z * sigma),
            )
        )
    return levels


def _inverse_standard_normal_cdf(q: float) -> float:
    """Standard-normal quantile. Uses the stdlib's NormalDist rather than
    scipy, which `financial/` does not depend on and should not start to for
    one function."""
    from statistics import NormalDist

    return NormalDist().inv_cdf(q)


@dataclass(frozen=True)
class FinancialDistribution:
    """How uncertain each financial assumption is - the SPREAD only, in the
    same units as `FinancialAssumptions`. Zero means "treat as exact".

    Deliberately std-only, unlike `nongfab_simulation.monte_carlo`'s
    `ScenarioDistribution`, which carries (mean, std). Here the means already
    live in `FinancialAssumptions`, and duplicating them would create a second
    place for the base case to be defined - so a Monte Carlo could silently
    centre on a different CAPEX than the deterministic result shown beside it.
    It would also make an explicit mean of 0 (a perfectly valid tariff
    escalation) indistinguishable from "not configured". One source of truth
    for the centre, one for the spread.

    `capex_per_kwp_std_thb` is per kWp rather than a total so one distribution
    applies to any array size.
    """

    capex_per_kwp_std_thb: float = 0.0
    tariff_std_thb_per_kwh: float = 0.0
    tariff_escalation_std_pct: float = 0.0
    discount_rate_std_pct: float = 0.0
    degradation_std_pct_per_year: float = 0.0
    opex_std_pct_of_capex: float = 0.0
    # Yield varies too, and it belongs in the SAME trial as the money draws: a
    # bad-sun year and a high-CAPEX year can coincide, and sampling them apart
    # would hide that the downside compounds.
    annual_yield_cv_pct: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "capex_per_kwp_std_thb",
            "tariff_std_thb_per_kwh",
            "tariff_escalation_std_pct",
            "discount_rate_std_pct",
            "degradation_std_pct_per_year",
            "opex_std_pct_of_capex",
            "annual_yield_cv_pct",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative, got {getattr(self, name)}")

    def any_uncertainty(self) -> bool:
        """False when every parameter is exact - the caller then has a single
        deterministic case and should say so rather than draw a fake spread."""
        return any(
            v > 0
            for v in (
                self.capex_per_kwp_std_thb,
                self.tariff_std_thb_per_kwh,
                self.tariff_escalation_std_pct,
                self.discount_rate_std_pct,
                self.degradation_std_pct_per_year,
                self.opex_std_pct_of_capex,
                self.annual_yield_cv_pct,
            )
        )


@dataclass(frozen=True)
class MetricPercentiles:
    """Empirical percentiles of one output metric across the trials."""

    metric: str
    p10: float | None
    p50: float | None
    p90: float | None
    mean: float | None
    # Trials where the metric was undefined (no IRR root, never paid back).
    # Reported rather than dropped silently: "12% of trials never pay back"
    # is the single most decision-relevant number this module can produce.
    undefined_trials: int = 0


@dataclass(frozen=True)
class MonteCarloFinancialResult:
    samples: int
    metrics: dict[str, MetricPercentiles] = field(default_factory=dict)
    # Share of trials with NPV < 0 - the plain-language "chance this loses
    # money under these assumptions".
    probability_npv_negative_pct: float = 0.0
    probability_no_payback_pct: float = 0.0


def _sample_or_fix(rng: np.random.Generator, mean: float, std: float, n: int, lo: float | None, hi: float | None) -> np.ndarray:
    if std <= 0:
        return np.full(n, mean)
    return np.clip(rng.normal(mean, std, size=n), lo, hi)


def _percentiles(metric: str, values: list[float | None]) -> MetricPercentiles:
    """Percentiles over the trials where the metric is defined. An all-undefined
    metric yields Nones rather than a fabricated zero - "this never paid back in
    any trial" and "it paid back at year 0" are opposite findings."""
    defined = [v for v in values if v is not None and np.isfinite(v)]
    undefined = len(values) - len(defined)
    if not defined:
        return MetricPercentiles(metric=metric, p10=None, p50=None, p90=None, mean=None, undefined_trials=undefined)
    arr = np.asarray(defined, dtype=float)
    return MetricPercentiles(
        metric=metric,
        p10=float(np.quantile(arr, 0.10)),
        p50=float(np.quantile(arr, 0.50)),
        p90=float(np.quantile(arr, 0.90)),
        mean=float(arr.mean()),
        undefined_trials=undefined,
    )


def monte_carlo_financial_analysis(
    year_1_ac_energy_kwh: float,
    installed_dc_capacity_kwp: float,
    base: FinancialAssumptions,
    distribution: FinancialDistribution,
    n_samples: int = DEFAULT_SAMPLES,
    seed: int = 0,
) -> MonteCarloFinancialResult:
    """Run `n_samples` full cash-flow analyses, each with its own draw of the
    uncertain assumptions, and report percentiles of NPV / IRR / LCOE /
    payback.

    `base` supplies the mean for anything the distribution leaves at zero std,
    and every non-sampled field (tax rate, BOI holiday, lifetime) verbatim - so
    this cannot silently disagree with the deterministic result the same
    assumptions produce.
    """
    if n_samples < 2:
        raise ValueError(f"n_samples must be at least 2, got {n_samples}")
    if installed_dc_capacity_kwp <= 0:
        raise ValueError(f"installed_dc_capacity_kwp must be positive, got {installed_dc_capacity_kwp}")
    if year_1_ac_energy_kwh < 0:
        raise ValueError(f"year_1_ac_energy_kwh cannot be negative, got {year_1_ac_energy_kwh}")

    rng = np.random.default_rng(seed)

    # Every centre comes from `base`, every spread from `distribution` - so a
    # zero-spread run reproduces the deterministic result exactly.
    base_capex_per_kwp = (
        base.capex_thb / installed_dc_capacity_kwp
        if base.capex_thb is not None
        else DEFAULT_CAPEX_PER_KWP_THB
    )

    capex_per_kwp = _sample_or_fix(rng, base_capex_per_kwp, distribution.capex_per_kwp_std_thb, n_samples, 1.0, None)
    tariff = _sample_or_fix(rng, base.tariff_thb_per_kwh, distribution.tariff_std_thb_per_kwh, n_samples, 0.0, None)
    tariff_esc = _sample_or_fix(
        rng, base.tariff_escalation_pct_per_year, distribution.tariff_escalation_std_pct, n_samples, None, None
    )
    discount = _sample_or_fix(rng, base.discount_rate_pct, distribution.discount_rate_std_pct, n_samples, -99.0, None)
    degradation = _sample_or_fix(
        rng, base.degradation_pct_per_year, distribution.degradation_std_pct_per_year, n_samples, 0.0, None
    )
    opex_pct = _sample_or_fix(
        rng, base.opex_pct_of_capex_per_year, distribution.opex_std_pct_of_capex, n_samples, 0.0, None
    )

    # Yield is drawn per trial from the same CV the P50/P90 table uses, so the
    # two views of uncertainty on this page cannot contradict each other.
    if distribution.annual_yield_cv_pct > 0:
        sigma = year_1_ac_energy_kwh * (distribution.annual_yield_cv_pct / 100)
        energy = np.clip(rng.normal(year_1_ac_energy_kwh, sigma, size=n_samples), 0.0, None)
    else:
        energy = np.full(n_samples, year_1_ac_energy_kwh)

    npvs: list[float | None] = []
    irrs: list[float | None] = []
    lcoes: list[float | None] = []
    paybacks: list[float | None] = []

    for i in range(n_samples):
        trial = FinancialAssumptions(
            capex_thb=float(capex_per_kwp[i]) * installed_dc_capacity_kwp,
            opex_pct_of_capex_per_year=float(opex_pct[i]),
            tariff_thb_per_kwh=float(tariff[i]),
            tariff_escalation_pct_per_year=float(tariff_esc[i]),
            opex_escalation_pct_per_year=base.opex_escalation_pct_per_year,
            discount_rate_pct=float(discount[i]),
            tax_rate_pct=base.tax_rate_pct,
            boi_tax_holiday_years=base.boi_tax_holiday_years,
            degradation_pct_per_year=float(degradation[i]),
            lifetime_years=base.lifetime_years,
        )
        result = compute_financial_analysis(float(energy[i]), installed_dc_capacity_kwp, trial)
        npvs.append(result.npv_thb)
        irrs.append(result.irr_pct)
        lcoes.append(result.lcoe_thb_per_kwh)
        paybacks.append(result.simple_payback_years)

    negative = sum(1 for v in npvs if v is not None and v < 0)
    no_payback = sum(1 for v in paybacks if v is None)

    return MonteCarloFinancialResult(
        samples=n_samples,
        metrics={
            "npv_thb": _percentiles("npv_thb", npvs),
            "irr_pct": _percentiles("irr_pct", irrs),
            "lcoe_thb_per_kwh": _percentiles("lcoe_thb_per_kwh", lcoes),
            "simple_payback_years": _percentiles("simple_payback_years", paybacks),
        },
        probability_npv_negative_pct=negative / n_samples * 100,
        probability_no_payback_pct=no_payback / n_samples * 100,
    )
