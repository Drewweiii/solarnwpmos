# Module 5 — Simulation Engine

What-if scenarios (cloud cover, curtailment, degradation), Monte Carlo
prediction intervals, and a PVWatts-style loss model (soiling, shading,
mismatch, DC wiring, inverter efficiency, DC/AC clipping) → performance
ratio per zone. A dev FastAPI wrapper exposes `POST /simulate/{zone}` and
`POST /simulate/{zone}/compare`.

**No battery/BESS, anywhere, permanently** - confirmed twice with the user
(2026-07-14): the plant is fully on-grid. This is not a "not started yet"
gap like the other items in "Known gaps" below - it is out of scope by
design and will not be added. The architecture doc's "battery dispatch
(SoC, charge/discharge, reserve allocation)" bullet does not apply to this
system.

## Pipeline

```
pipeline.simulate_zone_baseline(zone, irradiance, temp, index)   # orchestrates the chain below
        │
        ├─▶ nongfab_forecast.pv_conversion                        # Module 4's PV conversion (reused, not duplicated)
        │     default_params_from_capacity() + predict_power_kw() → DC power (temperature-derated)
        │
        ├─▶ loss_model.apply_losses()                              # soiling/shading/mismatch/DC-wiring/connections/availability + inverter efficiency → AC power
        │
        └─▶ loss_model.clip_to_inverter_capacity()                 # DC/AC clipping (e.g. GIS's 1.20 ratio "expect midday clipping")
                │
                ▼  baseline AC power (ZoneBaseline)
        what_if.apply_scenario()                    # cloud/curtailment/degradation deltas on top of the baseline
        what_if.compare_scenarios()                  # several named scenarios side by side (sensitivity analysis / presets)
                │
                ▼  adjusted AC power
        monte_carlo.monte_carlo_scenario_simulation()  # PI from real uncertainty in the scenario's own parameters (preferred)
        monte_carlo.monte_carlo_prediction_interval()   # PI from a generic external error_std (model-agnostic fallback)
```

`pipeline.py` exists so a caller (this module's own `api.py`, or a future
Module 6 endpoint) doesn't have to hand-assemble the fetch → PV-conversion →
loss-model → clipping chain itself - `simulate_zone_baseline()` is the one
call that does it.

## Two Monte Carlo approaches, and why both exist

- `monte_carlo_prediction_interval(point_forecast, error_std, ...)`: generic
  Gaussian noise around any point value. Model-agnostic, but the caller has
  to supply `error_std` from somewhere external (e.g. a model's own
  backtest error) - it knows nothing about *why* the forecast is uncertain.
- `monte_carlo_scenario_simulation(baseline, ScenarioDistribution, ...)`:
  samples the what-if parameters themselves (cloud/curtailment/degradation)
  from Gaussian `(mean, std)` distributions and re-runs `apply_scenario` per
  trial - the prediction interval comes from genuine uncertainty in the
  scenario assumptions, not an arbitrary externally-supplied number. This is
  the one `api.py`'s `/simulate/{zone}` endpoint uses (via the `*_std_pct`
  request fields) - it directly answers "how wide should the output range
  be, given how confident we are in the cloud/curtailment/degradation
  inputs", which is what "Monte Carlo" means once read alongside the
  architecture doc's what-if scenarios, not noise bolted onto an unrelated point.

## Loss model assumptions (confirmed with the user: literature/standard values, not fabricated)

- **Soiling**: NREL PVWatts default (2.5%/year) for GIS/ISB (land); 6%/year
  (midpoint of the commonly-cited 5-8% marine/coastal range) for Jetty, per
  the architecture doc's own callout that marine salt-spray soiling is
  higher there. Neither number is measured O&M data - none exists yet.
