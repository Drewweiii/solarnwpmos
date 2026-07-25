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

### 2026-07-25 - Soiling & Cleaning Advisor, replacing the soiling placeholder (Track 1)

Innovation A of four the user picked this round. `/energy-report` gained a
Soiling & Cleaning Advisor panel, and - per the user's explicit decision
("แทนค่า placeholder เลย") - the soiling figure the whole system derates by is
no longer a literature constant.

**Why this and not more forecasting**: the plant is fully grid-tied with no
battery, so the operationally actionable question isn't "what will output be at
15:00" but "is the glass costing us money, and when should it be washed". Every
input needed was already being ingested and unused for this.

**Model** (`features/src/nongfab_features/soiling_dynamics.py`, pure + 11 tests):
a Kimber-style accumulate-and-wash time series with a data-driven rate.
- Kimber et al. (2007): soiling grows ~linearly through a dry spell; rain above
  a threshold restores the array. That shape is why soiling is a *series*, not a
  derate.
- Coello & Boyle (2019, IEEE J. Photovoltaics) is why the rate isn't constant:
  daily soiling scales with ambient PM10, exactly what the CAMS ingestion stores
  hourly. Plus a marine salt term (this site's documented worse driver) scaled by
  the existing `salt_soiling_index`, and a small coarse-dust term.
- Rain cleaning is graded between 0.25 mm (Kimber's threshold - drizzle cleans
  nothing) and 5 mm (a complete wash), leaving a documented residue: rain never
  returns the glass to a perfect 0%.
- Saturates at 12%: a coated panel loses little more per extra gram, and a
  tropical rain-washed array never gets there anyway.

**Data path** (`api/soiling_service.py`): hourly stores rolled up to daily -
mean PM10/dust, mean salt index (derived from wind+humidity exactly as the
forecast features do, so the two can't disagree), and **summed** rainfall,
because a day's cleaning power is its total not its mean. Hours duplicated
across issue times are collapsed first so a heavily-reforecast hour can't
inflate the day's rain. Jetty takes the full sea-spray load (it sits on the
trestle over the water); GIS/ISB are set back inland, a documented exposure
allowance on the same footing as `DEFAULT_EXTERNAL_SHADING_PCT`.

**The replacement**: `refresh_measured_soiling` publishes each zone's window
average into `loss_model.set_measured_soiling_pct`, and `default_loss_factors`
prefers it over `DEFAULT_SOILING_PCT_LAND/MARINE`. That flows straight into the
Energy Report losses breakdown, `/financial` NPV/IRR/LCOE and `/simulate`.
Refreshed on the aerosol poll's own cadence (its inputs change hourly) and once
after startup backfill, never per-request - it walks 90 days per zone.

Honesty, kept explicit everywhere: the rate COEFFICIENTS are literature-
calibrated, not fitted to Nong Fab (no on-site soiling measurement or cleaning
log exists - that stays a known gap). Everything they multiply is this site's own
measurement. So `LossFactors` now carries `soiling_source`
(`measured-airquality-rainfall` vs `literature-default`), `/energy-report`
surfaces it, and the panel states which one is live. With no history the route
returns `available: false` + a Thai reason and the literature default stays in
force - it never invents a soiling level.

**Panel** (`SoilingAdvisorPanel.tsx`): headline recommendation (turns amber once
a wash is due), four KPIs (current loss %, %/day accumulation, days since the
last cleaning rain - "unknown", never 0, when none fell in the window - and the
฿/year the current dirt costs, priced at the facility's own implied tariff from
its real cost/load rather than the financial module's placeholder PEA rate), and
a 90-day sawtooth chart of accumulation against rain washes with the cleaning
trigger marked.

Tests: features +11, api +15 (roll-up, honest-empty, wet-vs-dry window, marine
vs inland, the placeholder replacement + its labelling, route auth/404/empty/
populated), web +6. tsc + ruff + oxlint clean; api 118 downstream tests
(energy-report/financial/simulate/simulation) still pass unchanged.

### 2026-07-25 - Forecast Verification & Skill Score (Track 1)

Innovation B of four. Until now every accuracy number on the site came from
TRAINING: `rmse_by_lead_hour` and `candidate_errors` are hold-out errors measured
while fitting a model. That answers "how well did this model fit its training
data", not "how good have the forecasts this system actually issued turned out to
be" - which is the question solar-forecasting work is judged on.

New `GET /forecast/{zone}/verification?days=N` scores the second one, from
history the app already keeps: hour-ahead issuances (`forecast_history`, horizon
`hour`) against the recorded actual output (same table, horizon `generated`).

`forecast/src/nongfab_forecast/verification.py` (pure, 17 tests):
- MAE / RMSE / MBE, plus RMSE normalized by the zone's AC capacity so the three
  zones are comparable. MBE's sign is reported explicitly because a
  systematically optimistic forecast is a different problem from a noisy one.
- **Skill score against persistence** ("output in k hours = output now"), the
  baseline the literature expects a model to beat: `1 - RMSE_model /
  RMSE_persistence`. > 0 = the model genuinely adds information, 0 = no better
  than assuming nothing changes, < 0 = worse than doing nothing. The model's RMSE
  in that ratio is measured over exactly the pairs persistence could also be
  scored on - mixing subsets would make the ratio meaningless.
- Lead time per row is recovered from `target_time - issued_at`, via a new
  `RealDataStore.forecast_history_issuances`.

Three honesty constraints, each unit-tested:
1. **Daylight filtering.** Night hours are trivially correct (everyone predicts
   zero) and would drag every metric toward zero error, so the headline is
   daylight-only - but a pair where only ONE side is zero is kept, because
   "predicted 40 kW, got nothing" is exactly the miss verification exists to
   catch. All-hours figures are shown beside the daylight ones rather than hidden.
2. **No invented pairs.** A forecast hour with no recorded actual is skipped;
   persistence is left `null` where its reference hour is missing; an empty
   window returns `n=0`, never a fabricated score. The route distinguishes "no
   history" from "both sides exist but no overlapping hours".
3. **The lead-time caveat is stated in the response.** `forecast_history` keys on
   (zone, horizon, target_time), so only each hour's freshest issuance survives -
   deliberately, since a forecast issued closer to its target is the better one to
   serve back. The lead breakdown therefore covers whichever issuance each hour
   last had, NOT a full lead-time matrix, and `lead_time_note` says so on screen.

Routing note: the router is registered **before** `routes_forecast`, whose
catch-all `/forecast/{zone}/{horizon}` would otherwise match
`/forecast/{zone}/verification` and 404 it as an unknown horizon.

`ForecastVerificationPanel` on /forecast: the skill score as an oversized
colour-coded headline (green beating persistence, red worse than doing nothing),
a metrics table (daylight vs all hours), an RMSE-by-lead bar chart, and a plain-
Thai "how to read this" note including the explicit statement that these are not
training errors. Its CSS lives in ForecastPage.css, not EnergyReportPage.css -
that page is lazy-loaded, so borrowing its `.ems-panel` classes would have left
the panel unstyled.

Tests: forecast +17, api +6, web +5 (454 total). ruff/tsc/oxlint clean.

### 2026-07-25 - System Health & Anomalies + a correction to the Verification panel (Track 1)

Innovation C, scoped by the user to **C1** after a finding that changed what was
buildable.

**The finding (and the correction it forced).** C was originally "compare actual
vs expected output and flag underperformance". This site has **no metered
generation at all** - `real_data.pv_params_for_zone` states it outright, and the
inverter portal is permanently closed (see forecast/README). The "Actual power"
series on the site is `record_generated_power`: this system's own physics model
evaluated on real weather. So an actual-vs-expected detector would compare a model
against itself - always zero, and any non-zero result an artifact. The user chose
C1 (feed health + seasonal anomalies) instead, and confirmed there is no route to
real meter data.

That same finding forced a correction to the Verification panel shipped hours
earlier: its caption said the figures were "the real result once the hour
arrived", which overstates them. The comparison side is the physics estimate on
verified weather, so the metric is NWP forecast error propagated through physics -
genuinely useful, but not accuracy against a meter. Fixed in the panel, the route
docstring, and a new `reference_note` field carried in every response so no
consumer can read it the wrong way.

**1. Data feed health** (`GET /diagnostics/feeds`). When an external source
silently stops, the model keeps answering - it just falls back to defaults, with
nothing on screen saying so. That is exactly how the CAMS aerosol feed broke
earlier the same day. The key design point (`forecast/health.py`, pure, 10 tests)
is that feeds come in two shapes and conflating them misreports both:
- **observation** feeds (satellite cloud, UV) are healthy while their NEWEST row
  is recent;
- **coverage** feeds (NWP, aerosol - forecasts that legitimately extend into the
  future) are healthy while their newest row still reaches FORWARD of now. A
  coverage feed that is merely "recent" has already run out of the window the
  model's leads need - the aerosol bug's exact signature, and now a `stale`
  verdict with an explicit "ครอบคลุมล่วงหน้าไม่พอ" reason.
Limits come from each source's own publish + poll cadence with one missed tick of
slack; `uv_history` is keyed by date, so its freshness is measured from the end of
its newest day rather than reading as 18 hours stale by evening.

**2. Seasonal output anomalies** (`GET /diagnostics/{zone}/anomalies`). Days whose
expected energy fell below 70% of that month's own norm (from the same seasonal
monthly estimates the Energy Report chart uses, so the two can't disagree), newest
first. The today-in-progress day is dropped, or its partial total would look like
a dramatic shortfall on every call. Causes are **ranked, not asserted**: whichever
measured driver (cloud / rain / soiling / aerosol) deviated most from its own
window median, each scaled onto a comparable 0..1 footing, and `unknown` when
nothing was measured that day rather than blaming the nearest candidate. A driver
*better* than median is never blamed. Every response carries `basis_note` saying
both sides are model estimates and this is not a claim that the array itself
underperformed.

`DataHealthPanel` on /forecast: overall status pill, a per-feed table with the
status colour carried on the row (so a dead feed is findable by scanning), and the
flagged-days table with its ranked cause. Feed health is the one diagnostic that
polls briskly - a stale reading of staleness is useless.

Tests: forecast +10, api +6, web +5 (459 total). ruff/tsc/oxlint clean.

### 2026-07-25 - Expansion Planner: what each planned phase actually buys (Track 1)

Innovation D of four, and the one that puts the whole plant in perspective.

config/assets.yaml already recorded the real planned phases (Jetty phase 1.5 =
+100 kW AC, phase 2 = +300 kW, note: "target total 600kW AC") and nothing on the
site answered the question they raise. The framing that matters: **400 kW AC
against a terminal drawing 13.5 MW covers about 0.5% of its own electricity**, and
even the 800 kW end state of the planned phases only reaches ~1%. That is not an
argument against the phases - it is the context any expansion decision needs, and
it was nowhere on the site before.

`financial/src/nongfab_financial/expansion.py` (pure, 12 tests) builds cumulative
scenarios with a **marginal column**, because that is the number a decision turns
on: a phase's total looks impressive next to nothing, while its yield per added
kWp is what says whether it is as good a deal as what came before. Also
`capacity_for_target_offset`, which prices out what a *meaningful* offset would
actually take - 10% of this facility's demand needs ~8.5 MWp, an order of
magnitude beyond the planned end state.

`GET /expansion` assembles it from real figures: today's three zones' capacities
and their seasonal annual energy, assets.yaml's own future_phases, the user's real
13.5 MW load, and the facility's **own implied tariff** (real annual cost / real
annual consumption ≈ ฿2.54/kWh) rather than the financial module's placeholder PEA
rate.

Two limits stated in the response and repeated on screen rather than buried:
- CAPEX is still the documented ฿30,000/kWp placeholder, so
  `simple_payback_years` inherits it (`capex_note`). Everything else -
  capacity, energy, offset, bill saving - comes from real figures.
- Each phase's energy is scaled proportionally from today's array (same site,
  latitude, tilt and module family), not simulated from a new layout - phase 2
  has no layout yet (`method_note`).

`ExpansionPlannerPanel` on /energy-report: the scenario table with its marginal
columns, an offset-by-scenario bar chart, and the "what would a real offset take"
table. Its CSS duplicates the verification-table rules rather than importing
ForecastPage.css, since only one page's stylesheet is loaded at a time.

Tests: financial +12, api +5, web +5 (464 total). ruff/tsc/oxlint clean.

### 2026-07-25 - Editable system values, part 1: the backend (Track 1)

The user asked for the system's numbers to be changeable from the web UI instead
of living in code and YAML, and picked **all eight groups** on offer: site &
facility figures, financial assumptions, loss factors, the soiling model's
coefficients, look-back windows, diagnostic thresholds, hand-control sensitivity
and the expansion plan. Persistence model, also their choice: **anyone can try
values in their own browser; only an admin publishes a shared default.**

This commit is the backend half. The UI is the next one - so nothing user-visible
changes yet, but every value below is already settable through the API and
verifiably takes effect.

**The design that makes eight groups affordable.**
`api/settings_registry.py` declares each editable value as DATA - key, group,
Thai label, unit, default, min/max/step - so the API describes itself and ONE
generic form can render all of it later. Adding a setting is one entry in that
file, not a route plus a screen. 46 settings today.

Every setting is numeric, deliberately: it covers all eight groups while keeping
validation to "a number inside these bounds", with no free text or structured
objects to sanitize. It is also why the expansion PHASES are three "additional
kW" numbers rather than an editable list - same expressive power for this plan,
none of the list-editing complexity (and 0 turns a phase off).

**`origin` - the honesty field, and the one that earns its keep.** Some defaults
are figures the user confirmed (the 13.5 MW load, the ฿300M/yr bill); some are
as-built values from the SLD; some are documented placeholders never verified for
this project (CAPEX ฿30,000/kWp); some are literature-calibrated coefficients;
some are pure interface taste. The API returns which, per field, so nobody edits
a confirmed figure thinking it is a guess or trusts a guess as a measurement.

**Storage** (`system_settings`, via `SystemSettingORM` + `settings_store.py`):
only OVERRIDES are stored. A setting at its default has no row, which is what
makes "reset" a plain DELETE and keeps the registry the single source of truth for
what a default is. It lives in the app database rather than the ephemeral
`RealDataStore` because an override is a decision somebody made and has to
outlive the container - with `updated_by`/`updated_at`, since these numbers move
money and physics figures site-wide. A stored key that this build's registry
doesn't know is ignored, not deleted: a key can vanish because a deploy rolled
back, and destroying somebody's saved figure in that window is the worse failure.

**Making them actually take effect** - two paths, and the distinction is the
point:
- *Read per request.* Windows, diagnostic thresholds, expansion phases/targets
  and the financial assumptions are read where they are used. `/financial`'s
  sliders still win per request (it stays a what-if playground), but an untouched
  request now answers with the published assumptions.
- *Injected*, for pure packages that can't reach a database from synchronous
  physics code - the same pattern `set_measured_soiling_pct` established.
  `nongfab_common.assets` gained `set_asset_overrides` (merged in BEFORE
  validation, so an override can't smuggle past the schema; `load_assets`
  re-reads YAML per call, so there is no cache to invalidate) and
  `loss_model` gained `set_loss_overrides`. `apply_effective_settings` also
  clears `annual_shading_loss_pct`'s lru_cache - it is computed from tilt, so a
  tilt edit would otherwise keep returning the pre-edit answer for the life of
  the process.

`soiling_dynamics` needed its coefficients settable without becoming globally
mutable: they moved into a `SoilingParams` dataclass passed explicitly per call.
The module keeps its constants as the defaults, and features/ stays free of
global state that two callers could change under each other.

`GET /settings` is viewer-level; `PUT /settings`, `DELETE /settings/{key}` and
`POST /settings/reset` are admin-only. A submission is validated in FULL before
anything is written, so one bad field rejects the whole form rather than saving
half of it.

Tests: api +23, covering the registry's own invariants (every default inside its
own bounds, unique keys, bounds/NaN/bool rejection), the permission split, whole-
form rejection, per-key and global reset, survival across a restart - and, the
part that matters, that a published value changes what the API answers: loss
factors reach `default_loss_factors`, a site figure reaches every `load_assets`
consumer, a zone capacity moves the expansion baseline, phases can be turned off
or added, CAPEX halves the payback, a window changes the default look-back, and a
feed limit changes the diagnostics verdict. api 280 / simulation 90 / features
102 / financial 31 all pass; ruff clean.

