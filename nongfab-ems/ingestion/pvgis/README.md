# PVGIS Historical Weather Backfill

Fetches one full year of real hourly weather (irradiance `G(i)`, 2m
temperature `T2m`, 10m wind speed `WS10m`) for Nong Fab's own coordinates
from PVGIS (Photovoltaic Geographical Information System), the European
Commission Joint Research Centre's free public solar-resource API. Added
2026-07-16 in response to a user request: forecast training was falling
back to `forecast/`'s synthetic sine-wave/random-noise generators far more
than necessary, and the user wanted a genuinely real, immediately-usable
weather source to seed training with while waiting for real plant telemetry
(Huawei FusionSolar) access.

## Scope (read this before extending)

Deliberately small, mirroring `ingestion/nasa_power`'s "smaller than Module
1/2" shape: no `scheduler.py`, `storage.py`, `models.py`, or a `main.py`/
`api.py` service entrypoint. PVGIS's `seriescalc` endpoint returns an entire
already-published year of hourly data in **one** HTTP call - there is
nothing to poll continuously (unlike Himawari's ~10min / GFS's ~1h live
cadence), so this is a one-time backfill, not a running service. Consumed
by `api/ingestion_scheduler.py`'s `_backfill_pvgis()`, which writes straight
into `forecast/local_store.py`'s shared `nwp_history` table (tagged
`source="pvgis-era5"`) - `forecast/real_data.py` itself needed **zero**
changes, since its Day-ahead builders (`real_day_frame`/
`real_future_regressors`) already read that table without caring which
source populated it.

### Day-ahead only - NOT Intra-day (deliberate, not a bug)