- **Shading/mismatch/DC-wiring/connections/availability**: generic PVWatts
  documentation defaults, not site-specific (no ray-cast shading model
  exists yet - that's Feature B, dashboard-side, not started).
- **Inverter efficiency**: 99% from the real Huawei SUN2000-50KTL-M3
  datasheet (`config/assets.yaml`'s `inverter_detail.efficiency_pct`), all
  three zones use this same inverter model.
- **Degradation**: caller-supplied `degradation_pct_per_year` in
  `what_if.ScenarioParams` - no default is baked in (crystalline-silicon
  modules commonly warranty ~0.4-0.7%/year, but this repo doesn't assert a
  specific figure without a source).

**Searched for a Thailand/marine-specific substitute (2026-07-18)**: the
user asked what the Energy Report's loss percentages are based on and
whether real Thailand-specific data could be pulled from the web instead of
the generic PVWatts defaults above. Found real but context-mismatched
studies - Thai composite-climate daily soiling-rate papers, Atacama Desert
coastal soiling data, offshore floating-PV salt-spray lab results - none of
which transfer cleanly to Nong Fab's actual tropical-monsoon, pier-over-
water conditions without introducing false precision (a specific-looking
number from the wrong climate/geometry is less honest than an
acknowledged generic default). Kept the existing PVWatts defaults; the full
search and its inconclusive verdict is documented in `loss_model.py`'s own
module docstring, not just here.

## Recheck findings (2026-07-24) - two real bugs, both fixed

1. **`ScenarioParams` allowed physically-backwards values.** `curtailment_pct`
   and `degradation_pct_per_year` could be negative (down to -100), which
   would silently *increase* output above baseline - nonsensical, since
   curtailment only ever reduces grid export and degradation only ever
   reduces performance over time. Fixed: both are now rejected if negative
   (`curtailment_pct` additionally capped at 100). `extra_cloud_attenuation_pct`
   is deliberately still allowed to go negative - cloud-edge irradiance
   enhancement is a real, documented phenomenon (same reasoning as Module
   3's `clear_sky_index` clip range).
2. **`api.py` leaked raw 500 errors on bad input.** Nothing caught the
   `ValueError`s `apply_scenario`/`compare_scenarios`/
   `monte_carlo_scenario_simulation` raise for invalid parameters - a bad
   request (e.g. `curtailment_pct: 150`) crashed with an unhandled
   stack-trace response instead of a clean 4xx. Fixed: both endpoints now
   catch `ValueError` and return `422` with the validation message.

## Bug caught by live-testing the dev API, not assumed (2026-07-14)

`POST /simulate/GIS` initially returned **nonzero AC power at midnight**
(00:00 UTC). Traced to Module 4's `pv_conversion.default_params_from_capacity()`:
its purely-additive linear form `P = beta*I + gamma*T + intercept` predicts
small *positive* power at zero irradiance whenever temperature is below
25degC (STC) - the temperature term alone is nonzero then, and the existing
Module 4 unit test happened to only check `predict_power_kw(0.0, 25.0, ...)`
(exactly STC temp), which coincidentally zeroed the artifact. A real PV
module cannot produce power with zero irradiance no matter how cold it is.
Fixed in `nongfab_forecast.pv_conversion.predict_power_kw()` by gating
output to zero whenever irradiance is zero, with regression tests added in
both Module 4 and re-verified live here after the fix.

## Layout

```
src/nongfab_simulation/
  loss_model.py    LossFactors, default_loss_factors(), combined_derate(), apply_losses(),
                     clip_to_inverter_capacity(), performance_ratio(), annual_specific_yield()
  what_if.py         ScenarioParams, apply_scenario(), compare_scenarios() (named-scenario sensitivity analysis)
  monte_carlo.py       monte_carlo_prediction_interval() (generic), ScenarioDistribution +
                       monte_carlo_scenario_simulation() (scenario-uncertainty-driven, preferred),
                       evaluate_monte_carlo_interval() (reuses nongfab_forecast.metrics)
  pipeline.py            simulate_zone_baseline() - orchestrates PV conversion + loss model + clipping;
                           estimate_annual_ac_energy_kwh(), loss_breakdown_with_temperature() (Module 7's
                           Energy Report, STEP 8C)
  api.py                  dev-only FastAPI: POST /simulate/{zone}, POST /simulate/{zone}/compare
tests/                pytest suite - synthetic baseline (see "Known gaps"), no live services needed
```

## Annual energy + temperature loss (Module 7's Energy Report, STEP 8C)

Added to `pipeline.py`, next to `simulate_zone_baseline()`, since both need
its `ZoneBaseline` output rather than duplicating the fetch/convert/derate
chain:

- `estimate_annual_ac_energy_kwh(baseline)`: `baseline`'s one synthetic day
  summed to kWh, x 365 - a **flat extrapolation**, not a real annual
  simulation with weather variability or seasonality (no accumulated daily
  generation history exists yet to average over - same caveat as every
  other module's dev-time behavior).
- `loss_breakdown_with_temperature(baseline, irradiance, temp)`:
  `baseline.loss_breakdown` plus a `temperature_pct` entry. `loss_model.py`
  deliberately excludes temperature (see that module's own docstring - it's
  already baked into DC power by `pv_conversion.predict_power_kw`'s
  temperature-coefficient term, not a separate multiplicative derate like
  soiling/shading/etc.), but Module 7's Energy Report wants temperature
  alongside those in one loss table. Estimated by comparing DC energy at the
  actual temperature profile against DC energy at STC (25degC) for the same
  irradiance - the gap is what temperature alone cost. This doesn't change
  `loss_model.py`'s own invariant (still temperature-free) - it's a report-
  side overlay computed from the `pv_conversion` side instead.

## Monthly generation + 25-year lifecycle estimate (2026-07-16)

Two more `pipeline.py` additions, requested against a Thai solar-monitoring
reference site (reslink.org) as the Energy Report's design reference - both
feed `api/routes_energy_report.py`'s new `monthly`/`lifecycle` response
fields:

- **`monthly_ac_energy_estimates(zone_id, year=None)`**: one AC energy
  estimate per calendar month, built from a **real** pvlib solar-position/
  Ineichen clear-sky day (`nongfab_features.clearsky`) at Nong Fab's actual
  coordinates - genuine astronomy (day length, sun angle) driving the
  month-to-month swing, not a fabricated seasonal curve. Unlike
  `estimate_annual_ac_energy_kwh`'s single UTC-indexed synthetic day, the
  representative day here is built in `Asia/Bangkok` local time
  (`NONG_FAB_TZ`) specifically so "hour 12" actually means local solar noon
  - the older synthetic generators (`dev_data.synthetic_day_irradiance_temp`,
  and this same file's own `estimate_annual_ac_energy_kwh` input) still build
  a `tz="UTC"` index and shape their sine curve against its raw hour number,
  which is off by Thailand's UTC+7 offset; not fixed everywhere in this pass
  (bigger blast radius, out of scope), just not repeated in the new code.
  `RAINY_SEASON_MONTHS` (Jun-Oct, the Thai Meteorological Department's
  conventional wet season) gets an extra cloud derate via `what_if.
  apply_scenario`'s `extra_cloud_attenuation_pct` -
  `RAINY_SEASON_EXTRA_CLOUD_ATTENUATION_PCT` is a **documented assumption**,
  not a measured monthly cloud climatology (no such dataset exists in this
  system - same "documented approximation" pattern as `pv_conversion.py`'s
  temperature coefficient).
- **`lifecycle_ac_energy_estimate(year_1_ac_energy_kwh, degradation_pct_per_year=DEFAULT_DEGRADATION_PCT_PER_YEAR, years=25)`**:
  reuses `what_if.apply_scenario`'s own validated linear degradation model
  (one call per year, since `apply_scenario` applies one uniform
  `years_since_commissioning` per call, not a schedule) to project year 1 ->
  year 25 output and a 25-year lifetime total.
  `DEFAULT_DEGRADATION_PCT_PER_YEAR = 0.55` is a typical modern
  crystalline-silicon linear warranty figure, not a Trina Vertex N-specific
  measured value (same gap as the temperature coefficient - `config/
  assets.yaml` doesn't carry a real one).

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../libs/nongfab_common
pip install -e ../features
pip install -e ../forecast
pip install -e ".[dev,api]"
pytest -v

# interactive dev API:
uvicorn nongfab_simulation.api:app --reload --port 8003
# then open http://localhost:8003/docs, or:
curl -X POST http://localhost:8003/simulate/GIS -H "Content-Type: application/json" -d '{}'

# scenario + Monte Carlo (uncertainty in the cloud assumption drives the PI):
curl -X POST http://localhost:8003/simulate/Jetty -H "Content-Type: application/json" \
  -d '{"extra_cloud_attenuation_pct": 20, "extra_cloud_attenuation_std_pct": 15}'

# sensitivity comparison across named presets:
curl -X POST http://localhost:8003/simulate/ISB/compare -H "Content-Type: application/json" -d '{
  "scenarios": {
    "typical": {}, "clear_sky": {"extra_cloud_attenuation_pct": -15},
    "heavy_cloud": {"extra_cloud_attenuation_pct": 50}, "grid_curtailed": {"curtailment_pct": 30}
  }
}'
```

## Verified live (2026-07-24)

- Full dev-API path exercised end-to-end for all three zones, both
  endpoints: `POST /simulate/{zone}` (baseline → scenario →
  scenario-uncertainty Monte Carlo) and `POST /simulate/{zone}/compare`
  (four named presets - typical/clear/heavy-cloud/curtailed - returned
  correctly ordered: clear_sky > typical > heavy_cloud, curtailed < typical,
  at every hour). Confirmed a `curtailment_pct: -5` request now returns a
  clean `422` with a descriptive message instead of a raw 500. All via curl
  against a running server, not just pytest's `TestClient`.
- 66 tests passing (up from 40 before this recheck/upgrade pass). `ruff check` clean.

## Known gaps / next steps

- **Not wired to real data** - same caveat as Modules 3/4: no real
  accumulated production history exists yet, so the dev API's baseline is
  a synthetic clear-day profile through `pipeline.simulate_zone_baseline()`,
  not real measurements. A thin loader (query TimescaleDB → the irradiance/
  temp series `simulate_zone_baseline()` expects) is the natural next step
  once real data exists.
- **No shading model** - `loss_model`'s `shading_pct` is a flat literature
  default, not the ray-cast per-panel shading Feature B calls for (3D
  visualization, not started). Once that exists, its output could feed
  `LossFactors.shading_pct` per-zone instead of a constant.
- **Degradation has no default rate** - deliberately left to the caller
  (`ScenarioParams.degradation_pct_per_year` defaults to 0.0, i.e. no
  degradation) rather than asserting an unsourced number.
- **No battery/BESS** - confirmed out of scope entirely, permanently (see
  top of this README) - not merely deferred.

## Added - seasonal annual energy is now the canonical annual figure (2026-07-22)

The Energy Report's headline "Annual energy" (and the 25-year lifecycle
projection built off it, and the `/financial` module's year-1 energy that
drives NPV/IRR/LCOE/payback) came from `estimate_annual_ac_energy_kwh()` -
a flat `x365` of one clear-sky day with zero seasonal variation - even
though `monthly_ac_energy_estimates()` (a genuine per-month pvlib solar-
position swing + a rainy-season cloud derate) already existed and was
*already shown as the Energy Report's monthly chart*. So the headline and
the chart right below it silently disagreed, and the payback ignored the
rainy season entirely.

New `seasonal_annual_ac_energy_kwh(zone_id, year=None)` = the sum of those
12 monthly estimates. It's now the canonical annual figure:

- `api/routes_energy_report.py` computes `monthly` once and sums it for the
  annual headline (so headline == chart, exactly), feeding specific yield +
  the 25-year lifecycle.
- `api/routes_financial.py` sums `seasonal_annual_ac_energy_kwh` across the
  installed zones for its year-1 energy (dropping the synthetic-day baseline
  it no longer needs) - a seasonally honest year-1 yield matters most here,
  since the rainy-season months it now accounts for are a real drag on the
  payback the crude x365 silently ignored.
- `api/routes_savings.py` (Track 2's savings table) already summed the same
  monthly estimates inline - unchanged, and now consistent with the other
  two via the shared formula.

`estimate_annual_ac_energy_kwh(baseline)` is kept as the simple single-day
building block (its x365 unit test still pins that definition) but no API
route uses it for an annual headline anymore. Still a documented
approximation, not a genuine day-by-day measured-weather annual sum - that
remains the natural next step once reliably-persistent real historical
weather exists (PVGIS's ERA5 seed is ephemeral per container - see the root
README), not a redesign of this function's shape.

**Tested**: `test_pipeline.py` +3 (`seasonal_annual_ac_energy_kwh` equals
the sum of the monthly estimates, is positive, and genuinely differs from
the flat x365 of one clear-sky day); `test_routes_energy_report.py` +1 (the
annual headline now equals the sum of the monthly chart values). Full
`simulation` (24) and `api` route suites pass, `ruff` clean.

### 2026-07-22 - Shading loss is now geometry-derived, not a flat literature default (roadmap item 3)

`default_loss_factors(zone_id)`'s `shading_pct` was the flat
`DEFAULT_SHADING_PCT = 3.0` PVWatts literature default for every zone. It is
now:

    shading_pct = annual_shading_loss_pct(zone_id)   # real array geometry
                + DEFAULT_EXTERNAL_SHADING_PCT        # 2.0% external allowance

`nongfab_features.shading.annual_shading_loss_pct` integrates the zone's real
modelled array geometry (`generate_zone_layout` -> `zone_solar_access`) over a
full year's clear-sky sun path (12 mid-month days x 24 h), energy-weighted by
each hour's clear-sky GHI so geometrically-severe but energetically-tiny
low-sun hours don't dominate. It is `@lru_cache`d (a fixed deterministic
geometric property), so it's cheap on the hot `default_loss_factors` path.

**Scope / honesty**: this models *inter-row self-shading only*. There is no
site obstacle survey in `config/assets.yaml`, so external-obstacle shading
(neighbouring structures, terrain, vegetation) is NOT modelled - it stays a
documented known gap. `DEFAULT_EXTERNAL_SHADING_PCT = 2.0` is an explicit
literature *allowance* for it, added on top so a well-pitched array (whose
real inter-row loss can be well under 1%) still carries a realistic total.
Replace it with a surveyed figure once a real obstacle survey exists.
`DEFAULT_SHADING_PCT = 3.0` is kept only as the `LossFactors` dataclass
fallback for zone-less direct construction (tests).

**Tested**: `test_loss_model.py` +2 (`shading_pct` equals
`annual_shading_loss_pct(zone) + external allowance`, is >= the external
allowance, and differs from the old flat 3% default); `features/test_shading.py`
+2 (`annual_shading_loss_pct` is a sane 0..100% and deterministic/cached).
Full `simulation` (26) and `api` energy-report route (13) suites pass, `ruff`
clean.