### 2026-07-25 - Editable system values, part 4: tariffs, carbon, and the emission factor nobody should decide silently (Track 1)

Continuing the other account's round. Their EGAT commit ended with a finding they
deliberately did **not** act on: กกพ's own UGT criteria document puts Thailand's
Grid Emission Factor at **0.4758 tCO2/MWh** (and ~0.407 for 2565), while
`green_savings.py` hardcodes **0.4999** (TGO). That number multiplies straight
into the avoided-CO2, tree-equivalent and carbon-credit figures published on the
Energy Report, so changing it moves numbers the user shows other people. Their
call, not ours - and correctly left alone.

This commit resolves the *mechanism* without touching the *decision*: the whole
Savings/Green group becomes editable through the settings system from part 1,
with **every default byte-identical to what shipped before**. Nothing published
moves until somebody deliberately publishes a new value.

Seven new settings under `green.*` (registry now 73 settings / 9 groups): the
normal PEA rate (฿4.1025/kWh), the UGT1 premium (฿0.0375/kWh), the UGT2 rate
(฿4.0423/kWh), the emission factor, carbon-credit units per
kWp-year (0.901), trees per kWp-year (101), and the carbon price
(฿100/tonne). The emission factor's `note` names **both** official figures and
their sources, so whoever edits it is choosing between two real published values
rather than typing a number they half-remember - which is the honest way to
present a conflict you are not entitled to settle.

