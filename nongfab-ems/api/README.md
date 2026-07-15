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
0004_users.sql`). If `API_SEED_DEMO_USERS=true` (the default) and the table
is empty on startup, three throwaway demo accounts are seeded:

| username | password | role |
|---|---|---|
| `admin` | `admin-demo-pw` | admin |
| `operator` | `operator-demo-pw` | operator |
| `viewer` | `viewer-demo-pw` | viewer |

These are dev/demo convenience only - never used as real credentials, never
committed anywhere but this repo's own source, and a real deployment should
set `API_SEED_DEMO_USERS=false` and provision real users via `UserStore.
create_user()`. No external identity provider or third-party credential is
involved anywhere in this module, so the "stop and ask before deciding on
credential/ToS matters for an external data source" rule was never
triggered building it - JWT auth here is entirely self-contained.

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
  forecast for `horizon` in `{minute, hour, day}`. 404 if the zone/horizon
  is unknown, or if no model has been trained yet for that (zone, horizon) -
  this module doesn't expose a `/train-now` route (that's Module 4's dev API
  only); training happens out-of-band (a scheduled retraining job, not yet
  built - see root README's module table).
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
  total.
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
  defaults and shading-model assumptions.
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
  (`nongfab_features.sld.build_sld()`). 404 for an unknown zone.
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
  one zone.

## Known gaps (same caveat as every other module)

No real accumulated (irradiance, temperature, power) history exists yet
(Modules 1-3 haven't been running in production long enough - see forecast/
simulation READMEs' own "Known gaps"). So:

- `/simulate/{zone}` and `/performance/{zone}` build their baseline day from
  `nongfab_simulation.dev_data.synthetic_day_irradiance_temp()`, not a real
  TimescaleDB query. Swapping in a real query is a follow-up to this
  module's shape, not a rewrite of it (the pipeline call underneath doesn't
  care where `irradiance_w_m2`/`temp_c` come from).
- `/ws/live`'s `current_ac_kw` is today's synthetic baseline's row nearest
  the current wall-clock time (not literally "the last received sensor
  reading" - there isn't one yet).
- `/forecast/{zone}/{horizon}` genuinely round-trips through the MLflow
  registry, but nothing in this module trains a model - see Module 4's dev
  API `/train-now/{zone}/{horizon}` to populate the registry before trying
  this route.
- `/energy-report/{zone}`'s annual figures are a flat extrapolation of one
  synthetic day (x365), not a real annual simulation with weather
  variability/seasonality - see `simulation/README.md`'s "Annual energy +
  temperature loss" section.
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

`pytest` - 87 tests, no real Postgres or MLflow server required:

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
- `test_routes_energy_report.py` (9) + `test_routes_irradiance_map.py` (6) -
  system-summary/annual-figure sanity, temperature present in the loss
  breakdown, Jetty's soiling higher than GIS's, CO2-saved arithmetic, SLD
  module-count totals matching `module_count` for both the approximate
  (GIS/ISB) and real (Jetty sub-array) cases, grid-value display-range
  bounds, night-time all-zero grid.
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