Every `PVGISHourlyPoint` this module produces has `issue_time == valid_time`
(see `schemas.py`'s own docstring): PVGIS is historical reanalysis, not a
multi-lead-time forecast, so there is no real "issued N hours before valid
time" for it to report. `forecast/real_data.py`'s Intra-day k-step builder
(`real_hour_frame_kstep`) filters real NWP history on `lead_hours =
valid_time - issue_time` matching one of `HOUR_LEAD_HOURS` (1-6) - which a
PVGIS row's `lead_hours = 0` never satisfies. This was discussed explicitly
with the user (2026-07-16) before building: duplicating one PVGIS reading
across all 6 lead-hour buckets was considered and rejected, since it would
teach the k-step models nothing real about how forecast skill degrades with
lead time (every lead would see identical input) - a methodologically weak
shortcut the user chose not to take. Intra-day continues to rely on real
GFS/NWP backfill (`ingestion/nwp`), which does carry genuine per-lead
structure, once/if that accumulates.

## Data source & ToS

**Live-verified for real** - unlike `ingestion/nasa_power`, which was built
entirely from documentation because its endpoint has never been reached
from any environment this repo was built in. This dev sandbox's own egress
policy returns a hard 403 for `re.jrc.ec.europa.eu` too (confirmed
2026-07-16 - same blanket organization-policy block that also stops
`developer.nrel.gov`, `www.kaggle.com`, `api.kaggle.com`), but the user ran
a one-off Python script directly in the Railway deployment's own Console
tab and confirmed a genuine `HTTP 200` with real data for Nong Fab's own
coordinates (`latitude: 12.6834, longitude: 101.1199`), using PVGIS's
`PVGIS-ERA5` radiation database. `fixtures/sample_seriescalc_response.json`
is built from that captured response's real `outputs.hourly` rows and
`inputs.location`/`inputs.meteo_data` fields (only the unused `meta`/
`mounting_system`/`pv_module` sub-objects were filled in from PVGIS's
documented shape for structural completeness - this module never reads
them).

- **Public, free, no API key/registration required** - `seriescalc` is
  PVGIS's own documented non-interactive API
  (`https://re.jrc.ec.europa.eu/api/v5_2/seriescalc`).
- **What's read**: `G(i)` (in-plane irradiance, W/m²) → `ssrd_w_m2`, `T2m`
  (2m air temperature, °C) → `temp2m_c`, `WS10m` (10m wind speed, m/s) →
  `wind10m_u_ms` (no direction available - see `schemas.py`). The response's
  own `P` field (PVGIS's own simple PV-power simulation for a 1kWp
  reference system) is deliberately **not** used - it's itself a
  physics-model output, not an independent measurement, so reusing it would
  bypass this repo's own per-zone `pv_conversion.py` physics model and
  introduce inconsistency between PVGIS-sourced and GFS-sourced training
  rows. PVGIS is used purely as a real **weather** source here, same role
  `nwp_ingestion`'s GFS data plays.
- **To re-verify or refresh**: `PVGIS_LIVE_TEST=1 pytest -v -m integration`
  from an environment with normal internet egress (a developer's own
  machine, or the Railway deployment itself, both confirmed working
  2026-07-16).

## Design

- **Whole-year fetch, not a range**: `seriescalc` has no day-level slicing -
  requesting `startyear=endyear=<year>` returns every hour of that calendar
  year (8760 or 8784 rows) in one response (`datasource.PVGISSource.
  fetch_year`'s docstring).
- **`issue_time == valid_time` for every row** - see "Day-ahead only" above.
- **`year` is a fixed, specific config value (default 2020)**, not
  "latest" - PVGIS-ERA5 has no such alias, and a fixed year keeps results
  reproducible. Live-verified reachable and valid for this exact year via
  Railway's console 2026-07-16, not guessed.
- Same adapter/mock/compliance/retry pattern as `ingestion/nasa_power`
  (`PVGISSource` ABC, `MockPVGISSource` backed by the (genuinely captured,
  see above) fixture, `tenacity` retry with exponential backoff,
  `RateLimiter` - though with only one request per backfill run, the rate
  limiter is mostly there for interface symmetry, not real load-bearing).

## Layout

```
src/pvgis_ingestion/
  config.py       Settings (env prefix PVGIS_)
  schemas.py      PVGISHourlyPoint, RawFetchResult (Pydantic validation), SOURCE_NAME
  compliance.py   RateLimiter only
  datasource.py   PVGISDataSource (real, live-verified via Railway) + MockPVGISSource (fixture-backed)
  backfill.py     backfill_year() - one whole-year request, not a fetch-per-slot loop
fixtures/sample_seriescalc_response.json   genuine captured response (hourly rows + inputs), meta padded for structural completeness only
tests/            pytest suite - hermetic by default, one integration test
                  gated behind PVGIS_LIVE_TEST=1 (blocked in this dev sandbox, confirmed working from Railway)
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../../libs/nongfab_common
pip install -e ".[dev]"
pytest -v                                # hermetic suite, no network needed

# live PVGIS fetch - NOT reachable from this dev sandbox, confirmed reachable
# from the Railway deployment 2026-07-16 (see "Data source & ToS"):
PVGIS_LIVE_TEST=1 pytest -v -m integration
```

## Known gaps

- **One fixed year (2020), not the most recent available** - PVGIS-ERA5's
  actual latest published year wasn't checked (the live capture only
  confirmed `year_min`/`year_max` *field names* exist in the response's
  `meta`, not their values for this deployment). A more recent year may be
  available and would anchor training data closer to "now" - a candidate
  follow-up, not blocking (NeuralProphet/day-ahead's own seasonality
  modeling is day-of-year-based, not absolute-year-based, so a few years'
  gap doesn't invalidate the daily/seasonal shape this exists to provide).
- **Doesn't feed Intra-day** - see "Day-ahead only" above. If real GFS/NWP
  backfill (`ingestion/nwp`) also stays thin/unreachable in a given
  deployment, Intra-day still falls back to synthetic training data even
  after this module successfully seeds Day-ahead.
- **`wind10m_v_ms`/`relative_humidity_pct` are placeholders**, not real
  PVGIS fields (see `schemas.py`) - harmless today since no current
  `real_data.py` builder reads them for *any* source, but would need real
  values if that ever changes.
- No `storage.py`/TimescaleDB table of its own, same reasoning as
  `ingestion/nasa_power` - writes straight into `forecast/local_store.py`'s
  shared SQLite-backed store via `api/ingestion_scheduler.py`.