UGT1 stays **derived** (`normal + premium`) rather than becoming its own field.
It is defined as a premium over the normal tariff, and two independently editable
numbers could be set to a combination that contradicts that definition.

`green_savings.py` gained a `GreenAssumptions` frozen dataclass +
`DEFAULT_ASSUMPTIONS`, threaded as an explicit `params` argument through
`compute_metrics()` and `assumptions()` - the same "no global mutable state in a
pure package" pattern `SoilingParams` established, so the module still computes
the same answer for the same inputs regardless of what any database says.
`routes_savings.py` resolves the effective values **once per request** and passes
that one object to every zone row and the combined row, so a mid-request publish
can't produce a report whose rows disagree with each other.

Tests: api +4 - that the emission-factor default is the published choice and its
note names both sources, that publishing an emission factor really moves the avoided CO2, that
publishing a tariff moves the bill saving while UGT1 stays derived from it, and
that a carbon price moves the credit value. Full regression: api 303 / forecast
190 / features+financial 133 / simulation 90 / web 491 all pass; ruff clean.

**Decided, same day:** asked which GEF to publish - TGO 0.4999, กกพ 0.4758, or
~0.407 for 2565 - the user chose **กกพ's 0.4758**, so that is now the shipped
default in `green_savings.py` and the registry (it lowers every published
avoided-CO2, tree-equivalent and carbon-credit figure by ~4.8%). The reasoning
is worth recording: the UGT1 and UGT2 tariffs on this same page already come
from that กกพ document, so taking the emission factor from it too keeps one page
sourced to one document instead of mixing two agencies' numbers in a single
table. The note still names TGO's 0.4999 and the ~0.407 for 2565, so the choice
stays visible rather than looking like the only figure that ever existed.

