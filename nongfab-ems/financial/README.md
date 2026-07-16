# Module 11: Financial / Investment Analysis

NPV, IRR, LCOE, and simple vs. discounted payback for the Nong Fab solar
installation over its 25-year design life.

## Why this module exists

Added 2026-07-16 after a conversation with the user reframed the whole
project's priorities. Sub-daily/hour-ahead/day-ahead forecasting (Module 4)
has little *operational* value at this specific site: the plant is fully
grid-tied with no battery, solar is not the primary generation source, and
installed capacity is capped by available land (it can't be expanded
regardless of what a forecast says). Nothing dispatch-related changes based
on a forecast here. What the user actually cares about for this asset is
the same thing that matters for any capital project: does it pay back, and
how does it compare against the cost of capital.

The user also flagged a second, separate reason real production data
matters that has nothing to do with forecast accuracy: if the site claims
**carbon credits** based on solar generation (one of the two stated reasons
solar exists at this site, alongside using otherwise-idle land), most
carbon-credit standards require *metered* generation data for MRV
(Measurement, Reporting, Verification), not a physics-model estimate. That
gap is tracked separately - see the root README's Module status table -
this module doesn't need that resolved, since financial modeling works off
a yield **estimate**, not real-time telemetry.

## What it computes

Reuses `nongfab_simulation.what_if.apply_scenario`'s own degradation model
(same one `simulation.pipeline.lifecycle_ac_energy_estimate()` uses) to
degrade a starting annual-energy estimate year over year, then turns that
into a 25-year cash flow table and derives:

- **NPV** (Net Present Value)
- **IRR** (Internal Rate of Return) - dependency-free bisection solver, no
  `numpy_financial`
- **LCOE** (Levelized Cost of Energy) - standard `(CAPEX + discounted OPEX)
  / discounted energy` definition, tax excluded (LCOE is a cost-of-energy
  metric, not a financing/accounting one)
- **Simple payback** and **discounted payback** (years, linearly
  interpolated within the crossing year for a fractional result)

Only the currently-installed zones (GIS, ISB) feed the year-1 energy
estimate - Jetty is excluded (`simulated: true` in `config/assets.yaml`,
design-mode, no panels installed yet, so there's no real capital outlay
there yet to analyze the payback of).

## Every assumption is a documented placeholder except one

`FinancialAssumptions` (in `src/nongfab_financial/model.py`) defaults every
cost/rate figure to a **documented placeholder**, not a confirmed number
for this project:

| Field | Default | Status |
|---|---|---|
| `capex_thb` | `None` -> ฿30,000/kWp × installed DC capacity | placeholder |
| `opex_pct_of_capex_per_year` | 1.2% | placeholder (industry rule of thumb) |
| `tariff_thb_per_kwh` | ฿4.0/kWh | placeholder (blended PEA industrial estimate) |
| `tariff_escalation_pct_per_year` | 3.0% | placeholder |
| `opex_escalation_pct_per_year` | 3.0% | placeholder |
| `discount_rate_pct` (WACC) | 8.0% | placeholder |
| `tax_rate_pct` | 20.0% | **real** - Thailand's actual standard corporate income tax rate |
| `boi_tax_holiday_years` | 0 | conservative placeholder (no BOI assumed until confirmed) |
| `degradation_pct_per_year` | 0.55%/yr | reused from `simulation.pipeline`'s own placeholder |
| `lifetime_years` | 25 | reused from `simulation.pipeline`'s own placeholder |

**The user still needs to supply**: real CAPEX, the actual PEA industrial
tariff/contract structure, BOI promotion status (if any) and its
tax-holiday length, and the company's real WACC. Tax/BOI treatment here is
a simplified flat-rate model for a rough estimate, **not tax advice** -
confirm with the user's finance/tax team before using this for a real
investment decision. `web/CLAUDE.md`-equivalent standing reminder: the root
`CLAUDE.md` carries a note to keep flagging this to the user until they
confirm real figures.

## API

`POST /financial` (`api/src/nongfab_api/routes_financial.py`), gated at
"operator" or higher (same reasoning as `/simulate`: a heavier
what-if computation carrying business-sensitive assumptions, not a plain
read). Every request field overrides one `FinancialAssumptions` default;
omitted fields keep the placeholder.

## Frontend

`/financial` (`web/src/pages/FinancialPage.tsx`) - an investment-analysis
playground mirroring the existing Simulation Playground's slider-input +
output-card UX: sliders for every assumption, a CAPEX auto-estimate/custom
toggle, NPV/IRR/LCOE/payback KPI cards, and a 25-year cumulative
(discounted vs. undiscounted) cash flow chart with a zero reference line to
visualize the payback crossing.

## Tests

`tests/test_model.py` - 19 tests covering NPV/IRR/LCOE/payback correctness,
BOI tax-holiday zeroing, degradation application, and the IRR
bisection solver's edge cases (never-breaks-even, exact doubling case).
`api/tests/test_routes_financial.py` - 7 tests covering auth/RBAC, default
assumptions, Jetty exclusion, and assumption overrides.
