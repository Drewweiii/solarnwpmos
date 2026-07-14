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
- **`GET /ws/live`** → WebSocket. Pushes `{"zones": [{"zone", "current_ac_kw",
  "forecast_hour_ahead_kw"}, ...]}` every `API_LIVE_PUSH_INTERVAL_SECONDS`
  (default 5s) for all 3 zones. `forecast_hour_ahead_kw` is `null` until an
  hour-ahead model has been registered for that zone. Closes with code 1008
  if `?token=` is missing, invalid, or expired.

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

`pytest` - 55 tests, no real Postgres or MLflow server required:

- `test_auth.py` (23) - password hashing, `UserStore` CRUD/seeding, JWT
  create/decode (expiry, wrong secret, malformed/missing claims),
  `require_role()`'s role-hierarchy enforcement across all 9 (caller role ×
  endpoint role) combinations via a throwaway test app.
- `test_login.py` (5) - `/auth/token` against the seeded demo users, wrong
  password/unknown username → 401.
- `test_routes_assets.py`, `test_routes_forecast.py`,
  `test_routes_simulate.py`, `test_routes_performance.py` - per-route auth
  requirement, RBAC enforcement, unknown-zone/horizon 404s, invalid-scenario
  422, Monte Carlo interval bounds.
- `test_ws_live.py` (6) - snapshot shape, repeated pushes, missing/invalid
  token rejection, and a regression test for a real bug caught during live
  verification (see below).

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