### 2026-07-25 - Hour-of-day grid carbon: what our solar actually displaces (Track 1)

**The question a flat emission factor cannot answer.** The Energy Report values
every avoided kWh at one annual number (กกพ's 0.4758). That is the right
reporting convention and physically wrong in an interesting way: at 02:00 the
Thai system runs on its cheapest baseload plant, and at 14:00 - exactly when
this array produces - it runs that baseload PLUS whatever more expensive, dirtier
unit was needed for the extra demand. So: does solar here displace clean
electricity or dirty electricity?

**What the data actually allows.** Thailand does not publish real-time
generation by fuel type. EPPO and กฟผ. publish it monthly, in reports, after the
fact - checked before building anything, and the user chose the honest hybrid:
real published levels, modelled hourly shape. `api/grid_carbon.py` therefore
states its own provenance line by line, and so does the API response:

  - REAL - the load curve (EGAT SysGen, per-minute, measured, Thai).
  - REAL - the published GEF the model is *forced* to reproduce.
  - CITED - per-fuel factors, IPCC AR5 WG3 Annex III lifecycle medians.
  - MODEL - which fuel is marginal at a given load (merit-order stack).
  - PLACEHOLDER - the fuel-mix shares themselves, pending EPPO's table.

**The method.** Stack the fuels cheapest-first as horizontal bands under the
day's load-duration curve, each band sized so its AREA equals that fuel's share
of the day's energy (bisection - the area is piecewise-linear in the band edge,
so there is no closed form). At any instant the load sits in exactly one band:
that fuel is MARGINAL - it would back off if this array made one more kWh.
Everything below is the mix actually running, whose weighted factor is the
AVERAGE intensity. Both are returned; conflating them is the classic error.

