# Module 1 — Himawari Cloud-Observation Ingestion

Polls a Himawari-derived cloud **tile** covering all 3 Nong Fab zones + a
wind-drift buffer every 10 minutes, validates it, and stores raw + parsed
copies. Feeds the Minute-Ahead CNN-LSTM forecaster (Module 4) as an image
sequence, and derives a coarse regional cloud-motion vector.

```
scheduler (APScheduler, cron */10)
        │
        ▼
CloudDataSource.fetch_latest()
        │
        ├─ list NOAA S3 prefix for the latest published 10-min slot (rate-limited, retried)
        ├─ lazily open that NetCDF file over HTTPS (fsspec + h5netcdf, no full download)
        └─ read only the HDF5 chunk(s) covering the Nong Fab bbox window (7x5 px)
        ▼
CloudRasterFrame (validated tile metadata)
        │
        ├─ motion.py: FFT phase-correlation vs. previous cycle's tile (in-memory)
        ▼
RawFetchResult (.npz: cloud_mask, cloud_probability, lat, lon arrays)
        │                                    │
        ▼                                    ▼
MinIO bucket `himawari-raw`          TimescaleDB hypertable `cloud_raster_frames`
(one .npz per 10-min slot,           (lightweight per-frame index: bbox, shape,
 the actual CNN-LSTM training data)   motion vector, MinIO object key)
        │
        └─ derived point sample ──► TimescaleDB hypertable `cloud_obs`
                                     (simple single-site time series, backward compat)
        ▼
Prometheus metrics on :9101/metrics
```

## Tile, not a single point

v0.1/v0.2 of this module sampled one pixel at Nong Fab's coordinate. That's
wrong for two things this module is meant to feed: the minute-ahead CNN-LSTM
needs to *see* cloud motion approaching before it arrives, and shading
analysis needs values across the plant's own footprint (3 zones + a ~1.25km
jetty), not one averaged point. Fixed in this revision:

- **Bounding box now comes from `config/assets.yaml`**, not a hardcoded
  duplicate: `geolocation.py` calls `nongfab_common.assets.target_bbox()` at
  import time, which unions all 3 zones' corner coordinates and pads by
  `cloud_tile.buffer_deg` (0.06°). Currently resolves to 12.607–12.744°N,
  101.055–101.180°E.
- That lat/lon extent is calibrated live against
  `geolocation.calibrate_bbox_index()` to `geolocation.NONG_FAB_BBOX` = Rows
  2085–2091, Columns 855–860 (re-verify against a live file if
  `config/assets.yaml`'s zone geometry ever changes — the pixel window is a
  cached constant, not recomputed every run).
