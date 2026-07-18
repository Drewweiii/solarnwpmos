# Nong Fab Solar EMS

Energy Management System for the PTT LNG Nong Fab solar plant, Rayong
(~12.71°N, 101.15°E): forecasting (minute/hour/day-ahead), what-if simulation,
and a live dashboard. Built module by module; each module has its own README,
tests, and `.env.example`.

> Repo directory is `nongfab-ems/` (not `nongfab-solar-ems`) — it was created
> under this name in an earlier session before that name was specified.
> Not renamed yet pending confirmation (renaming touches git history/links).

## Live demo (STEP 11B)

Deployed and publicly reachable:

- **Dashboard**: https://solarnwpmos.zerosynasis.workers.dev — the `web/`
  SPA, hosted on Cloudflare Workers (static assets, SPA-fallback routing),
  auto-built from this branch on every push (see `web/wrangler.jsonc`,
  `web/.env.production`).
- **API**: https://api-production-f161c.up.railway.app — Module 6
  (`api/`), hosted on Railway from `api/Dockerfile`. **⚠ Does NOT
  auto-deploy on push** (as of 2026-07-16 - the GitHub source is connected
  in Railway's Settings → Source, root directory `nongfab-ems`, but the
  "Branch connected to production" panel shows "Auto deploy unavailable" /
  intermittently "Bad credentials"; Railway's own troubleshooting steps
  were exhausted without resolving it - see "Deployment notes" below).
  **After every push that touches `api/` or anything it depends on
  (`libs/`, `features/`, `forecast/`, `simulation/`, `ingestion/`), someone
  has to manually open the Railway dashboard → the `api` service →
  Deployments, and click the purple "Deploy" button** to actually put the
  new code live. The Cloudflare dashboard above needs no such step.

Demo accounts (seeded on startup — throwaway credentials, see
`api/src/nongfab_api/auth.py`): `admin`/`admin-demo-pw`,
`operator`/`operator-demo-pw`, `pttlng`/`12345` (viewer role — this is the
public login handed out to site visitors for the chat/feedback
visitor-network features).

Deployment notes:

- **Railway (API) has no working auto-deploy - manual "Deploy" click
  required after every push (2026-07-16).** The Railway service's GitHub
  source is connected (repo `Drewweiii/solarnwpmos`, branch
  `claude/solar-optimization-forecasting-jryux7`, root directory
  `nongfab-ems`, Dockerfile path resolved via the `RAILWAY_DOCKERFILE_PATH`
  variable to `api/Dockerfile`) and the GitHub Railway App has "All
  repositories" access with no pending permission requests - correctly
  configured by every check Railway's own docs list - but the service still
  shows "Auto deploy unavailable" (at one point "Bad credentials" after a
  full App uninstall/reinstall). Full troubleshooting was done live with the
  user: verified GitHub App access, verified the Railway account's GitHub
  connection, disconnected/reconnected the repo source multiple times,
  uninstalled and reinstalled the Railway GitHub App entirely - none of it
  fixed the auto-deploy trigger itself. **Workaround**: every deploy has to
  be triggered manually - Railway dashboard → `api` service → Deployments
  tab → the purple "Deploy" button (appears whenever there's a pending
  source change to apply). A real fix likely needs Railway support directly
  (this looks like a backend-side sync bug, not a misconfiguration - see
  https://docs.railway.com/deployments/github-autodeploys#troubleshooting
  for the checklist that was already exhausted).
- The API's auth store is an **ephemeral SQLite file** on the demo, not a
  separate Postgres service — the only thing the API persists is the demo
  accounts (re-seeded each boot); all forecast/simulation data is synthetic
  (same "no real accumulated history yet" caveat as every module). See
  `api/config.py`'s `create_tables_on_startup`. The docker-compose path
  still uses the shared TimescaleDB + `db/migrations`.
- The API image installs the full ML stack (torch/neuralforecast/
  neuralprophet/mlflow), so `/forecast/{zone}/{horizon}` returns 404 "not
  trained" on the demo (no models registered, no MLflow server) - the
  working demo surface is login, `/assets`, `/performance`,
  `/energy-report`, `/irradiance-map`, `/geometry`, `/sun-path`, and
  `/simulate` (operator+). A single-resolver-pass `pip install` in the
  Dockerfile is load-bearing: per-package sequential installs left an
  ABI-inconsistent numpy that crashed at import on first deploy (caught by
  the Railway runtime logs, fixed and re-verified by reproducing the exact
  install in a throwaway venv and importing `nongfab_api.main`).