**The guardrail that makes it publishable.** `calibrate()` scales the whole
curve so its load-weighted mean equals the published GEF exactly. This page can
therefore only *redistribute* the official number across the day - it can never
quietly assert a different national carbon figure than the Energy Report does.
Four tests pin that invariant, including one that keeps it true after an admin
publishes a completely different fuel mix.

**What the model says for Thailand, which is not what I expected.** Thai demand
never falls far enough overnight for the gas fleet to leave the margin - the
trough is about two-thirds of the peak and gas alone is ~60% of generation - so
**natural gas comes out marginal at every hour of the day**. The marginal curve
is nearly flat. That looks like a bug and is the finding: every solar kWh here
displaces gas at ~0.49 kgCO2eq/kWh rather than the 0.4758 grid average, so the
flat annual factor slightly **understates** this array. The average curve does
still vary, because more of the gas band is in use at the peak. A test asserts
this explicitly rather than treating a flat line as a failure, and a second test
proves the mechanism does switch fuels when a mix has a peaker above gas.

New `gridmix.*` settings group (registry now 79 settings / 10 groups) holds the
six shares as percentages, defaulting to the placeholder and labelled
`placeholder` in the API and on screen until somebody enters real figures - at
which point the label flips to `published` on its own. Shares need not sum to
100: a published table that rounds to 99.8 is usable as-is.

