# Module 1b — NASA POWER UV Index Ingestion

Fetches daily UV index (`ALLSKY_SFC_UV_INDEX`) for Nong Fab from NASA POWER's
public daily-point API. Added specifically because neither Module 1
(Himawari cloud) nor Module 2 (GFS NWP) publish a UV field, and the user
asked for UV to be included as a model input alongside I/RH/T/WS/I_clr/k̂/I_wrf
(see the reference figure this was scoped against).

## Scope (read this before extending)

Deliberately smaller than Module 1/2: no `scheduler.py`, `storage.py`,
`models.py`, `metrics.py`, or `main.py`/`api.py` service entrypoints. NASA
POWER is a **daily-aggregate** product (one value per calendar day, several
days of publication lag), so there's no "poll every 10 minutes" loop to run
- a request for the last `backfill_lookback_days` days is one HTTP call
(`backfill.backfill_range()`), not a scheduled job. This module is consumed
directly by `forecast/`'s real-data feature layer (a UV column joined onto
the day-ahead frame by date), not run as its own standalone service. If a
continuous-refresh daily job is wanted later, add `scheduler.py` then -
premature now.

## Data source & ToS

**NOT live-verified** - unlike Module 1/2, whose data sources were checked
against the real endpoint. `power.larc.nasa.gov` is blocked outright by this
dev sandbox's egress policy (403 at the proxy's CONNECT tunnel, confirmed
2026-07-15 - same finding as `nomads.ncep.noaa.gov`, `api.open-meteo.com`,
and `www.noaa.gov`; only `*.s3.amazonaws.com` is reachable from here). Built
against NASA POWER's long-stable, publicly documented API instead of a live
capture:

- **What's documented, not verified live**: NASA POWER (power.larc.nasa.gov)
  is NASA's public "Prediction Of Worldwide Energy Resources" project -
  free, no API key or registration, explicitly built for renewable-energy
  applications (the `community=RE` parameter this module requests). The
  daily point API (`/api/temporal/daily/point`) and its JSON response shape
  (`properties.parameter.<PARAM>.<YYYYMMDD>`, `-999` missing-value
  sentinel) have been stable and publicly documented for years.
- **What this means for the code**: `datasource.py`'s real adapter
  (`NASAPowerDataSource`) is written against that documented shape and unit
  -tested against a **hand-constructed** fixture matching it
  (`fixtures/sample_power_response.json` - its own `messages` field says so
  in-band, not just this README), not a captured real response. The
  live-gated integration test (`NASA_POWER_LIVE_TEST=1`) exists and is
  correctly wired, but has only ever run against this sandbox's proxy 403,
  never the real API - see "Known gaps".
- **To close this gap**: run `NASA_POWER_LIVE_TEST=1 pytest -v -m
  integration` from an environment with normal internet egress (a
  developer's own machine, or once this deploys to Railway, whose own
  egress is unconfirmed either way but plausibly broader - see
  `ingestion/nwp/README.md`'s equivalent caveat), and diff the real response
  shape against the fixture. If it matches, the fixture can simply be
  replaced with the real capture; if NASA POWER's schema has drifted,
  `_parse_power_response()` needs updating first.

## Design

- **Range fetch, not "latest"**: NASA POWER's daily point API accepts a full
  `[start, end]` date range in one request - unlike Himawari/GFS's
  near-real-time single-slot polling, there's no meaningful "latest single
  value" call separate from "the whole recent range" (see
  `datasource.UVDataSource.fetch_range`'s docstring).
- **`publish_latency_days` (default 3)**: NASA POWER's most recent few days
  aren't published yet at request time (a documented characteristic of the
  underlying MERRA-2/CERES reanalysis products it aggregates, not something
  live-verified here) - `backfill_range()` ends its window that many days
  before "today", not at "today" itself.
- **Missing-sentinel handling**: NASA POWER uses `-999` for a day with no
  value (e.g. not yet processed) - `_parse_power_response()` silently skips
  those days rather than failing the whole fetch; `UVObservation`'s own
  validator additionally rejects a `-999`-shaped value if one somehow reaches
  construction directly (defense in depth, not the primary skip path).
- Same adapter/mock/compliance/retry pattern as Module 1/2 (`UVDataSource`
  ABC, `MockUVDataSource` backed by the (unverified, see above) fixture,
  `tenacity` retry with exponential backoff, `RateLimiter`).

## Layout

```
src/nasa_power_ingestion/
  config.py       Settings (env prefix NASA_POWER_)
  schemas.py       UVObservation, RawFetchResult (Pydantic validation)
  compliance.py     RateLimiter only (no scheduler to rate-limit against beyond this)
  datasource.py      NASAPowerDataSource (real, unverified live) + MockUVDataSource (fixture-backed)
  backfill.py         backfill_range() - one range request, not a fetch-per-slot loop
fixtures/sample_power_response.json   hand-constructed from documented API shape - NOT a live capture
tests/                pytest suite - hermetic by default, one integration test
                      gated behind NASA_POWER_LIVE_TEST=1 (currently blocked in this sandbox)
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../../libs/nongfab_common
pip install -e ".[dev]"
pytest -v                                     # hermetic suite, no network needed

# live NASA POWER fetch - NOT reachable from this dev sandbox (see "Data source & ToS"):
NASA_POWER_LIVE_TEST=1 pytest -v -m integration
```

## Known gaps

- The real API has never actually been reached from any environment this
  repo was built in - see "Data source & ToS" above for exactly what's
  verified (the documented shape) vs. not (a live response). Treat
  `NASAPowerDataSource` as **written-but-unverified** until someone with
  working egress runs the live test once.
- UV index correlates strongly with clear-sky GHI (both driven by the same
  solar-zenith-angle geometry and atmospheric attenuation), so it adds
  limited *independent* signal beyond what `features/clearsky.py` already
  derives from `pvlib` - included because the user explicitly asked for it
  as a model input, not because it's expected to move forecast accuracy
  much. If it turns out not to help once wired into `forecast/`'s real-data
  feature layer, dropping it back out is a one-line change (see
  `forecast/README.md`'s real-data feature section).
- No `storage.py`/TimescaleDB table of its own - the forecast module's
  real-data feature layer calls `backfill_range()`/`fetch_range()` directly
  and folds the result into its own local history store rather than this
  module persisting UV independently. If UV ever needs its own queryable
  history table, that's a deliberate follow-up, not an oversight.
