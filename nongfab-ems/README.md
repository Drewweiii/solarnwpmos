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
| 5. Simulation engine | `simulation/` | ⏳ not started |
| 6. Backend API | `api/` | ✅ Step 1 scaffold only (`/healthz`); real endpoints not started |
| 7. Dashboard | `web/` | ✅ Step 1 scaffold only (default Vite template); real pages not started |
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
