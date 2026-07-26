# Module 6 — Backend API

FastAPI production API: REST (`/assets`, `/forecast/{zone}/{horizon}`,
`/simulate/{zone}`, `/performance/{zone}`) + WebSocket (`/ws/live`) + OAuth2/
JWT auth with RBAC (admin/operator/viewer) + auto-generated OpenAPI docs
(`/docs`, `/openapi.json`).

**No battery/BESS, anywhere** - same as every other module (confirmed
2026-07-14, fully on-grid). Nothing in this API exposes charge/discharge/SoC.

This module doesn't reimplement Module 4's forecasting or Module 5's
simulation logic - it calls straight into `nongfab_forecast.serving.
get_latest_forecast()` and `nongfab_simulation.pipeline.
simulate_zone_baseline()` / `what_if` / `monte_carlo`, the same functions
those modules' own dev APIs call. Behavior can't drift between "the dev API
I tested" and "the production API a client actually hits".

## Real-data background ingestion (`ingestion_scheduler.py`)

Added to close this repo's biggest standing gap: **no model was ever
actually trained on real data, and nothing ever ran ingestion continuously**
(see forecast/README.md's now-resolved "not wired to real data" entry, and
this module's own former "Known gaps" text below, kept as history in git).
`/forecast/{zone}/{horizon}` used to 404 "not trained yet" on every fresh
deploy - a public dashboard visitor saw a permanent error, not a forecast.

The production deployment (Railway) hosts only this one API container - no
separate ingestion services, no persistent TimescaleDB (Module 1/2's own
`storage.py` needs real Postgres for `pg_insert`'s `ON CONFLICT`, which
isn't provisioned here). Rather than requiring new infrastructure this
session had no credentials to provision, `ingestion_scheduler.py` runs real
ingestion **inside this API process** as plain `asyncio` background tasks
(no new scheduler dependency - APScheduler is already used by the
standalone `ingestion/*` modules for their own separate-deploy path, but a
handful of sleep loops didn't need it here), writing into
`nongfab_forecast.local_store.RealDataStore` - a SQLite-backed store with
the same ephemeral-per-container durability as the already-accepted
`mlflow.db` pattern, not TimescaleDB (see `forecast/README.md`'s "Real-data
feature layer" section for the full store design).

On startup (`main.py`'s `lifespan`, gated by `Settings.
enable_background_ingestion`, **on by default** - the `settings` test
fixture explicitly turns it off so the suite stays hermetic/fast):

1. **One-shot backfill** (`run_startup_backfill`): NWP via
   `ingestion.nwp.backfill` (real GFS data from NOAA's AWS Open Data mirror
   - reachable from more environments than the NOMADS filter service this
   dev sandbox's egress policy blocks outright, see `ingestion/nwp/
   README.md`'s "Backfill" section) and Himawari cloud data via `ingestion.
   himawari.backfill`, both for `Settings.backfill_lookback_days` (default
   30). NASA POWER UV backfill is attempted too, but wrapped so its known
   unreachability from this dev sandbox (`ingestion/nasa_power/README.md`'s
   "Data source & ToS") can never take down the rest of ingestion - a bare
   `except Exception` around just that one call, logged and skipped.
   Skipped entirely (not re-run) if the store already has a reasonable
   amount of data, so a redeploy with a persistent store (`API_REAL_DATA_DB_
   PATH` pointed at a real volume) doesn't re-backfill from scratch on every
   restart. **(2026-07-16)** `_backfill_pvgis()` also seeds one full year of
   real historical weather (irradiance/temperature) from PVGIS for Nong
   Fab's own coordinates - gated on its own `pvgis-era5`-tagged row count
   (`RealDataStore.count_nwp_rows_by_source`), independent of the GFS/NWP
   gate above, so it seeds Day-ahead training even when GFS backfill is thin
   or unreachable. Day-ahead only, not Intra-day - see `ingestion/pvgis/
   README.md` and `forecast/README.md`'s matching dated entry for why.
   **(2026-07-18)** `_backfill_forecast_history()` now runs *first*, ahead
   of NWP/Himawari/PVGIS - it's a pure local computation (no HTTP calls),
   so a freshly-booted process seeds the dashboard's Forecast/Prediction-
   interval history within seconds instead of sitting blocked behind
   however long the network-dependent steps above take to succeed or fail.
   See `forecast/README.md`'s "Forecast history persistence" entry for the
   full story (including the live-tested sequencing bug this fixes).
2. **Continuous live polling**: Himawari every `API_HIMAWARI_POLL_INTERVAL_
   SECONDS` (default 600s, matching its native 10-min product cadence), GFS
   every `API_NWP_POLL_INTERVAL_SECONDS` (default 3600s - GFS only
   publishes every 6h, hourly is already generous) across
   `API_NWP_POLL_FORECAST_HOURS` (default: hourly out to 24h, 3-hourly 27-48h,
   6-hourly 54-72h - `config._default_nwp_poll_forecast_hours()` - dense
   enough near-term for hour-ahead's k-step models, reaching the full 72h
   day-ahead window at the far end without polling every hour out that far).
   Each Himawari frame also gets a real cloud motion vector
   (`_frame_with_motion()`, FFT phase correlation via `himawari_ingestion.
   motion.estimate_cloud_motion()`) computed against the previous frame -
   feeds `real_data.py`'s `motion_u_kmh`/`motion_v_kmh` minute-ahead features
   (see forecast/README.md's k-step section) - applied in both this live loop
   and the one-shot backfill above, so cold-start history gets motion too,
   not just frames ingested after this deployed.
3. **Periodic retraining, adaptive cadence**: after each retrain pass over
   all 3 zones x 3 horizons (`nongfab_forecast.training.train_now(zone,
   horizon, store)` via `asyncio.to_thread` - LightGBM/Random Forest/
   NeuralProphet/torch training is synchronous and CPU-bound, must not block
   the event loop), sleeps `API_RETRAIN_INTERVAL_COLD_SECONDS` (default
   3600s/1h) if the store's real `nwp_history` row count is still below
   `API_RETRAIN_WARM_THRESHOLD_ROWS` (default 500), else
   `API_RETRAIN_INTERVAL_WARM_SECONDS` (default 21600s/6h, one retrain per
   real GFS cycle) - re-checked every cycle, not decided once at startup, so
   a deployment that starts cold and accumulates real data live speeds up
   its own learning early on, then settles down once more retraining
   wouldn't meaningfully change the model. `train_now()` itself already
   prefers real data over synthetic once enough has accumulated (see
   forecast/README.md) - this loop just calls it on a schedule.

Every network/training call is wrapped so one failure never crashes the
loop or the app - logged and retried next tick, not propagated.

`/forecast/{zone}/{horizon}` now calls `nongfab_forecast.serving.
get_forecast_with_fallback()` (not the raw `get_latest_forecast()`) with
this process's shared `RealDataStore` (`request.app.state.real_data_store`)
- **never 404s "not trained yet" anymore**: while too little real history
has accumulated to train an ML model, it serves a real-weather physics
baseline instead (pvlib clear-sky x live cloud attenuation x the zone's PV
model), tagged `model_type: "physics_baseline"` in the response
(`ForecastResponse` gained `data_source`/`model_type` fields) so a client
can tell it apart from an actual ML forecast rather than it being silently
ambiguous. See `forecast/README.md`'s "Real-data feature layer" section for
`get_forecast_with_fallback()` itself.

## CORS

The dashboard (Module 7, `web/`) always runs on a different origin than this
API (its own Vite dev server port, or its own domain in production), so
`CORSMiddleware` is required - without it the browser blocks every request
before it reaches FastAPI at all (not a 401; the request never arrives).
Allowed origins come from `API_CORS_ORIGINS` (comma-separated, default
`http://localhost:5173,http://localhost:3000`) - override it with the
dashboard's real origin(s) in any deployment where `web/` isn't served from
one of the defaults. See `Settings.cors_origins` / `cors_allow_origins` in
`config.py`.

## Auth

OAuth2 password flow: `POST /auth/token` with form fields `username`/
`password` returns `{"access_token": ..., "token_type": "bearer"}`. Pass it
as `Authorization: Bearer <token>` on REST calls, or `?token=<token>` on the
WebSocket handshake (browsers can't set headers on a WS upgrade request).

Passwords are bcrypt-hashed in the `users` table (`db/migrations/
0004_users.sql`). If `API_SEED_DEMO_USERS=true` (the default), three
throwaway demo accounts are seeded on every startup - each one only if a
user with that exact username doesn't already exist, so this is safe to run
against an already-populated table and never touches a real user's row
(fixed 2026-07-18: this used to skip seeding entirely once the table had any
row at all, which silently prevented new/renamed DEMO_USERS entries from
ever reaching an already-seeded deployment - see `seed_demo_users`'s
docstring in `auth.py`):

| username | password | role |
|---|---|---|
| `admin` | `admin-demo-pw` | admin |
| `operator` | `operator-demo-pw` | operator |
| `pttlng` | `12345` | viewer |

The `viewer`-role account is intentionally the public login handed out to
site visitors (not the `<role>-demo-pw` pattern the other two use) - it's
what visitors sign in with to use the chat/feedback visitor-network features
(ws_chat.py, routes_feedback.py), which require authentication.

These are dev/demo convenience only - never used as real credentials, never
committed anywhere but this repo's own source, and a real deployment should
set `API_SEED_DEMO_USERS=false` and provision real users via `UserStore.
create_user()`. No external identity provider or third-party credential is
involved anywhere in this module, so the "stop and ask before deciding on
credential/ToS matters for an external data source" rule was never
triggered building it - JWT auth here is entirely self-contained.

### Auto-logout on redeploy (2026-07-17)

Every JWT embeds a `deploy_id` claim - a random value generated once per API
process start (`app.state.deploy_id`, `main.py`) - and every request re-checks
it (`auth.decode_access_token`). A Railway redeploy restarts this process, so
every token minted by the *previous* process is rejected afterwards
(`401 "session invalidated by a server redeploy"`), even though its signature
and expiry are still otherwise valid. This is the user's own explicit
request: any code Claude ships, on either GitHub (-> Cloudflare, frontend) or
Railway (backend), should force every currently-logged-in session to sign
back in, rather than leave someone running against a mismatched
frontend/backend pairing.

`GET /version` (unauthenticated) returns `{"deploy_id": "..."}` so the
frontend can poll for a changed value even on an idle tab that isn't making
any other authenticated call yet - see `web/lib/deployWatch.ts` for the
frontend half (which also detects a *frontend-only*, Cloudflare-side
redeploy, by diffing the served `index.html`, something this backend-side
check alone can't see).

## RBAC

Three roles, ordered least-to-most privileged: `viewer < operator < admin`.
`require_role(min_role)` accepts that role or higher.

| route | min role | why |
|---|---|---|
| `GET /assets`, `GET /assets/{zone_id}` | viewer | read-only |
| `GET /forecast/{zone}/{horizon}` | viewer | read-only |
| `GET /performance/{zone}` | viewer | read-only |
| `POST /simulate/{zone}` | operator | heavier what-if computation, not a plain read |
| `GET /ws/live` | viewer | read-only (JWT passed as `?token=`) |
| `GET /geometry/{zone}`, `GET /sun-path/{zone}` | viewer | read-only |
| `GET /energy-report/{zone}`, `GET /irradiance-map` | viewer | read-only |

`admin` isn't used to gate any route yet (no mutating endpoints exist in
this module) - it's provisioned so a future admin-only action (user
management, config writes) has somewhere to plug in without a schema change.

## Endpoints

- **`GET /assets`** → the full `config/assets.yaml` registry (site, all 3
  zones, environmental constants) via `nongfab_common.assets.load_assets()`.
- **`GET /assets/{zone_id}`** → one zone's full detail (equipment specs,
  corners, `simulated` flag). 404 for an unknown zone.
- **`GET /forecast/{zone}/{horizon}`** → latest MLflow-registered model's
  forecast for `horizon` in `{minute, hour, day}`, or - since
  `ingestion_scheduler.py` landed - a real-weather physics baseline
  (`model_type: "physics_baseline"`) instead of a 404 while too little real
  history has accumulated to train one yet. Still 404s only for a genuinely
  unknown zone/horizon. This module doesn't expose a `/train-now` route
  (that's Module 4's dev API only); production training happens out-of-band
  via this process's own background retrain loop - see "Real-data background
  ingestion" above. **(2026-07-16)** each point also carries `algorithm`
  (which model produced it - `"lightgbm"`/`"random_forest"` for hour-ahead's
  genuine per-lead-hour auto-select, a fixed `"cnn_lstm"`/`"neuralprophet"`
  for minute/day, `None` for the physics fallback) and `error` (that
  algorithm's own held-out validation RMSE, hour-ahead only) - see
  `forecast/README.md`'s own dated entry for the full story. **(2026-07-18)**
  for `hour`/`day` (not `minute`), `points` now also includes recent
  already-past target hours (persisted, not just this call's own forward-
  looking window) - see `forecast/README.md`'s "Forecast history
  persistence" entry. Each hour-ahead point also carries `candidate_errors`
  (every candidate's own RMSE for that lead hour, not just the winner's -
  e.g. `{"lightgbm": 6.6, "random_forest": 7.4, "sum_k_lstm": 42.6}`) -
  `None`/`{}` for minute/day/physics-baseline - see `forecast/README.md`'s
  "Per-candidate model error exposed" entry.
- **`POST /simulate/{zone}`** → what-if scenario (cloud/curtailment/
  degradation) applied to a baseline day, with an optional scenario-
  uncertainty Monte Carlo interval. Same request/response shape as Module
  5's own dev API (`simulation/src/nongfab_simulation/api.py`) so a client
  speaking one speaks both. 422 for a physically invalid scenario (e.g.
  negative curtailment).
- **`GET /performance/{zone}`** → today's energy/performance-ratio/specific-
  yield snapshot plus the PVWatts-style loss breakdown, via Module 5's
  `pipeline.simulate_zone_baseline()` and `loss_model.performance_ratio()`.
  Also returns `hourly`: today's synthetic baseline, hour by hour
  (`ac_kw`/`ssrd_w_m2`/`temp_c`) - added for Module 7's dashboard, which
  needs a real "generated power" time series to chart, not just a running
  total. Also returns `latitude`/`longitude` (the zone's own centroid) and
  `cloud_factor` (this zone's own value right now, via `nongfab_features.
  irradiance_map.cloud_factor_at()`) - Feature A's per-zone info panel.
  **(2026-07-18)** also returns `history: [{timestamp, ac_kw}]` - persisted
  actual/generated power for *previous* days (`hourly` above is always
  "today" only), covering the last 72h. This same call also *writes* one
  row into that same persisted history (`nongfab_forecast.serving.
  record_generated_power()`, the current hour's own `ac_kw` from `hourly`)
  before reading it back - see `forecast/README.md`'s "Actual/generated
  power history" entry for the full mechanism (backfill, upsert semantics,
  startup wiring).
- **`GET /ws/live`** → WebSocket. Pushes `{"zones": [{"zone", "current_ac_kw",
  "forecast_hour_ahead_kw"}, ...]}` every `API_LIVE_PUSH_INTERVAL_SECONDS`
  (default 5s) for all 3 zones. `forecast_hour_ahead_kw` is `null` until an
  hour-ahead model has been registered for that zone. Closes with code 1008
  if `?token=` is missing, invalid, or expired.
- **`GET /geometry/{zone}?at=<ISO datetime>`** → per-panel 3D layout (east/
  north meters, tilt/azimuth) plus that panel's solar-access % at `at`
  (defaults to now), the sun's azimuth/elevation at that instant, and the
  zone's average solar access. Built on Module 3's `nongfab_features.
  panel_geometry`/`shading` (added for this route, not duplicated here) -
  see `features/README.md`'s own section on them for the tilt/azimuth
  defaults and shading-model assumptions. Also returns `string_balance`
  (per-string estimated power + a flag against the zone's own
  `design_constraints.string_power_balance_max_kw`, via `nongfab_features.
  shading.string_power_balance()`) - only non-empty for Jetty, since only
  its layout assigns a real electrical string to each geometry row (see
  that function's own docstring for why GIS/ISB can't support this).
- **`GET /sun-path/{zone}?date=<YYYY-MM-DD>`** → that day's azimuth/
  elevation arc at 15-minute resolution, filtered to daylight only. Solar
  position comes from the plant's one shared site location (same as every
  other module), not a true per-zone calculation - identical across all 3
  zones today, kept under `/{zone}` only for path consistency with the rest
  of the API (an unknown zone still 404s).
- **`GET /energy-report/{zone}`** → Module 7's Feature D: system summary
  (capacity, module count, array area), annual generation (AC energy,
  specific yield, performance ratio - a **flat extrapolation** of one
  synthetic day, see `simulation/README.md`), a full loss breakdown
  including temperature (soiling/shading/mismatch/DC-wiring/connections/
  availability/inverter, Jetty's soiling correctly higher than GIS/ISB's),
  CO2 saved + trees-equivalent (from `config/assets.yaml`'s `environmental`
  block), and a real-equipment-derived interactive SLD topology
  (`nongfab_features.sld.build_sld()`). **(2026-07-16)** three more fields,
  against reslink.org as a design reference: `avg_solar_access_pct` (real
  per-panel row-to-row self-shading geometry, `nongfab_features.shading`, at
  local solar noon today), `monthly` (12 real pvlib-solar-position-based
  estimates with a documented rainy-season derate June-October, see
  `simulation/README.md`'s own section on this), and `lifecycle` (25-year
  degradation projection - see that same README section for the assumed
  degradation rate). 404 for an unknown zone.
- **`GET /irradiance-map?at=<ISO datetime>`** → Module 7's Feature E: a
  10x10 plant-wide irradiance grid (0-1000 W/m^2) plus the 3 zones' own
  pins, for a MapLibre overlay with a time scrubber. Built on
  `nongfab_features.irradiance_map` - solar position/clear-sky GHI computed
  once at the plant's nominal center (reusing `nongfab_features.clearsky`,
  same simplification `/sun-path/{zone}` already relies on), with a
  **documented synthetic cloud factor** per grid point (no live Himawari
  raster store exists in this dev environment yet - see that module's own
  docstring for the follow-up path once one does). Not zone-scoped (`at`
  only, no `{zone}` in the path) since the grid spans the whole plant, not
  one zone. Each zone pin also carries its own `ghi_w_m2`/`cloud_factor`
  (evaluated at that zone's own centroid, not the nearest generic grid
  cell), `estimated_ac_kw`/`plant_factor` (reusing Module 5's
  `simulate_zone_baseline()` with a fixed nominal ambient temperature - no
  real-time temperature exists for an arbitrary instant/location yet), and
  `boundary` (the zone's own 4 corners as a closed polygon ring, for
  Feature E's boundary overlay layer).
- **`GET /grid/today`** → the whole Thai power system next to this site
  (2026-07-25), from **EGAT SysGen**, EGAT's own public plan-vs-actual feed:
  today's actual and planned national generation, EGAT's peak records (this
  year / last year / all time), and the derived comparison this exists for -
  Thailand's system peak lands in the EVENING (2026: 35,992 MW at 20:50),
  hours after Nong Fab's own solar window has closed, so PV here with no
  battery cannot shave it. The solar window is computed from the same pvlib
  clear-sky model the forecast uses, at the site's real coordinates, so the
  claim rests on this site's physics rather than a rule of thumb.
  **Every timestamp in this feed is ICT, not UTC** - EGAT publishes
  `[seconds_since_local_midnight, MW, ambient_C]` against a `DD-MM-YYYY`
  day, so `egat_grid.py` builds Asia/Bangkok timestamps directly and the
  frontend renders them without a timezone conversion (which would rewrite a
  Thai time for any viewer abroad). Site-wide, not zone-scoped. Cached for
  `MIN_REFRESH_SECONDS` (60 s, the upstream's own publish cadence) so a page
  refresh never becomes one upstream request per viewer.
  Honest-empty: `available=false` with a reason when EGAT is unreachable.
- **`GET /metrics`** → Prometheus text exposition (STEP 10): request count
  and latency histograms, labeled by `method`/`path`/`status_code`. `path`
  is the matched route *template* (e.g. `/forecast/{zone}/{horizon}`), not
  the raw URL, so distinct zone values aggregate into one series instead of
  fragmenting; an unmatched path collapses to a fixed `"not_found"` label
  instead of leaking the raw (client-controlled) URL into a label value.
  Unauthenticated, matching the rest of the Prometheus/Grafana ecosystem's
  convention of relying on network-level access control for scrape
  endpoints rather than app-level auth. See `nongfab_api/metrics.py`.
- **`GET /version`** → `{"deploy_id": "..."}`, this process's own random
  boot-time identity. Unauthenticated (same reasoning as `/healthz`/
  `/metrics` - it's an ops/liveness-style signal, not application data).
  Polled by the frontend's deploy watcher to auto-log-out active sessions
  after a redeploy - see "Auto-logout on redeploy" above.

## Metrics

Exposed on `/metrics` (Prometheus text format) - same port as everything
else, since unlike Module 1/2 (standalone daemons with no web framework of
their own) this app already serves HTTP:

| Metric | Type | Meaning |
|---|---|---|
| `nongfab_api_requests_total{method,path,status_code}` | counter | requests handled; `path` is the matched route *template*, not the raw URL |
| `nongfab_api_request_duration_seconds{method,path}` | histogram | request latency |

`infra/prometheus/prometheus.yml`'s `nongfab-api` job scrapes this.

## Known gaps (same caveat as every other module)

No real accumulated (irradiance, temperature, power) history existed until
this pass's `ingestion_scheduler.py` (see "Real-data background ingestion"
above) - `/forecast/{zone}/{horizon}` now trains and serves on real data
once enough has accumulated.

**(2026-07-22) `/simulate/{zone}`, `/performance/{zone}`, and `/ws/live` are
now wired to the same real-data store too** - see "Real weather baseline for
/performance, /simulate, /ws/live" below; the two bullets that used to head
this list (their synthetic-only baseline) are resolved. The remaining gaps:

- ~~`/energy-report/{zone}`'s annual figures are a flat extrapolation of one
  synthetic day (x365)~~ **Resolved (2026-07-22)**: the annual headline (and
  the financial year-1 energy, and the savings table) now use
  `seasonal_annual_ac_energy_kwh` - the sum of the 12 representative-month
  estimates (real pvlib per-month solar-position swing + rainy-season derate)
  that the Energy Report's own monthly chart already showed. Still one step
  short of a genuine day-by-day measured-weather annual sum (which needs
  reliably-persistent real historical weather this deployment can't yet
  guarantee) - see `simulation/README.md`'s matching 2026-07-22 entry.
- `/irradiance-map`'s per-grid-point `cloud_factor` is a documented
  synthetic placeholder (no live Himawari raster store exists in this dev
  environment yet) - see `features/README.md`'s "SLD topology & irradiance
  grid" section.
- **Found but not fixed this pass** (pre-existing, unrelated to STEP 8C):
  `test_ws_live.py::test_zone_snapshot_uses_the_row_nearest_now_not_always_the_last_row`
  fails when run on a day after the test's hardcoded monkeypatched date
  (currently `2026-07-14`) - `nongfab_simulation.dev_data.
  synthetic_day_irradiance_temp()` anchors its synthetic day to the *real*
  wall-clock date via its own internal `datetime.now()` call, which the
  test doesn't (can't, from outside) monkeypatch, so the synthetic index
  drifts out of sync with the test's fixed "now" as real time passes past
  the hardcoded date. Confirmed via `git stash` that this fails identically
  on the pre-STEP-8C code, so it's environmental clock drift, not a
  regression introduced here.

## Running

Real deployment (`docker-compose up`, TimescaleDB running, `db/migrations/`
applied):

```
uvicorn nongfab_api.main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/docs` for interactive OpenAPI docs, or
`POST /auth/token` to get a bearer token.

Local dev without a real Postgres (points `API_TIMESCALE_DSN` at a file-
backed SQLite `users` table instead - same driver family the test suite
uses):

```
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from nongfab_api.models import Base

async def main():
    eng = create_async_engine('sqlite+aiosqlite:///./dev.db')
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await eng.dispose()

asyncio.run(main())
"
API_TIMESCALE_DSN="sqlite+aiosqlite:///./dev.db" uvicorn nongfab_api.main:app --reload --port 8000
```

(This mirrors what a real deployment's migration step does - `main.py`
deliberately never auto-creates tables itself; see `db/migrations/
0004_users.sql`.)

## Tests

`pytest` - 102 tests, no real Postgres or MLflow server required
(`enable_background_ingestion=False` in the `settings` test fixture keeps
`ingestion_scheduler.py`'s real network/training calls out of the suite -
see "Real-data background ingestion" above):

- `test_auth.py` (23) - password hashing, `UserStore` CRUD/seeding, JWT
  create/decode (expiry, wrong secret, malformed/missing claims),
  `require_role()`'s role-hierarchy enforcement across all 9 (caller role ×
  endpoint role) combinations via a throwaway test app.
- `test_login.py` (5) - `/auth/token` against the seeded demo users, wrong
  password/unknown username → 401.
- `test_routes_assets.py`, `test_routes_forecast.py`,
  `test_routes_simulate.py`, `test_routes_performance.py`,
  `test_routes_solar3d.py` (12) - per-route auth requirement, RBAC
  enforcement, unknown-zone/horizon 404s, invalid-scenario 422, Monte Carlo
  interval bounds, day/night solar-access behavior, malformed-date 422.
- `test_routes_energy_report.py` (12) + `test_routes_irradiance_map.py` (6) -
  system-summary/annual-figure sanity, temperature present in the loss
  breakdown, Jetty's soiling higher than GIS's, CO2-saved arithmetic, SLD
  module-count totals matching `module_count` for both the approximate
  (GIS/ISB) and real (Jetty sub-array) cases, grid-value display-range
  bounds, night-time all-zero grid; **(2026-07-16)** solar-access percentage
  range, 12-month coverage with the correct Jun-Oct rainy-season flags,
  25-year lifecycle degradation sanity (year 25 < year 1).
- `test_ws_live.py` (6) - snapshot shape, repeated pushes, missing/invalid
  token rejection, and a regression test for a real bug caught during live
  verification (see below).
- `test_cors.py` (3) + `test_config.py` (2) - CORS preflight/actual-response
  headers for allowed vs disallowed origins, and a real-env-var-parsing
  regression test for the bug in "Verified live" below.

Route/auth/websocket tests build the app via `create_app(settings, engine)`
against an in-memory SQLite engine (`tests/conftest.py`) - no live database
needed. `db/migrations/0004_users.sql` and `Base.metadata.create_all` define
the same schema; the test fixture uses the latter for speed, matching the
pattern already used by Module 5/6's own auth tests.

### Verified live (2026-07-14)

Ran a real `uvicorn` process (SQLite-backed `users` table, table created the
same way a migration would) and exercised every route with `curl` plus a
real WebSocket client:

- `/auth/token` for all 3 demo users; `/assets/GIS` returns the real zone
  detail; `/performance/GIS` returns PR ≈ 0.84 and a full loss breakdown;
  `/performance/Jetty` correctly reports `simulated_zone: true`.
- `/simulate/GIS` correctly 403s for a viewer token, 200s for
  operator/admin; a 40% extra cloud attenuation scenario cut midday output
  from 50.0 kW to 30.0 kW (60% of baseline, matching the multiplicative
  model exactly).
- `/forecast/GIS/hour` correctly 404s (no model has been trained into this
  DSN's MLflow registry).
- **Found and fixed a real bug**: `/ws/live`'s snapshot builder took
  `baseline.ac_power_kw.iloc[-1]` - always the synthetic day's 23:00 (always-
  dark) row, regardless of the real time of day - so `current_ac_kw` was
  silently always `0.0` no matter when you connected. Fixed to pick the row
  nearest the actual current time (`idx.get_indexer([now], method=
  "nearest")`); verified against a monkeypatched noon that the fix returns
  50.0 kW (correctly clipped at GIS's inverter capacity), and added
  `test_zone_snapshot_uses_the_row_nearest_now_not_always_the_last_row` as a
  regression test.

### Verified live again from Module 7's dashboard (2026-07-14)

Once `web/` (Module 7) existed, ran `uvicorn` + `vite dev` together and
drove the real login → forecast page flow with a headless browser (see
`web/README.md`'s own "Verified live" for the dashboard-side detail).
**Found and fixed two more real bugs this way**, neither of which any
existing unit test caught:

1. No `CORSMiddleware` at all - the dashboard (a different origin) couldn't
   call this API; every request was blocked by the browser before it ever
   reached FastAPI. Added `CORSMiddleware` + `Settings.cors_origins`
   (env var `API_CORS_ORIGINS`).
2. That fix's first version didn't actually work: the settings field was
   named `cors_origins_raw`, which pydantic-settings maps to env var
   `API_CORS_ORIGINS_RAW` - not the `API_CORS_ORIGINS` the code documented
   and `docker-compose.yml`/`.env.example` set. Overriding it via env var
   silently did nothing; curling the live server's preflight response
   proved the header never changed. Caught only by testing the *actual*
   deployed behavior against a real env var, not by `test_cors.py`'s
   existing tests (which construct `Settings(...)` with keyword arguments,
   sailing right past the env-var-name question). Renamed the field to
   `cors_origins` and added `test_config.py`, which builds `Settings()`
   through `monkeypatch.setenv()` specifically so this class of bug - "the
   field works when constructed directly but not from the env var it's
   documented to read" - can't silently reappear.

### Verified live a third time - Module 7's 3D view (2026-07-14)

`/geometry/{zone}` and `/sun-path/{zone}` (added for Feature B/C) were
exercised the same way: real `uvicorn` + `vite dev`, headless Chromium with
software WebGL (`--use-gl=swiftshader`). GIS/ISB/Jetty all rendered real
panel counts (84/196/320) correctly colored by solar access, the sun-path
arc line matched the compass readout, day/night transitions correctly drove
`average_solar_access_pct` from 0% (night) to 100% (clear midday), and
Jetty's `simulated_zone: true` flag correctly triggered the dashboard's
"no panels installed yet" badge. No backend bug this round - the one real
bug found (a default 3D camera framed on the geometric center of Jetty's
4 widely-spread sub-arrays, showing empty space instead of any panels) was
in `web/`'s `Solar3DScene.tsx`, not this module - see `web/README.md`.

### Verified live a fourth time - STEP 8C, Energy Report + irradiance map (2026-07-15)

`/energy-report/{zone}` and `/irradiance-map` (added for Feature D/E) were
exercised the same way: real `uvicorn` + `vite dev`, headless Chromium with
software WebGL. `curl`-verified both routes directly first (real physics:
GIS's PR ≈ 0.84, temperature loss ≈ 2.67% at the synthetic day's profile,
Jetty's soiling 6.0% vs GIS's 2.5%, CO2 saved = capacity_kw x the
`environmental` constant exactly), then drove the dashboard end to end:
system summary/annual/losses/CO2/SLD all render for GIS, switching to Jetty
correctly shows the simulated badge, higher soiling, and the SLD's real
sub-array ids (`01A.L`/`02A.L`/`03A.R`/`04A.R`); the SLD's string/inverter
nodes are click-interactive (a details panel updates per click). The
irradiance map's MapLibre canvas renders 100 grid points plus 3 zone pins,
the clear-sky GHI readout tracks the time scrubber (correctly 0 at night),
and the layer-toggle checkboxes hide/show each layer. No backend bug this
round - see `web/README.md`'s own "Verified live" for a real frontend bug
this same pass caught (a MapLibre canvas remount that silently reset the
layer-toggle state on every time-scrubber tick).

### Verified live a fifth time - recheck-driven spec gap closures (2026-07-15)

After a recheck against the full Feature A-E spec found 7 gaps (2 genuinely
out of scope pending real data - no obstacle survey exists for external
shading, no real As-Built SLD files/live Himawari store exist in this repo
- and 5 addressable now), closed the 5 addressable ones and re-verified
live the same way: real `uvicorn` + `vite dev`, headless Chromium with
software WebGL.

- **String power-balance flag** (`/geometry/{zone}`'s new `string_balance`):
  `curl`-verified Jetty at a low-sun, azimuth-aligned instant
  (`2026-07-14T11:15:00Z`) correctly flags all 4 sub-arrays as exceeding
  the 2kW design constraint (~2.97kW imbalance each); GIS returns an empty
  list (its layout doesn't have real per-string rows). The dashboard shows
  a warning banner listing the affected blocks - confirmed live.
- **Per-zone lat/lon + cloud factor** (`/performance/{zone}`'s new
  `latitude`/`longitude`/`cloud_factor`): confirmed GIS's coordinates match
  `config/assets.yaml` exactly and `cloud_factor` is in `[0, 1]`.
- **Zone-pin click panel + boundary layer** (`/irradiance-map`'s new
  `ghi_w_m2`/`cloud_factor`/`estimated_ac_kw`/`plant_factor`/`boundary` per
  zone): clicked a real zone pin on the live MapLibre canvas (scanning
  screen positions near the pin cluster, since pixel coordinates aren't
  exposed statically) and confirmed the popup shows all 5 new fields with
  real values (e.g. ISB: `lat/lon: 12.68134, 101.11832`, `plant factor:
  0.0%` at night). `estimated_ac_kw`/`plant_factor` reuse Module 5's
  `simulate_zone_baseline()` with a nominal ambient temperature (documented
  - no real-time temperature exists for an arbitrary point/instant yet).
- **Layer toggle categories**: added a third "Zone boundary" toggle
  (drawing each zone's real 4 corners as a polygon outline) - confirmed
  live it shows/hides independently of the other two. Deliberately did NOT
  add a fake "actual/estimated" toggle - there is no real telemetry to
  show as "actual" anywhere in this system yet (same caveat as every other
  module), so faking a second data layer would violate this project's own
  "don't fabricate site-specific data" rule; documented instead of faked.
- **Feature A <-> C integration**: the 3D page's sun-path scrub now looks
  up the nearest day-ahead forecast point and nearest actual/generated
  point to the scrubbed instant (reusing `/forecast/{zone}/day` and
  `/performance/{zone}`, not new backend logic) and shows both alongside
  the sun position - confirmed live it shows "no model trained yet"
  gracefully (no forecast model exists in this dev API instance) while
  still showing the real actual/generated value.

No backend bug found this round; see `web/README.md`'s own "Verified live"
for the two full new frontend pieces (the per-zone info panel and the
forecast/actual readout) built to surface this data.

### Verified live a sixth time - STEP 10, Prometheus metrics (2026-07-15)

Booted a real `uvicorn` instance (a throwaway file-backed sqlite DB, tables
created up front, since the real lifespan's `create_async_engine()` doesn't
run migrations itself) and `curl`ed `/metrics` before and after real
requests, rather than trusting the middleware logic from unit tests alone:

- `GET /healthz` twice → `nongfab_api_requests_total{method="GET",
  path="/healthz",status_code="200"} 2.0`, plus a matching
  `..._duration_seconds` histogram with real (sub-millisecond) buckets.
- `GET /assets` with no token → correctly recorded under `status_code="401"`
  (FastAPI's own exception handling runs *inside* `call_next()`, so the
  middleware sees the real translated status code, not a raw exception).
- `GET /forecast/GIS/hour` and `GET /forecast/ISB/hour` (both 401, no
  token) → both aggregated into the *same* series,
  `path="/forecast/{zone}/{horizon}"` - confirmed neither zone's literal
  value ever appears as a `path` label anywhere in the output.
- `GET /totally-bogus-path-xyz` → `path="not_found",status_code="404"` -
  confirmed the raw nonexistent path string never appears in the output
  either.

All four matched the intended design exactly on the first real run - no bug
found this time, but worth confirming live given the middleware sits in
front of every route in the app.

### Verified live (2026-07-15) - real-data background ingestion

Booted a real `uvicorn`-equivalent app (`TestClient` entering the actual
`lifespan`, `enable_background_ingestion=True`, a short `backfill_lookback_
days=1` so the run finished quickly) with real network access:

- Startup log showed all 4 background tasks spawned
  (`ingestion-startup-backfill`, `ingestion-poll-himawari`,
  `ingestion-poll-nwp`, `ingestion-retrain`); within ~10s the
  `RealDataStore` had real rows in both `nwp_history` and `cloud_history`.
- A focused second run (himawari polling disabled, nwp polling every 5s)
  showed `nwp_history` growing row-by-row as the live poll loop fetched
  each configured forecast hour for real, and the retrain loop firing
  immediately on startup (not waiting for its first interval) - registered
  real `nongfab-minute-GIS`, `nongfab-hour-GIS`, and `nongfab-day-GIS`
  model versions in MLflow during the same run.
- `GET /forecast/GIS/hour` after that: **`{"data_source": "real",
  "model_type": "ml", "points": [{"pred": 34.52, "lower": 23.63, "upper":
  52.99, ...}]}`** - a real LightGBM model, trained on real GFS-derived
  weather (via the physics-based PV conversion, see forecast/README.md),
  serving a physically plausible forecast for GIS's ~60kWp capacity. Before
  this session's changes, this same call would have been a 404.

**Found and fixed a real bug during this same live run**: the S3 backfill
datasource's field-matching (`ingestion/nwp/datasource.py`) only worked for
forecast hour 1 - `_poll_nwp_forever`'s multi-forecast-hour fetch (fhour
2/3/4/5/6/...) raised `ValueError: no GRIB2 message matching...` on every
hour past the first. Root cause and fix documented in `ingestion/nwp/
README.md`'s "Backfill" section (GFS's flux-field step-type text is
forecast-hour-dependent, e.g. "0-1 hour ave fcst" vs "6-12 hour ave fcst" -
the fix matches on `(shortName, level)` only, verified live across fhour
2/6/12/24 after the fix, not just re-trusting f001 again).

### Verified (2026-07-15) - k-step hour-ahead, motion vector, adaptive retrain

No live network egress available in this sandbox for this round (same
caveat as elsewhere in this doc), so this pass was verified via the full
test suite rather than another live `uvicorn` boot:

- **99 passed**, `ruff check api/src api/tests` clean - includes
  `test_get_forecast_no_model_trained_falls_back_to_physics_baseline` (now
  asserting 6 physics-baseline points, one per k-step lead hour, not 1)
  exercising `get_forecast_with_fallback()` against the new
  `HourAheadKStepModel` shape end-to-end through the actual `/forecast`
  route, not just forecast/'s own tests in isolation.
- `_retrain_forever()`'s new cold/warm branching and `_frame_with_motion()`'s
  wiring into both `_poll_himawari_forever()` and `_backfill_himawari()` have
  no dedicated unit tests of their own yet (no existing
  `test_ingestion_scheduler.py` in this module to extend) - covered
  indirectly via forecast/'s own k-step round-trip tests and the fact that
  `ingestion_scheduler.py` still imports/type-checks/runs cleanly against the
  new `Settings` fields. See forecast/README.md's "Verified (2026-07-15)"
  section for the k-step/RF/bias-correction-specific verification (a
  standalone smoke script + the forecast test suite).

### STEP 10: api/Dockerfile was broken and unbuildable

`api/Dockerfile` previously only `COPY`'d files from `api/` itself (`build:
./api` in `docker-compose.yml`), but `api/pyproject.toml` depends on four
sibling monorepo packages (`nongfab-common`, `nongfab-features`,
`nongfab-forecast`, `nongfab-simulation`) that are **not published to
PyPI** and were never present in that build context - `pip install -e .`
inside the image would have failed immediately trying to resolve
`nongfab-common` from the index (confirmed it genuinely 404s: `pip index
versions nongfab-common` → "No matching distribution found"). This had
never been caught because no Docker daemon exists in the dev sandbox that
built any of this - a working Dockerfile was never actually required until
STEP 10's CI/deployment work needed one.

**Update (2026-07-15)**: three more siblings (`nwp-ingestion`,
`himawari-ingestion`, `nasa-power-ingestion`) were added for real-data
background ingestion (see above) - the Dockerfile's `COPY`/install list was
extended the same way, and re-verified with the same throwaway-venv
technique below (still no Docker daemon available in this dev sandbox).

Fixed by pointing `docker-compose.yml`'s `api` service at a repo-root build
context (`context: ., dockerfile: api/Dockerfile`) and rewriting the
Dockerfile to copy + `pip install` each sibling in dependency order before
`api/` itself, plus a root `.dockerignore` (the repo root now has several
GB of `.venv`/`node_modules`/`mlruns` sitting in it - without this, `docker
build`'s context-upload step alone would be extremely slow). Also pinned
`NONGFAB_ASSETS_PATH` explicitly in the image rather than relying on
`nongfab_common.assets.load_assets()`'s `__file__`-relative fallback, which
is only correct for an *editable* install (see `orchestration/README.md`
for a real bug this exact fragility caused elsewhere).

Verified (still no Docker daemon available) by replicating the fixed
Dockerfile's exact install sequence - same paths, same order - in a
throwaway venv from the repo root, and confirming all 5 packages installed
successfully with **zero** PyPI lookups for the bare `nongfab-*` names.

### Verified live (2026-07-17) - auto-logout on redeploy

Live end-to-end, not just the test suite: booted `uvicorn` against a fresh
`dev.db`, logged in via the real `/auth/token` route to get a token, then
restarted the `uvicorn` process in place (the same effect on a live token as
a Railway redeploy - a fresh process, a fresh `app.state.deploy_id`):

- `GET /version` returned a different `deploy_id` after the restart
  (`4a87bd28570a2582` -> `38c8af3a3418cdf2` in one run).
- The token minted **before** the restart, replayed against the **new**
  process: `401 {"detail": "session invalidated by a server redeploy"}` -
  confirmed a still-signature-valid, still-unexpired token is genuinely
  rejected purely on the `deploy_id` mismatch.
- Full 114-test `api/tests` suite still green after the `auth.py`/`main.py`/
  `ws_live.py` changes (including `conftest.py`'s `token_factory` fixture,
  updated to mint tokens against whichever `app` fixture instance a test
  actually uses, so its `deploy_id` always matches).

The frontend half (an actual browser session auto-logging out after this
same kind of restart, with the Thai notice shown on the Login screen) was
also verified live via Playwright - see `web/README.md`'s matching dated
entry for that half and its screenshot.

### Added - `GET /weather/clouds` (2026-07-18)

New route in `routes_weather.py`, alongside the existing `/weather/strip`:
the single latest real Himawari cloud reading (site-wide, same "weather
isn't per-zone" reasoning `/weather/strip` already documents) - opacity %
plus a motion vector (speed/direction), straight off `cloud_history`
(Module 2's ingestion, the same table Module 4's Sum-k LSTM cloud-index
feature and the minute-ahead model's motion features already read).
`available: false` (not a 404/error) when no cloud row has ever been
recorded yet or the latest one is older than 30 minutes (a stalled-poller
guard, not an expected steady-state path - the Himawari poller runs every
~10min).

Built for `web/`'s Solar3DPage - a drifting cloud-layer visualization,
after the user noticed every panel's solar-access color seemed to move in
lockstep with the sun alone and asked for real cloud data to be shown. See
`web/README.md`'s matching dated entry for the frontend half, including the
honesty caveat on what this can and can't claim to show (a site-wide
opacity scalar + motion vector, not a spatial raster - no per-panel shadow
claim is made).

**Found and fixed a real bug while building this**: seeding a manually-
inserted cloud reading (`observed_at` from `datetime.now()`, carrying
microseconds) alongside real backfilled rows (a fixed poll-tick timestamp,
no microseconds) 500'd - `forecast/nongfab_forecast/local_store.py`'s
`cloud_history_df()` (and `nwp_history_df()`, sharing the same bug) used
`pd.to_datetime(..., utc=True)` without an explicit `format=`, which infers
one fixed timestamp precision from the first row and rejects any other row
that doesn't match exactly. Fixed with `format="ISO8601"` - see
`forecast/README.md`'s matching dated entry for the full story and its
regression test.

**Tested**: `test_get_cloud_conditions_requires_auth`,
`..._unavailable_when_store_empty`, `..._returns_latest_reading_with_motion`,
`..._unavailable_when_latest_reading_too_stale` (`test_routes_weather.py`) -
full suite 146 passed. **Live-verified**: seeded a real row into a
file-backed store, confirmed the endpoint 500'd (the mixed-precision bug
above) before the `local_store.py` fix and returned the seeded reading
correctly after it - see `web/README.md`'s entry for the rendered cloud
layer itself.

### Rewritten - `/ws/chat` is private 1:1 messaging, not a public broadcast room (2026-07-18)

**Correction, same day**: this originally said a manual `psql` migration
against Railway's Postgres was required. That was wrong - checking
production's actual `API_TIMESCALE_DSN` variable live (2026-07-18) found
it's `sqlite+aiosqlite:////data/app.db`, a plain SQLite file on a Railway
volume, **not Postgres at all** (the Postgres service in the Railway
project is provisioned but unused/orphaned - `chat_messages` doesn't exist
there, which is why running the migration SQL against it failed with
`relation "chat_messages" does not exist"`). Railway gives no SQL console
for a plain volume file the way it does for its own Postgres plugin, so
"run this by hand" had nowhere to actually run it.

Fixed properly instead: `main.py`'s `_ensure_recipient_client_id_column()`
runs right after `Base.metadata.create_all` on every startup (still gated
by `create_tables_on_startup`) and patches the column in via SQLAlchemy's
dialect-agnostic inspector if a `chat_messages` table already exists
without it - no manual DB step needed at all, just the usual manual
Railway "Deploy" click after this pushes (see root `README.md`'s
"Deployment notes" - Railway's auto-deploy still doesn't trigger on its
own). Works unchanged if a deployment ever does move to real Postgres.

The user reported the previous `/ws/chat` (site-wide single room + a
public message broadcast to everyone connected) as a real privacy bug -
"ต้องทำเพราะมันจำเป็น" (must fix, it's necessary) - not a UX nice-to-have.
Rewrote `ws_chat.py` so every message is addressed to exactly one
`recipient_client_id` and is only ever delivered - both the live WS push
and the persisted row - to the two participants' own sockets;
`ConnectionManager.send_to_client()` is now the only delivery primitive
(the old `broadcast()` fan-out-to-everyone method is gone entirely).

- **`ws_chat.py`**: connect now requires `?client_id=` (not just `?token=`)
  so the server knows identity immediately, before any message is ever
  sent - this is what populates the new `online_users` broadcast (replaces
  the old `presence` count-only event) with `{client_id, display_name,
  avatar, role}` per connected visitor, deduped per browser (several tabs
  = one entry). No more bulk `history` push on connect - a client only
  gets a conversation's history once it picks a specific peer (`GET /chat/
  history?my_client_id=&peer_client_id=`, `ChatStore.conversation_
  messages()` replacing the old separate `recent_messages()`/`messages_
  before()` methods with one `before_id`-optional method). A new `type:
  "update_profile"` WS message syncs a live name/avatar edit into the
  online list without requiring a reconnect.
- **`models.py`**: `ChatMessageORM` gained `recipient_client_id` (nullable
  only because pre-2026-07-18 rows predate the column and were public
  broadcasts with no single intended recipient - every row written from
  this date on always has one).
- **`db/migrations/0007_chat_direct_messages.sql`** (new): the column plus
  two indexes on `(client_id, recipient_client_id)` and its reverse, for
  the conversation-scoped lookup `GET /chat/history` now does.

**Tested**: `test_ws_chat.py` fully rewritten (16 tests) - the load-bearing
one proves a message sent to one recipient is never delivered to a third
connected client, only to sender+recipient (the actual privacy property,
not just a UI filter) - plus online-list broadcast/dedup, admin-prefix
enforcement, multi-tab delivery, live profile sync, and peer-scoped history
pagination/isolation. Full backend suite 148 passed. See `web/README.md`'s
matching dated entry for the frontend contact-list/thread rework and its
live 3-visitor Playwright verification (including the same privacy
property proven end-to-end through real browsers, not just the WS layer).

### Added - `GET /weather/precipitation` (2026-07-18)

Sibling route to `/weather/clouds` just above, same "site-wide, not
per-zone" reasoning - the latest real GFS precipitation (APCP) reading near
"now", off `nwp_history` (see `ingestion/nwp/README.md`'s and
`forecast/README.md`'s matching dated entries for the ingestion/storage
halves - this route's own change is additive, just a new query against a
table that already existed). Built for Solar3DPage's rain animation, per
the same 2026-07-18 request as the cloud layer - the user explicitly
confirmed real Thai Met data was required (no seasonal-calendar heuristic)
and explicitly excluded snow.

`nwp_history` also holds forecast rows out to 72h (unlike `cloud_history`,
which only ever holds already-observed frames) - without a lead-time cap,
"latest row" would mean "furthest-future forecast row", not "now". New
`_PRECIP_MAX_LEAD_HOURS = 1.5` restricts the search to near-term rows,
reusing `/weather/strip`'s existing `_nearest_real_row()` helper rather than
duplicating it. `available: false` when no row within that window carries a
non-null `precip_mm` - either the GFS subset genuinely carried no APCP
message for that hour, or no fresh poll has landed recently.

`intensity` (`"none"`/`"light"`/`"moderate"`/`"heavy"`) applies WMO surface-
observation bands (light <2.5mm, moderate 2.5-7.6mm, heavy >7.6mm) directly
to `precip_mm`, as a deliberate simplification for a decorative visual, not
a rigorous rain-rate computation - `precip_mm` is GFS's raw accumulated-
since-init value for whichever hour was decoded, not a de-accumulated mm/h
rate (see `ingestion/nwp/README.md`'s entry). Restricting to near-term rows
keeps this an honest approximation (GFS's own accumulation window is close
to 1h at short lead times).

**Tested**: requires-auth, unavailable-when-store-empty, unavailable-when-
no-row-carries-precip (rows exist but all `precip_mm` are `NULL` - must not
be confused with "confirmed dry"), returns-the-near-term-reading-over-a-
heavier-far-future-one, and a parametrized sweep of the 5 intensity-band
edges (`test_routes_weather.py`) - full suite green. **Live-verified**:
booted the API against a file-backed store, seeded a real `precip_mm=6.2`
row via `RealDataStore.insert_nwp_points`, confirmed `GET
/weather/precipitation` returned `{"available": true, "precip_mm": 6.2,
"intensity": "moderate", ...}` end-to-end; then loaded `/3d` in a real
browser (Playwright) and confirmed the reading reached the frontend (network
response inspected directly) and rendered as visible falling rain streaks
over the panels with zero console errors - see `web/README.md`'s matching
entry for the frontend half and screenshot.

### Fixed - `GET /performance/{zone}` silently claimed backfilled estimates were real "actual power" (2026-07-18)

The user reported that "Actual power (before today)" looked identical to
"Forecast" for the same historical hour - not a coincidence: `forecast/
serving.py`'s `backfill_generated_power_history()` and
`backfill_forecast_history()` both call the *same* `real_data.
physics_baseline_series(zone, timestamps, store)` for the same cold-start
window, so a backfilled "actual" row and the forecast for that hour really
were the identical number by construction. See `forecast/README.md`'s
matching dated entry for the root cause and the new
`GENERATED_POWER_ESTIMATED_MARKER` provenance flag (`serving.py` reuses the
already-existing, previously-unused `algorithm` column on
`forecast_history` rather than adding a new one).

This route's own half: `GeneratedPowerPoint` gained an `estimated: bool`
field (`estimated=p.algorithm == GENERATED_POWER_ESTIMATED_MARKER`), so the
frontend can label physics-estimated backfill rows honestly instead of
implying they're confirmed telemetry - see `web/README.md`'s matching entry
for the "(estimated)" tooltip suffix this feeds.

**Tested**: `test_routes_performance.py`'s main test now asserts
`{"timestamp", "ac_kw", "estimated"} <= body["history"][0].keys()`, every
backfilled row carries `estimated: true`, and the one row the test's own
request live-polls carries `estimated: false` (a live poll's `INSERT OR
REPLACE` naturally clears the marker) - full suite green.

### Added - `moon` field on `GET /geometry/{zone}` + `GET /moon-path/{zone}` (2026-07-18)

Backend half of Solar3DPage's new Moon feature - see `web/README.md`'s
matching dated entry for the frontend (the animated marker, and why it
took a wrap-window redesign to make the Moon actually appear during Play)
and `features/README.md`'s for the lunar-position math itself
(`nongfab_features.moon.moon_position()`, a pure-Python low/medium-
precision algorithm - no new ephemeris dependency was added).

- **`GeometryResponse.moon: SolarPositionOut`** - the Moon's azimuth/
  elevation at the requested instant, computed the same way `sun` already
  is, always populated (not gated on the sun being down) so the frontend
  decides visibility itself.
- **`GET /moon-path/{zone}`** - mirrors `/sun-path/{zone}` (same `date`
  param, same 96-point/15-minute-resolution day sweep) but **deliberately
  does NOT filter to `elevation_deg > 0`** the way `/sun-path` does - the
  whole point of the feature is showing the Moon specifically while the
  Sun is down, which has nothing to do with whether the Moon's own
  elevation happens to be positive at that instant. Filtering here would
  remove exactly the points the frontend's continuous-clock interpolation
  needs to glide through a moonrise/moonset transition.

**Tested**: `test_routes_solar3d.py` gained 6 tests -
`test_get_geometry_includes_moon_position` (valid azimuth/elevation
ranges), and 5 for `/moon-path` (auth-required, returns the full unfiltered
96-point sweep with at least one below-horizon point present - proving it
isn't silently daylight-filtered, defaults to today, rejects a malformed
date, 404s on an unknown zone). Full suite 21 passed.

**Live-verified**: booted the API, fetched `/geometry/GIS?at=2026-07-18T18:00:00Z`
(a real night instant per `/sun-path`) and confirmed a real `moon` object
came back (`{"azimuth_deg": 282.5, "elevation_deg": -42.2}` - below its own
horizon at that particular instant, a real astronomical fact, not a bug);
fetched `/moon-path/GIS?date=2026-07-18` and confirmed all 96 points came
back with a genuine mix of 46 below-horizon and 50 above-horizon points
(moonrise ~02:30Z, moonset ~15:00Z that day) - see `web/README.md`'s entry
for the rendered scene.

### Fixed - feedback/chat timestamps silently wrong by a fixed offset (2026-07-18)

The user reported admin feedback timestamps "don't match the real send time
at all" - lined up like `14:49`, `14:50` (consistently off, not random
garbage). Root cause, confirmed directly (see `models.as_utc`'s docstring):
`created_at` is always written as `datetime.now(timezone.utc)`, but what a
row reads back **as** depends on the DB driver - asyncpg round-trips a
`TIMESTAMPTZ` column's tzinfo correctly, but aiosqlite silently drops it,
so `row.created_at` comes back tz-**naive** even though the value itself is
still UTC. A naive datetime serializes with no UTC offset in the JSON
(`"...T15:23:32"` instead of `"...+00:00"`/`"...Z"`), and a browser's `new
Date(...)` then reads a timezone-less ISO string as **local** time, not
UTC - every timestamp ends up wrong by exactly the viewer's own UTC offset
(ICT = +7h). Fixed with a new `models.as_utc()` helper (attach `timezone.
utc` only if the value comes back naive - safe, since it was always UTC to
begin with), applied everywhere a `created_at` is read off a row before
going into a response: `routes_feedback.py`'s `FeedbackStore.add()`/`list_
all()` and `ws_chat.py`'s `_row_to_message()`. (Sender name was already
shown correctly in `AdminFeedbackPage.tsx` - no separate fix needed there.)

**Tested**: two regression tests assert the serialized `created_at` always
carries an explicit UTC marker - `test_routes_feedback.py`'s new test
against the SQLite-backed `app` fixture (the exact backend this bug
reproduces on) and `test_ws_chat.py`'s matching test for chat messages.
Full backend suite 159 passed.

### Added - `GET /weather/conditions` + extended `GET /weather/strip` for all 9 Songsiri reference variables (2026-07-19)

The user asked whether ForecastPage's app actually uses all 9 input
variables from Jitkomut Songsiri's reference deck (I, RH, T, UV, WS, I_clr,
cosθ, k̂, I_wrf - see "Reference: Songsiri" in `forecast/README.md`), and
if not, whether the missing ones could be sourced. Audited `real_data.py`/
`local_store.py`/`clearsky.py`: I/T/I_clr/k̂(as cloud index)/I_wrf(as
`real_future_regressors`) were already real model features; RH and wind
(`wind10m_u_ms`/`wind10m_v_ms`) were ingested into `nwp_history` but never
exposed via any route or used as a feature; UV was ingested via a separate
NASA POWER daily source (`uv_history`) but never wired to anything;
zenith angle was computed internally (`clearsky.compute_clearsky_and_
position`) but never surfaced as its own field.

New `GET /weather/conditions` route (`routes_weather.py`) returns a single
"now" snapshot of all 9: `irradiance_w_m2`, `temp_c`, `relative_humidity_
pct`, `wind_speed_ms`, `clearsky_ghi_w_m2`, `zenith_deg`, `cos_zenith`,
`clear_sky_index`, `forecast_irradiance_w_m2`/`forecast_valid_at` (I_wrf -
honestly documented as the same underlying GFS source at a near-future
valid_time, not an independent second model, since no independent
telemetry sensor exists at this site), `uv_index`/`uv_observation_date`
(can be `None` even when everything else is available, since NASA POWER is
daily-cadence, not hourly - `_UV_MAX_AGE_DAYS = 2` staleness tolerance).

A single snapshot can't power a time-series graph, so `GET /weather/strip`
(already a time series, already consumed by ForecastPage's `WeatherStrip`
component) was extended instead of building a second windowed endpoint -
`WeatherStripPoint` gained `relative_humidity_pct`/`wind_speed_ms`
(from the matched real NWP row when available, `None` in synthetic-fallback
mode) and `clearsky_ghi_w_m2`/`zenith_deg`/`cos_zenith`/`clear_sky_index`
(always populated in both real and synthetic mode - pure pvlib astronomy,
independent of data source). Reuses the existing real/synthetic honesty
labeling (`data_source` field) rather than introducing a new one.

**Tested**: `test_routes_weather.py` grew from ~14 to 25 tests - new
coverage for `/weather/conditions` (all-9-present happy path, UV null when
no/stale UV data, no-forecast-row when only past data exists, requires
auth) and for the extended `/weather/strip` (synthetic points carry
astronomy fields but not RH/wind, real points carry all 6 new fields with
correct values, RH/wind null specifically for future timestamps - see the
merge-reconciliation note below). Full `api` suite 174 passed, `ruff check`
clean. This round's frontend consumer (the 3x3 live table + grouped
variable graphs) is documented in `web/README.md`'s matching 2026-07-19
entry.

**Merge note**: Track 2 independently built the same `/weather/strip`
extension in parallel (with the user's permission to cross into Track 1
territory for this one piece), using different field names
(`ghi_clearsky_w_m2`/`cloud_index`/a separate `uv_daily` list) and a
genuinely better catch: RH/wind should stay `None` for *future* timestamps
even in real-data mode, since - unlike ssrd/temp - neither was ever
validated as a trained-model regressor in this pipeline, so showing them
as "forecast" would overstate confidence this project hasn't earned for
them. Reconciling the two independent implementations (both pushed to this
shared branch before either was aware of the other): kept this round's own
field names/shape end-to-end, since a complete, tested frontend (3x3 table
+ grouped graphs) was already built against them and Track 2's own
frontend piece hadn't landed yet - but adopted the RH/wind future-nulling
fix into `_real_window()`. Track 2's `cloud_index` (real Himawari k-hat,
an alternative to this round's ssrd/clearsky-ratio `clear_sky_index`) and
`uv_daily` (a real multi-day UV trend, which could someday replace the "no
UV chart" honest placeholder on ForecastPage - see web/README.md) were not
carried over, to keep this reconciliation scoped - either would be a
reasonable follow-up, not a redo of this round's work.

**Update (2026-07-19)**: the UV follow-up happened - see this file's own
`GET /weather/uv-history` entry below. Independently reimplemented (not a
revival of Track 2's discarded `uv_daily` code, which was never carried
over into any commit on this branch), same underlying idea. `cloud_index`
as a `clear_sky_index` alternative is still open.

### Added - `GET /weather/uv-history` (2026-07-19)

The user asked for UV to get a real chart despite its daily-only cadence,
after `/weather/conditions`' single-snapshot `uv_index` left ForecastPage
with only a caption-only placeholder for it (see this file's entry above).

New route (`routes_weather.py`) returns every real row `local_store.py`'s
`uv_history` table has accumulated - `{points: [{observation_date,
uv_index}, ...]}`, oldest first, straight off `store.uv_history_df()` with
no date-range filtering (this table only ever holds a few dozen rows at
most, one per real day this deployment has polled NASA POWER). Same
`require_role("viewer")` gate as every other `/weather/*` route. An empty
`points` list on a fresh deploy (or one where NASA POWER has never been
reachable - see `ingestion/nasa_power/README.md`'s "not reachable from
this dev sandbox" caveat) is a legitimate response, not an error - the
frontend renders its own honest "not enough days yet" state for it rather
than this route trying to backfill/estimate anything.

Sibling change in `forecast/`: `backfill_generated_power_history()` now
also (separately, unrelated to UV) uses real historical Himawari cloud
data instead of a single "latest reading" snapshot for its own physics
estimate - see `forecast/README.md`'s matching 2026-07-19 entry for that
half, it doesn't touch this route.

**Tested**: `test_routes_weather.py` +3 (`requires_auth`, `empty_when_
store_empty`, `returns_every_real_day_oldest_first` - inserted out of
order, asserts the response comes back sorted). Full `api` suite 180
passed, `ruff check` clean. Frontend consumer (`SolarVariablesGraphs`'s
new UV bar chart) documented in `web/README.md`'s matching 2026-07-19
entry.

### Added - real weather baseline for /performance, /simulate, /ws/live (2026-07-22)

The first medium-term roadmap item after the project recheck: three routes
(`/performance/{zone}`, `/simulate/{zone}`, `/ws/live`) built their hourly
irradiance/temperature baseline from `nongfab_simulation.dev_data.
synthetic_day_irradiance_temp()` - a purely synthetic day - even though
`/forecast` and `/weather/strip` had already been reading *real* ingested
NWP from the same `RealDataStore` for weeks. The plumbing to fix this was
described in the old Known-gaps bullet as "a follow-up to this route's
shape, not a rewrite" (the pipeline underneath - `simulate_zone_baseline` -
already documents that it "doesn't care which" its irradiance/temp are);
this wires it up.

- **New `nongfab_forecast.real_data.real_day_conditions(store, now=None)`**
  returns `(idx, ssrd_w_m2, temp_c)` for the current UTC calendar day
  (00:00-23:00 hourly) from real NWP history - the exact tuple shape
  `synthetic_day_irradiance_temp()` returns, so it's a drop-in. Each hourly
  slot is filled from the nearest real NWP `valid_time` within a 1.5h
  tolerance (matching `_nearest_real_row`); small gaps are interpolated from
  the surrounding real values. Raises `InsufficientHistoryError` if fewer
  than 80% of the day's 24 slots have a real match - the same 0.8 coverage
  bar `/weather/strip`'s `_real_window` already uses, and for the same
  reason (a day stitched from a handful of scattered real rows is worse than
  an honest, fully-populated synthetic fallback). Zone-independent: weather
  is site-wide here, exactly as the synthetic generator and `/weather/strip`
  already assume.
- **New `api/baseline.py`** `day_baseline_conditions(store, now=None)` is the
  single shared real-or-synthetic switch all three routes now call: tries
  `real_day_conditions`, falls back to `synthetic_day_irradiance_temp()` on
  `InsufficientHistoryError`, and returns a `data_source` label (`"real"` /
  `"synthetic"`) so each response can say honestly which drove its numbers -
  the same pattern `/weather/strip` and `/forecast` already expose. Factored
  out so the three routes share one behaviour instead of three copies.
- **`PerformanceResponse` and `SimulateResponse` gained a `data_source`
  field; the `/ws/live` payload gained a top-level `data_source`.** The
  power/energy numbers are still a physics conversion of the weather (never
  a measured plant output - no telemetry exists anywhere in this system, see
  this file's own caveats), but the flag now tells the dashboard whether the
  *weather* driving them is real. `/ws/live` builds the day's conditions
  once per push and reuses them across all three zones (weather is
  site-wide) rather than the old per-zone synthetic recompute.

Behaviour is unchanged wherever no real NWP has accumulated for today (a
cold-start / empty-store deploy) - `data_source` reads `"synthetic"` and the
numbers are exactly what they were before. `/performance`'s existing
`live_efficiency_factor` derate still applies on top either way (a bounded
<=1.0 loss layer, documented separately - it never claims *more* than the
weather-driven physics estimate).

**Tested**: new `test_baseline.py` (synthetic on empty store, real when
today is fully covered); `forecast/tests/test_real_data.py` +4
(`real_day_conditions`: full real day round-trips, empty store and thin
coverage both raise, small gaps interpolate with no NaN); `data_source`
assertions added to the `/performance` and `/simulate` route tests;
`test_ws_live.py`'s `_zone_snapshot` test updated for the new shared-
conditions signature. Full `api` and `forecast` suites pass, `ruff` clean.
See `forecast/README.md`'s matching 2026-07-22 entry for the
`real_day_conditions` half.

### 2026-07-22 - Loss-breakdown shading is now geometry-derived (roadmap item 3)

Every route that surfaces a loss breakdown (`/energy-report/{zone}`,
`/geometry/{zone}`, `/simulate`, `/performance`) previously showed the flat
`DEFAULT_SHADING_PCT = 3.0` PVWatts literature default for `shading_pct`,
identically for all three zones. It now shows the array's real
geometry-derived inter-row self-shading loss
(`nongfab_features.shading.annual_shading_loss_pct`, energy-weighted over a
full year's sun path) plus a `DEFAULT_EXTERNAL_SHADING_PCT = 2.0` allowance
for external-obstacle shading that has no site survey - see the `simulation`
and `features` READMEs' matching entries. The external-obstacle shading gap
noted in the 2026-07-15 recheck entry above remains a documented gap; the 2%
figure is now an explicit labelled allowance for it, not silently folded into
a flat 3%. All 13 `/energy-report` route tests pass unchanged.

### 2026-07-22 - /irradiance-map cloud level anchored to real Himawari (roadmap item 4)

`GET /irradiance-map` previously drew its cloud overlay entirely from the
synthetic sine field (`irradiance_map.cloud_factor_at`), since no live cloud
data was wired in. It now anchors the overlay's cloud *level* to the real
plant-wide Himawari observation (`cloud_history`, via
`nongfab_forecast.real_data.cloud_factor_for_time`) nearest the requested
instant, falling back to the synthetic field only when no real reading exists
within tolerance. A new response field `cloud_data_source` ("real"/"synthetic")
reports which path was taken.

**Honest scope**: only the plant-wide cloudiness is real. The sub-2km spatial
variation across the grid is still interpolated texture - there is no per-point
cloud raster store on Railway (no MinIO/`RawObjectStorage`), so
`himawari_ingestion.sampling.sample_cloud_at_time` can't run here. A true
per-point raster overlay remains a documented follow-up. Tested:
`test_routes_irradiance_map.py` asserts `cloud_data_source` is present/valid;
`features/test_irradiance_map.py` +4 and `forecast/test_real_data.py` +4 cover
the anchoring math and the real-vs-none provenance signal.

### 2026-07-22 - Hourly UV resolution (roadmap item 5)

UV was daily-only (Open-Meteo `uv_index_max`, one bar per day). Added a real
**hourly** UV curve end-to-end:

- `openmeteo_uv.fetch_hourly_uv_observations` - Open-Meteo `hourly=uv_index` at
  Nong Fab's coordinates, `timezone=UTC`, returned tz-aware UTC (same convention
  as cloud_history), oldest-first, nulls skipped.
- `local_store` new `uv_hourly_history` table (+ `insert_hourly_uv_observations`,
  `uv_hourly_history_df`, added to `counts()`).
- `ingestion_scheduler` - `_backfill_uv_hourly` at startup (guarded on empty
  table) and the live UV poll now refreshes hourly UV alongside daily, both
  non-fatal.
- New route `GET /weather/uv-hourly-history` -> `{points: [{observed_at,
  uv_index}]}` oldest-first, UTC-aware (frontend renders ICT), honest-empty.

Same Thailand-first exception already approved for Open-Meteo (2026-07-19):
non-Thai service, but queried at Nong Fab's own real coordinates. Frontend: the
ForecastPage UV chart now shows the real hourly line when hourly data exists,
falling back to the daily bar otherwise. Tested: `test_openmeteo_uv.py` +4,
`test_local_store.py` +2, `test_routes_weather.py` +3; `forecast` local_store
and `api` openmeteo/routes_weather suites pass, `ruff` clean.

### 2026-07-26 - Four new read routes: ramp, evolution, interval/sky verification, provenance (Track 1)

Four backend additions from the forecast-innovation round (projects A-D) and the
interface round (project O). All viewer-level reads; none of them changes an
existing response shape.

**`GET /forecast/{zone}/ramp`** (`routes_ramp.py`, `nongfab_forecast.ramp`) -
how fast output is about to change, not just how much of it there will be. A
ramp is `Δkw / hours` between consecutive points, reported as a percentage of AC
capacity per hour so a number is comparable across zones of different sizes.
`ramps_from_series()` collapses duplicate timestamps first, because
`forecast_history` can hold two rows for one target time mid-write.

**`GET /forecast/{zone}/evolution`** (`routes_evolution.py`,
`nongfab_forecast.evolution`) - how the forecast for one hour changed as that
hour approached. This needed a **new table**: `forecast_history`'s primary key is
`(zone, horizon, target_time)` with `INSERT OR REPLACE`, so only the freshest
issuance for a target ever survives and the earlier ones - exactly the data this
question is about - were being destroyed. Rather than change the serving
contract, `local_store.record_forecast_evolution()` writes to a second table
whose key includes `issued_at`, retained 14 days.
`TargetEvolution.is_converging()` returns `None` below three issuances instead of
guessing a trend from two points.

**`GET /verification/{zone}` extended** - the published P10-P90 band is now
scored, not just the line through it: PICP (coverage), PINAW (sharpness) and
**pinball loss**. Deliberately *not* CRPS: with only two quantiles a CRPS-shaped
number would be an approximation dressed as a proper score, and pinball is a
proper scoring rule at the quantiles actually published. Nominal coverage is
computed by `nominal_coverage_pct()` rather than inline, because
`(0.95 - 0.05) * 100` is `89.99999999999999` in float and that string was going
on screen. A second split reports metrics **by sky condition** (clear / partly /
overcast, from the clear-sky index `kt = GHI / GHI_clearsky`), since one RMSE
hides whether the model is bad overall or only bad under broken cloud. That
split is wrapped in its own `try/except`: a pvlib failure then costs the sky
table and not the whole verification response.

**`GET /provenance` + `GET /provenance/{key}`** (`provenance.py`,
`routes_provenance.py`) - click any published number, see the chain behind it:
source -> model -> setting -> computation, each link carrying its `origin`.

The one design rule worth restating here: **a setting's origin and note are
never copied into `provenance.py`** - `resolve_step()` reads them from
`settings_registry.BY_KEY` at request time. Hand-written provenance text would
start lying the moment somebody edited the registry, and no test would catch it,
which is precisely the failure this feature exists to prevent. A step naming a
setting key that does not exist is a hard error at import
(`validate_registry()`, called at module import) - it caught four wrong keys
while the six entries were being written, which is the whole point.

The headline is the **weakest link, not the average**: payback's chain contains
an as-built degradation model and a user-confirmed BOI figure, but also a
placeholder CAPEX, so it headlines `placeholder`. Averaging would flatter it.
Viewer-level on purpose - being able to see that a number rests on a guess is
exactly what a public dashboard should not hide behind a login.

Six chains ship: `forecast.expected_energy_kwh` (derived),
`tou.blended_rate_thb_per_kwh` (placeholder), `green.co2_avoided_kg`
(literature), `financial.payback_years` (placeholder),
`verification.skill_score` (tuning), `simulation.annual_energy_kwh`
(literature).

Route-order note repeated because it bit twice: new `/forecast/{zone}/...`
routes must be registered **before** `routes_forecast`, or its `{horizon}`
parameter swallows them.

**What the provenance inspector caught on its first live run.** `zone.*.tilt_deg`
and `zone.*.azimuth_deg` were marked `origin=as-built` in `settings_registry`,
which rendered a blue "from the project's as-built/SLD documents" chip on two
angles no document contains - `config/assets.yaml` carries `tilt_deg: null` and
`azimuth_deg: null` for every zone, and `routes_orientation.py` has warned about
exactly this on screen since it shipped. The registry and the orientation route
were telling users opposite things about the same fact. Both origins are now
`placeholder` with notes that say the angles have never been measured; the
`ac_capacity_kw` / `dc_capacity_kwp` rows beside them stay `as-built`, because
those figures really are as-built.

Nothing computed changes - `origin` is honesty metadata, not an input. What
changes is that `simulation.annual_energy_kwh` now headlines `placeholder`
instead of `literature`, which is right: its shakiest input is an unmeasured
tilt, not a literature loss coefficient.

Also noted while checking, and deliberately **not** changed:
`green.normal_rate_thb_per_kwh` (the PEA TOU Peak rate) is marked `literature`
though `CLAUDE.md` records it as a real published figure the user supplied on
2026-07-19. That direction of error under-claims rather than over-claims, and
promoting a tariff to `confirmed` is the user's call, not a session's - flagged
rather than edited.

### 2026-07-26 - `GET /poster/{zone}` - a year of light, as data (project S, Track 1)

Feeds one generated image (see `web/README.md`'s matching entry): a radial dial
of 365 rays, each spanning that day's sunrise to sunset, months coloured by
output.

**What shaped the endpoint was a constraint, not a design.** The obvious poster
is 365 × 24 cells coloured by generation. This project's annual energy model is
twelve representative days - `nongfab_simulation.pipeline.monthly_ac_energy_estimates`
says so itself - so painting 8,760 cells would invent 8,748 values nobody
computed. The response therefore carries two layers at two openly different
resolutions and labels both: `days` is per-day and exact (pvlib sunrise/sunset
and solar-noon elevation at the site's real coordinates - astronomy, not
measurement), `months` is per-month and modelled. There is deliberately **no
per-day energy field**, so the frontend has nothing to colour a fake gradient
with, and a test asserts its absence.

Times are converted to ICT before serialising. That is the one bug this route
could plausibly have shipped: UTC sunrise at Nong Fab lands around 23:37 the
previous day, which looks odd rather than wrong, so a test pins every sunrise
between 05:00 and 07:00 local.

`build_poster` is importable and tested directly, which is why the two tests
that go through HTTP were the only ones to catch the route filtering zones on
`zone.zone_id` - a field that does not exist. The real one is `zone.id`.

Year is clamped to 2000-2100: pvlib will happily return solar positions for
year 3, and a poster of them would be a plausible-looking picture of nothing.
