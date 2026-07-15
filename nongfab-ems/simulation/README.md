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