Frontend `GridCarbonPanel` on /forecast: the published factor next to the one
this array earns, the percentage gap, the marginal fuel by name, and a chart
overlaying both intensity curves on the site's own hourly output - plus a
standing on-screen warning while the mix is a placeholder, and a collapsible
"what is measured, what is modelled" block.

The site profile weighting the average is CLEAR-SKY, from the same pvlib solar
position the monthly estimates use - this site still has no generation meter, so
that limitation is stated on the panel rather than papered over.

Tests: api +20, web +7. api 323 / web 498 pass; ruff clean; `npm run build`
clean.

**Open, and genuinely blocking better numbers:** EPPO's monthly
generation-by-fuel table. Everything else in this feature is real.

### 2026-07-25 - The fuel mix is no longer a placeholder: EPPO's real 2566 split (Track 1)

Went looking for the data the previous entry said was blocking, and found it.
Thailand's whole-system generation for 2566/2023, from สำนักงานนโยบายและแผนพลังงาน
(EPPO), 219,540.04 GWh total:

| fuel | GWh | share |
|---|---|---|
| natural gas | 128,678.77 | 58.61% |
| imported (mostly Lao hydro) | 32,805.15 | 14.94% |
| coal / lignite | 28,758.06 | 13.10% |
| renewables | 22,867.18 | 10.42% |
| hydro (domestic) | 6,421.04 | 2.92% |
| oil | 9.85 | 0.01% |

