# Module 4 — Forecasting Engine (3 horizons)

Three horizon-specific forecasters (minute/hour/day-ahead), a linear PV
conversion model (irradiance/temperature → AC power), point + interval
evaluation metrics (RMSE/MAE/MBE/NRMSE, PICP/PINAW), an MLflow experiment/
registry layer, and a dev FastAPI wrapper exposing `GET /forecast/{zone}/{horizon}`.

## Horizons

| Horizon | Model | Input | Loss | Tuning |
|---|---|---|---|---|
| Minute-ahead | hand-written CNN-LSTM (torch) | cloud opacity/index + cloud motion vector (u/v, km/h) sequence | Huber or L1 (`neuralforecast.losses.pytorch`) | Adam + early stopping |
| Hour-ahead (+1h..+6h, k-step) | LightGBM **or** Random Forest, auto-selected per lead hour on held-out RMSE, + bias-correction cascade | NWP + lag + clear-sky features | L2 (L1 selectable, LightGBM only) | Optuna (Bayesian, LightGBM) + early stopping |
| Day-ahead (+1h..+72h, 3 days) | NeuralProphet + bias-correction cascade | trend + seasonality + future regressors (SSRD, T) | MAE | quantile regression for PI |

## Simulated zones (Jetty)

`pv_conversion.nong_fab_simulated_zone_ids()` reads `config/assets.yaml`'s
per-zone `simulated` flag (`nongfab_common.assets.Zone.simulated`) - `True`
for Jetty, confirmed by satellite imagery (2026-07-14) to have no panels
physically installed yet, vs. `False` for GIS/ISB (real installed hardware
that just hasn't accumulated sensor history yet - a different, temporary
kind of gap). Callers should treat a simulated zone's PV output as a
permanent capacity-driven projection (`default_params_from_capacity()`) -
`fit_pv_conversion_model()` against real (I, T, P) history will never apply
to Jetty until it's actually built, unlike GIS/ISB where it's just a matter
of waiting for enough history to accumulate. Not yet wired into the dev
API's `/train-now` (which trains all three zones identically on synthetic
data regardless), but the distinction is available for Module 5
(simulation engine, not started) and any future real-data training path to
branch on.

## Design notes / deviations from a literal reading of the spec

- **Minute-ahead "CNN-LSTM (neuralforecast)"**: `neuralforecast` does not ship
  a model literally named "CNN-LSTM" (its `LSTM`/`TCN`/`RNN` classes are each
  a single family, not this specific hybrid). Rather than force-fit an
  off-the-shelf architecture that isn't actually a CNN-LSTM, `minute_ahead.py`
  hand-writes the real architecture (Conv1d → LSTM → Linear head) in plain
  PyTorch, while still genuinely using `neuralforecast` for its loss
  functions (`neuralforecast.losses.pytorch.HuberLoss`/`MAE`) - not just an
  installed-and-unused dependency.
