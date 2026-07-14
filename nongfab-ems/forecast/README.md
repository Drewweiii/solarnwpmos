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

## Known gaps / next steps

- **Not wired to real data** - same caveat as Module 3: Module 1/2 haven't
  accumulated enough real history yet, so every model here trains against
  synthetic data shaped like the real thing (same generators the test suite
  and the dev API's `/train-now` both use). A thin loader (query
  TimescaleDB/Module 3's feature functions → the DataFrame shapes these
  models expect) is the natural next step once that history exists, not a
  redesign of this module.
- **No automatic retraining pipeline** - `registry.log_run()` + `load_model()`
  give you versioning and A/B comparison, but nothing schedules retraining
  yet (no natural trigger exists without real data volume to watch); likely
  Prefect (cross-cutting, not started) once there's something to react to.
- **Hour-ahead's Optuna search space and NeuralProphet's epoch counts are
  deliberately small** in the dev API's `/train-now` (n_trials=5, epochs=15)
  to keep interactive verification fast - not tuned against real accuracy
  targets, which don't exist yet without real data.
- **`neuralprophet`/`pytorch_lightning` emit internal deprecation warnings**
  (pandas `.view()`/`DataFrameGroupBy.apply` FutureWarnings) during fit/
  predict - from those libraries' own internals, not this module's code;
  harmless today, worth revisiting on a future neuralprophet upgrade.