Shipped as the defaults because the GWh column **reconciles to the stated total
exactly** and two independent searches returned the same breakdown - that is
what separates a usable published figure from a plausible-looking one. Origin
moves `placeholder` -> `literature`, and the API's label moves `placeholder` ->
`annual`.

**The trap avoided.** EGAT publishes a second, similar-looking fuel table - "in
EGAT's system" - where imports are ~1% rather than ~15%, because it covers only
plant EGAT itself runs. Stacking that against a NATIONAL load curve would push
about 14% of clean imported hydro out of the merit order entirely. A test pins
imports above 10% specifically to stop a future edit from swapping in the wrong
table.

**Still caveated, just differently.** These are real figures at the wrong time
resolution: an annual average, when Thai hydrology and gas availability both
move seasonally. The panel now says exactly that instead of "this is a guess",
and the origin flips to `published` the moment somebody enters a monthly table.

**A consequence worth recording.** With the real mix, oil's 0.01% share becomes
a band ~80 MW wide at the top of a 36 GW stack, so the daily peak now reads as
oil-marginal where the old round-numbers mix said gas all day. Applying an
ANNUAL share to a SINGLE day implies oil runs a sliver every day, when really it
runs on a handful of peak days a year - so that label over-attributes on a
typical day. Kept, because it is the model's only representation of a peaking
unit and it barely moves the intensity; documented, because it is not exactly
right. The earlier "gas is marginal at every hour" claim is now "gas for
essentially the whole day", which is what the tests assert.

api 326 / web 498 pass; ruff clean; `npm run build` clean.