- **Tile shape: 7×6 = 42 pixels.** Verified live 2026-07-14. (An earlier
  revision of this constant, calibrated before `config/assets.yaml` existed
  against a slightly narrower hardcoded bbox, was 7×5 — re-verifying against
  the wider config-derived bbox picked up one more column. This is exactly
  why it's re-verified against real data rather than assumed unchanged.)

### ⚠️ Real resolution constraint — read before relying on this for Feature B

At this location the product's native grid spacing is **~2.2km/row,
~2.8km/col** (`geolocation.NONG_FAB_ROW_SPACING_KM` /
`NONG_FAB_COL_SPACING_KM`, both derived from the live-verified degree
spacing) — **coarser than the ~1.25–1.5km jetty/trestle** this is meant to
help shade. This tile is genuinely useful for:
- plant-level cloud opacity/index (what `cloud_obs` already carried), and
- **regional cloud-motion direction/speed** (see below) — knowing a front is
  approaching from the SW at 25km/h is real, actionable minute-ahead signal.

It **cannot** resolve differential shading along the jetty itself (head vs.
tail) — the whole jetty likely sits inside 1–2 pixels. That needs a
complementary technique (e.g. NOAA's Cloud Height product + sun-geometry
shadow projection, or a ground-based sky camera) — out of scope for this
ingestion module; flagged here so nobody downstream assumes sub-pixel detail
that was never captured.

### Cloud motion vector (optical flow)

`motion.py` runs FFT-based phase correlation (Kuglin & Hines, 1975) between
the current tile's `CloudProbability` array and the previous cycle's (kept
in-memory by `IngestionJob`, not re-read from storage) and converts the
resulting pixel shift to `motion_speed_kmh` / `motion_direction_deg` using
the real pixel spacing above. Sign convention verified against synthetic
known shifts in `tests/test_motion.py` before trusting it on real data.

Null on: the first frame of a run, a shape mismatch (e.g. bbox reconfigured
mid-run), or a non-positive time interval — never fatal to the ingestion
cycle (`scheduler.IngestionJob._with_motion` swallows and logs any motion
error and continues without it).

At this tile size (7×6), phase correlation gives a *dominant regional shift*
for the whole tile, not per-cloud tracking — and on a uniformly overcast sky
(no spatial texture to correlate against) the result is not meaningful, which
is exactly what live testing during a monsoon-season overcast period showed
(uniform `CloudProbability≈1.0` across the tile → a low-confidence, near
arbitrary shift). This is expected FFT phase-correlation behavior on a
featureless field, not a bug — real value shows up once cloud cover is
partial/textured within the tile.

## Sampling at any coordinate/time — `sampling.py`

Feature B (differential shading along the Jetty, sampled per sub-array) and
anything else that wants a value at a specific point/time, not just Nong
Fab's own reference pixel, uses `sampling.py`:

- `sample_cloud_at(arrays, lat, lon) -> CloudSample` — pure nearest-neighbor
  lookup within one already-loaded tile's own lat/lon grid (no I/O). Returns
  the matched grid point and how far it actually is from the request
  (`distance_km`) so callers can judge whether the ~2-3km grid is fine enough
  for their purpose - it usually won't be for resolving individual sub-arrays
  a few hundred meters apart (see the resolution constraint above).
- `sample_cloud_at_time(reader, raw_storage, source, lat, lon, t) -> CloudSample | None`
  — the full "t" chain: looks up whichever stored `cloud_raster_frames` row is
  closest to `t` (`storage.TimescaleReader.find_nearest_raster_frame`, capped
  at `max_delta_minutes`), fetches that frame's `.npz` from raw storage
  (`storage.RawObjectStorage.get_raw` - new; the reverse of `put_raw`), and
  samples it. Returns `None` if nothing is close enough to `t`.

Verified live end-to-end: real NOAA fetch → real tile stored → queried back by
timestamp → sampled at a Jetty mid-trestle coordinate (12.673°N, 101.116°E,
distance from the matched grid point ≈1.3km).

## Data source

**himawari.optemis.space (v0.1) is dead** — its TLS certificate is expired
(verified via direct handshake: `certificate_expired` alert). Replaced with
**NOAA/NESDIS's `AHI-L2-FLDK-Clouds` product**, published on
[AWS Open Data](https://registry.opendata.aws/noaa-himawari/) at
`s3://noaa-himawari9/AHI-L2-FLDK-Clouds/` as part of the NOAA Big Data
Program — public-domain US government data, readable anonymously over plain
HTTPS, no credentials, no robots.txt/ToS gate (documented open-data
distribution endpoint, not a scraped website).

Two alternatives were investigated and rejected for the point-source revision
— see git history for the detailed writeup:
- `himawari8.nict.go.jp` (NICT's real-time web viewer): reachable, but serves
  web-viewer tile *images* with no publicly documented pixel↔lat/lon mapping.
  A Web Mercator hypothesis was tested live and **disproved** (landed on open
  ocean, not Thailand).
- `cusolarforecast.com`: the CU research group's own operational BEMS
  (IEEE1888/SOAP-backed), not a public REST/JSON API.

### What's actually in the product (verified live, 2026-07-14)

The `AHI-CMSK` (Cloud Mask) NetCDF file for each 10-min slot carries full
`Latitude`/`Longitude` coordinate grids (5500×5500 full disk, real satellite
navigation — no projection math guessed by us) plus:
- `CloudMask`: categorical, `flag_values=[0,1,2,3]`,
  `flag_meanings="clear probably_clear probably_cloudy cloudy"`
- `CloudProbability`: continuous 0-1

Neither field is literally called "opacity", so `_build_raster_frame`
(datasource.py) maps `CloudProbability × 100` → `*_cloud_opacity_pct`
(closest continuous analog) and `CloudMask / 3` → `*_cloud_index`. Documented
substitution: the original spec's "Cloud Opacity/Cloud Index" names come from
a commercial provider (Solcast); NOAA's public product uses different but
scientifically equivalent fields.

### Tile extraction without downloading the whole file

Full-disk files are large (CMSK ≈ 347MB). Downloading one every 10 minutes
just to read a 7×6 window would be ~50GB/day for no reason. Instead:

1. **One-time calibration** (`geolocation.calibrate_bbox_index`): pulls the
   full lat/lon grids once, finds every pixel inside the target bbox, caches
   the resulting rectangular window as `geolocation.NONG_FAB_BBOX`.
2. **Every ingestion cycle**: `fsspec` opens the remote file lazily and reads
   only the HDF5 chunk(s) (200×200px native chunking) covering that 7×6
   window via HTTP range requests. Verified live: metadata-open + windowed
   read together take **~6-8s** against a 347MB source file (up from ~1.5s for
   the single-pixel version — reading across a chunk boundary now, still far
   cheaper than the full file), vs. ~100-112s to pull the full lat/lon grids
   once for calibration.

Re-run calibration if NOAA ever changes this product's fixed grid — nothing
else in the pipeline needs to change.

### Publish latency

Files appear ~40 minutes after their observation time (NOAA processing lag).
`fetch_latest()` accounts for this by searching backward from
`now - HIMAWARI_PUBLISH_LATENCY_MINUTES` across `HIMAWARI_LOOKBACK_SLOTS`
10-minute slots for the first one that has a published `AHI-CMSK` file.

### Rate limiting / retries

Even though this isn't a scraped site, `RateLimiter` still throttles the S3
list-objects calls (default: 2s floor) and `tenacity` retries the tile read
with exponential backoff — good citizenship on a shared public resource, same
mechanics as any other adapter in this codebase.

Default mode is **`mock`**, which synthesizes a small raster (same shape as
`NONG_FAB_BBOX`) from `fixtures/sample_himawari_response.json` with
per-pixel jitter. The rest of the pipeline (motion, MinIO, TimescaleDB,
scheduler, metrics) is fully implemented and tested against this mock.

## Layout

```
src/himawari_ingestion/
  config.py       Settings (env-driven, prefix HIMAWARI_)
  schemas.py       CloudObservation, CloudRasterFrame (validated ranges), RawFetchResult
  compliance.py    RobotsChecker (kept for future scrape-based adapters), RateLimiter
  geolocation.py   CalibratedPixel/BBox, NONG_FAB_PIXEL/BBOX (bbox extent sourced from
                    config/assets.yaml via nongfab_common), calibrate_*_index()
  motion.py        FFT phase-correlation cloud motion vector
  datasource.py    CloudDataSource interface, HimawariAHICloudSource, MockCloudDataSource,
                    (de)serialize_raster (.npz)
  sampling.py      sample_cloud_at() / sample_cloud_at_time() - query any coordinate/time
  storage.py       RawObjectStorage (MinIO, put_raw+get_raw), TimescaleWriter
                    (cloud_obs + cloud_raster_frames), TimescaleReader (frame lookup by time)
  models.py        SQLAlchemy ORM for both hypertables
  scheduler.py     IngestionJob (fetch -> motion -> store -> derive point) + APScheduler wiring
  metrics.py       Prometheus counters/gauges
  api.py           Dev-only FastAPI wrapper (see below)
  main.py          Production entrypoint (asyncio)
fixtures/          Sample response used by MockCloudDataSource and tests
tests/             pytest suite (unit tests run with no external services)
```

## Run locally

Depends on the shared `nongfab-common` library (`../../libs/nongfab_common`)
for `config/assets.yaml` — install it first, into the same venv:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../../libs/nongfab_common
pip install -e ".[dev]"
cp .env.example .env   # defaults to source_mode=mock, safe to run as-is

pytest -v                       # unit tests + 2 integration tests (skipped by default)
python -m himawari_ingestion.main   # runs the scheduler; needs MinIO + TimescaleDB reachable
```

To exercise the real data source / DB integration tests:

```bash
# Hits the real public NOAA bucket (no credentials needed, ~5-10s):
RUN_LIVE_NOAA_TESTS=1 pytest -v -m integration -k noaa

# Needs db/migrations/0001_cloud_obs.sql AND 0002_cloud_raster_frames.sql applied:
TIMESCALE_TEST_DSN=postgresql+asyncpg://postgres:postgres@localhost:5432/nongfab_ems pytest -v -m integration -k timescale
```

## Dev verification API (optional, not Module 6)

Module 1 is normally headless (scheduler + Prometheus metrics only — see
`main.py`). For interactively poking it during development, `api.py` wraps the
same `IngestionJob` in a small FastAPI app:

```bash
pip install -e ".[dev,api]"
uvicorn himawari_ingestion.api:app --reload --port 8000
# open http://localhost:8000/docs
```

- `GET /health` — source mode, last fetch time/error, where raw/parsed data is going
- `GET /latest-observation` — most recently ingested single-point `CloudObservation` (404 if none yet)
- `GET /latest-raster` — most recently ingested tile's metadata + motion vector (pixel arrays are in raw storage, not this response)
- `POST /fetch-now` — triggers one real ingestion cycle immediately (fetch → motion → store), same code path the cron job uses

Two things about this API are dev-only stand-ins, reported explicitly in
`/health` so it's never ambiguous:
- **Raw storage** writes to local disk (`.dev-minio-data/`) instead of a real
  MinIO server — `main.py` (production) always uses the real `minio.Minio` client.
- **TimescaleDB** writes go to whatever Postgres `HIMAWARI_TIMESCALE_DSN`
  points at; if you don't have the TimescaleDB extension installed, apply
  both migrations with the `CREATE EXTENSION`/`create_hypertable` lines
  stripped — the plain tables still support every query this module makes,
  you just lose hypertable partitioning (irrelevant for a dev check).

## Database migrations

Apply, in order, to the TimescaleDB instance before running with
`source_mode=http` or the integration tests:
1. `../../db/migrations/0001_cloud_obs.sql` — single-point time series
2. `../../db/migrations/0002_cloud_raster_frames.sql` — tile metadata + motion vector

## Metrics

Exposed on `:9101/metrics` (Prometheus text format):

| Metric | Type | Meaning |
|---|---|---|
| `himawari_fetch_success_total{source}` | counter | successful ingestion cycles |
| `himawari_fetch_failure_total{source,reason}` | counter | failed cycles, labeled by exception type |
| `himawari_fetch_duration_seconds{source}` | histogram | wall-clock time per cycle |
| `himawari_last_cloud_opacity_pct` | gauge | most recent Nong Fab point value ingested |
| `himawari_last_cloud_index` | gauge | most recent Nong Fab point value ingested |
