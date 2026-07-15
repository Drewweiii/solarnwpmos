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
| 5. Simulation engine | `simulation/` | ✅ built, tested, rechecked/upgraded (what-if scenarios incl. `compare_scenarios()` presets, scenario-uncertainty Monte Carlo, PVWatts-style loss model + DC/AC clipping, `pipeline.py` orchestration, dev `/simulate/{zone}` + `/simulate/{zone}/compare` endpoints, 71 tests); STEP 9 confirmed this module already covers everything its own brief asked for except battery dispatch, which stays out of scope (**no battery/BESS**, confirmed a third time: fully on-grid, permanently out of scope - see `web/README.md`'s STEP 9 section) - production `/simulate/{zone}` (Module 6) now has a real UI consumer, Module 7's `/simulation` Playground; simulates on synthetic baseline (same data-accumulation caveat as Modules 3/4) |
| 6. Backend API | `api/` | ✅ built, tested, live-verified 5x (REST `/assets`, `/forecast/{zone}/{horizon}`, `/simulate/{zone}`, `/performance/{zone}`, `/geometry/{zone}`, `/sun-path/{zone}`, `/energy-report/{zone}`, `/irradiance-map` + WebSocket `/ws/live`, OAuth2/JWT auth with RBAC admin/operator/viewer, CORS, auto OpenAPI docs, 94 tests); reuses Module 3/4/5's own serving/pipeline functions directly (no logic duplicated); **no battery/BESS**; read routes run on synthetic baseline data (same data-accumulation caveat as Modules 3/4/5) |
| 7. Dashboard | `web/` | ✅ STEP 8 (Feature A) + STEP 8B (Feature B+C, 3D shading/solar-access + sun-path sweep) + STEP 8C (Feature D+E, Energy Report + interactive SLD viewer + MapLibre irradiance map) + STEP 9 (Simulation Playground) all done, plus a full spec recheck (2026-07-15) that closed 5 more gaps: zone selector, Day-ahead/Intra-day toggle, Recharts power chart, weather strip, KPI cards + per-zone info panel (lat/lon/cloud factor), JWT login, `/3d` 3D panel view (+ string power-balance warning, + forecast-vs-actual readout tied to Feature A), `/energy-report` (system summary/annual/losses incl. temperature/CO2/interactive SLD), `/irradiance-map` (MapLibre grid overlay + zone pins with a full click-panel + zone boundary layer + time scrubber + layer toggles), `/simulation` (what-if scenario sliders + Monte Carlo interval + loss breakdown, driving Module 6's existing `/simulate/{zone}`), route-based code-splitting (Three.js/MapLibre lazy-loaded), 72 tests, live-verified 5x with a real headless browser (incl. software-WebGL/MapLibre rendering) |
| Cross-cutting: docker-compose | `docker-compose.yml`, `infra/` | ✅ 7 services (timescaledb, minio, mlflow, api, web, prometheus, grafana); `api`'s build context fixed to the repo root so its Dockerfile can actually resolve its monorepo sibling dependencies (STEP 10, was broken - see "Cross-cutting" further-reading below); Grafana auto-provisions a Prometheus datasource + an 11-panel dashboard (`infra/grafana/`) on startup; config validated (`docker compose config`), **not** live-tested (no Docker daemon available in the dev sandbox that built this) |
| 8. Orchestration (Prefect flows) | `orchestration/` | ✅ STEP 10 built, tested (7 tests); flows wrapping Module 1/2's `IngestionJob.run_once()` and Module 4's `training.train_now()` (extracted from `forecast/`'s dev API so both share one implementation), plus a `full_pipeline_flow()` chaining ingestion -> retrain with per-step failure isolation |
| Cross-cutting: CI | `.github/workflows/ci.yml` | ✅ STEP 10 built: one lint+test job per Python module (ruff + pytest, editable-installed in dependency order) + web lint/test/build + `docker compose config` validation + a real `docker build` of `api/`'s (now-fixed) Dockerfile |

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

See `web/README.md`'s STEP 8C section and `features/README.md`'s "SLD
topology & irradiance grid" section for Feature D/E (the Energy Report +
interactive SLD viewer, and the MapLibre irradiance map): the SLD is
generated from each zone's own real equipment counts rather than a scanned
PDF, annual generation figures are an explicitly-flagged flat extrapolation
of one synthetic day (no accumulated history exists yet), and the
irradiance map's cloud factor is a documented synthetic placeholder pending
a live Himawari raster store. Live verification caught two real frontend
bugs, both around the time-scrubber's query-cache behavior remounting the
WebGL/MapLibre canvas on every tick (discarding camera state, and for the
irradiance map, silently resetting layer-toggle state) - fixed with
`placeholderData: keepPreviousData` plus a `layersReady` guard, documented
in `web/README.md`.

A full recheck against the original Feature A-E spec (2026-07-15) found 7
gaps: 2 genuinely out of scope pending real data (external obstacle
shading needs a real survey; a "real As-Built SLD"/live Himawari cloud
tile needs files/infrastructure this repo doesn't have) - documented as
known gaps, not faked - and 5 addressable now, all closed and re-verified
live: a string power-balance flag (`features/README.md`'s
`string_power_balance()`, surfaced as a warning banner on `/3d`, Jetty
only - GIS/ISB's layout has no real per-string rows to flag); per-zone
lat/lon + cloud factor on `/forecast`; a full zone-click info panel + a
"zone boundary" map layer on `/irradiance-map`; and a Feature C <-> Feature
A integration (`/3d`'s sun-path scrub now shows the nearest forecast point
and nearest actual/generated point to the scrubbed time, not just a
standalone 3D scene). See `api/README.md`'s "Verified live a fifth time"
and `web/README.md`'s matching section for the full detail.

See `orchestration/README.md` for the full picture on STEP 10's Prefect
piece: flows wrapping Module 1/2's `IngestionJob.run_once()` and Module 4's
`training.train_now()` (newly extracted from `forecast/`'s dev API so both
share one implementation instead of two copies that could drift), a
`full_pipeline_flow()` that chains ingestion -> retrain with per-zone/
per-horizon failure isolation, and a real packaging bug it caught along the
way: installing a sibling package non-editably into a venv shared with
another module silently broke that other module's `config/assets.yaml`
path resolution (10 previously-passing `forecast/` tests started failing) -
fixed, and now guarded against in `orchestration/tests/conftest.py`.

STEP 10 also fixed a real, previously-undetected bug in `api/Dockerfile`:
it only ever `COPY`'d `api/`'s own files, but `api/pyproject.toml` depends
on four sibling monorepo packages that were never in that build context, so
the image could never have actually built. Fixed by moving the build
context to the repo root (`docker-compose.yml`) and copying each sibling in
dependency order; verified (since no Docker daemon exists in this dev
sandbox to actually run `docker build`) by replicating the exact same
install order in a throwaway venv and confirming pip never needed to reach
PyPI for any of the four bare `nongfab-*` package names - see
`api/README.md`'s STEP 10 section.

Building the GitHub Actions workflow (`.github/workflows/ci.yml`) surfaced
one more real gap along the way: `ingestion/himawari`'s `tests/test_api.py`
imports `fastapi`, but `fastapi` only lived in that module's `api` extra,
not its `dev` extra - the documented `pip install -e ".[dev]"` workflow
never actually installed it, so this had silently been relying on
`fastapi` already being present in whatever venv ran it. Fixed by adding
`fastapi` to the `dev` extra directly; caught by simulating each CI job's
exact install command in a fresh venv before trusting the workflow file.

## Compliance

Every module that fetches data from an external source checks that
source's terms of service / `robots.txt` **before** writing any fetch code,
not after:

- **Module 1** (`ingestion/himawari`): the original Himawari data source
  had a TLS/reachability issue, so this module fetches from NOAA's AWS Open
  Data bucket instead - public domain, no auth, no posted rate limit; a
  conservative client-side rate limit is still applied. See
  `ingestion/himawari/README.md`'s "Data source" section.
- **Module 2** (`ingestion/nwp`): fetches GFS forecasts via NOAA NOMADS's
  official filter/subset API - `robots.txt` returns a plain 404 (no rules
  either way) and NOMADS's own `info.php` documents and endorses this exact
  endpoint. See `ingestion/nwp/README.md`'s "Data source & ToS" section.

Neither module scrapes HTML or bypasses any access control; both are
documented open-data APIs. See each module's own README for the full
verification trail (what was checked, when, and the exact evidence).