- **PV conversion "P = β·I + γ·T + ..." (MOSKF)**: implemented as literally
  stated - an OLS linear fit (`fit_pv_conversion_model`) - plus a
  capacity-derived default (`default_params_from_capacity`) for when no (I,
  T, P) history exists to fit against yet (today's situation - see "Known
  gaps"). The module temperature coefficient used in the default
  (-0.30%/°C) is a typical N-type i-TOPCon value, not sourced from the
  Trina Vertex N datasheet (`config/assets.yaml` doesn't carry one) -
  documented as an approximation in `pv_conversion.py`, not a measured constant.
- **MLflow registry**: MLflow 3.x deprecated the plain filesystem tracking
  backend (`file:./mlruns` raises `MlflowException` telling you to migrate to
  a DB backend) - `registry.py` defaults to a local sqlite file
  (`sqlite:///mlflow.db`) instead, overridable via `MLFLOW_TRACKING_URI` to
  point at the docker-compose mlflow service (Postgres-backed) in production.
  Models are logged via a generic `mlflow.pyfunc.PythonModel` wrapper that
  cloudpickles whatever object is passed in (NeuralProphet has no native
  MLflow flavor at all) - `load_model()` unwraps it back to the original
  object rather than exposing MLflow's `predict()` serving contract, since
  each horizon's own `predict_*()` function has an incompatible signature and
  nothing consumes a pyfunc-serving endpoint yet (Module 6 doesn't exist).

## Real-data feature layer (`real_data.py` + `local_store.py`)

Closes the "not wired to real data" gap this README used to list (see git
history) - `training.train_now()` and `serving.get_latest_forecast()` now
**prefer real ingested/backfilled data over the synthetic generators**
whenever enough has accumulated, falling back to the original synthetic path
below that bar. This was an opportunistic, backward-compatible addition, not
a rewrite: both functions gained an optional `store: RealDataStore | None`
parameter that defaults to an empty in-memory store, so every existing
caller/test that doesn't pass one sees zero behavior change.

- **`local_store.RealDataStore`**: a SQLite-backed store (`sqlite3`, stdlib,
  no new dependency) for real NWP/cloud/UV history - **not** TimescaleDB.
  `ingestion/nwp` and `ingestion/himawari`'s own `storage.py` need a real
  Postgres/TimescaleDB (`pg_insert`'s `ON CONFLICT` is Postgres-specific
  SQL), which the production deployment (Railway, `api/`) doesn't have - see
  `api/README.md`'s "Real-data background ingestion" section for the full
  story of why. Same ephemeral-per-container durability as the already-
  accepted `mlflow.db` pattern (`registry.py`): `:memory:` by default
  (`NONGFAB_REAL_DATA_DB` env var to point at a real file), safe as a
  single-instance-per-process cache since `api/`'s lifespan creates exactly
  one `RealDataStore` for the whole app lifetime, not one per request.
- **`real_data.py`**: builds model-ready frames from that store -
  `real_hour_frame`/`real_day_frame`/`real_minute_frame` (training),
  `current_hour_conditions`/`real_future_regressors`/`recent_minute_window`
  (serving) - each raising `InsufficientHistoryError` below its own minimum
  row count (`MIN_HOUR_ROWS=24`, `MIN_DAY_ROWS=72`, `MIN_MINUTE_ROWS=30`)
  rather than degrading silently.
- **No real generated-power telemetry exists anywhere in this system**
  (Jetty is a simulated capacity projection with no panels installed;
  GIS/ISB have no SCADA tap wired in - and the user who requested this pass
  explicitly scoped it to real *weather* inputs, not fabricated "real" power
  output). So every `power_kw` value `real_data.py` produces is the physics
  -based PV conversion model (`pv_conversion.predict_power_kw`) applied to
  REAL irradiance/temperature, never a real measured target -
  `pv_params_for_zone()` always uses `default_params_from_capacity()`, never
  `fit_pv_conversion_model()`, for every zone including non-simulated ones.
  This mirrors the actual academic reference this project cites (Suksamosorn
  & Songsiri, MOS+KF): forecast the weather-driven signal, convert through a
  calibrated physical model. It is the standard approach when no plant
  telemetry exists, not a shortcut.
- **`serving.get_forecast_with_fallback()`**: a new function alongside (not
  replacing) `get_latest_forecast()` - same contract for bad input
  (`UnknownZoneError`/`UnknownHorizonError`), but never raises
  `ModelNotTrainedError`: falls back to `real_data.physics_baseline_series()`
  (pvlib clear-sky × live cloud attenuation × the zone's PV model, no ML)
  instead, tagged `model_type="physics_baseline"`. `api/`'s production
  `/forecast/{zone}/{horizon}` route calls this one; Module 4's own dev API
  (`api.py`) still calls the raw `get_latest_forecast()` (its job is raw
  model verification, not a friendly public-facing default - see
  `api/routes_forecast.py`'s own docstring for this split).
- **`ForecastResult`/`TrainResult` gained a `data_source` field**
  (`"real"`/`"synthetic"`), and `ForecastResult` a `model_type` field
  (`"ml"`/`"physics_baseline"`) - so a caller can tell what's actually
  driving a number instead of it being silently ambiguous.

## k-step hour-ahead, RF-vs-LightGBM auto-select, bias-correction cascade, cloud motion (2026-07-15)

Extends the real-data feature layer above, per the Songsiri deck's own
"Forecast results: k-step" evaluation (scores each lead hour separately) and
its RF/SVR/MARS/ANN comparison (finding Random Forest the best performer):

- **Hour-ahead is now k-step, not single-point**: `HourAheadKStepModel`
  (`hour_ahead.py`) bundles **6 independently-trained models**, one per lead
  hour (`serving.HOUR_LEAD_HOURS = (1, 2, 3, 4, 5, 6)`), not one multi-output
  model - each lead sees a different NWP-forecast-skill/feature relationship
  as lead time grows, matching how the reference deck scores each `k`
  separately rather than pooling. `real_data.real_hour_frame_kstep()` /
  `current_hour_conditions_kstep()` select real NWP rows by
  `lead_hours = valid_time - issue_time` (not just `valid_time`), since the
  same GFS cycle forecasts every lead hour and the earlier single-lead code's
  history dedup collapsed away the exact distinction k-step training needs.
  Bundled as **one** MLflow-registered object (not 6 separate registrations)
  so the existing one-model-per-`(horizon, zone)` registry naming scheme
  needed no changes.
- **Random Forest alongside LightGBM, auto-selected per lead hour**:
  `train_rf_hour_ahead_model()` trains a `RandomForestRegressor`; its
  prediction interval comes from the empirical (5th, 95th) percentile across
  individual trees' own predictions (a standard "quantile regression forest"
  approximation), vs. LightGBM's two extra `quantile`-objective models.
  `training._train_hour_ahead_kstep()` trains both candidates per lead hour
  and registers whichever wins on held-out validation RMSE -
  `algorithm_by_lead_hour` records which won, and MLflow `params` log
  `lead{N}_algorithm` per lead so it's visible after the fact, not just at
  training time.
- **Bias-correction cascade (hour-ahead and day-ahead)**: `bias_correction.py`
  trains a `Ridge` regressor on a model's own held-out validation *residual*
  (`y_true - primary_pred`), then adds its prediction to future point/lower/
  upper forecasts (`apply_bias_correction()`) - the "second model learns the
  first model's residual error" pattern the deck's MOS+KF section describes,
  applied as a lightweight residual regression rather than a full Kalman
  filter (the latter wasn't requested). Day-ahead's cascade trains on its own
  80/20 split of real training history; hour-ahead's trains on each lead
  hour's own validation split.
- **Day-ahead extended from 24h to 72h** (`serving.MAX_DAY_AHEAD_HOURS = 72`):
  3 days, not literally "one day ahead" (name kept for the architecture doc's
  3-horizon taxonomy) - capped there because that's the actual reach of the
  real NWP data ingested (`api/config.py`'s `nwp_poll_forecast_hours`) and
  because post-processed NWP-driven solar forecast skill degrades sharply
  past ~3-4 days (see the Songsiri reference above), so serving further would
  just be presenting numbers with no real basis for the extra confidence.
- **Cloud motion vector wired into minute-ahead**: `real_data.py`'s
  `MINUTE_FEATURE_COLS` gained `motion_u_kmh`/`motion_v_kmh` - Cartesian
  components (not raw speed/direction, to avoid the 0°/360° circular
  discontinuity as an ML feature) converted from `himawari_ingestion.motion`'s
  FFT-phase-correlation optical flow output
  (`api/ingestion_scheduler.py`'s `_frame_with_motion()`, wired into both the
  live poll loop and cold-start backfill so history accumulated before this
  change gets motion filled in going forward, not just new frames).
- **Adaptive retrain interval**: `api/ingestion_scheduler.py`'s
  `_retrain_forever()` now retrains every `API_RETRAIN_INTERVAL_COLD_SECONDS`
  (default 1h) while real `nwp_history` is thin, or every
  `API_RETRAIN_INTERVAL_WARM_SECONDS` (default 6h, one retrain per real GFS
  cycle) once it crosses `API_RETRAIN_WARM_THRESHOLD_ROWS` (default 500) -
  re-checked every cycle, not decided once at startup, so a deployment that
  starts cold and accumulates real data live transitions on its own.
- **Statistical honesty caveat, unchanged from the section above**: RF-vs-
  LightGBM comparisons and every bias-correction residual still reflect
  fitting the same deterministic physics formula (`pv_conversion.py`), not
  real forecast skill - no real generation telemetry exists anywhere in this
  system yet. The comparison/cascade machinery is genuinely real and will
  reflect true forecast skill the moment real telemetry exists to train
  against; see each new module's own docstring (`hour_ahead.py`,
  `bias_correction.py`) for the same caveat in more detail.

**Fixed the `PYTHONHASHSEED`-flaky round-trip test documented below**, not
just worked around it: `_predict_lgbm_hour_ahead()` now clips the point
prediction into `[lower, upper]` after computing all three (the point,
lower, and upper models are three independently-trained LightGBM models with
no cross-model consistency constraint - clipping `pred` is what actually
guarantees `lower <= pred <= upper`, not just that `lower <= upper`, which is
all the pre-existing clip did). This was found because k-step training now
runs this same independently-trained-trio pattern 6x per zone/horizon
instead of once, which turned a rare `PYTHONHASHSEED`-dependent failure into
a reliable one - worth fixing now rather than carrying 6x the exposure to it.

## Bug caught by live-testing the dev API, not assumed

`day_ahead.predict_day_ahead()` originally returned a DataFrame indexed by
tz-**naive** timestamps even when given a tz-aware (UTC) input - traced to
NeuralProphet normalizing timestamps to UTC internally then handing them back
tz-naive (undocumented behavior, confirmed live by comparing
`history_df.index.tz` going in vs. `result.index.tz` coming out). Caught by
actually curling the running dev API end-to-end and noticing the
`/forecast/Jetty/day` response's `timestamp` field was missing the `Z`
suffix that `/forecast/.../hour` and `/forecast/.../minute` both had - not
caught by unit tests alone until a regression test
(`test_predict_day_ahead_preserves_tz_awareness`) was added afterward. Fixed
by re-localizing to UTC in `predict_day_ahead()` when the input was tz-aware.

## Layout

```
src/nongfab_forecast/
  pv_conversion.py   fit_pv_conversion_model(), default_params_from_capacity(), predict_power_kw()
  metrics.py           rmse/mae/mbe/nrmse, picp/pinaw, evaluate_by_group() (hourly / k-step breakdowns)
  hour_ahead.py          LightGBM + Optuna, quantile models for PI; Random Forest; k-step bundle (HourAheadKStepModel)
  minute_ahead.py          hand-written CNN-LSTM (torch) + neuralforecast losses
  day_ahead.py               NeuralProphet, trend+seasonality+future regressors
  bias_correction.py           Ridge residual regressor cascade (hour-ahead + day-ahead)
  registry.py                 MLflow experiment logging, Model Registry versioning, A/B compare
  api.py                       dev-only FastAPI: POST /train-now/{zone}/{horizon}, GET /forecast/{zone}/{horizon}
tests/                pytest suite - synthetic data (see "Known gaps"), no live services needed
                      besides a local sqlite MLflow DB (auto-created)
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../libs/nongfab_common
pip install -e ../features
pip install -e ".[dev,api]"
pytest -v                # ~2 min - trains small real models (LightGBM/CNN-LSTM/NeuralProphet),
                          # not mocked

# interactive dev API:
uvicorn nongfab_forecast.api:app --reload --port 8002
# then open http://localhost:8002/docs, or:
curl -X POST http://localhost:8002/train-now/Jetty/hour
curl http://localhost:8002/forecast/Jetty/hour
```

Installing `neuralforecast`/`neuralprophet` pulls in PyTorch - use the CPU
wheel index if you don't need CUDA: `pip install torch --index-url
https://download.pytorch.org/whl/cpu` before `pip install -e ".[dev,api]"`.

## Verified live (2026-07-14)

- Full dev-API path exercised end-to-end for all three horizons: `POST
  /train-now/{zone}/{horizon}` → train on synthetic data → log to a real
  (sqlite-backed) MLflow registry → `GET /forecast/{zone}/{horizon}` → loads
  the registered model back out of MLflow → produces a forecast. Confirmed
  via curl against a running server, not just pytest's `TestClient`.
- Retraining bumps the MLflow registered model version (`model_version: 2`
  on a second `/train-now` call), and `/forecast` picks up the new version -
  the "versioning" half of "MLflow registry ... versioning, A/B compare".
  `registry.compare_versions()` covers the "A/B compare" half.
- 59 tests passing (`pytest -v`, ~2 min). `ruff check` clean.

## Reference: Songsiri, "An Introduction to Solar Energy Forecasting" (Chula/CUEE)

`http://jitkomut.eng.chula.ac.th/pdf/solarforecast_intro.pdf` (Jitkomut
Songsiri, Chula EE/Smart Grid Research Unit Center, "NIDA lecture" deck, read
2026-07-14; not vendored into this repo - it's a third-party course PDF, ~12MB,
cite the URL rather than committing the binary) - a course deck on solar
forecasting fundamentals. Cross-checked against this module's existing
design, not a from-scratch redesign prompt:

- **Horizon taxonomy matches**: the deck's "nowcasting" (5-60min, spinning
  reserve/demand response), "intra-day" (1-6h, load-following), "short-term"
  (1-3 days, planning/unit commitment) map directly onto this module's minute/
  hour/day-ahead - confirms the architecture doc's 3-horizon split isn't
  arbitrary, it's the standard framing.
- **Feature set matches** Module 3's existing `nongfab_features` output
  (lagged I/P, previous-day same-time value, T/RH, solar zenith angle,
  clear-sky irradiance, EMA of irradiance) almost field-for-field against the
  deck's "typical features" slide.
- **Loss function guidance matches**: "selecting the cost objective function:
  ℓ1 or ℓ2" for neural nets - same choice already exposed in `hour_ahead.py`
  (`loss="l1"|"l2"`) and `minute_ahead.py` (`loss="l1"|"huber"`).
- **Prediction-interval rationale matches**: "the lower bound tells us to
  reserve some other source of generation" - the same "สำรองกำลัง" (reserve
  capacity) rationale the architecture doc gives for PICP/PINAW, now with an
  independent source confirming it's standard practice, not a one-off requirement.

Concrete refinements the deck suggests that **aren't** implemented yet -
listed here as next-step candidates, not applied speculatively this round:

- **Parallel models by time-of-day**: the deck's CUEE example splits into
  sub-models per hour-of-day bucket (e.g. 6-9am, 9:30am-12pm, ...) since
  irradiance variance differs sharply by hour, using simpler/fewer features
  in low-variance early-morning/late-evening buckets. `hour_ahead.py`
  currently trains one LightGBM model across the whole day - Module 3's
  `filter_daytime()` + `evaluate_by_group()`'s hourly breakdown are already
  in place to support this split if/when real data shows it's worth the
  added complexity.
- **Bias-correction cascade**: a second model learns the residual error of a
  first (e.g. NWP-driven) model rather than predicting the target directly.
  Conceptually close to what `day_ahead.py` already does (NeuralProphet
  regresses on NWP's SSRD/T directly) but not a literal two-stage cascade -
  worth revisiting once Module 2 has enough real NWP-vs-actual history to
  measure whether a correction stage earns its complexity.
- **Baseline linear regression** as an explicit comparison point ("simplest
  model, typically used as a baseline") - not currently logged anywhere;
  `registry.compare_versions()` already supports comparing arbitrary logged
  models, so a trivial linear baseline could be logged alongside each
  horizon's real model once real data exists, to make "is the ML model
  actually earning its complexity" a checkable question instead of an assumption.

## Verified live (2026-07-15) - real-data feature layer

Seeded a real, file-backed `RealDataStore` with 3 days of real-shaped NWP
history + real future rows, then ran `training.train_now("GIS", "hour",
store=...)` and `training.train_now("GIS", "day", store=...)` followed by
`serving.get_latest_forecast("GIS", ..., store=...)` for both horizons - both
training and serving correctly reported `data_source="real"` (not the
synthetic fallback), and produced physically plausible predictions (e.g.
hour-ahead ~7.5kW for GIS at a low-irradiance hour). See `api/README.md`'s
own "Verified live" section for the fuller end-to-end version of this same
check (real S3 ingestion → this store → a real trained LightGBM model → a
real `/forecast/GIS/hour` response, 94/94 tests passing, `ruff check` clean).

**Found a real, pre-existing bug while investigating an unrelated test
failure**: `tests/test_api.py::test_hour_ahead_train_then_forecast_round_trip`
asserts `lower <= pred <= upper` on a live-served forecast, but
`serving.py`'s synthetic "current conditions" seeds (`hash((zone,
"hour-now")) % 1000`) use Python's built-in `hash()` on a string tuple -
which is **not deterministic across process runs** by default (`PYTHONHASHSEED`
is randomized per-process unless pinned). Combined with `hour_ahead.py`'s
point/lower/upper models being three independently-trained LightGBM models
with no cross-model consistency constraint, some `PYTHONHASHSEED` values
draw a synthetic "now" input where the point prediction falls outside its
own interval. Confirmed by running the *unmodified* pre-existing code
(`git stash`) under 5 different `PYTHONHASHSEED` values: passed at 1, 2, 4,
failed at 3, 5 - reproducible flakiness that predates this session's changes
and is unrelated to the real-data feature layer. **Fixed in the 2026-07-15
k-step round above** (`_predict_lgbm_hour_ahead()` now clips `pred` into
`[lower, upper]`) rather than left open - the k-step change made this same
gap 6x more exposed (one independently-trained trio per lead hour instead of
one total), so it stopped being safely ignorable.

## Verified (2026-07-15) - k-step / RF / bias-correction / adaptive retrain

No live network egress available in this sandbox for this round (unchanged
from the caveat in the section above), so this was verified against the
existing local test suite plus a standalone smoke script exercising the new
code paths end-to-end, not a fresh live curl:

- A standalone script simulated 15 real-shaped GFS cycles (issue times 6h
  apart, lead hours 1-6 each), trained all 6 k-step models via
  `real_data.real_hour_frame_kstep()` + `train_hour_ahead_model()`/
  `train_rf_hour_ahead_model()`, confirmed Random Forest wins on some leads
  and LightGBM on others (not a fixed winner - genuinely comparing per lead),
  and confirmed `predict_hour_ahead_kstep()` returns a DataFrame indexed
  exactly `[1, 2, 3, 4, 5, 6]`.
- Full test suite: **98 passed** (`pytest -v`, includes the `@pytest.mark.slow`
  train-then-forecast round trips for all three horizons against the new
  k-step/72h/bias-correction code paths). `ruff check` clean.
- `api/`'s own test suite (which imports and exercises this module through
  `ingestion_scheduler.py` and the production `/forecast` route): **99
  passed**, `ruff check` clean.

## Per-point algorithm + validation error exposed to serving (2026-07-16)

The user asked for the dashboard to visibly show the hour-ahead LightGBM-vs-
Random Forest auto-select actually switching per lead hour (not just claim it
in prose), plus a "model error" figure from the same per-lead competition
shown as a line on the chart.

Both were already computed during training (`training.py`'s
`_train_hour_ahead_kstep()` logs `lead{N}_lgbm_rmse`/`lead{N}_rf_rmse` to
MLflow) but never carried past training time. Wired through instead of
recomputed:

- `HourAheadKStepModel` gained `rmse_by_lead_hour: dict[int, float]` (the
  winning candidate's own held-out validation RMSE per lead) alongside the
  pre-existing `algorithm_by_lead_hour` - both now live on the pickled model
  object itself, not just in MLflow's metrics store, so serving.py can read
  them without an extra registry round trip per request.
- `predict_hour_ahead_kstep()` now returns `algorithm`/`error_rmse` columns
  alongside `pred`/`lower`/`upper`.
- `serving.ForecastPoint` gained `algorithm: str | None` and `error: float |
  None`. Hour-ahead points get real per-lead values; minute-ahead points get
  a fixed `"cnn_lstm"` (that horizon doesn't auto-select); day-ahead points
  get a fixed `"neuralprophet"`; the physics-only fallback leaves both `None`
  (no ML model ran, so there is no algorithm or validation error to report -
  see `FALLBACK_PI_HALF_WIDTH_PCT`'s own docstring for the same
  don't-invent-a-number spirit).
- Both API surfaces (`api/routes_forecast.py` and this module's own
  `api.py`) pass the two new fields straight through in `ForecastPointOut`.

Test coverage: `test_hour_ahead.py` gained 2 tests exercising
`predict_hour_ahead_kstep()`'s new columns directly (including the "not every
lead has a recorded RMSE" edge case); `test_serving.py`'s physics-baseline
test now also asserts `algorithm`/`error` stay `None`; `test_api.py`'s three
`@pytest.mark.slow` round-trip tests now assert the real values a live
train-then-forecast cycle produces (`algorithm in ("lightgbm",
"random_forest")` with `error >= 0` for hour-ahead; fixed `"cnn_lstm"`/
`"neuralprophet"` strings for minute/day).

## Real historical weather from PVGIS seeds Day-ahead training (2026-07-16)

The user's forecasting-optimization priority list ranked real plant
telemetry (Huawei FusionSolar) as the top blocker for several items, but
access is pending on credentials the user doesn't control yet. Rather than
sit idle, the user asked for a substitute *weather* source usable
immediately - explicitly ruling out anything that isn't genuinely
pullable on demand (a one-time CSV download, e.g. Kaggle, didn't qualify)
and anything that's real generation data from a *different* site (PVOutput/
NREL PVDAQ/Ausgrid were all considered and rejected for this specific
purpose - see `ingestion/pvgis/README.md`'s "Data source & ToS" for the
full reasoning: bias-correction/Sum-k-LSTM validation needs Nong Fab's own
measured output, which no other site's data can substitute for, real-time
or not).

PVGIS (EU JRC's public solar-resource API) passed both bars: free, no API
key, and - unlike `ingestion/nasa_power`, which was built blind - actually
**live-verified working** by the user running a one-off script in the
Railway deployment's own console (this dev sandbox's own egress can't reach
it either, same organization-policy block as everything else tried). See
`ingestion/pvgis/README.md` for the full data-source story and exactly what
was captured live vs. reconstructed from docs.

New `ingestion/pvgis` package backfills a full year of real ERA5-based
hourly irradiance/temperature for Nong Fab's own coordinates directly into
`local_store.py`'s shared `nwp_history` table (tagged `source="pvgis-era5"`)
via `api/ingestion_scheduler.py`'s new one-time `_backfill_pvgis()` seed (not
a continuous poll - PVGIS returns a whole already-published year in one
call). This module (`real_data.py`) needed **zero code changes** - its
Day-ahead builders (`real_day_frame`/`real_future_regressors`) already read
`nwp_history` regardless of which source populated it.

**Day-ahead only, not Intra-day - a deliberate scope decision, discussed
with the user before building, not an oversight.** Every PVGIS-sourced row
has `issue_time == valid_time` (PVGIS is historical reanalysis, not a
multi-lead forecast - see `pvgis_ingestion.schemas.PVGISHourlyPoint`'s own
docstring), so `real_hour_frame_kstep`'s `lead_hours = valid_time -
issue_time` filter never matches any of `HOUR_LEAD_HOURS` (1-6) for these
rows - they're structurally invisible to Intra-day k-step training. Two
options were weighed with the user (duplicate one reading across all 6
lead buckets vs. Day-ahead-only); duplicating was rejected as
methodologically weak (it would teach the k-step models nothing real about
how forecast skill degrades with lead time, since every lead would see
identical input) even though it's still a large realism upgrade over the
current synthetic generator (`_synthetic_hour_df` is pure `rng.uniform(0,
1000)` noise with no day/night structure at all). Intra-day still relies on
real GFS/NWP backfill (`ingestion/nwp`), which does carry genuine per-lead
structure, once/if that accumulates in a given deployment.

New `RealDataStore.count_nwp_rows_by_source(source)` (local_store.py) lets
the PVGIS backfill gate itself independently of however many rows GFS's own
backfill has already contributed to the same shared table, so it seeds
Day-ahead even when GFS/NWP backfill is thin or unreachable in a given
deployment (and doesn't re-seed on every restart once it has already run
once).

## Sum-k LSTM: a third competing candidate for Intra-day (2026-07-16)

The user's own reference material (course slides on probabilistic hour-ahead
irradiance forecasting) described a specific architecture - "Sum-k LSTM" -
that neither this module nor its priority-list notes had ever defined; the
user supplied the slides directly (four images: study sites, features, model
architecture, results) rather than have this built from a guess.

**Architecture** (`sum_k_lstm.py`): one shared "common model" `M_c` (an LSTM
- the slides' headlined/winning variant) processes only *lagged* regressors;
K independent small head networks `M_1..M_k`, one per forecast step, each
combine the shared representation with *that step's own future regressors*
to predict a prediction interval (not a bare point value); trained *jointly*,
one loss `L_total = Σ L_i(θ_c, θ_i)` across every head at once, not K
independently-trained models. Each head's loss (`qd_loss()`) balances
coverage (PICP) against interval width - a genuine Quality-Driven-style
(Pearce et al., 2018) objective, not plain point-accuracy error, matching
the slides' "loss = PICP + sum of large width".

**Adaptations from the literal slides** (discussed with the user before
building, not silent deviations - see `sum_k_lstm.py`'s own module
docstring for the full reasoning):
- K=6 steps at **1-hour** resolution (this project's own `HOUR_LEAD_HOURS`),
  not the slides' K=4 steps at 15-minute resolution.
- LSTM backbone only - the slides' alternative ANN backbone isn't built.
- "Auto-lagged regressors" = a length-K sequence of each lead-hour bucket's
  own `[power_lag1, cloud_index]` (this project's k-step data is bucketed by
  lead hour, not one continuous per-minute series the way the slides'
  dataset apparently was); "future regressors" per head =
  `[ssrd_w_m2, temp2m_c, clear_sky_ssrd_w_m2]`, matching the slides' I_nwp/
  T_nwp/I_clr roles. This required two new real features on *all three*
  candidates' shared input (`real_data.py`'s `real_hour_frame_kstep`/
  `current_hour_conditions_kstep`), not just Sum-k LSTM's:
  - `clear_sky_ssrd_w_m2` (I_clr) - clear-sky GHI at the *future* valid_time,
    via `nongfab_features.clearsky` - needs no forecast at all, since it's a
    deterministic function of solar geometry and time.
  - `cloud_index` (CI) - real Himawari-derived cloud index nearest the
    forecast's *issue* time (a lagged/exogenous regressor, not a future
    one), falling back to a documented neutral default when no fresh
    reading exists rather than blocking training.

**Integration** (per the user's own explicit decision): Sum-k LSTM competes
as a genuine third candidate in `training.py`'s existing per-lead-hour
auto-select, picked by the same held-out validation RMSE LightGBM/Random
Forest already use (not by its own PICP/width metrics, which are recorded as
extra `lead{N}_sum_k_rmse` metrics but don't drive selection) - keeps the
3-way comparison on one consistent, simple criterion. Trained *once* jointly
across all 6 leads' own training splits (aligned to a common row count via
`align_common_rows` - real per-lead series can differ in length, so this
truncates to the shortest lead's own row count, most-recent rows first);
LightGBM/Random Forest are unaffected and keep training on each lead's
*full* own series independently, since forcing Sum-k LSTM's alignment onto
them would shrink their data for no benefit of their own. A lead won by
Sum-k LSTM records `None` in `HourAheadKStepModel.models_by_lead_hour` (not
a duplicate model object) - the one shared `sum_k_model` field is read
instead, dispatched by `algorithm_by_lead_hour`. A Sum-k LSTM training
failure (e.g. too little aligned history) is logged and non-fatal - the
other two candidates still compete normally that training run.

**Not (yet) wired in this round, by explicit scope decision**: the "data
closest to Huawei" question (PVOutput.org/NREL PVDAQ/Ausgrid, considered and
set aside - see this file's PVGIS entry above and `ingestion/pvgis/
README.md`'s "Data source & ToS" for why real generation data from a
*different* site can't substitute for Nong Fab's own measured output) and
real bias-correction validation (item 3 of the user's priority list) both
still need Nong Fab's own telemetry (Huawei FusionSolar, access pending) -
building Sum-k LSTM's architecture didn't need to wait on either.

Verified end-to-end: `test_hour_ahead_train_then_forecast_round_trip`/
`test_hour_ahead_retrain_bumps_version` (both `@pytest.mark.slow`, real
training) confirm Sum-k LSTM trains successfully, wins some leads (observed
alternating with LightGBM/Random Forest across leads in a real run, not a
fixed winner), and survives a full MLflow/cloudpickle registry round-trip
(register -> load -> predict) with its torch modules intact. 8 new
`test_sum_k_lstm.py` unit tests plus 3 new `real_data.py` feature tests -
119 tests in the whole `forecast/` module now (was 107).

## Known gaps / next steps

- **No automatic retraining pipeline of its own** - `registry.log_run()` +
  `load_model()` give you versioning and A/B comparison; `api/`'s
  `ingestion_scheduler.py` now provides a real, adaptive retrain loop
  (`API_RETRAIN_INTERVAL_COLD_SECONDS`, default 1h, while real history is
  thin; `API_RETRAIN_INTERVAL_WARM_SECONDS`, default 6h, once it isn't - see
  the k-step section above) for the production deployment, but this module
  itself still has no scheduler - Prefect (cross-cutting, not started)
  remains the natural fit for a non-`api/`-hosted deploy path.
- **Hour-ahead's Optuna search space and NeuralProphet's epoch counts are
  deliberately small** in the dev API's `/train-now` (n_trials=5, epochs=15)
  to keep interactive verification fast - not tuned against real accuracy
  targets, which don't exist yet without real data.
- **`neuralprophet`/`pytorch_lightning` emit internal deprecation warnings**
  (pandas `.view()`/`DataFrameGroupBy.apply` FutureWarnings) during fit/
  predict - from those libraries' own internals, not this module's code;
  harmless today, worth revisiting on a future neuralprophet upgrade.
