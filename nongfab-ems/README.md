# Nong Fab Solar EMS

Energy Management System for the PTT LNG Nong Fab solar plant, Rayong
(~12.71°N, 101.15°E): forecasting (minute/hour/day-ahead), what-if simulation,
and a live dashboard. Built module by module; each module has its own README,
tests, and `.env.example`.

> Repo directory is `nongfab-ems/` (not `nongfab-solar-ems`) — it was created
> under this name in an earlier session before that name was specified.
> Not renamed yet pending confirmation (renaming touches git history/links).

## Status

| Module | Path | Status |
|---|---|---|
| Scaffold (folders, docker-compose, root config) | this repo | ✅ Step 1 done |
| Shared asset registry loader | `libs/nongfab_common/` | ✅ built, tested (Pydantic validation + `target_bbox()`) |
| Asset registry data | `config/assets.yaml` | ✅ real zone/equipment specs; all 3 zones (GIS, ISB, Jetty) refined to Google Maps survey-grade coordinates + per-corner ground elevation, equipment detail (module/optimizer/inverter) added from real Single Line Diagrams; Jetty flagged `simulated: true` (no panels installed yet, confirmed by satellite imagery - forecast/simulation modules should treat it as a permanent capacity projection, not real sensor history) (2026-07-14) |
| 1. Himawari cloud-observation ingestion | `ingestion/himawari/` | ✅ built, tested; tile bbox now sourced from `config/assets.yaml`; `sample_cloud_at(lat, lon, t)` added |
| 2. NCEP/NOAA NWP (GFS) ingestion | `ingestion/nwp/` | ✅ built, tested; NOMADS ToS/robots.txt checked and cleared (public domain, no robots.txt, official filter/subset API); fetches GFS 0.25° GRIB2 via NOMADS filter service, decodes with cfgrib/xarray, stores to `nwp_forecast` |
| 3. Feature store | `features/` | ✅ built, tested (clear-sky/solar position, lag/EMA/future-regressor features, curtailment/degradation QC, daytime filter, multi-step framing + chronological split); not yet wired to a real data source (Module 1 and 2 both lack accumulated history yet) |
| 4. Forecast engine (minute/hour/day-ahead) | `forecast/` | ✅ built, tested (minute-ahead CNN-LSTM/torch, hour-ahead LightGBM+Optuna, day-ahead NeuralProphet, PV conversion, RMSE/MAE/MBE/NRMSE+PICP/PINAW metrics, MLflow registry/versioning/A-B-compare, dev `/forecast/{zone}/{horizon}` endpoint); trains on synthetic data (Module 1/2 still lack accumulated history) |
| 5. Simulation engine | `simulation/` | ✅ built, tested, rechecked/upgraded (what-if scenarios incl. `compare_scenarios()` presets, scenario-uncertainty Monte Carlo, PVWatts-style loss model + DC/AC clipping, `pipeline.py` orchestration, dev `/simulate/{zone}` + `/simulate/{zone}/compare` endpoints, 66 tests); **no battery/BESS** (confirmed twice: fully on-grid, permanently out of scope); simulates on synthetic baseline (same data-accumulation caveat as Modules 3/4) |
| 6. Backend API | `api/` | ✅ built, tested, live-verified 3x (REST `/assets`, `/forecast/{zone}/{horizon}`, `/simulate/{zone}`, `/performance/{zone}`, `/geometry/{zone}`, `/sun-path/{zone}` + WebSocket `/ws/live`, OAuth2/JWT auth with RBAC admin/operator/viewer, CORS, auto OpenAPI docs, 72 tests); reuses Module 3/4/5's own serving/pipeline functions directly (no logic duplicated); **no battery/BESS**; read routes run on synthetic baseline data (same data-accumulation caveat as Modules 3/4/5) |
| 7. Dashboard | `web/` | 🟡 in progress - STEP 8 (Feature A, "CU Solar Forecast" style) + STEP 8B (Feature B+C, 3D shading/solar-access + sun-path sweep, react-three-fiber) done: zone selector, Day-ahead/Intra-day toggle, Recharts power chart, weather strip, KPI cards, JWT login, `/3d` 3D panel view (colored by solar access or string, compass readout, sun-path arc, date/time scrubber + auto-play), 38 tests, live-verified twice with a real headless browser (incl. software-WebGL rendering). STEP 8C (Energy Report + irradiance map) not started |
| Cross-cutting: docker-compose | `docker-compose.yml`, `infra/` | ✅ 7 services (timescaledb, minio, mlflow, api, web, prometheus, grafana); config validated (`docker compose config`), **not** live-tested (no Docker daemon available in the dev sandbox that built this) |
| Cross-cutting: CI, Prefect flows | `.github/` | ⏳ not started |

