# Module 1 — Himawari Cloud-Observation Ingestion

Polls Himawari-derived cloud data for the Nong Fab site (~12.71°N, 101.15°E)
every 10 minutes, validates it, and stores raw + parsed copies. Feeds the
Minute-Ahead CNN-LSTM forecaster (Module 4).

```
scheduler (APScheduler, cron */10)
        │
        ▼
CloudDataSource.fetch_latest()
        │
        ├─ list NOAA S3 prefix for the latest published 10-min slot (rate-limited, retried)
        ├─ lazily open that NetCDF file over HTTPS (fsspec + h5netcdf, no full download)
        └─ read only the HDF5 chunk covering Nong Fab's pre-calibrated pixel
        ▼
RawFetchResult (small JSON manifest) ──► MinIO bucket `himawari-raw` (audit/replay)
CloudObservation (validated)         ──► TimescaleDB hypertable `cloud_obs`
        │
        ▼
Prometheus metrics on :9101/metrics
```

## Data source

**himawari.optemis.space (v0.1 of this module) is dead** — its TLS certificate
is expired (verified via direct handshake: `certificate_expired` alert). It has
been replaced with **NOAA/NESDIS's `AHI-L2-FLDK-Clouds` product**, published on
[AWS Open Data](https://registry.opendata.aws/noaa-himawari/) at
`s3://noaa-himawari9/AHI-L2-FLDK-Clouds/` as part of the NOAA Big Data Program —
public-domain US government data, readable anonymously over plain HTTPS, no
credentials, no robots.txt/ToS gate (it's a documented open-data distribution
endpoint, not a scraped website).

Two alternatives were investigated and rejected — see git history for the
detailed writeup:
- `himawari8.nict.go.jp` (NICT's real-time web viewer): reachable, but serves
  web-viewer tile *images*, not georeferenced data. A Web Mercator tiling
  hypothesis (suggested by JS in the viewer) was tested live and **disproved**
  (fetched tile landed on open ocean, not Thailand) — there's no publicly
  documented pixel↔lat/lon mapping for these simplified tiles, so trusting them
  for automated point extraction would mean shipping unverified geolocation.
- `cusolarforecast.com`: is the CU research group's own operational BEMS,
  backed by IEEE1888/SOAP (`IEEE1888.min.js`, `soapclient.min.js`), not a
  public REST/JSON API. Not used as a data source.

### Why this product, and what's actually in it (verified live, 2026-07-14)

The `AHI-CMSK` (Cloud Mask) NetCDF file for each 10-min slot carries full
`Latitude`/`Longitude` coordinate grids (5500×5500, ~2km/pixel, real satellite
navigation — no projection math guessed by us) plus:
- `CloudMask`: categorical, `flag_values=[0,1,2,3]`,
  `flag_meanings="clear probably_clear probably_cloudy cloudy"`
- `CloudProbability`: continuous 0-1

Neither field is literally called "opacity", so `_map_ahi_cmsk_to_observation`
(datasource.py) maps `CloudProbability × 100` → `cloud_opacity_pct` (closest
continuous analog) and `CloudMask / 3` → `cloud_index`. This is a deliberate,
documented substitution — the original spec's "Cloud Opacity/Cloud Index" names
come from a commercial provider (Solcast); NOAA's public product uses different
but scientifically equivalent fields.

### Point extraction without downloading the whole file

Full-disk files are large (CMSK ≈ 347MB). Downloading one every 10 minutes just
to read a single pixel would be ~50GB/day for no reason. Instead:

1. **One-time calibration** (`geolocation.calibrate_pixel_index`): pulls the
   full lat/lon grids once, does a nearest-neighbor search, caches the result.
   Already run and hardcoded as `geolocation.NONG_FAB_PIXEL` = Rows=2086,
   Columns=859 → actual grid point (12.708836°N, 101.14675°E), ~350m from the
   nominal site coordinates (expected at 2km/pixel resolution).
2. **Every ingestion cycle**: `fsspec` opens the remote file lazily and reads
   only the HDF5 chunk (200×200px, chunked storage) covering that one pixel via
   HTTP range requests. Verified live: metadata-open + windowed read together
   take **~1.5s** against a 347MB source file, vs. ~93s to pull the full
   lat/lon grids once. Confirmed against real data: `CloudMask=3`,
   `CloudProbability≈0.999` for an actually-cloudy moment at Nong Fab.

Re-run calibration if NOAA ever changes this product's fixed grid — nothing
else in the pipeline needs to change.

### Publish latency

Files appear ~40 minutes after their observation time (NOAA processing lag).
`fetch_latest()` accounts for this by searching backward from
`now - HIMAWARI_PUBLISH_LATENCY_MINUTES` across `HIMAWARI_LOOKBACK_SLOTS`
10-minute slots for the first one that has a published `AHI-CMSK` file.

### Rate limiting / retries

Even though this isn't a scraped site, `RateLimiter` still throttles the S3
list-objects calls (default: 2s floor) and `tenacity` retries the pixel read
with exponential backoff — good citizenship on a shared public resource, same
mechanics as any other adapter in this codebase.

- Default mode is **`mock`**, which replays `fixtures/sample_himawari_response.json`
  with realistic jitter. The rest of the pipeline (MinIO, TimescaleDB,
  scheduler, metrics) is fully implemented and tested against this mock.

## Layout

```
src/himawari_ingestion/
  config.py       Settings (env-driven, prefix HIMAWARI_)
  schemas.py       CloudObservation (validated ranges), RawFetchResult
  compliance.py    RobotsChecker (kept for future scrape-based adapters), RateLimiter
  geolocation.py   CalibratedPixel, NONG_FAB_PIXEL, calibrate_pixel_index()
  datasource.py    CloudDataSource interface, HimawariAHICloudSource, MockCloudDataSource
  storage.py       RawObjectStorage (MinIO), TimescaleWriter (upsert into cloud_obs)
  models.py        SQLAlchemy ORM for cloud_obs
  scheduler.py     IngestionJob + APScheduler wiring
  metrics.py       Prometheus counters/gauges
  main.py          Entrypoint (asyncio)
fixtures/          Sample response used by MockCloudDataSource and tests
tests/             pytest suite (unit tests run with no external services)
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # defaults to source_mode=mock, safe to run as-is

pytest -v                       # 25 unit tests, 2 integration tests (skipped by default)
python -m himawari_ingestion.main   # runs the scheduler; needs MinIO + TimescaleDB reachable
```

To exercise the real data source / DB integration tests:

```bash
# Hits the real public NOAA bucket (no credentials needed, ~5-10s):
RUN_LIVE_NOAA_TESTS=1 pytest -v -m integration -k noaa

# Needs db/migrations/0001_cloud_obs.sql applied to a running TimescaleDB:
TIMESCALE_TEST_DSN=postgresql+asyncpg://postgres:postgres@localhost:5432/nongfab_ems pytest -v -m integration -k timescale
```

## Database migration

Apply `../../db/migrations/0001_cloud_obs.sql` to the TimescaleDB instance
before running with `source_mode=http` or the integration test — it creates
the `cloud_obs` hypertable this module writes to.

## Metrics

Exposed on `:9101/metrics` (Prometheus text format):

| Metric | Type | Meaning |
|---|---|---|
| `himawari_fetch_success_total{source}` | counter | successful ingestion cycles |
| `himawari_fetch_failure_total{source,reason}` | counter | failed cycles, labeled by exception type |
| `himawari_fetch_duration_seconds{source}` | histogram | wall-clock time per cycle |
| `himawari_last_cloud_opacity_pct` | gauge | most recent value ingested |
| `himawari_last_cloud_index` | gauge | most recent value ingested |
