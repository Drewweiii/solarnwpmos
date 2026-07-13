# Claude Code — Bootstrapping the Nong Fab EMS

Run these in your terminal with **Claude Code** installed (`npm install -g @anthropic-ai/claude-code`,
Node.js 18+). Drop the four generated reference files (`ARCHITECTURE.md`, `db_models.py`,
`schemas.py`, `forecast_router.py`, `ingestion_providers.py`) into the repo root first so Claude
Code uses them as the source of truth.

```bash
# 0. Create + enter project, seed context
mkdir nongfab-ems && cd nongfab-ems && git init
mkdir -p _seed
#   copy the generated files into _seed/ so Claude Code can read them:
#   ARCHITECTURE.md db_models.py schemas.py forecast_router.py ingestion_providers.py
```

```bash
# 1. Scaffold the whole tree from the architecture doc
claude "Read _seed/ARCHITECTURE.md as the authoritative spec. Create the full directory \
structure exactly as in section 2 (backend/, frontend/, data-pipeline/, docker/, config/). \
Create empty stub files with a one-line docstring/comment describing each file's role. \
Do not write real logic yet — structure only."
```

```bash
# 2. Backend foundation (DB + schemas + router from the seed files)
claude "Move _seed/db_models.py to backend/app/db/models.py, _seed/schemas.py to \
backend/app/schemas/forecast.py, and _seed/forecast_router.py to \
backend/app/api/v1/forecast.py. Then create backend/app/db/base.py with an async SQLAlchemy \
engine + session factory (asyncpg + TimescaleDB), and backend/app/main.py as a FastAPI app \
factory with CORS, a lifespan that opens/closes the DB pool, and includes the forecast router. \
Add config/plant.yaml seeded with the SLD values from ARCHITECTURE.md section 0 (ISB 140.14kWp/150kW, \
GIS 60.06kWp/50kW) and pydantic-settings in config/settings.py."
```

```bash
# 3. TimescaleDB migration + hypertables
claude "Add Alembic to the backend. Generate the initial migration for models.py, and in the \
same migration run raw SQL to create hypertables on telemetry(time), weather_forecast(valid_time), \
solar_prediction(target_time), plus a 15-minute continuous aggregate and a 90-day compression policy."
```

```bash
# 4. ML layer skeletons
claude "Create backend/app/ml/{registry,minute_ahead,hour_ahead,day_ahead,conversion,intervals}.py. \
registry.py caches loaded models by (name, site). conversion.py implements clip_aware_power(irradiance, \
beta1, beta0, inverter_ac_kw) = min(beta1*I+beta0, inverter_ac_kw). intervals.py has quantile + \
conformal PI helpers. Wire hour_ahead.py to LightGBM quantile regressors and day_ahead.py to \
NeuralProphet with future regressors. Leave clear TODOs where trained artifacts load."
```

```bash
# 5. ETL pipeline (Celery + providers)
claude "Move _seed/ingestion_providers.py to data-pipeline/providers.py. Create data-pipeline/ \
worker.py (Celery app on Redis) and tasks.py with beat schedule: himawari every 10 min, gfs every \
6 h, telemetry mock every 1 min. Each task fetches via the provider and upserts into TimescaleDB \
through the backend's async session. Default satellite provider = HimawariAwsProvider (noaa-himawari9), \
NWP = GfsNomadsProvider with OpenMeteoProvider fallback."
```

```bash
# 6. Frontend — Next.js dashboard + 3D sim
claude "Scaffold frontend/ with Next.js 14 (App Router, TypeScript, Tailwind). Build \
components/charts/NetLoadChart.tsx (Recharts stacked area: gross load, solar with p10-p90 shaded \
band, GTG output), components/map/GisHeatmap.tsx (Leaflet + irradiance overlay + time slider over \
Nong Fab), and the (dashboard) route wiring them to GET /api/v1/forecast. Add a zero-export guard \
banner driven by reserve.zero_export_risk."
```

```bash
# 7. 3D mobile simulation
claude "Create components/three/SolarScene.tsx with React Three Fiber: low-poly LNG terminal, PV \
arrays colored green→yellow→red by real-time yield, a sun-path light computed from Nong Fab \
coords + time, and dynamic shadow casting. Mobile-first touch controls via camera-controls. Add \
components/three/SldEditor.tsx to group panels into strings and export a downloadable SVG single-line \
diagram."
```

```bash
# 8. Docker + compose
claude "Create docker/docker-compose.yml with services: timescaledb, redis, backend (uvicorn), \
worker (celery), frontend (next). Multi-stage docker/Dockerfile.backend (python:3.11-slim) and \
docker/Dockerfile.frontend (node:20-alpine). Add a Makefile with up/down/migrate/seed targets."
```

```bash
# 9. Bring it up
docker compose -f docker/docker-compose.yml up -d --build
make migrate && make seed
# backend  → http://localhost:8000/docs
# frontend → http://localhost:3000
```

## Notes before production
- Replace the `600kW`/`20MW GTG` placeholders in `config/plant.yaml` with confirmed values.
- Confirm data-source licensing (NOAA open data = safe; JAXA P-Tree commercial from 2026-02-01).
- Swap `TelemetryMockProvider` for the real SCADA/Modbus/inverter tap.
- Add auth (the EMS touches dispatch signals) before any non-local deployment.