## Tech stack

- **Backend**: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), TimescaleDB
- **ML**: neuralforecast, lightgbm, neuralprophet, pvlib, xarray/cfgrib, optuna, mlflow
- **Ingestion**: httpx, tenacity, APScheduler; orchestration via Prefect
- **Frontend**: React 19 + TypeScript + Vite (Recharts + MapLibre + TanStack Query land with Module 7's real pages)
- **Infra**: Docker Compose (dev), Prometheus + Grafana, GitHub Actions CI

## Repo layout convention

Each module is a self-contained Python (or, for `web/`, Node) project with its
own `pyproject.toml`/`package.json`, `tests/`, and `README.md`, so it can be
developed, tested, and containerized independently. Shared SQL migrations live
in `db/migrations/`, applied in order against the shared TimescaleDB instance
(not auto-applied by `docker compose up` — see each module's README).

## Getting started

```bash
cp .env.example .env
docker compose config   # validates the compose file: services, env resolution, healthchecks
docker compose up       # not live-verified in the environment that built this - see caveat above
```

Or run a module standalone (works today, verified):

```bash
cd ingestion/himawari   # or api/, or web/
python3 -m venv .venv && source .venv/bin/activate   # skip for web/
pip install -e ".[dev]"                              # or `npm install` for web/
pytest -v                                             # or `npm run test` for web/
```

See `ingestion/himawari/README.md` for the full picture on Module 1,
including the known upstream TLS issue on the original Himawari data source
and how the module works around it (NOAA AWS Open Data instead), and the
cloud-tile/motion-vector/sampling design.

See `ingestion/nwp/README.md` for the full picture on Module 2, including the
NOMADS ToS/robots.txt check performed before writing any code, the GFS
variable-naming gotcha (GRIB `sdswrf` vs. the architecture doc's "SSRD"), and
a cfgrib coordinate-merge bug caught by decoding a real sample file during
development rather than assumed to work.

See `forecast/README.md` for the full picture on Module 4, including a
cross-check against Songsiri's "An Introduction to Solar Energy Forecasting"
(Chula/CUEE) reference deck - confirms this module's horizon taxonomy,
feature set, and loss-function choices against an independent academic
source, and lists concrete next-step candidates (time-of-day parallel
models, bias-correction cascades, an explicit linear baseline) it suggests
but that aren't implemented yet.

See `simulation/README.md` for the full picture on Module 5, including why
there's no battery/BESS sub-module (confirmed out of scope - the plant is
fully on-grid) and a real PV-conversion bug (nonzero power predicted at
midnight) caught by curling the live dev API rather than unit tests alone,
fixed in Module 4's `pv_conversion.py`.

See `api/README.md` for the full picture on Module 6 (auth/RBAC design,
per-route role table, WebSocket payload shape, known gaps) - including
another real bug caught by live verification rather than unit tests alone:
`/ws/live` was silently always reporting `0.0 kW` regardless of the actual
time of day, fixed and covered by a regression test.

See `web/README.md` for the full picture on Module 7's Feature A (data
model notes on the "All zones" aggregate and Day-ahead/Intra-day mapping) -
including two more real bugs live verification caught in Module 6's API
that no existing unit test had: a completely missing CORS policy (the
dashboard's requests never reached FastAPI at all), and then a second bug
in the first fix itself (a settings field name that didn't match the env
var its own docs promised), both now covered by regression tests.

See `web/README.md`'s STEP 8B section and `features/README.md`'s own
section on `panel_geometry.py`/`shading.py` for Feature B/C (the 3D
solar-access view + sun-path sweep): reuses Module 3's existing pvlib solar
position rather than duplicating it, models fixed-tilt row self-shading
analytically (documented as visualization-grade, not a bankable yield
calculation), and gives Jetty its own array azimuth default since its
~1.25km north-south trestle makes GIS/ISB's south-facing default
physically nonsensical there. Live verification (real headless Chromium
with software WebGL, since no unit test can render an actual WebGL canvas)
caught a real default-camera bug specific to Jetty's widely-spread real
sub-array layout, fixed and documented in `web/README.md`.
