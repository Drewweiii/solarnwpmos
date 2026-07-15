# Module 4 — Forecasting Engine (3 horizons)

Three horizon-specific forecasters (minute/hour/day-ahead), a linear PV
conversion model (irradiance/temperature → AC power), point + interval
evaluation metrics (RMSE/MAE/MBE/NRMSE, PICP/PINAW), an MLflow experiment/
registry layer, and a dev FastAPI wrapper exposing `GET /forecast/{zone}/{horizon}`.

## Horizons

| Horizon | Model | Input | Loss | Tuning |
|---|---|---|---|---|
| Minute-ahead | hand-written CNN-LSTM (torch) | cloud opacity/index sequence | Huber or L1 (`neuralforecast.losses.pytorch`) | Adam + early stopping |
| Hour-ahead | LightGBM | NWP + lag + clear-sky features | L2 (L1 selectable) | Optuna (Bayesian) + early stopping |
| Day-ahead | NeuralProphet | trend + seasonality + future regressors (SSRD, T) | MAE | quantile regression for PI |

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
  hour_ahead.py          LightGBM + Optuna, quantile models for PI
  minute_ahead.py          hand-written CNN-LSTM (torch) + neuralforecast losses
  day_ahead.py               NeuralProphet, trend+seasonality+future regressors
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
and is unrelated to the real-data feature layer. Not fixed this pass (out of
scope - a real fix means either pinning `PYTHONHASHSEED` in CI, seeding with
something deterministic instead of `hash()`, or enforcing point-within-
interval at the `predict_hour_ahead()` level); flagged here so it isn't
mistaken for a regression next time CI or a local run happens to hit it.

## Known gaps / next steps

- **No automatic retraining pipeline of its own** - `registry.log_run()` +
  `load_model()` give you versioning and A/B comparison; `api/`'s
  `ingestion_scheduler.py` now provides a real retrain loop (every
  `API_RETRAIN_INTERVAL_SECONDS`, default 6h) for the production deployment,
  but this module itself still has no scheduler - Prefect (cross-cutting,
  not started) remains the natural fit for a non-`api/`-hosted deploy path.
- **Hour-ahead's Optuna search space and NeuralProphet's epoch counts are
  deliberately small** in the dev API's `/train-now` (n_trials=5, epochs=15)
  to keep interactive verification fast - not tuned against real accuracy
  targets, which don't exist yet without real data.
- **`neuralprophet`/`pytorch_lightning` emit internal deprecation warnings**
  (pandas `.view()`/`DataFrameGroupBy.apply` FutureWarnings) during fit/
  predict - from those libraries' own internals, not this module's code;
  harmless today, worth revisiting on a future neuralprophet upgrade.
