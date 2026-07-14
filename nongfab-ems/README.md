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
| Asset registry (`config/assets.yaml`) | `config/` | ⏳ blocked — needs real zone/equipment specs, not yet provided |
| 1. Himawari cloud-observation ingestion | `ingestion/himawari/` | ✅ built, tested; ⚠️ bbox still hardcoded, not read from `config/assets.yaml` yet (blocked on the item above) |
| 2. NCEP/NOAA NWP (GFS) ingestion | `ingestion/nwp/` | ⏳ not started — blocked on explicit go-ahead to check NOMADS ToS/robots.txt |
| 3. Feature store | `features/` | ⏳ not started |
| 4. Forecast engine (minute/hour/day-ahead) | `forecast/` | ⏳ not started |
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
and how the module works around it (NOAA AWS Open Data instead), the
cloud-tile/motion-vector design, and its own current limitation (bbox not
yet driven by `config/assets.yaml`).
