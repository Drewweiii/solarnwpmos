# Module 5 — Simulation Engine

What-if scenarios (cloud cover, curtailment, degradation), Monte Carlo
prediction intervals, and a PVWatts-style loss model (soiling, shading,
mismatch, DC wiring, inverter efficiency, DC/AC clipping) → performance
ratio per zone. A dev FastAPI wrapper exposes `POST /simulate/{zone}`.

**No battery/BESS** - confirmed with the user (2026-07-14): the plant is
fully on-grid, no battery storage exists or is planned before 2035 (and
even then, unbuilt). The architecture doc's "battery dispatch (SoC,
charge/discharge, reserve allocation)" bullet does not apply to this
system and is not implemented here.

## Pipeline

```
nongfab_forecast.pv_conversion            # Module 4's PV conversion (reused, not duplicated)
  default_params_from_capacity() + predict_power_kw()
        │
        ▼  DC power (temperature-derated, but NOT yet loss-derated)
loss_model.apply_losses()                 # soiling/shading/mismatch/DC-wiring/connections/availability + inverter efficiency
        │
        ▼  AC power
loss_model.clip_to_inverter_capacity()    # DC/AC clipping (e.g. GIS's 1.20 ratio "expect midday clipping")
        │
        ▼  baseline AC power
what_if.apply_scenario()                  # cloud/curtailment/degradation deltas on top of the baseline
        │
        ▼  adjusted AC power
monte_carlo.monte_carlo_prediction_interval()  # optional - PI around the adjusted series
```

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
- **Degradation**: user-supplied `degradation_pct_per_year` in
  `what_if.ScenarioParams` - no default is baked in (crystalline-silicon
  modules commonly warranty ~0.4-0.7%/year, but this repo doesn't assert a
  specific figure without a source).

## Bug caught by live-testing the dev API, not assumed

`POST /simulate/GIS` initially returned **nonzero AC power at midnight**
(00:00 UTC). Traced to Module 4's `pv_conversion.default_params_from_capacity()`:
its purely-additive linear form `P = beta*I + gamma*T + intercept` predicts
small *positive* power at zero irradiance whenever temperature is below
25degC (STC) - the temperature term alone is nonzero then, and the existing
Module 4 unit test happened to only check `predict_power_kw(0.0, 25.0, ...)`
(exactly STC temp), which coincidentally zeroes the artifact. A real PV
module cannot produce power with zero irradiance no matter how cold it is.
Fixed in `nongfab_forecast.pv_conversion.predict_power_kw()` by gating
output to zero whenever irradiance is zero, with regression tests added in
both Module 4 (`test_predict_power_is_exactly_zero_at_zero_irradiance_regardless_of_temperature`)
and re-verified live here after the fix.

## Layout

```
src/nongfab_simulation/
  loss_model.py    LossFactors, default_loss_factors(), combined_derate(), apply_losses(),
                     clip_to_inverter_capacity(), performance_ratio(), annual_specific_yield()
  what_if.py         ScenarioParams, apply_scenario() - cloud/curtailment/degradation deltas
  monte_carlo.py       monte_carlo_prediction_interval(), evaluate_monte_carlo_interval()
                       (reuses nongfab_forecast.metrics.evaluate_prediction_interval)
  api.py                 dev-only FastAPI: POST /simulate/{zone}
tests/                pytest suite - synthetic baseline (see "Known gaps"), no live services needed
```

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
curl -X POST http://localhost:8003/simulate/Jetty -H "Content-Type: application/json" \
  -d '{"curtailment_pct": 15, "monte_carlo_error_std_kw": 10}'
```

## Verified live (2026-07-14)

- Full dev-API path exercised end-to-end for all three zones: `POST
  /simulate/{zone}` → synthetic baseline day → PV conversion → loss model +
  DC/AC clipping → what-if scenario → (optional) Monte Carlo interval.
  Confirmed GIS's AC output never exceeds its 50kW inverter capacity even
  at simulated midday peak (the DC/AC=1.20 clipping behavior the config's
  own notes predict), Jetty's soiling loss is higher than GIS's, and
  curtailment visibly reduces adjusted output - all via curl against a
  running server, not just pytest's `TestClient`.
- 40 tests passing. `ruff check` clean.

## Known gaps / next steps

- **Not wired to real data** - same caveat as Modules 3/4: no real
  accumulated production history exists yet, so the dev API's baseline is
  a synthetic clear-day profile through Module 4's PV conversion, not real
  measurements. A thin loader (query TimescaleDB → the DataFrame shapes
  `apply_losses`/`apply_scenario` expect) is the natural next step once
  real data exists.
- **No shading model** - `loss_model`'s `shading_pct` is a flat literature
  default, not the ray-cast per-panel shading Feature B calls for (3D
  visualization, not started). Once that exists, its output could feed
  `LossFactors.shading_pct` per-zone instead of a constant.
- **Degradation has no default rate** - deliberately left to the caller
  (`ScenarioParams.degradation_pct_per_year` defaults to 0.0, i.e. no
  degradation) rather than asserting an unsourced number.
- **No battery/BESS** - confirmed out of scope entirely (see top of this
  README), not merely deferred.
