# Module 1 — Himawari Cloud-Observation Ingestion

Polls a Himawari cloud-product source (Cloud Opacity, Cloud Index) for the Nong
Fab site (~12.71°N, 101.15°E) every 10 minutes, validates it, and stores raw +
parsed copies. Feeds the Minute-Ahead CNN-LSTM forecaster (Module 4).

```
scheduler (APScheduler, cron */10)
        │
        ▼
CloudDataSource.fetch_latest()  ──►  RobotsChecker (fail-closed gate)
        │                            RateLimiter (min interval floor)
        │                            tenacity retry (exponential backoff)
        ▼
RawFetchResult (bytes) ──► MinIO bucket `himawari-raw` (audit/replay)
CloudObservation (validated) ──► TimescaleDB hypertable `cloud_obs`
        │
        ▼
Prometheus metrics on :9101/metrics
```

## ⚠️ Known limitation — read before enabling `HIMAWARI_SOURCE_MODE=http`

1. **himawari.optemis.space's TLS certificate is currently expired** (verified
   2026-07-13 via direct TLS handshake — the server sent a `certificate_expired`
   alert). The real HTTP adapter (`HimawariOptemisSource`) cannot be exercised
   against the live site until this is fixed on their end; do not route around
   it by disabling certificate verification.
2. Because the site was unreachable, **the JSON field mapping in
   `_parse_json_response` (datasource.py) is an unverified placeholder** —
   built to a plausible shape (`timestamp`, `latitude`, `longitude`,
   `cloud_opacity`, `cloud_index`), not a confirmed one. Recalibrate it (and
   `api_path` in config.py) against a real response before trusting this in
   production. If Optemis turns out to only offer scraped HTML rather than a
   JSON API, replace `_parse_json_response` with an HTML parser behind the
   same `CloudDataSource` interface — nothing else needs to change.
3. Default mode is **`mock`**, which replays `fixtures/sample_himawari_response.json`
   with realistic jitter. The rest of the pipeline (compliance gate, retry,
   MinIO, TimescaleDB, scheduler, metrics) is fully implemented and tested
   against this mock, so it's provably correct independent of item 1.

## Compliance posture

- `RobotsChecker` fetches and caches `robots.txt`; if it can't be read, the
  adapter **fails closed** (refuses to fetch) unless an operator explicitly
  sets `HIMAWARI_ALLOW_FETCH_IF_ROBOTS_UNREACHABLE=true` after an independent
  ToS review. It never assumes permission.
- Every request sets a descriptive `User-Agent` identifying the project and a
  contact point (see `.env.example`).
- `RateLimiter` enforces a minimum wall-clock gap between requests
  (`HIMAWARI_MIN_SECONDS_BETWEEN_REQUESTS`, default 5s) independent of the
  10-minute poll schedule, so retries can't hammer the origin.
- Retries use `tenacity` with capped exponential backoff
  (`HIMAWARI_MAX_RETRY_ATTEMPTS`, default 4 attempts).
- **Before flipping to `http` mode in production**, get an explicit ToS
  sign-off for the specific endpoint/rate in use — this scaffold enforces
  mechanics (robots.txt, rate limit, UA), not legal review.

## Layout

```
src/himawari_ingestion/
  config.py       Settings (env-driven, prefix HIMAWARI_)
  schemas.py       CloudObservation (validated ranges), RawFetchResult
  compliance.py    RobotsChecker, RateLimiter
  datasource.py    CloudDataSource interface, HimawariOptemisSource, MockCloudDataSource
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

pytest -v                       # 20 unit tests, 1 integration test (skipped by default)
python -m himawari_ingestion.main   # runs the scheduler; needs MinIO + TimescaleDB reachable
```

To exercise the real DB/MinIO integration test:

```bash
# once db/migrations/0001_cloud_obs.sql has been applied to a running TimescaleDB:
TIMESCALE_TEST_DSN=postgresql+asyncpg://postgres:postgres@localhost:5432/nongfab_ems pytest -v -m integration
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
