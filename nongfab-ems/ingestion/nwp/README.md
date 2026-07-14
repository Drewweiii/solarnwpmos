# Module 2 — NCEP/NOAA NWP (GFS) Ingestion

Fetches GFS 0.25° GRIB2 subsets from NOAA NOMADS around Nong Fab, decodes them
with `cfgrib`/`xarray`, and stores forecast points (SSRD, 2m temperature, 10m
wind u/v, relative humidity) to TimescaleDB `nwp_forecast`, keyed on
`(issue_time, valid_time, source)`. Feeds Module 4's Hour-Ahead LightGBM and
Day-Ahead NeuralProphet models as future regressors.

## Data source & ToS

Checked before any code was written, per this repo's standing rule (see root
README): "หยุดถามก่อนตัดสินใจเรื่อง credential/ToS ของแหล่งข้อมูลภายนอก" - always
stop and ask before deciding on an external data source's credentials/ToS. The
user explicitly approved this check ("I approve the NOMADS ToS check").

Findings, verified live 2026-07-14:

- `https://nomads.ncep.noaa.gov/robots.txt` → **404** (no robots.txt exists;
  permissive by default, same convention as Module 1's NOAA S3 bucket).
- `https://nomads.ncep.noaa.gov/info.php` (NOMADS's own "Information" page)
  documents and endorses exactly the approach this module uses: the GRIB
  filter/subset CGI script, with pages titled "GRIB NOMADS Grib Filter Help",
  "Fast downloading of NOMADS Grib2 Files", and "How to write scripts to use
  Grib Filter to download subsets of NCEP data".
- `https://www.weather.gov/disclaimer` ("Terms of Data Usage", linked from
  info.php) confirms: NWS/NOAA data is **public domain**, usable "without
  charge for any lawful purpose"; restrictions are about *misrepresentation*
  (claiming NWS data as your own, implying endorsement, presenting modified
  data as official) and abuse (SQL injection etc.) - none of which apply to a
  backend ingestion pipeline. No registration, API key, or credential is
  required. No formal rate limit is published - the page's own guidance is to
  match request frequency to the data's actual refresh cadence (GFS publishes
  every 6h) and back off on error responses instead of retrying blindly.
- The GFS filter CGI endpoint (`cgi-bin/filter_gfs_0p25.pl`) was confirmed
  live: a real ~1KB subset around Nong Fab (leftlon=100.9, rightlon=101.4,
  toplat=13.0, bottomlat=12.4, vars DSWRF/TMP/RH/UGRD/VGRD) was fetched and
  decoded successfully - see `fixtures/sample_gfs_nongfab.grib2`, a **real**
  file (not synthetic), used by the hermetic decode test.

**Verdict: clear to proceed.** No `RobotsChecker` is needed here (unlike
Module 1's original scraping target) - see `compliance.py`.

## GFS variable naming gotcha (verified live, not assumed)

The architecture doc calls the irradiance variable "SSRD" (ECMWF/CDS naming,
used in ERA5). **GFS's own GRIB2 short_name is `sdswrf`** (Surface Downward
Short-Wave Radiation Flux), not `ssrd` - confirmed by decoding a real GFS
`.idx` file (`DSWRF:surface:0-1 hour ave fcst`). The Pydantic field is named
`ssrd_w_m2` to match the paper/architecture-doc terminology, but the GRIB
variable actually extracted is `sdswrf` - see `datasource.py`'s docstring.

## cfgrib coordinate-merge gotcha (caught by live testing, not assumed)

Requesting 2m-above-ground fields (TMP, RH) and 10m-above-ground fields
(UGRD, VGRD) together and decoding with a single `xarray.open_dataset(...,
engine="cfgrib")` call **raises `cfgrib.dataset.DatasetBuildError`**: cfgrib
can't merge two different fixed values of the same `heightAboveGround`
coordinate (2.0 vs 10.0) into one Dataset. Fixed by opening the file three
separate times with explicit `filter_by_keys` (`surface`/`sdswrf`,
`heightAboveGround`/`level=2`, `heightAboveGround`/`level=10`) - see
`_decode_grib_sync()` in `datasource.py`. This was caught by decoding a real
sample file during development, not discovered later in production.

## Design

- **Point subset, not a tile**: unlike Module 1 (which needs a raster for
  cloud-motion estimation), the architecture doc calls for NWP subset "ที่
  พิกัดหนองแฟบ" (at the Nong Fab coordinate) - a single point. The fetch bbox
  (`geolocation.nong_fab_fetch_bbox()`, padded 0.3° beyond the plant's own
  bbox from `config/assets.yaml`) exists only to guarantee at least one full
  surrounding 0.25° grid cell for `.sel(..., method="nearest")`, not to build
  a raster.
- **One cycle, many forecast hours**: each ingestion run fetches every
  configured forecast hour (`Settings.forecast_hours`, default: hourly to
  24h then 3-hourly to 48h) of the most recently published GFS cycle, not a
  single point in time - Module 4 needs a full future-regressor curve.
- **Scheduling is cycle-based, not interval-based**: `scheduler.py` triggers
  once per GFS cycle (00/06/12/18 UTC), offset by the expected publish
  latency (default 240min/4h) - a cron `*/N` poll doesn't fit since a new
  cycle simply doesn't exist yet between runs.
- **`(issue_time, valid_time, source)` primary key, not `(valid_time,
  source)`**: successive GFS cycles overlap in valid_time (the 00z run's f024
  and the 06z run's f018 are both valid at the same instant). Module 4's
  training needs to reconstruct "what was known as of issue_time X", so every
  distinct issue is kept, not overwritten - see `models.py`.
- Same adapter/mock/compliance/retry pattern as Module 1
  (`NWPDataSource` ABC, `MockNWPDataSource` backed by the real sample GRIB2
  fixture, `tenacity` retry with exponential backoff, `RateLimiter`).

## Layout

```
src/nwp_ingestion/
  config.py        Settings (env prefix NWP_)
  geolocation.py    nong_fab_fetch_bbox() - reads config/assets.yaml via nongfab_common
  schemas.py         NWPForecastPoint, RawFetchResult (Pydantic validation)
  compliance.py       RateLimiter only (no RobotsChecker - see "Data source & ToS")
  datasource.py        NomadsGfsDataSource (real) + MockNWPDataSource (fixture-backed)
  models.py             NWPForecastORM -> nwp_forecast hypertable
  storage.py             RawObjectStorage (MinIO), TimescaleWriter (upsert)
  scheduler.py            IngestionJob, build_scheduler() - cron on GFS cycle+latency
  metrics.py               Prometheus counters/gauges
  main.py                   production entrypoint (headless worker)
  api.py                    dev-only FastAPI wrapper for interactive verification
fixtures/sample_gfs_nongfab.grib2   real ~1KB GFS subset (gfs.20260714/00z f001)
tests/                pytest suite - hermetic by default, integration tests
                      gated behind NWP_LIVE_TEST=1 / TIMESCALE_TEST_DSN
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../../libs/nongfab_common
pip install -e ".[dev,api]"
pytest -v                                     # hermetic suite, no network/DB needed

# live NOMADS fetch (real network call, ~1-3s):
NWP_LIVE_TEST=1 pytest -v -m integration -k nomads

# real Postgres roundtrip (needs db/migrations/0003_nwp_forecast.sql applied):
TIMESCALE_TEST_DSN="postgresql+asyncpg://postgres:postgres@localhost:5432/nongfab_ems" \
  pytest -v -m integration tests/test_storage.py

# interactive dev API:
uvicorn nwp_ingestion.api:app --reload --port 8001
# then open http://localhost:8001/docs, or:
curl -X POST http://localhost:8001/fetch-now
```

Decoding GRIB2 requires the ecCodes C library (`cfgrib`'s backend). If
`import cfgrib` fails with a library-loading error: `apt-get install -y
libeccodes0` (Debian/Ubuntu) before `pip install cfgrib`.

## Verified live (2026-07-14)

- GFS filter CGI endpoint reachable, returns real ~1KB GRIB2 subsets for the
  Nong Fab bbox (`test_nomads_gfs_datasource_against_real_nomads`, gated
  behind `NWP_LIVE_TEST=1`).
- Full dev-API path exercised end-to-end against a real (non-Timescale,
  plain-table) local Postgres: `POST /fetch-now` → decode real fixture GRIB2
  → validate → local-disk MinIO stand-in → Postgres upsert → `GET
  /latest-cycle` returns the persisted row.
- `ruff check` clean.

## Known gaps / next steps

- `db/migrations/0003_nwp_forecast.sql` is written but, like Module 1's
  migrations, not live-tested against a real TimescaleDB (extension
  unavailable in this dev sandbox - verified only against a plain Postgres
  table with the same schema, extension/hypertable statements omitted).
- No spatial interpolation between grid points yet - `_decode_grib_sync`
  uses nearest-neighbor (`method="nearest"`) to the plant's nominal center,
  same simplification Module 1 makes for `sample_cloud_at`.
- `forecast_hours` default (hourly to 24h, 3-hourly to 48h) is a reasonable
  first choice for Hour-Ahead/Day-Ahead regressors, not a value tuned against
  Module 4 (not built yet) - configurable via `NWP_FORECAST_HOURS` env var
  when that tuning happens.