Sources: [EPPO electricity statistics](https://www.eppo.go.th/index.php/en/en-energystatistics/electricity-statistic) ·
[DEDE PV status 1.1](https://pvstatus.dede.go.th/th/section_1-1.php) ·
[EGAT fuel-usage share](https://www.egat.co.th/home/en/statistics-fuel-usage/) (the EGAT-system table, deliberately NOT used)

### 2026-07-25 - BOI is confirmed: 8 years general area, 12 for the Jetty (Track 1)

Went looking for the three outstanding financial figures. Found market
references for all three, brought them to the user rather than adopting them,
and the answers split:

- **CAPEX and WACC stay as they are.** Thai C&I solar runs ~฿20,000-25,000/kWp
  for systems under 1 MWp and IRENA's 2024 global utility-scale average is
  ~USD 691/kW (≈฿23,500); PTT PCL's WACC is estimated by third parties at
  ~6.8%. The user chose to keep ฿30,000/kWp and 8% rather than publish numbers
  that are not this project's own - reasonable, since the references are either
  vendor marketing, a global average, or an outside estimate of the parent
  company rather than a project hurdle rate. Worth knowing that ฿30,000 sits
  ABOVE current Thai market rates, so the payback the site shows is probably
  pessimistic. Both stay `origin=placeholder`.
- **BOI is a real answer.** The project holds BOI promotion: **8 years** of
  corporate income tax exemption in the general areas (GIS, ISB) and **12 years**
  for the Jetty. Both wired in as `origin=confirmed`, replacing the
  conservative 0 that had been standing in since the module was written.

The Jetty's longer holiday is why this is two settings rather than one. It only
bites once a phase including the Jetty is analysed - /financial covers the two
installed general-area zones today - but the figure belongs in the system now,
while it is known, not later when somebody has to go ask again.

Selectable, as the user asked: the /financial slider now reaches 15 years and
has one-click **8 ปี — พื้นที่ทั่วไป** / **12 ปี — Jetty** presets beside it, so
the real split is one click away instead of a number the reader has to
remember. The page's own caveat paragraph was rewritten to match - tariff and
BOI are now confirmed, CAPEX and WACC are what remain estimated.

Tests: api +3 - the two defaults and their `confirmed` origin, that the pure
`financial` package's own default agrees with the registry (two sources of truth
for a tax holiday is how a report and a playground end up disagreeing about
payback), and that 12 years really does produce a better NPV than 8. api 329 /
web 498 / financial 31 pass; ruff clean.

CLAUDE.md's standing Financial reminder was rewritten: it had been chasing four
figures, three of which are now real. Only CAPEX and WACC remain, and the note
records that market benchmarks were already offered and declined so a future
session does not re-propose them.

### 2026-07-25 - Panel degradation is the installed module's own warranty now (Track 1)

Auditing what is still an estimate turned up a value the code had already
flagged against itself. `pipeline.py`'s comment on
`DEFAULT_DEGRADATION_PCT_PER_YEAR = 0.55` said outright that it was a generic
0.4-0.7%/yr industry range and "not a Trina Vertex N-specific measured value
(config/assets.yaml doesn't carry one)".

But assets.yaml does name the part: **Trina Vertex N TSM-NEG21C.20**, N-type
i-TOPCon, 715 W. Trina publishes a warranty for exactly that module - **1% in
year 1, then 0.40%/year, 87.4% guaranteed at year 30** on a 30-year LINEAR power
warranty.

Those three figures check each other, which is what makes them usable rather
than merely quoted: **100 − 1 − (0.4 × 29) = 87.4** exactly. Two independent
searches returned the same terms (Trina's own datasheet and ENF both 403 the
fetcher, so the corroboration is across search results rather than the PDF).

**"Linear" is the part that made this drop straight in.** `apply_scenario` and
`degradation_factor` were already linear rather than compounding, so the model's
shape and the warranty's shape agree - no conversion, no silent change of
method. Had the model been compounding, adopting these numbers would have meant
changing the maths as well as the constants, which is a much bigger claim.

The first-year 1% is modelled separately (`degradation_first_year_pct`) rather
than folded into the annual rate, because light-induced degradation is a real
one-off, not a rounding of the annual figure. Together:

    factor(y) = 1 − first/100 − (annual/100) × (y − 1)

which gives 99.00% at year 1, 89.40% at year 25 and 87.40% at year 30 - the
warranted number, reproduced rather than approximated.

Direction of the change: 0.55%/yr flat gave 86.8% at year 25 against the
warranted 89.40%, so the old figure was **pessimistic** about this array. The
published payback improves slightly, and now matches the contract the modules
actually carry.

Tests: financial +2 - the year-30 figure pinned against the datasheet (it is the
one that proves the other two), and that the first-year term genuinely reaches
the cash flow rather than sitting unused on the dataclass. api 360 / financial 74
/ simulation 90 / web 538 pass; ruff clean; build clean.

Sources: [Trina Vertex N TSM-NEG21C.20 datasheet](https://static.trinasolar.com/sites/default/files/Datasheet_NEG21C.20.pdf) ·
[ENF panel directory entry](https://www.enfsolar.com/pv/panel-datasheet/crystalline/69962)