- **(2026-07-18, corrected same day) `/ws/chat`'s private-messaging rework
  needed a schema patch for the same reason the bullet above already
  documents - production really is SQLite (`API_TIMESCALE_DSN =
  sqlite+aiosqlite:////data/app.db` on a Railway volume, confirmed live by
  reading the actual Railway variable), not Postgres. An earlier version of
  this note said to run a manual `psql` migration against Railway's
  Postgres service - wrong: that Postgres service exists in the project
  but nothing is actually connected to it (`chat_messages` doesn't exist
  there at all). Fixed properly instead - `main.py` now patches the
  missing `recipient_client_id` column into `chat_messages` automatically
  on startup (dialect-agnostic, so this also works if a deployment ever
  does move to real Postgres) - no manual DB step needed, just the usual
  manual Railway "Deploy" click above. See `api/README.md`'s matching
  dated entry for the full story.
- End-to-end verified through the live public URLs (frontend serves, the
  deployed bundle points at the Railway API, login returns a real JWT with
  correct CORS for the Cloudflare origin, every read route 200s, RBAC
  enforced). A headless-Chromium pass was blocked by this sandbox's egress
  proxy (`ERR_CONNECTION_RESET` to `*.workers.dev`), not by the app.

## Status

| Module | Path | Status |
|---|---|---|
| Scaffold (folders, docker-compose, root config) | this repo | ✅ Step 1 done |
| Shared asset registry loader | `libs/nongfab_common/` | ✅ built, tested (Pydantic validation + `target_bbox()`) |
| Asset registry data | `config/assets.yaml` | ✅ real zone/equipment specs; all 3 zones (GIS, ISB, Jetty) refined to Google Maps survey-grade coordinates + per-corner ground elevation, equipment detail (module/optimizer/inverter) added from real Single Line Diagrams; Jetty flagged `simulated: true` (no panels installed yet, confirmed by satellite imagery - forecast/simulation modules should treat it as a permanent capacity projection, not real sensor history) (2026-07-14) |
| 1. Himawari cloud-observation ingestion | `ingestion/himawari/` | ✅ built, tested; tile bbox now sourced from `config/assets.yaml`; `sample_cloud_at(lat, lon, t)` added; **(2026-07-15)** `fetch_at(anchor)`/`backfill.py` added for historical seeding, live-verified against real NOAA data (a 3-days-ago fetch and a real 9-slot backfill both succeeded) |
| 1b. NASA POWER UV index ingestion | `ingestion/nasa_power/` | ✅ **new (2026-07-15)** - daily UV index, added because neither Himawari nor GFS publish one and the user's model-input spec asked for it explicitly; built against NASA POWER's long-documented API shape but **not live-verified** - `power.larc.nasa.gov` is blocked by this dev sandbox's egress policy (unlike the S3-hosted Himawari/GFS sources); wrapped everywhere it's called so this can never take down the rest of ingestion if unreachable wherever this actually deploys either |
| 1c. PVGIS historical weather backfill | `ingestion/pvgis/` | ✅ **new (2026-07-16)** - one-time seed of a real year of ERA5-based hourly irradiance/temperature for Nong Fab's own coordinates, substituting for real plant telemetry (Huawei FusionSolar, access still pending) on the *weather* side while training - PVOutput/NREL PVDAQ/Ausgrid/Kaggle were all considered and rejected first (either not genuinely real-time-pullable, or real generation data from a *different* site that can't substitute for Nong Fab's own measured output); **live-verified working** (unlike NASA POWER above) - the user ran a one-off script in the Railway deployment's own console and got a real HTTP 200 with real data for the plant's coordinates, since this dev sandbox's own egress blocks `re.jrc.ec.europa.eu` too; feeds Day-ahead training only, not Intra-day (PVGIS is historical reanalysis, not a multi-lead forecast - a scope decision discussed with the user, not an oversight - see `forecast/README.md`'s matching dated entry) |
| 2. NCEP/NOAA NWP (GFS) ingestion | `ingestion/nwp/` | ✅ built, tested; NOMADS ToS/robots.txt checked and cleared (public domain, no robots.txt, official filter/subset API); fetches GFS 0.25° GRIB2 via NOMADS filter service, decodes with cfgrib/xarray, stores to `nwp_forecast`; **(2026-07-15)** `S3GfsBackfillDataSource`/`backfill.py` added for historical seeding via NOAA's AWS Open Data GFS mirror (reachable from this dev sandbox, unlike NOMADS) - caught and fixed a real bug live (field-matching only worked at forecast hour 1; GFS's flux-field step-type text is forecast-hour-dependent), re-verified across multiple forecast hours after the fix |
| 3. Feature store | `features/` | ✅ built, tested (clear-sky/solar position, lag/EMA/future-regressor features, curtailment/degradation QC, daytime filter, multi-step framing + chronological split); real ingested history now flows through Module 4's own `real_data.py` layer rather than through this module directly (see Module 4's row) |
| 4. Forecast engine (minute/hour/day-ahead) | `forecast/` | ✅ built, tested (minute-ahead CNN-LSTM/torch, hour-ahead LightGBM+Optuna, day-ahead NeuralProphet, PV conversion, RMSE/MAE/MBE/NRMSE+PICP/PINAW metrics, MLflow registry/versioning/A-B-compare, dev `/forecast/{zone}/{horizon}` endpoint); **(2026-07-15) now wired to real data** - `real_data.py` + `local_store.RealDataStore` (SQLite-backed, not TimescaleDB - see that file's docstring) build real training/serving frames from ingested NWP/cloud history once enough has accumulated, falling back to the original synthetic generators below that bar; every `power_kw` value is still the physics PV-conversion model applied to real weather, never a real measured target (no plant telemetry exists anywhere in this system - see that module's own docstring); a new `get_forecast_with_fallback()` never 404s, serving a physics-only baseline instead while real history is still thin |
| 5. Simulation engine | `simulation/` | ✅ built, tested, rechecked/upgraded (what-if scenarios incl. `compare_scenarios()` presets, scenario-uncertainty Monte Carlo, PVWatts-style loss model + DC/AC clipping, `pipeline.py` orchestration, dev `/simulate/{zone}` + `/simulate/{zone}/compare` endpoints, 71 tests); STEP 9 confirmed this module already covers everything its own brief asked for except battery dispatch, which stays out of scope (**no battery/BESS**, confirmed a third time: fully on-grid, permanently out of scope - see `web/README.md`'s STEP 9 section) - production `/simulate/{zone}` (Module 6) now has a real UI consumer, Module 7's `/simulation` Playground; simulates on synthetic baseline still (not yet wired to `real_data.py` - see api/README.md's "Known gaps"); **(2026-07-16)** `dev_data.synthetic_day_irradiance_temp()`'s day/night sine phase was wrong for Thailand (peaked at 12:00 UTC = 19:00 ICT, nighttime) - shifted to peak at 05:00 UTC (Thai noon), fixing every caller at once (`/performance`, `/simulate`, `/energy-report`, `/irradiance-map`, `/ws/live`); also added `live_efficiency_factor()`, a bounded [0.85, 1.0] real-time-varying multiplier so `/performance` doesn't return frozen numbers - see web/README.md's own dated section for the full story |
| 6. Backend API | `api/` | ✅ built, tested, live-verified 6x (REST `/assets`, `/forecast/{zone}/{horizon}`, `/simulate/{zone}`, `/performance/{zone}`, `/geometry/{zone}`, `/sun-path/{zone}`, `/energy-report/{zone}`, `/irradiance-map` + WebSocket `/ws/live`, OAuth2/JWT auth with RBAC admin/operator/viewer, CORS, auto OpenAPI docs, 102 tests); reuses Module 3/4/5's own serving/pipeline functions directly (no logic duplicated); **no battery/BESS**; **(2026-07-15)** `ingestion_scheduler.py` now runs real ingestion (Himawari/GFS/NASA POWER) + periodic retraining as in-process background tasks (no separate TimescaleDB/ingestion services exist in this deployment), live-verified end-to-end producing a real trained LightGBM forecast (`data_source: "real", model_type: "ml"`) from real S3-sourced weather data - `/forecast/{zone}/{horizon}` no longer 404s; `/simulate`/`/performance`/`/ws/live` still run on synthetic baseline data (not yet wired to the same real-data store); **(2026-07-16)** `/energy-report/{zone}` gained `avg_solar_access_pct`, a 12-month generation estimate (real pvlib solar geometry + a documented rainy-season derate), and a 25-year degradation projection - see `simulation/README.md`'s own section |
| 7. Dashboard | `web/` | ✅ STEP 8 (Feature A) + STEP 8B (Feature B+C, 3D shading/solar-access + sun-path sweep) + STEP 8C (Feature D+E, Energy Report + interactive SLD viewer + MapLibre irradiance map) + STEP 9 (Simulation Playground) all done, plus a full spec recheck (2026-07-15) that closed 5 more gaps: zone selector, Day-ahead/Intra-day toggle, Recharts power chart, weather strip, KPI cards + per-zone info panel (lat/lon/cloud factor), JWT login, `/3d` 3D panel view (+ string power-balance warning, + forecast-vs-actual readout tied to Feature A), `/energy-report` (system summary/annual/losses incl. temperature/CO2/interactive SLD), `/irradiance-map` (MapLibre grid overlay + zone pins with a full click-panel + zone boundary layer + time scrubber + layer toggles), `/simulation` (what-if scenario sliders + Monte Carlo interval + loss breakdown, driving Module 6's existing `/simulate/{zone}`), route-based code-splitting (Three.js/MapLibre lazy-loaded), 84 tests, live-verified 5x with a real headless browser (incl. software-WebGL/MapLibre rendering); **(2026-07-16)** `/energy-report` gained a monthly generation chart, sun-exposure card, and 25-year estimate section, and `/3d` gained real building/pier-deck volumes on a grid floor, a reslink.org-style icon rail and solar-access gauge, and an (unverified-live, egress-blocked from this sandbox) Esri World Imagery satellite ground texture, reslink.org used as the design reference throughout |
| Cross-cutting: docker-compose | `docker-compose.yml`, `infra/` | ✅ 7 services (timescaledb, minio, mlflow, api, web, prometheus, grafana); `api`'s build context fixed to the repo root so its Dockerfile can actually resolve its monorepo sibling dependencies (STEP 10, was broken - see "Cross-cutting" further-reading below); Grafana auto-provisions a Prometheus datasource + an 11-panel dashboard (`infra/grafana/`) on startup; config validated (`docker compose config`), **not** live-tested (no Docker daemon available in the dev sandbox that built this) |
| 8. Orchestration (Prefect flows) | `orchestration/` | ✅ STEP 10 built, tested (7 tests); flows wrapping Module 1/2's `IngestionJob.run_once()` and Module 4's `training.train_now()` (extracted from `forecast/`'s dev API so both share one implementation), plus a `full_pipeline_flow()` chaining ingestion -> retrain with per-step failure isolation |
| 11. Financial/Investment analysis | `financial/` | ✅ **new (2026-07-16)** - NPV/IRR/LCOE/simple+discounted payback over the 25-year design life, reusing `simulation.pipeline`'s own degradation model (no real telemetry needed - financial modeling works off a yield estimate); added after the user reframed project priorities: sub-daily/hour-ahead/day-ahead forecasting has little operational value at a fully grid-tied, no-battery, land-capped site, so investment payback is what actually matters here; every cost/tariff/rate assumption is a documented placeholder pending the user's real CAPEX/PEA-tariff/WACC/BOI figures (Thailand's 20% corporate tax rate is the one real fact used); 19 tests (`financial/`) + 7 tests (`api/`); `POST /financial` (operator+) and a new `/financial` investment-analysis playground page in `web/` - see `financial/README.md` |
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
  **(2026-07-15)** also gained a second, additive backfill path
  (`S3GfsBackfillDataSource`) against NOAA's AWS Open Data GFS mirror
  (`noaa-gfs-bdp-pds`) - same public-domain/no-credential/no-ToS-gate
  profile, registered at registry.opendata.aws.
- **Module 1b** (`ingestion/nasa_power`): NASA POWER's daily point API -
  public, free, no API key/registration, explicitly built for renewable-
  energy applications. Built against its long-stable documented shape;
  **not live-verified** (this dev sandbox's egress policy blocks
  `power.larc.nasa.gov` outright) - see that module's own README for the
  exact gap and how to close it.
- **Module 1c** (`ingestion/pvgis`): PVGIS `seriescalc` API (European
  Commission JRC) - public, free, no API key/registration. This dev
  sandbox's egress policy blocks `re.jrc.ec.europa.eu` outright too (same
  as every other external host tried, apparently a blanket organization
  policy), but **live-verified working** via the user's own Railway
  deployment console, which returned a genuine HTTP 200 with real hourly
  weather for Nong Fab's coordinates - see `ingestion/pvgis/README.md`'s
  "Data source & ToS" for the exact evidence.

None of these modules scrape HTML or bypass any access control; all are
documented open-data APIs. See each module's own README for the full
verification trail (what was checked, when, and the exact evidence).
