# Nong Fab Solar EMS

Energy Management System for the PTT LNG Nong Fab solar plant, Rayong
(~12.71°N, 101.15°E): forecasting (minute/hour/day-ahead), what-if simulation,
and a live dashboard. Built module by module; each module has its own README,
tests, and `.env.example`.

## Status

| Module | Path | Status |
|---|---|---|
| 1. Himawari cloud-observation ingestion | `ingestion/himawari/` | ✅ built, tested |
| 2. NCEP/NOAA NWP (GFS) ingestion | `ingestion/nwp/` | ⏳ not started |
| 3. Feature store | `features/` | ⏳ not started |
| 4. Forecast engine (minute/hour/day-ahead) | `forecast/` | ⏳ not started |
| 5. Simulation engine | `simulation/` | ⏳ not started |
| 6. Backend API | `api/` | ⏳ not started |
| 7. Dashboard | `web/` | ⏳ not started |
| Cross-cutting (docker-compose, CI, monitoring) | `infra/`, `.github/` | ⏳ not started |

## Tech stack

- **Backend**: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), TimescaleDB
- **ML**: neuralforecast, lightgbm, neuralprophet, pvlib, xarray/cfgrib, optuna, mlflow
- **Ingestion**: httpx, tenacity, APScheduler; orchestration via Prefect
- **Frontend**: React 18 + TypeScript + Vite + Recharts + MapLibre + TanStack Query
- **Infra**: Docker Compose (dev), Prometheus + Grafana, GitHub Actions CI

## Repo layout convention

Each module is a self-contained Python (or, for `web/`, Node) project with its
own `pyproject.toml`/`package.json`, `tests/`, and `README.md`, so it can be
developed, tested, and containerized independently. Shared SQL migrations live
in `db/migrations/`, applied in order against the shared TimescaleDB instance.

## Getting started (Module 1 only, for now)

```bash
cd ingestion/himawari
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

See `ingestion/himawari/README.md` for the full picture, including a
known upstream TLS issue on the Himawari data source and how the module
works around it for now (mock data source, real adapter scaffolded).
